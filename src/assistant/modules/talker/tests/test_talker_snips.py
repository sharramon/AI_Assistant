"""The Talker's side of the snips and the viewer's open tabs, heard by name with no import of the
viewer: html_viewer's named events (`html_viewer.tabs_changed`, `html_viewer.clip`) and the temp UI's
(`temp_ui.clip` for a pasted image, `temp_ui.clip_dropped`), and the names it declares. The temp UI's
side is in its own folder (`modules/temp_ui/tests/test_temp_ui_snips.py`)."""

import asyncio
import logging
from pathlib import Path

from assistant.contracts import InputReceived, ModuleEvent, ResponseReady
from assistant.core import App
from assistant.modules.talker import TalkerModule
from assistant.testkit import FAKE, clip_event, dropped_event


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def talker_app() -> tuple[App, asyncio.Queue]:
    app = App([TalkerModule], {"modules": {"enabled": ["talker"], "talker": {"program": FAKE}}, "core": {}})
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    return app, replies


def test_talker_declares_the_names_it_hears():
    assert set(TalkerModule.manifest.listens_named) == {"html_viewer.tabs_changed", "html_viewer.clip", "temp_ui.clip",
                                                        "temp_ui.clip_dropped"}  # fmt: skip


async def test_talker_sends_snips_with_your_next_message(tmp_path):
    image = write(tmp_path / "snip.png", "png")
    app, replies = talker_app()
    await app.start()
    try:
        for n in range(4):  # one more than it keeps
            app.bus.publish(clip_event(f"s{n}", image, "C:/docs/a.html", heading="Parts"))
        app.bus.publish(dropped_event("s3"))
        await asyncio.sleep(0.05)
        app.bus.publish(InputReceived(text="what is this?", source="test"))
        reply = (await asyncio.wait_for(replies.get(), 10)).text
        assert reply.startswith("[2 image(s)] [Viewer] snip from C:/docs/a.html, near \"Parts\"")
        assert reply.endswith("what is this?") and reply.count("[Viewer] snip") == 2  # s0 fell off, s3 was dropped
        app.bus.publish(InputReceived(text="And now?", source="test"))
        assert (await asyncio.wait_for(replies.get(), 10)).text == "And now?"  # used once
    finally:
        await app.stop()


async def test_talker_labels_a_pasted_image(tmp_path):
    image = write(tmp_path / "paste.png", "png")
    app, replies = talker_app()
    await app.start()
    try:
        app.bus.publish(clip_event("paste-1", image, "(pasted)", source="temp_ui"))
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
            app.bus.publish(clip_event(f"s{n}", image, "C:/a.html"))
        app.bus.publish(dropped_event("s0"))
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
