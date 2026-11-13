"""The listeners' side of the snips and the viewer's open tabs, heard by name with no import of the
viewer: the Talker and the temp UI hear html_viewer's named events (`html_viewer.tabs_changed`,
`html_viewer.clip`) and the temp UI's own (`temp_ui.clip` for a pasted image, `temp_ui.clip_dropped`).
Also the chat's Open in viewer button and the SHOW tag's arguments. The viewer app and its module
are tested in its own folder (`modules/html_viewer/tests`)."""

import asyncio
import json
import logging
import sys
from pathlib import Path

from assistant.contracts import (
    InputReceived,
    IToolProvider,
    Manifest,
    ModuleContext,
    ModuleEvent,
    ModuleProtocol,
    ResponseReady,
    Result,
    ToolSpec,
)
from assistant.core import App
from assistant.infra import LogSession
from assistant.infra.agent_tags import parse_show
from assistant.modules.talker import TalkerModule
from assistant.modules.temp_ui import TempUIModule
from assistant.testkit import FAKE
from tests.test_temp_ui import request, ui_port

PNG = b"\x89PNG\r\n\x1a\nfake"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def clip(snip_id: str, image: Path, file: str, heading: str | None = None, source: str = "html_viewer") -> ModuleEvent:
    """A snip as its publisher sends it: html_viewer's `html_viewer.clip`, or the temp UI's `temp_ui.clip`."""
    data = {"id": snip_id, "image_path": str(image), "file": file, "heading": heading}
    return ModuleEvent(name=f"{source}.clip", source=source, data=data)


def dropped(snip_id: str) -> ModuleEvent:
    return ModuleEvent(name="temp_ui.clip_dropped", source="temp_ui", data={"id": snip_id})


def named(app: App, name: str) -> asyncio.Queue:
    """The data of every named event `name` published on `app`'s bus, as it arrives."""
    found: asyncio.Queue = asyncio.Queue()

    async def put(event: ModuleEvent) -> None:
        if event.name == name:
            await found.put(event.data)

    app.bus.subscribe(ModuleEvent, put)
    return found


def talker_app() -> tuple[App, asyncio.Queue]:
    app = App([TalkerModule], {"modules": {"enabled": ["talker"], "talker": {"program": FAKE}}, "core": {}})
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    return app, replies


def temp_ui_config() -> dict:
    return {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}


def test_the_listeners_declare_the_names_they_hear():
    talker, temp_ui = TalkerModule.manifest, TempUIModule.manifest
    assert set(talker.listens_named) == {"html_viewer.tabs_changed", "html_viewer.clip", "temp_ui.clip",
                                         "temp_ui.clip_dropped"}  # fmt: skip
    assert set(temp_ui.listens_named) == {"html_viewer.clip", "temp_ui.clip"}
    assert set(temp_ui.publishes_named) == {"temp_ui.clip", "temp_ui.clip_dropped"}


def test_show_tag_arguments():
    assert parse_show(r"C:\a b\page.html") == (r"C:\a b\page.html", None, None)
    assert parse_show('C:/p.html | "the core hosts" | Parts') == ("C:/p.html", "the core hosts", "Parts")
    assert parse_show("'C:/p.html' | “quoted” |") == ("C:/p.html", "quoted", None)


async def test_talker_sends_snips_with_your_next_message(tmp_path):
    image = write(tmp_path / "snip.png", "png")
    app, replies = talker_app()
    await app.start()
    try:
        for n in range(4):  # one more than it keeps
            app.bus.publish(clip(f"s{n}", image, "C:/docs/a.html", heading="Parts"))
        app.bus.publish(dropped("s3"))
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
    app = App([TempUIModule], temp_ui_config())
    drops = named(app, "temp_ui.clip_dropped")
    await app.start()
    try:
        ui = app._lifecycle._active["temp_ui"][0]
        for n in range(2):
            app.bus.publish(clip(f"s{n}", image, "C:/a.html"))
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
        app.bus.publish(clip("s0", image, "C:/a.html"))
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


async def test_talker_labels_a_pasted_image(tmp_path):
    image = write(tmp_path / "paste.png", "png")
    app, replies = talker_app()
    await app.start()
    try:
        app.bus.publish(clip("paste-1", image, "(pasted)", source="temp_ui"))
        await asyncio.sleep(0.05)
        app.bus.publish(InputReceived(text="see the bar?", source="test"))
        reply = (await asyncio.wait_for(replies.get(), 10)).text
        assert reply.startswith(f"[1 image(s)] [Pasted] image (image attached; file: {image})")
    finally:
        await app.stop()


async def test_talker_logs_each_snip_step(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    image = write(tmp_path / "snip.png", "png")
    app, replies = talker_app()
    await app.start()
    try:
        for n in range(2):
            app.bus.publish(clip(f"s{n}", image, "C:/a.html"))
        app.bus.publish(dropped("s0"))
        await asyncio.sleep(0.05)
        app.bus.publish(InputReceived(text="(snip)", source="temp_ui"))
        await asyncio.wait_for(replies.get(), 10)
        assert "Snip s1 received" in caplog.text and "Snip s0 dropped: the x on its thumbnail" in caplog.text
        assert "1 snip(s) attached ['s1']" in caplog.text
    finally:
        await app.stop()


async def test_talker_hears_the_open_tabs_with_your_next_message():
    app, replies = talker_app()
    await app.start()
    try:
        data = {"tabs": ["C:/a.html", "C:/b.html"], "active": "C:/b.html", "highlights": [["C:/a.html", "core"]]}
        app.bus.publish(ModuleEvent(name="html_viewer.tabs_changed", source="html_viewer", data=data))
        await asyncio.sleep(0.05)
        # The fake Talker repeats what it's sent: the tally comes first, once.
        app.bus.publish(InputReceived(text="What's open?", source="test"))
        reply = await asyncio.wait_for(replies.get(), 10)
        assert reply.text == ('[Viewer] open: C:/a.html, C:/b.html (showing); highlighted: "core" in C:/a.html\n'
                              "What's open?")  # fmt: skip
        app.bus.publish(InputReceived(text="Again", source="test"))
        assert (await asyncio.wait_for(replies.get(), 10)).text == "Again"
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
