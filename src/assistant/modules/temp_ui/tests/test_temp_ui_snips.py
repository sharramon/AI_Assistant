"""temp_ui's side of the snips, heard by name with no import of the viewer: the names it declares,
hearing html_viewer's `html_viewer.clip` and its own `temp_ui.clip` (a pasted image), publishing
`temp_ui.clip_dropped`; and the chat's Open in viewer button. The Talker's side is in its folder
(`modules/talker/tests/test_talker_snips.py`), the SHOW tag's arguments in `tests/test_agent_tags.py`,
the viewer app and its module in `modules/html_viewer/tests`. Uses only the shared test kit."""

import asyncio
import json
import logging
import sys
from pathlib import Path

from assistant.contracts import (
    InputReceived,
    IPageOpener,
    Manifest,
    ModuleContext,
    ModuleEvent,
    ModuleProtocol,
    Result,
)
from assistant.core import App
from assistant.infra import LogSession
from assistant.modules.temp_ui import TempUIModule
from assistant.testkit import clip_event, request, ui_port

PNG = b"\x89PNG\r\n\x1a\nfake"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def named(app: App, name: str) -> asyncio.Queue:
    """The data of every named event `name` published on `app`'s bus, as it arrives."""
    found: asyncio.Queue = asyncio.Queue()

    async def put(event: ModuleEvent) -> None:
        if event.name == name:
            await found.put(event.data)

    app.bus.subscribe(ModuleEvent, put)
    return found


def temp_ui_config() -> dict:
    return {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}


def test_temp_ui_declares_the_names_it_hears_and_publishes():
    temp_ui = TempUIModule.manifest
    assert set(temp_ui.listens_named) == {"html_viewer.clip", "temp_ui.clip"}
    assert set(temp_ui.publishes_named) == {"temp_ui.clip", "temp_ui.clip_dropped"}


async def test_temp_ui_shows_snips_until_you_send(tmp_path):
    image = write(tmp_path / "snip.png", "png")
    app = App([TempUIModule], temp_ui_config())
    drops = named(app, "temp_ui.clip_dropped")
    await app.start()
    try:
        ui = app._lifecycle._active["temp_ui"][0]
        for n in range(2):
            app.bus.publish(clip_event(f"s{n}", image, "C:/a.html"))
        await asyncio.sleep(0.05)
        assert [s["id"] for s in ui._snips_item()["snips"]] == ["s0", "s1"]
        reader, writer = await request(ui_port(app), b"GET /snip/s0 HTTP/1.1\r\n\r\n")
        assert (await reader.read()).endswith(b"png")
        writer.close()
        body = b'{"id": "s0"}'
        reader, writer = await request(ui_port(app), b"POST /drop-snip HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))
        await reader.read()
        writer.close()
        assert (await asyncio.wait_for(drops.get(), 5)) == {"id": "s0"}
        app.bus.publish(InputReceived(text="what is this?", source="test"))
        await asyncio.sleep(0.05)
        assert ui._snips_item()["snips"] == []
        you = [i for c in ui._chats.values() for i in c if i["kind"] == "you"][-1]  # the sent bubble carries the snip
        assert [s["id"] for s in you["snips"]] == ["s1"]
        reader, writer = await request(ui_port(app), b"GET /snip/s1 HTTP/1.1\r\n\r\n")
        assert (await reader.read()).endswith(b"png")  # still served for the bubble
        writer.close()
    finally:
        await app.stop()


async def say(app, text: str) -> None:
    body = json.dumps({"text": text}).encode()
    reader, writer = await request(ui_port(app), b"POST /say HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))
    await reader.read()
    writer.close()


async def test_temp_ui_sends_a_snip_alone_and_logs_each_step(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    image = write(tmp_path / "snip.png", "png")
    app = App([TempUIModule], temp_ui_config())
    inputs: asyncio.Queue[InputReceived] = asyncio.Queue()
    app.bus.subscribe(InputReceived, inputs.put)
    await app.start()
    try:
        await say(app, "")  # nothing typed, no snip: nothing goes out
        await asyncio.sleep(0.05)
        assert inputs.empty()
        app.bus.publish(clip_event("s0", image, "C:/a.html"))
        await asyncio.sleep(0.05)
        await say(app, "  ")
        sent = await asyncio.wait_for(inputs.get(), 5)
        assert sent.text == "(snip)"
        await asyncio.sleep(0.05)
        assert "Snip s0 shown" in caplog.text and "Snips ['s0'] moved into sent message" in caplog.text
    finally:
        await app.stop()


async def paste(app, data: bytes, size: int | None = None) -> dict:
    head = b"POST /paste-image HTTP/1.1\r\nContent-Length: %d\r\n\r\n" % (len(data) if size is None else size)
    reader, writer = await request(ui_port(app), head + data)
    answer = json.loads((await reader.read()).split(b"\r\n\r\n", 1)[1])
    writer.close()
    return answer


async def test_temp_ui_turns_a_pasted_image_into_a_snip(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    logs = tmp_path / "logs" / "session"
    app = App([TempUIModule], temp_ui_config(), logs=LogSession(logs))
    clips = named(app, "temp_ui.clip")
    inputs: asyncio.Queue[InputReceived] = asyncio.Queue()
    app.bus.subscribe(InputReceived, inputs.put)
    await app.start()
    try:
        ui = app._lifecycle._active["temp_ui"][0]
        assert (await paste(app, b"GIF89a not a png"))["ok"] is False
        assert (await paste(app, b"", size=11 * 1024 * 1024))["error"].startswith("too big")
        assert clips.empty()
        answer = await paste(app, PNG)
        pasted = await asyncio.wait_for(clips.get(), 5)
        assert answer == {"ok": True, "id": pasted["id"]} and pasted["file"] == "(pasted)" and pasted["heading"] is None
        image = Path(pasted["image_path"])
        assert image == logs / "snips" / f"{pasted['id']}.png" and image.read_bytes() == PNG
        await asyncio.sleep(0.05)
        assert [s["id"] for s in ui._snips_item()["snips"]] == [pasted["id"]]  # a thumbnail, like a viewer snip
        await say(app, "")
        assert (await asyncio.wait_for(inputs.get(), 5)).text == "(snip)"
        assert "Paste refused: not a PNG" in caplog.text and "Paste refused: 11534336 bytes" in caplog.text
        assert f"Image pasted as snip {pasted['id']}" in caplog.text
    finally:
        await app.stop()


# --- the chat's Open in viewer button ---

class FakeViewer(ModuleProtocol, IPageOpener):
    """Any add-on that fills the page-opener slot; temp_ui never names it."""

    manifest = Manifest(id="fake_viewer", provides=(IPageOpener,))
    opened: list[str] = []
    front: list[bool] = []

    async def init(self, ctx: ModuleContext) -> None:
        ctx.provide(IPageOpener, self)

    async def open(self, path: str, quote: str | None = None, heading: str | None = None, front: bool = False) -> Result:
        self.opened.append(path)
        self.front.append(front)
        return Result.ok({})


async def open_in_viewer(app: App, path: str) -> bytes:
    body = json.dumps({"path": path}).encode()
    reader, writer = await request(
        ui_port(app), b"POST /open-in-viewer HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
    )
    answer = await reader.read()
    writer.close()
    return answer


async def test_temp_ui_open_in_viewer_button():
    config = {"modules": {"enabled": ["temp_ui", "fake_viewer"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule, FakeViewer], config)
    await app.start()
    try:
        answer = await open_in_viewer(app, "docs/html/agents/runtime.html")
        assert b'"ok": true' in answer and FakeViewer.opened == ["docs/html/agents/runtime.html"]
        assert FakeViewer.front == [True]  # your click brings the viewer to the front
        page = (Path(sys.modules[TempUIModule.__module__].__file__).with_name("page.html")).read_text(encoding="utf-8")
        assert "Open in viewer" in page
    finally:
        await app.stop()


async def test_temp_ui_open_in_viewer_with_no_page_viewer_says_so():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    await app.start()
    try:
        answer = await open_in_viewer(app, "a.html")
        assert b'{"ok": false, "error": "No page viewer is on"}' in answer
    finally:
        await app.stop()
