"""The temporary two-pane UI: the page, posting input, and the event stream."""

import asyncio
import json
import time

from assistant.contracts import (
    AgentActivity,
    InputReceived,
    ListeningState,
    Manifest,
    Module,
    ModuleContext,
    ReportKind,
    ResponseReady,
    Result,
    StartListening,
    StopListening,
    TaskState,
    TaskUpdated,
    VoiceState,
    VoiceTranscript,
)
from assistant.core import App
from assistant.modules.temp_ui import TempUIModule


async def request(port: int, raw: bytes) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    return reader, writer


async def read_events(port: int, count: int) -> list[dict]:
    """The first `count` items on /events, after its leading `hello`."""
    reader, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
    items = []
    async with asyncio.timeout(2):
        while len(items) < count + 1:
            line = await reader.readline()
            if line.startswith(b"data: "):
                items.append(json.loads(line[6:]))
    writer.close()
    assert items[0]["kind"] == "hello" and items[0]["launch"]
    return items


def ui_port(app: App) -> int:
    return int(app._lifecycle._active["temp_ui"][0].url.rsplit(":", 1)[1].strip("/"))


async def test_each_launch_has_its_own_id():
    # The page closes itself when the id changes on reconnect (a relaunch opened a fresh window).
    launches = []
    for _ in range(2):
        config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
        app = App([TempUIModule], config)
        await app.start()
        try:
            first, again = await read_events(ui_port(app), 0), await read_events(ui_port(app), 0)
            assert first[0]["launch"] == again[0]["launch"]
            launches.append(first[0]["launch"])
        finally:
            await app.stop()
    assert launches[0] != launches[1]


async def test_page_input_and_events():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    inputs: asyncio.Queue[InputReceived] = asyncio.Queue()
    app.bus.subscribe(InputReceived, inputs.put)
    await app.start()
    port = int(app._lifecycle._active["temp_ui"][0].url.rsplit(":", 1)[1].strip("/"))
    try:
        reader, writer = await request(port, b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
        page = await reader.read()
        assert b"200 OK" in page and b"Main Assistant" in page
        writer.close()

        body = json.dumps({"text": "hello"}).encode()
        reader, writer = await request(
            port, b"POST /say HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
        )
        assert b"204" in await reader.read()
        writer.close()
        said = await asyncio.wait_for(inputs.get(), 2)
        assert said.text == "hello" and said.source == "temp_ui"

        app.bus.publish(ResponseReady(text="hi there"))
        app.bus.publish(AgentActivity(agent_id="main_assistant", text="→ Write poems.txt"))
        items = (await read_events(port, 3))[1:]
        assert [(i["pane"], i["kind"]) for i in items] == [("talker", "you"), ("talker", "talker"), ("worker", "tool")]
    finally:
        await app.stop()


class FakeVoiceIn(Module):
    """Stands in for voice_in: answers the two commands with the events voice_in publishes."""

    manifest = Manifest(id="voice_in")

    async def init(self, ctx: ModuleContext) -> None:
        self.ctx, self.session = ctx, None
        ctx.handle(StartListening, self.listen)
        ctx.handle(StopListening, self.stop_listening)

    async def listen(self, command: StartListening) -> Result:
        self.session = command.id
        self.ctx.publish(VoiceState(state=ListeningState.STARTING, correlation_id=command.id))
        self.ctx.publish(VoiceState(state=ListeningState.LISTENING, correlation_id=command.id))
        return Result.ok({"session_id": command.id})

    async def stop_listening(self, command: StopListening) -> Result:
        sid = self.session
        self.ctx.publish(VoiceTranscript(session_id=sid, text="hello there", final=True, correlation_id=sid))
        self.ctx.publish(InputReceived(text="hello there", source="voice"))
        self.ctx.publish(VoiceState(state=ListeningState.IDLE, correlation_id=sid))
        return Result.ok({"text": "hello there", "latency_ms": 50})


async def post(port: int, path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    reader, writer = await request(port, b"POST %s HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (path.encode(), len(data), data))
    raw = await reader.read()
    writer.close()
    return json.loads(raw.split(b"\r\n\r\n", 1)[1])


async def next_item(reader: asyncio.StreamReader, match) -> dict:
    """The next item on an open /events stream for which `match(item)` is true."""
    async with asyncio.timeout(2):
        while True:
            line = await reader.readline()
            if line.startswith(b"data: ") and match(item := json.loads(line[6:])):
                return item


def voice(state: str):
    return lambda i: i.get("kind") == "voice" and i["state"] == state


async def test_mic_button_round_trip():
    config = {"modules": {"enabled": ["temp_ui", "voice_in"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule, FakeVoiceIn], config)
    await app.start()
    port = ui_port(app)
    try:
        events, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
        assert (await next_item(events, voice("idle")))["text"] == ""  # the current state, on connect
        assert await post(port, "/mic", {"on": True}) == {"ok": True, "error": None}
        await next_item(events, voice("listening"))
        sid = app._lifecycle._active["voice_in"][0].session

        # A stale session's text is ignored; the current one's partial is the live line.
        app.bus.publish(VoiceTranscript(session_id="old", text="stale", correlation_id="old"))
        app.bus.publish(VoiceTranscript(session_id=sid, text="hello the", correlation_id=sid))
        assert (await next_item(events, lambda i: i.get("kind") == "voice" and i["text"]))["text"] == "hello the"

        # Dropped: the countdown's end comes from the detail, and the text stays for the word count.
        app.bus.publish(VoiceState(state=ListeningState.DROPPED, reason="mic_dropped",
                                   detail="mic dropped, waiting 15 s for it to come back", correlation_id=sid))
        dropped = await next_item(events, voice("dropped"))
        assert dropped["text"] == "hello the" and 14_000 < dropped["until"] - time.time() * 1000 <= 15_000
        app.bus.publish(VoiceState(state=ListeningState.LISTENING, correlation_id=sid))
        await next_item(events, voice("listening"))

        # Stop: the spoken message lands in the chat as yours, marked spoken; the line clears.
        assert (await post(port, "/mic", {"on": False}))["ok"]
        said = await next_item(events, lambda i: i.get("kind") == "you")
        assert said["text"] == "hello there" and said["voice"] is True
        assert (await next_item(events, voice("idle")))["text"] == ""
        writer.close()
    finally:
        await app.stop()


async def test_mic_without_voice_in_says_it_is_off():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    await app.start()
    port = ui_port(app)
    try:
        events, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
        await next_item(events, voice("idle"))
        assert not (await post(port, "/mic", {"on": True}))["ok"]
        assert (await next_item(events, voice("failed")))["detail"] == "voice input is off"
        writer.close()
    finally:
        await app.stop()


async def test_permission_card_on_talker_side():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    await app.start()
    port = int(app._lifecycle._active["temp_ui"][0].url.rsplit(":", 1)[1].strip("/"))
    try:
        app.bus.publish(
            TaskUpdated(task_id="t1", state=TaskState.WAITING_FOR_INPUT, kind=ReportKind.PERMISSION, text="Bash rm x")
        )
        app.bus.publish(TaskUpdated(task_id="t1", state=TaskState.RUNNING, text="permission allowed"))
        items = (await read_events(port, 4))[1:]
        # The Allow / Deny card and its answer go to the Talker pane; the worker pane only logs them.
        assert [(i["pane"], i["kind"]) for i in items] == [
            ("talker", "permission"),
            ("worker", "task"),
            ("talker", "answered"),
            ("worker", "task"),
        ]
        assert items[0]["task_id"] == "t1" and items[0]["text"] == "Bash rm x"
        assert "asks permission: Bash rm x" in items[1]["text"]
        assert "permission allowed" in items[3]["text"]
    finally:
        await app.stop()
