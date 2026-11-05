"""app_kit: the parts shared by the main app and the independent apps."""

from __future__ import annotations

import ast
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import app_kit
from app_kit import CompanionApp, load_layered
from app_kit.window import devtools_port, open_app_window


def test_app_kit_never_imports_assistant():
    for file in Path(app_kit.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(n.split(".")[0] == "assistant" for n in names), file


def test_load_layered_merges_the_local_file(tmp_path):
    base = tmp_path / "voice.toml"
    base.write_text('a = 1\nlist = [1, 2]\n[t]\nx = 1\ny = 2\n', encoding="utf-8")
    assert load_layered(base) == {"a": 1, "list": [1, 2], "t": {"x": 1, "y": 2}}
    (tmp_path / "voice.local.toml").write_text('list = [3]\n[t]\ny = 9\n', encoding="utf-8")
    assert load_layered(base) == {"a": 1, "list": [3], "t": {"x": 1, "y": 9}}
    other = tmp_path / "other.toml"
    other.write_text("a = 5\n", encoding="utf-8")
    assert load_layered(base, other)["a"] == 5


def test_load_layered_needs_the_base_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_layered(tmp_path / "missing.toml")


def test_devtools_port(tmp_path):
    assert devtools_port(tmp_path) is None
    (tmp_path / "DevToolsActivePort").write_text("51234\n/devtools/browser/x\n")
    assert devtools_port(tmp_path) == 51234


def test_open_app_window_falls_back_to_a_browser_tab(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("app_kit.window.EDGE", [tmp_path / "no-edge.exe"])
    monkeypatch.setattr("app_kit.window.webbrowser.open", opened.append)
    assert open_app_window("http://127.0.0.1:1/", tmp_path, devtools=True) is None
    assert opened == ["http://127.0.0.1:1/"]


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/ping":
            self._json(200, {"app": "gone" if QUIT.is_set() else "fake"})
        elif self.path == "/missing":
            self._json(404, {"error": "no such thing"})
        elif self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for n in range(3):
                self.wfile.write(f"data: {json.dumps({'n': n})}\n\n".encode())
            self.wfile.flush()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/quit":
            QUIT.set()  # the fake "quits": its ping stops answering with its name
        self._json(200, {"echo": body})


QUIT = threading.Event()


@pytest.fixture
def fake_app():
    QUIT.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


async def test_companion_app_talks_to_a_running_app(fake_app):
    app = CompanionApp("fake", "127.0.0.1", fake_app, ping="/ping")
    assert await app.ping()
    assert await app.ensure_running() is False and not app.launched  # already running
    assert await app.call("POST", "/x", {"a": 1}) == {"echo": {"a": 1}}
    assert await app.call("GET", "/missing") == {"error": "no such thing"}
    assert [e async for e in app.events("/events")] == [{"n": 0}, {"n": 1}, {"n": 2}]
    await app.stop()  # not ours: nothing to quit


async def test_companion_app_quits_an_adopted_app_only_when_asked(fake_app):
    app = CompanionApp("fake", "127.0.0.1", fake_app, ping="/ping")
    assert await app.ensure_running() is False
    await app.stop()  # not ours: left running
    assert await app.ping()
    await app.ensure_running()
    await app.stop(adopted=True)  # a reload with new code: quit it anyway
    assert QUIT.is_set() and not await app.ping()


async def test_companion_app_notices_its_code_changed(fake_app, tmp_path, monkeypatch):
    package = tmp_path / "companion_probe_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "__main__.py").write_text("print('v1')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    app = CompanionApp("companion_probe_pkg", "127.0.0.1", fake_app, ping="/ping", name="fake")
    assert not app.code_changed()  # not used yet
    await app.ensure_running()  # adopted: its code is noted now
    assert not app.code_changed()
    main = package / "__main__.py"
    main.write_text("print('v2')\n")
    os.utime(main, ns=(main.stat().st_atime_ns, main.stat().st_mtime_ns + 10**9))
    assert app.code_changed()


async def test_companion_app_ping_checks_the_name(fake_app):
    assert not await CompanionApp("other", "127.0.0.1", fake_app, ping="/ping").ping()


async def test_companion_app_fails_early_when_the_process_exits():
    app = CompanionApp("app_kit_no_such_module", "127.0.0.1", 1, ping="/ping", start_timeout=20)
    with pytest.raises(OSError, match="exited"):
        await asyncio.wait_for(app.ensure_running(), 20)
    assert app.launched
    await app.stop()
    assert not app.launched
