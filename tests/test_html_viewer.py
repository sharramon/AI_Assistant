"""The HTML viewer: its document model, its own HTTP API, and the html_viewer module."""

import asyncio
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from assistant.contracts import (
    AgentActivity,
    InputReceived,
    InvokeTool,
    IToolProvider,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ResponseReady,
    Result,
    ToolSpec,
    ViewerClip,
    ViewerClipDropped,
    ViewerTabsChanged,
)
from assistant.core import App
from assistant.infra import LogSession
from assistant.modules.html_viewer import HtmlViewerModule
from assistant.modules.html_viewer.module import parse_show
from assistant.modules.talker import TalkerModule
from assistant.modules.temp_ui import TempUIModule
from html_viewer.document import EditText, HtmlDocument, add_ids
from html_viewer.highlight import count
from html_viewer.markdown_source import MarkdownSource, blocks
from html_viewer.viewer import ViewerServer, fs_path, fs_url
from tests.test_agents import FAKE
from tests.test_temp_ui import request, ui_port

PAGE = (
    "<!doctype html>\r\n<html><head><title>T &amp; t</title>\r\n"
    "<script>if (1 < 2) { document.title += '<p>'; }</script></head>\r\n"
    "<body><h1>Title</h1><p>First <b>bold</b> para</p><br/><img src=x.png>\r\n"
    "<ul><li>one<li>two</ul><p>Last</p></body></html>\r\n"
)


def element_id(doc: HtmlDocument, text: str) -> str:
    """The id of the element whose content is exactly `text`."""
    match = re.search(rf'data-hv-id="(\d+)">{re.escape(text)}</', doc.source)
    assert match, text
    return match.group(1)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- document state and commands ---

def test_ids_round_trip_exactly():
    doc = HtmlDocument(PAGE)
    assert doc.source.count("data-hv-id") >= 10
    assert "'<p>'" in doc.source  # script content isn't touched
    assert doc.text == PAGE  # CRLF, entities, and <br/> come back byte for byte
    assert add_ids(doc.source) == doc.source  # already tagged: nothing added


def test_edit_command_and_undo():
    doc = HtmlDocument(PAGE)
    title = element_id(doc, "Title")
    command = EditText(title, doc.content(title), "New title")
    command.do(doc)
    assert "<h1>New title</h1>" in doc.text
    last = element_id(doc, "Last")  # offsets after the edit still line up
    doc.replace_content(last, "End")
    command.undo(doc)
    assert doc.text == PAGE.replace("<p>Last</p>", "<p>End</p>")


def test_implicitly_closed_elements_are_not_editable():
    doc = HtmlDocument(PAGE)
    li = doc.source.index("<li ")
    li_id = doc.source[li:].split('"')[1]
    with pytest.raises(KeyError):
        doc.content(li_id)


def test_fs_urls_round_trip(tmp_path):
    path = (tmp_path / "a b" / "page.html").resolve()
    assert fs_url(path).startswith("/fs/") and " " not in fs_url(path)
    assert fs_path(fs_url(path)) == path


# --- the viewer program's API ---

@pytest.fixture
def viewer(tmp_path):
    server = ViewerServer(port=0, window="none", profile=tmp_path / "profile", generated=[tmp_path / "built"])
    server.start()
    yield server
    server.stop()


def call(server: ViewerServer, method: str, path: str, body=None, content_type="application/json", host=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", content_type)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def write(path: Path, text: str = PAGE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def test_open_edit_save_undo(viewer, tmp_path):
    page = write(tmp_path / "notes" / "page.html")
    status, opened = call(viewer, "POST", "/api/open", {"path": str(page)})
    assert status == 200 and opened["ok"] and not opened["reloaded"]
    tab = opened["tab"]
    copy = next(viewer._temp.iterdir())
    assert copy.read_bytes() == page.read_bytes()  # the safety copy of the original

    # The view: the tab's state, with ids; other files in the folder are served as they are.
    _, info = call(viewer, "GET", "/api/tabs")
    assert info["active"] == tab and info["tabs"][0]["supports"] == ["render", "anchor", "edit", "save"]
    _, view = call(viewer, "GET", info["tabs"][0]["src"])
    assert b'<h1 data-hv-id="' in view
    write(tmp_path / "notes" / "style.css", "p {}")
    _, css = call(viewer, "GET", fs_url(tmp_path / "notes" / "style.css"))
    assert css == b"p {}"

    title = element_id(viewer._tabs[tab].doc, "Title")
    _, edited = call(viewer, "POST", "/api/edit", {"tab": tab, "id": title, "html": "Edited"})
    assert edited["html"] == "Edited" and edited["dirty"]
    assert page.read_bytes() == PAGE.encode()  # nothing written before Save

    _, saved = call(viewer, "POST", "/api/save", {"tab": tab})
    assert saved["saved"] and page.read_bytes() == PAGE.replace("Title", "Edited").encode()

    # Undo still works after a save; saving again puts the file back.
    _, undone = call(viewer, "POST", "/api/undo", {"tab": tab})
    assert undone["id"] == title and undone["html"] == "Title" and undone["dirty"]
    call(viewer, "POST", "/api/save", {"tab": tab})
    assert page.read_bytes() == PAGE.encode()
    _, empty = call(viewer, "POST", "/api/undo", {"tab": tab})
    assert empty["empty"]

    call(viewer, "POST", "/api/close", {"tab": tab})
    assert not copy.exists() and call(viewer, "GET", "/api/tabs")[1]["tabs"] == []


def test_open_again_switches_and_reloads_if_changed(viewer, tmp_path):
    first = write(tmp_path / "a.html")
    second = write(tmp_path / "b.html")
    tab = call(viewer, "POST", "/api/open", {"path": str(first)})[1]["tab"]
    call(viewer, "POST", "/api/open", {"path": str(second)})
    again = call(viewer, "POST", "/api/open", {"path": str(first)})[1]
    assert again["tab"] == tab and not again["reloaded"]
    assert call(viewer, "GET", "/api/tabs")[1]["active"] == tab

    write(first, PAGE.replace("Title", "Rebuilt"))
    os.utime(first, (first.stat().st_atime, first.stat().st_mtime + 5))
    again = call(viewer, "POST", "/api/open", {"path": str(first)})[1]
    assert again["reloaded"] and "Rebuilt" in viewer._tabs[tab].doc.text

    # With unsaved edits, a change on disk doesn't throw them away.
    title = element_id(viewer._tabs[tab].doc, "Rebuilt")
    call(viewer, "POST", "/api/edit", {"tab": tab, "id": title, "html": "Mine"})
    os.utime(first, (first.stat().st_atime, first.stat().st_mtime + 10))
    assert not call(viewer, "POST", "/api/open", {"path": str(first)})[1]["reloaded"]
    assert "Mine" in viewer._tabs[tab].doc.text


def test_saving_into_a_built_folder_warns_first(viewer, tmp_path):
    page = write(tmp_path / "built" / "agents" / "index.html")
    tab = call(viewer, "POST", "/api/open", {"path": str(page)})[1]["tab"]
    title = element_id(viewer._tabs[tab].doc, "Title")
    call(viewer, "POST", "/api/edit", {"tab": tab, "id": title, "html": "Edited"})
    _, answer = call(viewer, "POST", "/api/save", {"tab": tab})
    assert not answer["saved"] and "overwrite" in answer["warning"]
    assert page.read_bytes() == PAGE.encode()
    _, answer = call(viewer, "POST", "/api/save", {"tab": tab, "confirm": True})
    assert answer["saved"] and b"Edited" in page.read_bytes()


SOURCE_MD = (
    "# Title\r\n\r\n"
    "> **Status: done.** Built today.\r\n\r\n"
    "Turns modules on and off, see [core](core.md) and **bold** words.\r\n\r\n"
    "- First item\r\n"
    "- Same line\r\n\r\n"
    "Same line\r\n\r\n"
    "| Part | What |\r\n"
    "|------|------|\r\n"
    "| Hub | Coordinates `agents` |\r\n\r\n"
    "```\r\nTitle in code\r\n```\r\n"
)


def built_page(tmp_path: Path, md_text: str = SOURCE_MD) -> tuple[Path, Path]:
    """A Markdown file under docs/ and its page under built/, as scripts/build_docs.py makes them."""
    import markdown

    md = write(tmp_path / "docs" / "notes.md", md_text)
    body = markdown.markdown(md_text.replace("\r\n", "\n"), extensions=["tables", "fenced_code", "sane_lists"])
    page = write(tmp_path / "built" / "notes.html",
                 "<!doctype html>\n<!-- Generated from docs/notes.md by scripts/build_docs.py. -->\n"
                 f"<html><body>{body}<footer>Generated</footer></body></html>\n")
    return md, page


def test_markdown_blocks_and_write_back():
    md = MarkdownSource(SOURCE_MD)
    texts = [SOURCE_MD[b.start:b.end] for b in blocks(SOURCE_MD)]
    assert texts[:3] == ["Title", "**Status: done.** Built today.", texts[2]]
    assert "Hub" in texts and "Coordinates `agents`" in texts and "Title in code" not in texts

    # Only the changed words, inside links and bold left alone.
    assert md.write_back('Turns modules on and off, see <a href="core.html">core</a> and <strong>bold</strong> words.',
                         'Turns modules on or off, see <a href="core.html">core</a> and <strong>bold</strong> words.')
    assert "Turns modules on or off, see [core](core.md) and **bold** words.\r\n" in md.text
    assert md.write_back("Coordinates <code>agents</code>", "Coordinates <code>agents</code> | tasks")
    assert "| Hub | Coordinates `agents` \\| tasks |" in md.text
    assert md.write_back("Title", "New title") and md.text.startswith("# New title\r\n")
    assert md.write_back("First item", "First thing") and "- First thing\r\n" in md.text

    # Ambiguous or unplaceable: the Markdown isn't touched.
    before = md.text
    assert not md.write_back("Same line", "Other line")  # two blocks match
    assert not md.write_back("Nowhere in the file", "x")  # no block matches
    assert not md.write_back("<strong>Status: done.</strong> Built today.",
                             "<strong>Status: </strong>finished today.")  # crosses the bold
    assert md.text == before


def test_saving_a_built_page_writes_the_markdown_too(viewer, tmp_path):
    md, page = built_page(tmp_path)
    tab = call(viewer, "POST", "/api/open", {"path": str(page)})[1]["tab"]
    doc = viewer._tabs[tab].doc
    title = element_id(doc, "Title")
    call(viewer, "POST", "/api/edit", {"tab": tab, "id": title, "html": "Better title"})
    _, answer = call(viewer, "POST", "/api/save", {"tab": tab})
    assert answer["saved"] and "notes.md" in answer["note"] and "warning" not in answer
    assert md.read_bytes() == SOURCE_MD.replace("# Title", "# Better title").encode()
    assert b"<h1>Better title</h1>" in page.read_bytes()

    # Undo after the save, then save again: both files go back.
    call(viewer, "POST", "/api/undo", {"tab": tab})
    call(viewer, "POST", "/api/save", {"tab": tab})
    assert md.read_bytes() == SOURCE_MD.encode()

    # An edit that can't be placed: a warning first, then only the HTML changes.
    same = re.search(r'data-hv-id="(\d+)">Same line</p>', doc.source).group(1)
    call(viewer, "POST", "/api/edit", {"tab": tab, "id": same, "html": "Changed"})
    _, answer = call(viewer, "POST", "/api/save", {"tab": tab})
    assert not answer["saved"] and "notes.md" in answer["warning"] and '"Same line"' in answer["warning"]
    _, answer = call(viewer, "POST", "/api/save", {"tab": tab, "confirm": True})
    assert answer["saved"] and "not written" in answer["note"]
    assert md.read_bytes() == SOURCE_MD.encode() and b"<p>Changed</p>" in page.read_bytes()


# --- highlights ---

SECTIONS = (
    "<html><head><script>var s = 'Parts of the app';</script></head><body>"
    "<h1>Overview</h1><p>The core hosts modules.</p>"
    "<h2>Parts</h2><p>The core hosts   the\n<b>Agent Hub</b>.</p>"
    "<pre class=\"mermaid\">flowchart Parts</pre>"
    "<h2>Other</h2><p>The core hosts modules.</p></body></html>"
)


def test_highlight_finds_page_text_only():
    assert count(SECTIONS, "the core hosts modules") == 2  # case and whitespace don't matter
    assert count(SECTIONS, "the core hosts modules", heading="Other") == 1
    assert count(SECTIONS, "hosts the Agent Hub") == 1  # across tags and line breaks
    assert count(SECTIONS, "The core hosts modules", heading="Parts") == 0  # only that section
    assert count(SECTIONS, "Parts of the app") == 0 and count(SECTIONS, "flowchart") == 0  # no scripts, no Mermaid
    assert count(SECTIONS, "The core hosts modules", heading="No such heading") == 2  # heading ignored
    assert count(SECTIONS, "   ") == 0


def test_highlight_api_scrolls_survives_and_clears(viewer, tmp_path):
    page = write(tmp_path / "sections.html", SECTIONS)

    status, missing = call(viewer, "POST", "/api/highlight", {"path": str(page), "text": "not on the page"})
    assert status == 200 and missing["found"] is False and missing["tab"]  # opened, nothing marked
    tab = missing["tab"]
    _, found = call(viewer, "POST", "/api/highlight", {"path": str(page), "text": "core hosts modules", "heading": "Other"})
    assert found["found"] and found["matches"] == 1 and found["tab"] == tab
    _, again = call(viewer, "POST", "/api/highlight", {"path": str(page), "text": "core hosts modules", "heading": "Other"})
    assert again["highlight"] == found["highlight"]  # the same highlight, scrolled to again
    focus = call(viewer, "GET", "/api/tabs")[1]["tabs"][0]["focus"]
    assert focus == {"id": found["highlight"], "n": 2}  # in the tab's state, for a window opened later
    call(viewer, "POST", "/api/highlight", {"path": str(page), "text": "Agent Hub"})
    marks = call(viewer, "GET", "/api/tabs")[1]["tabs"][0]["highlights"]
    assert [h["text"] for h in marks] == ["core hosts modules", "Agent Hub"]

    # Never part of the file: an edit and a save write no marks.
    doc = viewer._tabs[tab].doc
    first = re.search(r'<h1 data-hv-id="(\d+)">', doc.source).group(1)
    call(viewer, "POST", "/api/edit", {"tab": tab, "id": first, "html": "Intro"})
    call(viewer, "POST", "/api/save", {"tab": tab})
    assert "mark" not in page.read_text() and "Intro" in page.read_text()

    # Editing the highlighted text away drops that highlight; undo doesn't bring it back.
    hub = re.search(r'<b data-hv-id="(\d+)">Agent Hub</b>', doc.source).group(1)
    call(viewer, "POST", "/api/edit", {"tab": tab, "id": hub, "html": "Hub"})
    assert [h["text"] for h in viewer._tabs[tab].highlights] == ["core hosts modules"]

    # A reload from disk keeps highlights whose text is still there.
    call(viewer, "POST", "/api/undo", {"tab": tab})
    write(page, SECTIONS.replace("<h2>Other</h2>", "<h2>Other things</h2>"))
    call(viewer, "POST", "/api/reload", {"tab": tab})
    assert [h["text"] for h in viewer._tabs[tab].highlights] == ["core hosts modules"]

    call(viewer, "POST", "/api/highlight", {"path": str(page), "text": "Agent Hub"})
    one = viewer._tabs[tab].highlights[0]["id"]
    call(viewer, "POST", "/api/clear", {"tab": tab, "id": one})
    assert [h["text"] for h in viewer._tabs[tab].highlights] == ["Agent Hub"]
    call(viewer, "POST", "/api/clear", {"tab": tab, "all": True})
    assert viewer._tabs[tab].highlights == []
    assert call(viewer, "POST", "/api/highlight", {"path": str(page), "text": " "})[0] == 400


# --- snip ---

PNG = b"\x89PNG\r\n\x1a\nfake"


def test_snip_saves_the_image_and_announces_it(tmp_path):
    boxes = []

    def capture(profile, url, box):
        boxes.append(box)
        return PNG

    server = ViewerServer(port=0, window="none", profile=tmp_path / "profile", capture=capture)
    server.start()
    try:
        page = write(tmp_path / "page.html")
        tab = call(server, "POST", "/api/open", {"path": str(page)})[1]["tab"]
        events = server.subscribe(page=False)
        status, snip = call(server, "POST", "/api/snip",
                            {"tab": tab, "x": 10, "y": 20, "width": 300, "height": 200, "heading": "Parts"})
        assert status == 200 and boxes == [{"x": 10.0, "y": 20.0, "width": 300.0, "height": 200.0}]
        assert Path(snip["path"]).read_bytes() == PNG and snip["file"] == str(page.resolve())
        items = [events.get(timeout=1) for _ in range(2)]
        assert {"kind": "snip", **{k: snip[k] for k in ("id", "path", "file", "heading")}} in items
    finally:
        server.stop()


def test_snip_without_the_app_window_says_why(viewer, tmp_path):
    tab = call(viewer, "POST", "/api/open", {"path": str(write(tmp_path / "page.html"))})[1]["tab"]
    status, answer = call(viewer, "POST", "/api/snip", {"tab": tab, "x": 0, "y": 0, "width": 50, "height": 50})
    assert status == 400 and b"app window" in answer


def test_refuses_what_it_cant_do(viewer, tmp_path):
    status, answer = call(viewer, "POST", "/api/open", {"path": str(tmp_path / "missing.html")})
    assert status == 400 and b"No such file" in answer
    status, answer = call(viewer, "POST", "/api/open", {"path": str(write(tmp_path / "notes.txt", "x"))})
    assert status == 400 and b"HTML files only" in answer
    # Not JSON (a plain form from a web page), or not addressed to the viewer: refused.
    assert call(viewer, "POST", "/api/quit", {}, content_type="text/plain")[0] == 415
    assert call(viewer, "GET", "/api/tabs", host="evil.example:80")[0] == 403
    assert not viewer.quit.is_set()


# --- bringing the window to the front ---

def windowed(tmp_path, found=True):
    """A viewer with fake window functions: records what it opened and raised."""
    calls = []
    server = ViewerServer(
        port=0, profile=tmp_path / "profile",
        open_win=lambda url, profile: calls.append("open"), raise_win=lambda pid: calls.append("raise") or found,
    )
    return server, calls


def test_front_raises_a_showing_window_only_when_asked(tmp_path):
    server, calls = windowed(tmp_path)
    page = write(tmp_path / "page.html")
    try:
        server.subscribe(page=True)  # the window is showing
        server.open(page)
        assert calls == []  # an agent's page: stays in the background
        server.open(page, front=True)
        assert calls == ["raise"]
        server.highlight(page, "First", front=True)
        assert calls == ["raise", "raise"]
    finally:
        server.stop()


def test_front_opens_a_window_when_none_is_showing_or_it_is_gone(tmp_path):
    server, calls = windowed(tmp_path, found=False)
    page = write(tmp_path / "page.html")
    try:
        server.open(page, front=True)
        assert calls == ["open"]  # no window: open one (no raise needed)
        server.subscribe(page=True)  # it connected, then you closed it before the viewer noticed
        server.open(page, front=True)
        assert calls == ["open", "raise", "open"]  # not found: opened again, no 15 s wait
    finally:
        server.stop()


def test_a_closed_window_opens_again_straight_away(tmp_path):
    server, calls = windowed(tmp_path)
    page = write(tmp_path / "page.html")
    try:
        server.open(page)
        q = server.subscribe(page=True)
        server.unsubscribe(q)  # the window closed
        server.open(page)
        assert calls == ["open", "open"]
    finally:
        server.stop()


# --- the html_viewer module ---

def module_config(port: int, **extra):
    return {"modules": {"enabled": ["html_viewer"], "html_viewer": {"port": port, "window": "none", **extra}}, "core": {}}


async def test_module_starts_the_viewer_relays_tabs_and_stops_it(tmp_path):
    port = free_port()
    page = write(tmp_path / "page.html")
    app = App([HtmlViewerModule], module_config(port, window_profile=str(tmp_path / "profile")))
    changes: asyncio.Queue[ViewerTabsChanged] = asyncio.Queue()
    app.bus.subscribe(ViewerTabsChanged, changes.put)
    await app.start()
    try:
        assert (await app.router.send(InvokeTool(name="viewer.tabs"))).value == []  # not started yet
        result = await app.router.send(InvokeTool(name="viewer.open", args={"path": str(page)}), timeout=20)
        assert result.is_ok, result.error
        change = await asyncio.wait_for(changes.get(), 5)
        while not change.tabs:
            change = await asyncio.wait_for(changes.get(), 5)
        assert change.tabs == (str(page.resolve()),) and change.active == str(page.resolve())
        tabs = (await app.router.send(InvokeTool(name="viewer.tabs"))).value
        assert tabs == [{"path": str(page.resolve()), "active": True, "unsaved": False, "highlights": []}]
        proc = app._lifecycle._active["html_viewer"][0]._app.process
        assert proc is not None and proc.returncode is None
    finally:
        await app.stop()
    assert proc.returncode is not None  # the app started it, so the app stopped it


async def test_module_leaves_a_viewer_you_started_running(tmp_path):
    server = ViewerServer(port=0, window="none", profile=tmp_path / "profile")
    server.start()
    page = write(tmp_path / "page.html")
    app = App([HtmlViewerModule], module_config(server.port))
    await app.start()
    try:
        result = await app.router.send(InvokeTool(name="viewer.open", args={"path": str(page)}))
        assert result.is_ok and not app._lifecycle._active["html_viewer"][0]._app.launched
        await app.stop()
        assert not server.quit.is_set() and server.tabs()["tabs"][0]["path"] == str(page.resolve())
    finally:
        server.stop()


async def test_main_assistant_show_tag_opens_the_file(tmp_path):
    server = ViewerServer(port=0, window="none", profile=tmp_path / "profile")
    server.start()
    page = write(tmp_path / "report.html")
    app = App([HtmlViewerModule], module_config(server.port))
    await app.start()
    try:
        app.bus.publish(AgentActivity(agent_id="main_assistant", text=f"Done.\n<<SHOW: {page}>>"))
        async with asyncio.timeout(5):
            while not server.tabs()["tabs"]:
                await asyncio.sleep(0.02)
        assert server.tabs()["tabs"][0]["path"] == str(page.resolve())
    finally:
        await app.stop()
        server.stop()


def test_show_tag_arguments():
    assert parse_show(r"C:\a b\page.html") == (r"C:\a b\page.html", None, None)
    assert parse_show('C:/p.html | "the core hosts" | Parts') == ("C:/p.html", "the core hosts", "Parts")
    assert parse_show("'C:/p.html' | “quoted” |") == ("C:/p.html", "quoted", None)


async def test_highlight_tool_and_show_tag(tmp_path):
    server = ViewerServer(port=0, window="none", profile=tmp_path / "profile")
    server.start()
    page = write(tmp_path / "sections.html", SECTIONS)
    app = App([HtmlViewerModule], module_config(server.port))
    changes: asyncio.Queue[ViewerTabsChanged] = asyncio.Queue()
    app.bus.subscribe(ViewerTabsChanged, changes.put)
    await app.start()
    try:
        result = await app.router.send(InvokeTool(name="viewer.highlight", args={
            "path": str(page), "text": "core hosts modules", "heading": "Other"}))
        assert result.is_ok and result.value["found"] and result.value["matches"] == 1
        missing = await app.router.send(InvokeTool(name="viewer.highlight", args={"path": str(page), "text": "nowhere"}))
        assert missing.is_ok and missing.value["found"] is False
        bad = await app.router.send(InvokeTool(name="viewer.highlight", args={"path": str(page)}))
        assert bad.status == "invalid_arguments"

        # The Main Assistant's tag form.
        app.bus.publish(AgentActivity(agent_id="main_assistant", text=f'See:\n<<SHOW: {page} | "Agent Hub" | Parts>>'))
        async with asyncio.timeout(5):
            while len(server.tabs()["tabs"][0]["highlights"]) < 2:
                await asyncio.sleep(0.02)
        async with asyncio.timeout(5):
            change = await changes.get()
            while len(change.highlights) < 2:
                change = await changes.get()
        assert change.highlights == ((str(page.resolve()), "core hosts modules"), (str(page.resolve()), "Agent Hub"))
        tabs = (await app.router.send(InvokeTool(name="viewer.tabs"))).value
        assert tabs[0]["highlights"] == ["core hosts modules", "Agent Hub"]
    finally:
        await app.stop()
        server.stop()


async def test_module_relays_snips_into_the_log_folder(tmp_path):
    server = ViewerServer(port=0, window="none", profile=tmp_path / "profile", capture=lambda *_: PNG)
    server.start()
    page = write(tmp_path / "page.html")
    logs = tmp_path / "logs" / "session"
    app = App([HtmlViewerModule], module_config(server.port), logs=LogSession(logs))  # no theme: its root
    clips: asyncio.Queue[ViewerClip] = asyncio.Queue()
    app.bus.subscribe(ViewerClip, clips.put)
    await app.start()
    try:
        await app.router.send(InvokeTool(name="viewer.open", args={"path": str(page)}))
        tab = server.tabs()["tabs"][0]["id"]
        await asyncio.to_thread(server.snip, tab, {"x": 0, "y": 0, "width": 40, "height": 30}, "Title")
        clip = await asyncio.wait_for(clips.get(), 5)
        assert Path(clip.image_path).parent == logs / "snips" and Path(clip.image_path).read_bytes() == PNG
        assert clip.file == str(page.resolve()) and clip.heading == "Title"
    finally:
        await app.stop()
        server.stop()


async def test_talker_sends_snips_with_your_next_message(tmp_path):
    image = write(tmp_path / "snip.png", "png")
    config = {"modules": {"enabled": ["talker"], "talker": {"program": FAKE}}, "core": {}}
    app = App([TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        for n in range(4):  # one more than it keeps
            app.bus.publish(ViewerClip(id=f"s{n}", image_path=str(image), file="C:/docs/a.html", heading="Parts"))
        app.bus.publish(ViewerClipDropped(id="s3"))
        await asyncio.sleep(0.05)
        app.bus.publish(InputReceived(text="what is this?", source="test"))
        reply = (await asyncio.wait_for(replies.get(), 10)).text
        assert reply.startswith("[2 image(s)] [Viewer] snip from C:/docs/a.html, near \"Parts\"")
        assert reply.endswith("what is this?") and reply.count("[Viewer] snip") == 2  # s0 fell off, s3 was dropped
        app.bus.publish(InputReceived(text="And now?", source="test"))
        assert (await asyncio.wait_for(replies.get(), 10)).text == "And now?"  # used once
    finally:
        await app.stop()


async def test_temp_ui_shows_snips_until_you_send(tmp_path):
    image = write(tmp_path / "snip.png", "png")
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    dropped: asyncio.Queue[ViewerClipDropped] = asyncio.Queue()
    app.bus.subscribe(ViewerClipDropped, dropped.put)
    await app.start()
    try:
        ui = app._lifecycle._active["temp_ui"][0]
        for n in range(2):
            app.bus.publish(ViewerClip(id=f"s{n}", image_path=str(image), file="C:/a.html"))
        await asyncio.sleep(0.05)
        assert [s["id"] for s in ui._snips_item()["snips"]] == ["s0", "s1"]
        reader, writer = await request(ui_port(app), b"GET /snip/s0 HTTP/1.1\r\n\r\n")
        assert (await reader.read()).endswith(b"png")
        writer.close()
        body = b'{"id": "s0"}'
        reader, writer = await request(ui_port(app), b"POST /drop-snip HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))
        await reader.read()
        writer.close()
        assert (await asyncio.wait_for(dropped.get(), 5)).id == "s0"
        app.bus.publish(InputReceived(text="what is this?", source="test"))
        await asyncio.sleep(0.05)
        assert ui._snips_item()["snips"] == []
    finally:
        await app.stop()


async def test_open_tool_checks_its_path(tmp_path):
    app = App([HtmlViewerModule], module_config(free_port()))
    await app.start()
    try:
        missing = await app.router.send(InvokeTool(name="viewer.open", args={"path": str(tmp_path / "nope.html")}))
        assert missing.status == "invalid_arguments"
        assert (await app.router.send(InvokeTool(name="viewer.open", args={}))).status == "invalid_arguments"
    finally:
        await app.stop()


# --- the chat's Open in viewer button ---

class FakeViewer(ModuleProtocol, IToolProvider):
    manifest = Manifest(id="fake_viewer", provides=(IToolProvider,))
    opened: list[str] = []
    front: list[bool] = []

    async def init(self, ctx: ModuleContext) -> None:
        ctx.provide(IToolProvider, self)

    def tools(self) -> list[ToolSpec]:
        return [ToolSpec(name="viewer.open", description="open")]

    async def invoke(self, name: str, args: dict) -> Result:
        self.opened.append(args["path"])
        self.front.append(args.get("front"))
        return Result.ok({})


async def test_temp_ui_open_in_viewer_button():
    config = {"modules": {"enabled": ["temp_ui", "fake_viewer"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule, FakeViewer], config)
    await app.start()
    try:
        body = json.dumps({"path": "docs/html/agents/runtime.html"}).encode()
        reader, writer = await request(
            ui_port(app), b"POST /open-in-viewer HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
        )
        answer = await reader.read()
        writer.close()
        assert b'"ok": true' in answer and FakeViewer.opened == ["docs/html/agents/runtime.html"]
        assert FakeViewer.front == [True]  # your click brings the viewer to the front
        page = (Path(sys.modules[TempUIModule.__module__].__file__).with_name("page.html")).read_text(encoding="utf-8")
        assert "Open in viewer" in page
    finally:
        await app.stop()


async def test_talker_hears_the_open_tabs_with_your_next_message():
    config = {"modules": {"enabled": ["talker"], "talker": {"program": FAKE}}, "core": {}}
    app = App([TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        app.bus.publish(ViewerTabsChanged(tabs=("C:/a.html", "C:/b.html"), active="C:/b.html"))
        await asyncio.sleep(0.05)
        # The fake Talker repeats what it's sent: the tally comes first, once.
        app.bus.publish(InputReceived(text="What's open?", source="test"))
        reply = await asyncio.wait_for(replies.get(), 10)
        assert reply.text == "[Viewer] open: C:/a.html, C:/b.html (showing)\nWhat's open?"
        app.bus.publish(InputReceived(text="Again", source="test"))
        assert (await asyncio.wait_for(replies.get(), 10)).text == "Again"
    finally:
        await app.stop()
