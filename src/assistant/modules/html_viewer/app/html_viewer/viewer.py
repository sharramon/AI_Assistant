"""The HTML viewer: its own app and window, with a local HTTP API and event stream as its hooks.

Run it alone with `python -m html_viewer [files...]`, or let the assistant's `html_viewer`
module start it. It doesn't import the assistant. It serves `page.html` (tabs, the toolbar,
the edit tool, highlights, snip) on http://127.0.0.1:<port>/ and keeps each open tab's
document state, undo history, and highlights in memory. Standard library, plus `markdown`
for writing edits back to Markdown sources.

API (POST bodies are JSON and need `Content-Type: application/json`):
- `GET /api/ping`: `{"app": "html_viewer"}`, so the app can tell it's running
- `GET /api/tabs`, and `GET /api/events` (Server-Sent Events: `tabs`, `reload`, `changed`, `snip`)
- `POST /api/open` `{"path"}` (or `{"fs"}`, a `/fs/...` URL path): open a file in a tab, or
  switch to its tab and reload it if the file changed; opens the window if none is showing.
  With `"front": true`, also brings a showing window to the front (or opens a new one if
  it's gone): for your clicks, not for pages an agent opens on its own
- `POST /api/focus`, `/api/close`, `/api/reload` `{"tab"}`
- `POST /api/edit` `{"tab", "id", "html"}`: replace one element's content (a command)
- `POST /api/undo` `{"tab"}`: reverse the tab's last command
- `POST /api/save` `{"tab", "confirm"}`: write the file. In a folder built from Markdown
  (`--generated`), text edits are written back to the page's Markdown source too; edits that
  can't be placed there, or a page without a source, need a warning and `confirm` first
- `POST /api/highlight` `{"path", "text", "heading", "front"}`: open the file and highlight the quoted
  text (in the heading's section); `{"found", "matches"}`. Highlights are tab state, never saved
- `POST /api/clear` `{"tab", "id"}` (or `"all": true`): remove a highlight
- `POST /api/snip` `{"tab", "x", "y", "width", "height", "heading"}`: a PNG of that box of the
  window (CSS pixels of the viewer page); saved in the viewer's temp folder and announced as a
  `snip` event `{"id", "path", "file", "heading"}`
- `POST /api/quit`
- `GET /fs/<path>`: a file; with `?tab=<id>`, that tab's document state (the view)
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import mimetypes
import os
import queue
import shutil
import tempfile
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit
from uuid import uuid4

from app_kit.config import load_layered, merge
from app_kit.local_guard import local_request, require_loopback
from app_kit.window import close_app_windows, open_app_window, raise_window, window_profile
from html_viewer import highlight, snip
from html_viewer.document import EditText, HtmlDocument, HtmlHandler, handler_for
from html_viewer.markdown_source import MarkdownSource, find_source, plain

PAGE = Path(__file__).with_name("page.html")
DEFAULT_PROFILE = window_profile("html_viewer")
# Optional, beside the app (with its gitignored .local.toml); none is committed: the defaults below hold.
DEFAULT_CONFIG = Path(__file__).with_name("html_viewer.toml")
CONFIG_DEFAULTS: dict[str, Any] = {"host": "127.0.0.1", "port": 8766, "window": "app", "profile": "", "generated": []}
WINDOWS = ("app", "browser", "none")
GENERATED_WARNING = (
    "{name} is built from Markdown by scripts/build_docs.py. The next docs rebuild will overwrite this edit."
)
UNMAPPED_WARNING = (
    "{count} can't be written to {source}: the next docs rebuild will overwrite {them}: {which}"
)

log = logging.getLogger("html_viewer")


def fs_url(path: Path) -> str:
    """The viewer's URL path for a file. Real paths, so a page's relative links and files work."""
    return "/fs/" + quote(path.as_posix().lstrip("/"))


def _short(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def fs_path(url_path: str) -> Path:
    rest = unquote(url_path.removeprefix("/fs/"))
    return Path(rest if os.name == "nt" else "/" + rest)


@dataclass
class Tab:
    id: str
    path: Path
    handler: HtmlHandler
    doc: HtmlDocument
    mtime: float  # the file's, when last loaded or saved: a newer one means it changed elsewhere
    copy: Path  # the file as it was when opened; deleted when the tab closes
    undo: list[EditText] = field(default_factory=list)
    dirty: bool = False
    touched: set[str] = field(default_factory=set)  # elements edited or undone since the last save
    saved: HtmlDocument = field(init=False)  # the state as last loaded or saved
    highlights: list[dict[str, Any]] = field(default_factory=list)  # {"id", "text", "heading"}; drawn, never saved
    focus: dict[str, Any] | None = None  # the highlight to scroll to, {"id", "n"}; n counts requests

    def __post_init__(self) -> None:
        self.mark_saved()

    def mark_saved(self) -> None:
        self.saved = copy.copy(self.doc)
        self.touched.clear()

    def changes(self) -> list[tuple[str, str]]:
        """(old, new) content of each element changed since the last save."""
        out = []
        for element_id in sorted(self.touched, key=int):
            try:
                old, new = self.saved.content(element_id), self.doc.content(element_id)
            except KeyError:
                continue
            if old != new:
                out.append((old, new))
        return out

    def info(self, active: str | None) -> dict[str, Any]:
        return {
            "id": self.id, "path": str(self.path), "name": self.path.name, "src": f"{fs_url(self.path)}?tab={self.id}",
            "active": self.id == active, "dirty": self.dirty, "supports": list(self.handler.supports),
            "highlights": list(self.highlights), "focus": self.focus,
        }

    def recheck_highlights(self) -> None:
        """Drop highlights whose text is no longer on the page (after a reload or an edit)."""
        self.highlights = [h for h in self.highlights if highlight.count(self.doc.source, h["text"], h["heading"])]


class ViewerError(Exception):
    """A request the viewer can't do; its message goes back to the caller."""


class ViewerServer:
    """The viewer's state and HTTP API. `start` serves in a background thread."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8766,
        window: str = "app",
        profile: Path = DEFAULT_PROFILE,
        generated: list[Path] | None = None,
        capture: Callable[[Path, str, dict[str, float]], bytes] | None = None,
        open_win: Callable[[str, Path], Any] | None = None,
        raise_win: Callable[[int | None], bool] | None = None,
    ) -> None:
        self._window = window
        self._capture = capture or snip.capture  # (profile, page url, box) -> PNG; swappable for tests
        self._open_win = open_win or _open_window  # (url, profile) -> the Edge process; swappable for tests
        self._raise_win = raise_win or _raise_window  # (Edge pid) -> found the window; swappable for tests
        self._profile = Path(profile).resolve()
        self._generated = [Path(g).resolve() for g in generated or []]
        self._lock = threading.RLock()
        self._tabs: dict[str, Tab] = {}
        self._active: str | None = None
        self._subscribers: list[tuple[queue.Queue, bool]] = []  # (queue, is the page)
        self._window_opened = 0.0
        self._edge = None
        self._temp = Path(tempfile.mkdtemp(prefix="html_viewer_"))
        self.quit = threading.Event()
        self._serving: threading.Thread | None = None
        self._http = ThreadingHTTPServer((require_loopback(host), port), _handler(self))
        self._http.daemon_threads = True
        self.port = self._http.server_address[1]
        self.url = f"http://{host}:{self.port}/"

    def start(self) -> None:
        self._serving = threading.Thread(target=self._http.serve_forever, name="html_viewer", daemon=True)
        self._serving.start()
        log.info("HTML viewer at %s", self.url)

    def stop(self) -> None:
        if self._serving is not None:
            self._http.shutdown()
        self._http.server_close()
        with self._lock:
            for q, _ in self._subscribers:
                q.put(None)
        shutil.rmtree(self._temp, ignore_errors=True)
        if self._edge is not None and self._edge.poll() is None:
            close_app_windows(self._profile, log)

    # --- tabs ---

    def open(self, path: Path, front: bool = False) -> dict[str, Any]:
        """Open `path` in a tab (or switch to it). `front`: bring the window to the front too."""
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            raise ViewerError(f"No such file: {path}")
        handler = handler_for(path)
        if handler is None:
            raise ViewerError(f"The viewer opens HTML files only, not {path.name}")
        with self._lock:
            tab = next((t for t in self._tabs.values() if t.path == path), None)
            reloaded = False
            if tab is None:
                tab_id = uuid4().hex[:8]
                opened = self._temp / f"{tab_id}_{path.name}"
                shutil.copy2(path, opened)
                tab = Tab(tab_id, path, handler, handler.load(path), path.stat().st_mtime, opened)
                self._tabs[tab_id] = tab
            elif path.stat().st_mtime != tab.mtime:
                # Already open, and the file changed since: reload it, unless it has unsaved edits.
                if tab.dirty:
                    self._emit({"kind": "changed", "tab": tab.id})
                else:
                    self._load(tab)
                    reloaded = True
            self._active = tab.id
            self._emit_tabs()
            showing = any(page for _, page in self._subscribers)
        # A window closed only moments ago can still look connected; not finding it means it's gone.
        if not showing or (front and self._window == "app" and not self._raise()):
            self._open_window(force=showing)
        return {"tab": tab.id, "path": str(path), "reloaded": reloaded}

    def _raise(self) -> bool:
        return self._raise_win(getattr(self._edge, "pid", None))

    def _load(self, tab: Tab) -> None:
        tab.doc = tab.handler.load(tab.path)
        tab.mtime = tab.path.stat().st_mtime
        tab.undo.clear()
        tab.dirty = False
        tab.mark_saved()
        tab.recheck_highlights()
        shutil.copy2(tab.path, tab.copy)
        self._emit({"kind": "reload", "tab": tab.id})

    def focus(self, tab_id: str) -> None:
        with self._lock:
            self._tab(tab_id)
            self._active = tab_id
            self._emit_tabs()

    def close(self, tab_id: str) -> None:
        with self._lock:
            tab = self._tabs.pop(self._tab(tab_id).id)
            tab.copy.unlink(missing_ok=True)
            if self._active == tab_id:
                self._active = next(reversed(self._tabs), None)
            self._emit_tabs()

    def reload(self, tab_id: str) -> None:
        with self._lock:
            self._load(self._tab(tab_id))
            self._emit_tabs()

    def highlight(self, path: Path, text: str, heading: str | None = None, front: bool = False) -> dict[str, Any]:
        """Open the file and highlight the quoted text; the page scrolls to it."""
        if not text.strip():
            raise ViewerError("A highlight needs some text to find")
        heading = heading.strip() if heading and heading.strip() else None
        opened = self.open(path, front)
        with self._lock:
            tab = self._tab(opened["tab"])
            matches = highlight.count(tab.doc.source, text, heading)
            if not matches:
                return {**opened, "found": False, "matches": 0}
            mark = next((h for h in tab.highlights if h["text"] == text and h["heading"] == heading), None)
            if mark is None:
                mark = {"id": uuid4().hex[:8], "text": text, "heading": heading}
                tab.highlights.append(mark)
            # State, not an event: a window that opens only now still scrolls to it.
            tab.focus = {"id": mark["id"], "n": (tab.focus or {}).get("n", 0) + 1}
            self._emit_tabs()
        return {**opened, "found": True, "matches": matches, "highlight": mark["id"]}

    def clear(self, tab_id: str, highlight_id: str | None = None) -> None:
        """Remove one highlight, or all of a tab's when `highlight_id` is None."""
        with self._lock:
            tab = self._tab(tab_id)
            tab.highlights = [h for h in tab.highlights if highlight_id is not None and h["id"] != highlight_id]
            self._emit_tabs()

    def snip(self, tab_id: str, box: dict[str, float], heading: str | None = None) -> dict[str, Any]:
        """Screenshot a box of the window over a tab; saves the PNG and announces it."""
        with self._lock:
            tab = self._tab(tab_id)
        try:
            png = self._capture(self._profile, self.url, box)
        except snip.SnipError as exc:
            raise ViewerError(str(exc)) from None
        snip_id = uuid4().hex[:8]
        folder = self._temp / "snips"
        folder.mkdir(exist_ok=True)
        path = folder / f"snip_{snip_id}.png"
        path.write_bytes(png)
        item = {"id": snip_id, "path": str(path), "file": str(tab.path), "heading": heading or None}
        with self._lock:
            self._emit({"kind": "snip", **item})
        return item

    def tabs(self) -> dict[str, Any]:
        with self._lock:
            return {"tabs": [t.info(self._active) for t in self._tabs.values()], "active": self._active}

    # --- commands ---

    def edit(self, tab_id: str, element_id: str, html: str) -> dict[str, Any]:
        with self._lock:
            tab = self._tab(tab_id)
            try:
                command = EditText(element_id, tab.doc.content(element_id), html)
            except KeyError as exc:
                raise ViewerError(str(exc.args[0])) from None
            if command.old != command.new:
                command.do(tab.doc)
                tab.undo.append(command)
                tab.touched.add(element_id)
                tab.dirty = True
                tab.recheck_highlights()
                self._emit_tabs()
            return {"id": element_id, "html": tab.doc.content(element_id), "dirty": tab.dirty}

    def undo(self, tab_id: str) -> dict[str, Any]:
        with self._lock:
            tab = self._tab(tab_id)
            if not tab.undo:
                return {"empty": True, "dirty": tab.dirty}
            command = tab.undo.pop()
            command.undo(tab.doc)
            tab.touched.add(command.element_id)
            tab.dirty = True
            tab.recheck_highlights()
            self._emit_tabs()
            return {"id": command.element_id, "html": tab.doc.content(command.element_id), "dirty": tab.dirty}

    def save(self, tab_id: str, confirm: bool = False) -> dict[str, Any]:
        with self._lock:
            tab = self._tab(tab_id)
            built = next((g for g in self._generated if tab.path.is_relative_to(g)), None)
            answer: dict[str, Any] = {"saved": True}
            if built is not None:
                written = self._write_back(tab, confirm)
                if "warning" in written:
                    return {"saved": False, **written}
                answer.update(written)
            tab.handler.save(tab.doc, tab.path)
            tab.mtime = tab.path.stat().st_mtime
            tab.dirty = False  # the undo history stays, so undo still works after a save
            tab.mark_saved()
            self._emit_tabs()
            return answer

    def _write_back(self, tab: Tab, confirm: bool) -> dict[str, Any]:
        """Write a built page's text edits into its Markdown source, first of the two files.

        Returns `{"warning"}` when something can't be written back and `confirm` isn't set;
        otherwise what was written (`markdown`, `note`).
        """
        source = find_source(tab.path)
        if source is None:
            if confirm:
                return {}
            return {"warning": GENERATED_WARNING.format(name=tab.path.name)}
        with open(source, encoding="utf-8", errors="surrogateescape", newline="") as file:
            md = MarkdownSource(file.read())
        original = md.text
        unmapped = [old for old, new in tab.changes() if not md.write_back(old, new)]
        name = source.name
        if unmapped and not confirm:
            which = "; ".join(f'"{_short(plain(old))}"' for old in unmapped)
            count = f"{len(unmapped)} edit{'s' if len(unmapped) > 1 else ''}"
            them = "them" if len(unmapped) > 1 else "it"
            return {"warning": UNMAPPED_WARNING.format(count=count, source=name, them=them, which=which)}
        if md.text != original:
            with open(source, "w", encoding="utf-8", errors="surrogateescape", newline="") as file:
                file.write(md.text)
        if unmapped:
            note = f"Saved. {len(unmapped)} edit(s) not written to {name}: the next docs rebuild will overwrite them."
        else:
            note = f"Saved; also written to {name}. The docs still need a rebuild before committing."
        return {"markdown": str(source), "note": note}

    def _tab(self, tab_id: str) -> Tab:
        tab = self._tabs.get(tab_id)
        if tab is None:
            raise ViewerError(f"No tab {tab_id!r}")
        return tab

    # --- events and the window ---

    def subscribe(self, page: bool) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.append((q, page))
            if page:
                self._window_opened = 0.0  # the window is up: once it's closed, another may open
            q.put({"kind": "tabs", **self.tabs()})
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers = [(s, page) for s, page in self._subscribers if s is not q]

    def _emit_tabs(self) -> None:
        self._emit({"kind": "tabs", **self.tabs()})

    def _emit(self, item: dict[str, Any]) -> None:
        for q, _ in self._subscribers:
            if not q.full():
                q.put_nowait(item)

    def _open_window(self, force: bool = False) -> None:
        # One window: don't open another while the last one is still loading its page
        # (unless `force`: you asked for the window and it's gone).
        if self._window == "none" or (not force and time.monotonic() - self._window_opened < 15):
            return
        self._window_opened = time.monotonic()
        if self._window == "browser":
            webbrowser.open(self.url)
        else:
            self._edge = self._open_win(self.url, self._profile)


def _open_window(url: str, profile: Path) -> Any:
    # DevTools on: snip screenshots the window through it.
    return open_app_window(url, profile, size="1200,900", devtools=True, log=log)


def _raise_window(pid: int | None) -> bool:
    return raise_window(pid, "HTML viewer")


def _handler(viewer: ViewerServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            log.debug(format, *args)

        def do_GET(self) -> None:
            if not self._host_ok():
                return
            url = urlsplit(self.path)
            if url.path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
            elif url.path == "/api/ping":
                self._json({"app": "html_viewer"})
            elif url.path == "/api/tabs":
                self._json(viewer.tabs())
            elif url.path == "/api/events":
                self._stream(page=parse_qs(url.query).get("client") == ["page"])
            elif url.path.startswith("/fs/"):
                self._file(fs_path(url.path), parse_qs(url.query).get("tab", [None])[0])
            else:
                self._send(404, "text/plain", b"Not found")

        def do_POST(self) -> None:
            if not self._host_ok():
                return
            # JSON only: a web page can't send it here without the browser asking first (CORS).
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._send(415, "text/plain", b"JSON only")
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                answer = self._command(urlsplit(self.path).path, body)
            except ViewerError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self._json({"ok": False, "error": f"Bad request: {exc}"}, 400)
            else:
                if answer is None:
                    self._send(404, "text/plain", b"Not found")
                else:
                    self._json({"ok": True, **answer})

        def _command(self, path: str, body: dict[str, Any]) -> dict[str, Any] | None:
            if path == "/api/open":
                return viewer.open(fs_path(body["fs"]) if "fs" in body else Path(body["path"]), body.get("front") is True)
            if path == "/api/highlight":
                heading = body.get("heading")
                return viewer.highlight(Path(body["path"]), str(body["text"]), str(heading) if heading else None,
                                        body.get("front") is True)
            if path == "/api/snip":
                box = {key: float(body[key]) for key in ("x", "y", "width", "height")}
                heading = body.get("heading")
                return viewer.snip(str(body["tab"]), box, str(heading) if heading else None)
            if path == "/api/clear":
                viewer.clear(str(body["tab"]), None if body.get("all") else str(body["id"]))
                return {}
            if path == "/api/edit":
                return viewer.edit(str(body["tab"]), str(body["id"]), str(body["html"]))
            if path == "/api/undo":
                return viewer.undo(str(body["tab"]))
            if path == "/api/save":
                return viewer.save(str(body["tab"]), bool(body.get("confirm")))
            if path in ("/api/focus", "/api/close", "/api/reload"):
                getattr(viewer, path.removeprefix("/api/"))(str(body["tab"]))
                return {}
            if path == "/api/quit":
                viewer.quit.set()
                return {}
            return None

        def _file(self, path: Path, tab_id: str | None) -> None:
            tab = viewer._tabs.get(tab_id) if tab_id else None
            if tab is not None and tab.path == path.resolve():
                with viewer._lock:
                    body = tab.doc.source.encode("utf-8", "surrogateescape")
                self._send(200, "text/html; charset=utf-8", body)
            elif path.is_file():
                kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._send(200, kind, path.read_bytes())
            else:
                self._send(404, "text/plain", b"Not found")

        def _stream(self, page: bool) -> None:
            q = viewer.subscribe(page)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    try:
                        item = q.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                    else:
                        if item is None:
                            return
                        self.wfile.write(f"data: {json.dumps(item)}\n\n".encode())
                    self.wfile.flush()
            except (ConnectionError, OSError):
                pass
            finally:
                viewer.unsubscribe(q)

        def _host_ok(self) -> bool:
            # Only requests addressed to this machine (no DNS rebinding from a web page), and from a
            # browser only the viewer's own page (app_kit.local_guard).
            if local_request(self.headers.get("Host"), self.headers.get("Origin")):
                return True
            self._send(403, "text/plain", b"Forbidden")
            return False

        def _json(self, value: Any, status: int = 200) -> None:
            self._send(status, "application/json", json.dumps(value).encode())

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def load_viewer_config(path: str | Path | None = None) -> dict[str, Any]:
    """The defaults, then `path` (default `html_viewer.toml` beside the app) and its `.local.toml`.

    A missing default file means the defaults alone; a missing `path` raises `FileNotFoundError`.
    """
    file = Path(path) if path is not None else DEFAULT_CONFIG
    if path is None and not file.exists():
        return dict(CONFIG_DEFAULTS)
    return merge(dict(CONFIG_DEFAULTS), load_layered(file))


def viewer_settings(argv: list[str] | None = None) -> tuple[dict[str, Any], list[Path]]:
    """The viewer's settings (the config, then the command-line flags over it) and the files to open."""
    parser = argparse.ArgumentParser(description="The HTML viewer: view, edit, highlight, and snip HTML files")
    parser.add_argument("--config", type=Path, help="a TOML config (default html_viewer.toml beside the app, if present)")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--window", choices=WINDOWS)
    parser.add_argument("--profile", type=Path, help="Edge profile for the window")
    parser.add_argument("--generated", type=Path, action="append",
                        help="a folder built from Markdown: saving there writes edits back to the "
                             "Markdown source (repeatable)")
    parser.add_argument("files", nargs="*", type=Path, help="files to open")
    args = parser.parse_args(argv)
    settings = load_viewer_config(args.config)
    for key in ("host", "port", "window", "profile", "generated"):
        if getattr(args, key) is not None:
            settings[key] = getattr(args, key)
    if settings["window"] not in WINDOWS:
        parser.error(f"window must be one of {', '.join(WINDOWS)}")
    settings["port"] = int(settings["port"])
    settings["profile"] = Path(settings["profile"]) if settings["profile"] else DEFAULT_PROFILE
    settings["generated"] = [Path(folder) for folder in settings["generated"]]
    return settings, args.files


def main(argv: list[str] | None = None) -> int:
    settings, files = viewer_settings(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    viewer = ViewerServer(settings["host"], settings["port"], settings["window"], settings["profile"],
                          settings["generated"])  # fmt: skip
    viewer.start()
    try:
        for file in files:
            try:
                viewer.open(file)
            except ViewerError as exc:
                log.error("%s", exc)
        while not viewer.quit.wait(0.5):  # a timeout, so Ctrl+C gets through on Windows
            pass
    except KeyboardInterrupt:
        pass
    finally:
        viewer.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
