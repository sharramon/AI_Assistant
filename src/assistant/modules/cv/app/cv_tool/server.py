"""CV Tool server: a local JSON API on 127.0.0.1 plus its own Edge app window.

The cv module launches it with `CompanionApp` (`python -m cv_tool --window none`) and opens the window with
`POST /api/window` when cv_agent calls `cv.open_tool`. Run by hand, it opens its window at once.

- `GET /api/ping` → `{"app": "cv_tool"}`; `POST /api/quit` stops it and closes its window.
- Only requests addressed to this machine, and from a browser only its own page (`app_kit.local_guard`).
- Every POST is JSON (415 otherwise), so no web page can post here without the browser asking first.
- The module's calls: `POST /api/job/import`, `GET /api/job/status?id=`, `POST /api/round`, `GET /api/job/result?id=`,
  `GET /api/rules`, `POST /api/window`, `GET /api/submitted` (every submitted job, for the module's catch-up look).
- `GET /api/events`: Server-Sent Events for the cv module, `{"kind": "submitted", "job_id", "submitted_at"}` after
  each Submit, so the module delivers it without waiting for an agent, and `{"kind": "rezi_request", "job_id",
  "request_id", "at", "company", "role"}` after each Send JD and CV to Rezi click, so the module tells cv_agent
  to start the First Draft. The Internal or Rezi pick itself sends no event: it's only saved on the job.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import queue
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app_kit.config import load_layered, merge
from app_kit.local_guard import local_request, require_loopback
from app_kit.window import close_app_windows, open_app_window, raise_window, window_profile
from cv_tool import cvlib

log = logging.getLogger("cv_tool")

CONFIG = Path(__file__).with_name("cv_tool.toml")
CONFIG_DEFAULTS: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8771,
    "window": "app",  # "app" (Edge app window) or "none" (the cv module opens it with /api/window)
    "data_dir": cvlib.DEFAULT_DATA,
    "cv_dir": cvlib.DEFAULT_CV_DIR,  # the cv module's workspace; your own in cv_tool.local.toml
    "cv_prefix": "CV_Test_",  # the start of the CV file names; the real one in cv_tool.local.toml
    "rules_dir": cvlib.DEFAULT_RULES,
    "agent_work": "",
    "facts": "",
    "profile": "",
}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".ttf": "font/ttf", ".pdf": "application/pdf"}
TITLE = "CV Tool"


class Tool:
    """The running app: the HTTP server, its window and the jobs the module just imported."""

    def __init__(self, host: str, port: int, profile: Path, window: str = "app") -> None:
        self.host, self.port, self.profile, self.window = host, port, profile, window
        self.quit = threading.Event()
        self._fresh: list[dict[str, str]] = []  # jobs the module imported, for the open page to switch to
        self._lock = threading.Lock()
        self._edge: Any = None
        self._listeners: list[queue.Queue[dict[str, Any] | None]] = []  # the /api/events streams
        self._http = ThreadingHTTPServer((require_loopback(host), port), _handler(self))
        self.port = self._http.server_address[1]
        self.url = f"http://{host}:{self.port}/"

    def start(self) -> None:
        threading.Thread(target=self._http.serve_forever, name="cv_tool", daemon=True).start()
        log.info("CV Tool at %s", self.url)
        if self.window == "app":
            self.open_window()

    def stop(self) -> None:
        with self._lock:
            for q in self._listeners:
                q.put(None)  # ends each stream
        self._http.shutdown()
        self._http.server_close()
        close_app_windows(self.profile, log)

    def open_window(self, job: str = "") -> dict[str, Any]:
        """Bring the window up on `job`: raise it if it's open (the page switches through /api/inbox), else open it."""
        pid = self._edge.pid if self._edge is not None and self._edge.poll() is None else None
        if pid and raise_window(pid, TITLE):
            return {"opened": False, "raised": True}
        self._edge = open_app_window(self.url + (f"?job={job}" if job else ""), self.profile, size="1500,950", log=log)
        return {"opened": True, "raised": False}

    def imported(self, job: dict[str, Any]) -> None:
        with self._lock:
            self._fresh.append({"id": job["id"], "company": job.get("company", ""), "role": job.get("role", "")})

    def fresh(self) -> list[dict[str, str]]:
        with self._lock:
            out, self._fresh = self._fresh, []
        return out

    def listen(self) -> queue.Queue[dict[str, Any] | None]:
        q: queue.Queue[dict[str, Any] | None] = queue.Queue()
        with self._lock:
            self._listeners.append(q)
        return q

    def unlisten(self, q: queue.Queue[dict[str, Any] | None]) -> None:
        with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)

    def publish(self, item: dict[str, Any]) -> None:
        """One event to every /api/events stream."""
        with self._lock:
            for q in self._listeners:
                q.put(item)


def _save_job(body: dict[str, Any]) -> dict[str, Any]:
    """The page's save: keeps what only the server writes (loop, submitted, versions, Rezi rounds)."""
    old = cvlib.load_job(body["id"])  # must exist
    if old.get("content_saved_at", "") > body.get("content_saved_at", ""):
        body["content"] = old.get("content")  # an outside update is newer than the page's copy
    for k in ("loop", "submitted"):
        if old.get(k):
            body[k] = old[k]
        else:
            body.pop(k, None)
    if old.get("content") != body.get("content"):
        body["content_saved_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        cvlib._unsubmit(body)
    else:
        body["content_saved_at"] = old.get("content_saved_at", "")
    body["versions"] = old.get("versions", [])
    have = {r.get("request_id") for r in body.get("rounds", []) if r.get("request_id")}
    body["rounds"] = body.get("rounds", []) + [r for r in old.get("rounds", [])
                                               if r.get("request_id") and r["request_id"] not in have]
    if old.get("rezi_content") and not body.get("rezi_content"):
        body["rezi_content"] = old["rezi_content"]
    body["rezi_pending"] = body.get("rezi_pending") or old.get("rezi_pending")
    if not body["rezi_pending"] or body["rezi_pending"] in {r.get("request_id") for r in body["rounds"]}:
        body.pop("rezi_pending")
    cvlib.save_job(body)
    return {"ok": True, "content_saved_at": body.get("content_saved_at", "")}


def api(tool: Tool, path: str, q: dict[str, str], body: dict[str, Any]) -> Any:
    if path == "/api/ping":
        return {"app": "cv_tool", "data_dir": cvlib.ROOT}
    if path == "/api/quit":
        tool.quit.set()
        return {"ok": True}
    # the cv module's calls
    if path == "/api/job/import":
        job = cvlib.import_request(body)
        tool.imported(job)
        return {"job_id": job["id"], "tool": job.get("tool", ""), "has_content": bool(job.get("content"))}
    if path == "/api/job/status":
        return cvlib.job_status(q["id"])
    if path == "/api/round":
        return cvlib.agent_round(body)
    if path == "/api/job/result":
        return cvlib.job_result(q["id"])
    if path == "/api/rules":
        return cvlib.rules()
    if path == "/api/window":
        return tool.open_window(str(body.get("job", "")))
    # the page's calls
    if path == "/api/cvs":
        return cvlib.list_cvs()
    if path == "/api/cv":
        return {"paras": cvlib.odt_paras(q["name"])}
    if path == "/api/jobs":
        return cvlib.list_jobs()
    if path == "/api/job/new":
        return cvlib.new_job(body["company"].strip() or "Job", body.get("role", "").strip())
    if path == "/api/job":
        return cvlib.load_job(q["id"])
    if path == "/api/job/save":
        return _save_job(body)
    if path == "/api/terms":
        return cvlib.mark_terms(cvlib.jd_terms(body.get("jd", ""), body.get("role", ""), body.get("company", "")),
                                body.get("content"))
    if path == "/api/parse_cv":
        return cvlib.parse_cv(body["name"])
    if path == "/api/load_content":
        if not str(body["path"]).lower().endswith(".json"):
            raise PermissionError("a content .json only")
        with open(body["path"], encoding="utf-8") as f:
            c = json.load(f)
        c.setdefault("education_first", False)
        return c
    if path == "/api/check":
        c = body["content"]
        return {"html": cvlib.render(c), "fills": cvlib.fills(c), "lint": cvlib.lint(c),
                "truth": cvlib.truth_check(c), "fill_target": cvlib.FILL_TARGET, "page_h_pt": cvlib.text_height()}
    if path == "/api/confirm":
        d = cvlib.confirmed()
        for key in ("words", "phrases"):
            d.setdefault(key, [])
            d[key] += [w for w in body.get(key, []) if w not in d[key]]
        cvlib.save_confirmed(d)
        return d
    if path == "/api/confirmed":
        return cvlib.confirmed()
    if path == "/api/export":
        return cvlib.export_pdf(cvlib.load_job(body["id"]))
    if path == "/api/open":
        f = os.path.abspath(body["path"])
        if not cvlib._inside(f, cvlib.JOBS):
            raise PermissionError("only files in the jobs folder")
        os.startfile(f)
        return {"ok": True}
    if path == "/api/score/internal":
        return cvlib.internal_score(cvlib.load_job(body["id"]))
    if path == "/api/snapshot":
        return cvlib.save_snapshot(body["id"], body["n"], body["data"])
    if path == "/api/score/parse":
        return cvlib.parse_score(body.get("panel", ""), body.get("matched", ""), body.get("missing", ""))
    if path == "/api/cv/upload":
        return cvlib.upload_cv(body["id"], body["name"], body["data"])
    if path == "/api/inbox":
        return cvlib.process_inbox() + tool.fresh()
    if path == "/api/draft/internal":
        return cvlib.draft_internal(cvlib.load_job(body["id"]))
    if path == "/api/draft/internal/apply":  # the module's cv.tool_draft with apply
        return cvlib.apply_internal_draft(cvlib.load_job(body["id"]), bool(body.get("reorder", True)),
                                          list(body.get("add") or []))  # fmt: skip
    if path == "/api/draft/rezi":  # the Send JD and CV to Rezi click: the module tells cv_agent (as Submit does)
        job = cvlib.load_job(body["id"])
        made = cvlib.rezi_request(job)
        tool.publish({"kind": "rezi_request", "job_id": made["job_id"], "request_id": made["request_id"],
                      "at": made["at"], "company": job.get("company", ""), "role": job.get("role", "")})
        return made
    if path == "/api/rezi/results":
        return cvlib.rezi_results()
    if path == "/api/loop":
        return cvlib.loop_state(cvlib.load_job(q["id"]))
    if path == "/api/loop/sig":
        return cvlib.loop_sig(q["id"])
    if path == "/api/loop/internal":
        return cvlib.internal_round(cvlib.load_job(body["id"]))
    if path == "/api/submitted":
        return {"jobs": cvlib.submitted_jobs()}
    if path == "/api/submit":  # never refused for the CV itself: small text is only a warning
        result = cvlib.submit(cvlib.load_job(body["id"]))
        tool.publish({"kind": "submitted", "job_id": result["job_id"], "submitted_at": result["submitted_at"]})
        return result
    return None


def _handler(tool: Tool) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            log.debug(format, *args)

        def _send(self, code: int, data: Any, ctype: str = "application/json; charset=utf-8") -> None:
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self) -> bool:
            if local_request(self.headers.get("Host"), self.headers.get("Origin")):
                return True
            self._send(403, b"Forbidden", "text/plain")
            return False

        def _job_file(self, q: dict[str, str], kinds: dict[str, str]) -> None:
            try:
                f = os.path.join(cvlib.job_dir(q["id"]), os.path.basename(q["name"]))
                ext = os.path.splitext(f)[1].lower()
                if ext not in kinds:
                    raise PermissionError("not a file type the page shows")
                if "p" in q:  # one page of a PDF as a PNG; the PDF stays as it is
                    self._send(200, cvlib.render_page_png(f, int(q["p"])), "image/png")
                    return
                with open(f, "rb") as fh:
                    self._send(200, fh.read(), kinds[ext])
            except Exception as e:  # noqa: BLE001 - shown to the page
                self._send(404, {"error": str(e)})

        def _stream(self) -> None:
            q = tool.listen()
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
                tool.unlisten(q)

        def _any(self, body: dict[str, Any]) -> None:
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/api/events":
                return self._stream()
            if u.path == "/api/file":
                return self._job_file(q, {".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf"})
            if u.path == "/api/pdfpage":
                return self._job_file(dict(q, p=q.get("p", "0")), {".pdf": "image/png"})
            if u.path.startswith("/api/"):
                try:
                    answer = api(tool, u.path, q, body)
                except FileNotFoundError as e:
                    self._send(404, {"error": f"FileNotFoundError: {e}"})
                except Exception as e:  # noqa: BLE001 - every error goes back to the caller
                    log.debug("%s", traceback.format_exc())
                    self._send(500, {"error": f"{type(e).__name__}: {e}"})
                else:
                    self._send(404, {"error": "not found"}) if answer is None else self._send(200, answer)
                return
            rel = "static/index.html" if u.path == "/" else u.path.lstrip("/")
            f = os.path.abspath(os.path.join(cvlib.APP, rel))
            ok = cvlib._inside(f, os.path.join(cvlib.APP, "static")) or cvlib._inside(f, os.path.join(cvlib.APP, "assets"))
            if not ok or not os.path.isfile(f):
                self._send(404, {"error": "not found"})
                return
            with open(f, "rb") as fh:
                self._send(200, fh.read(), TYPES.get(os.path.splitext(f)[1], "application/octet-stream"))

        def do_GET(self) -> None:
            if self._host_ok():
                self._any({})

        def do_POST(self) -> None:
            if not self._host_ok():
                return
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._send(415, b"JSON only", "text/plain")
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError as e:
                self._send(400, {"error": f"Bad JSON: {e}"})
                return
            self._any(body if isinstance(body, dict) else {})

    return Handler


def settings(argv: list[str] | None = None) -> dict[str, Any]:
    """The defaults, then `cv_tool.toml` and its `.local.toml`, then the command-line flags."""
    p = argparse.ArgumentParser(description="CV Tool: the cv module's UI (Job & CV, CV Tool, First Draft, ATS Loop)")
    p.add_argument("--config", type=Path, help="a TOML config (default cv_tool.toml beside this file)")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--window", choices=["app", "none"])
    p.add_argument("--no-window", action="store_true", help="same as --window none")
    for key in ("data-dir", "cv-dir", "cv-prefix", "rules-dir", "agent-work", "facts", "profile"):
        p.add_argument(f"--{key}")
    a = p.parse_args(argv)
    file = a.config or CONFIG
    s = merge(dict(CONFIG_DEFAULTS), load_layered(file) if file.exists() or a.config else {})
    for key in ("host", "port", "window", "data_dir", "cv_dir", "cv_prefix", "rules_dir", "agent_work", "facts",
                "profile"):  # fmt: skip
        if getattr(a, key) is not None:
            s[key] = getattr(a, key)
    if a.no_window:
        s["window"] = "none"
    s["port"] = int(s["port"])
    s["profile"] = Path(s["profile"]) if s["profile"] else window_profile("cv_tool")
    return s


def main(argv: list[str] | None = None) -> int:
    s = settings(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cvlib.configure(s["data_dir"], s["cv_dir"], s["rules_dir"], s["agent_work"], s["facts"], s["cv_prefix"])
    tool = Tool(s["host"], s["port"], s["profile"], s["window"])
    tool.start()
    try:
        while not tool.quit.wait(0.5):  # a timeout, so Ctrl+C gets through on Windows
            pass
    except KeyboardInterrupt:
        pass
    finally:
        tool.stop()
    return 0
