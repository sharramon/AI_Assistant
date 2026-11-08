"""The temporary two-pane UI: the page, posting input, and the event stream."""

import asyncio
import json
import time

from assistant.contracts import (
    AgentActivity,
    AgentInfo,
    FocusChanged,
    InputReceived,
    IVoice,
    ListAgents,
    ListeningState,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ModuleState,
    ModuleStateChanged,
    ReportKind,
    ResponseReady,
    Result,
    SetFocus,
    StartListening,
    Status,
    StopListening,
    TaskInfo,
    TaskState,
    TaskUpdated,
    VoiceDestination,
    VoiceState,
    VoiceTranscript,
)
from assistant.core import App
from assistant.modules.temp_ui import TempUIModule
from assistant.modules.temp_ui.module import CHAT_HISTORY, reset_target


def test_reset_buttons_reset_the_pair_of_the_tab_you_are_in():
    assert reset_target("worker", "cv_agent", "main_assistant") == "cv_agent"
    assert reset_target("talker", "cv_agent", "main_assistant") == "talker:cv_agent"
    assert reset_target("worker", "main_assistant", "main_assistant") == "main_assistant"
    assert reset_target("talker", "main_assistant", "main_assistant") == "talker"
    assert reset_target("worker", "", "main_assistant") == "main_assistant"  # no tab: the main pair
    assert reset_target("talker", "", "main_assistant") == "talker"
    assert reset_target("other", "cv_agent", "main_assistant") is None


async def test_reset_post_publishes_for_the_helper_tab():
    from assistant.contracts import ResetRequested

    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    await app.start()
    resets: asyncio.Queue = asyncio.Queue()
    app.bus.subscribe(ResetRequested, resets.put)
    try:
        body = json.dumps({"agent": "talker", "tab": "cv_agent"}).encode()
        reader, writer = await request(ui_port(app), b"POST /reset HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))
        await reader.read()
        writer.close()
        async with asyncio.timeout(2):
            assert (await resets.get()).agent_id == "talker:cv_agent"
    finally:
        await app.stop()


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
        # Replay sends the worker history first, then each tab's chat.
        assert [(i["pane"], i["kind"]) for i in items] == [("worker", "tool"), ("talker", "you"), ("talker", "talker")]
    finally:
        await app.stop()


class _FakeVoice(IVoice):
    """The fake's IVoice: the same sessions as its commands; finish ends only its own id."""

    def __init__(self, fake: "FakeVoiceIn") -> None:
        self.fake = fake

    async def listen(self, session_id, destination=VoiceDestination.CALLER):
        return await self.fake.listen(StartListening(id=session_id, send_as_input=destination == VoiceDestination.TALKER))

    async def finish(self, session_id, discard=False):
        if self.fake.session != session_id:
            return Result.ok({"text": "", "ended": True})
        return await self.fake.stop_listening(StopListening(discard=discard))


class FakeVoiceIn(ModuleProtocol):
    """Stands in for voice_in: answers the two commands and IVoice with the events voice_in publishes."""

    manifest = Manifest(id="voice_in", provides=(IVoice,), handles=(StartListening, StopListening))

    async def init(self, ctx: ModuleContext) -> None:
        self.ctx, self.session, self.commands = ctx, None, []
        self.fail: tuple[str, str] | None = None  # (reason, detail): the next start fails so
        ctx.handle(StartListening, self.listen)
        ctx.handle(StopListening, self.stop_listening)
        ctx.provide(IVoice, _FakeVoice(self))

    async def listen(self, command: StartListening) -> Result:
        self.commands.append(command)
        self.session = command.id
        self.ctx.publish(VoiceState(state=ListeningState.STARTING, correlation_id=command.id))
        if self.fail:
            reason, detail = self.fail
            self.ctx.publish(VoiceState(state=ListeningState.FAILED, reason=reason, detail=detail, correlation_id=command.id))
            self.session = None
            return Result(status=Status.NOT_AVAILABLE, error=detail, retryable=True)
        self.ctx.publish(VoiceState(state=ListeningState.LISTENING, correlation_id=command.id))
        return Result.ok({"session_id": command.id})

    async def stop_listening(self, command: StopListening) -> Result:
        self.commands.append(command)
        sid = self.session
        if sid is None:
            return Result.ok(None)
        if command.discard:
            self.ctx.publish(VoiceTranscript(session_id=sid, text="", final=True, correlation_id=sid))
            self.ctx.publish(VoiceState(state=ListeningState.IDLE, reason="cleared", detail="cleared", correlation_id=sid))
            return Result.ok({"text": "", "discarded": True})
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
        # The stop names the tab it was pressed in, so the final goes there.
        assert (await post(port, "/mic", {"on": False, "agent": "helper"}))["ok"]
        stop = app._lifecycle._active["voice_in"][0].commands[-1]
        assert isinstance(stop, StopListening) and stop.agent_id == "helper"
        said = await next_item(events, lambda i: i.get("kind") == "you")
        assert said["text"] == "hello there" and said["voice"] is True
        assert (await next_item(events, voice("idle")))["text"] == ""
        writer.close()
    finally:
        await app.stop()


async def test_mic_settled_text_reaches_the_page_and_finishing_keeps_the_line():
    config = {"modules": {"enabled": ["temp_ui", "voice_in"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule, FakeVoiceIn], config)
    await app.start()
    port = ui_port(app)
    try:
        events, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
        await next_item(events, voice("idle"))
        await post(port, "/mic", {"on": True})
        await next_item(events, voice("listening"))
        sid = app._lifecycle._active["voice_in"][0].session
        app.bus.publish(VoiceTranscript(session_id=sid, text="Hello there. HOW", settled_chars=12, correlation_id=sid))
        assert (await next_item(events, lambda i: i.get("kind") == "voice" and i["text"]))["settled"] == 12
        app.bus.publish(VoiceState(state=ListeningState.FINISHING, detail="cleaning up…", correlation_id=sid))
        finishing = await next_item(events, voice("finishing"))
        assert (finishing["text"], finishing["settled"], finishing["detail"]) == ("Hello there. HOW", 12, "cleaning up…")
        app.bus.publish(VoiceTranscript(session_id=sid, text="Hello there. How?", final=True, correlation_id=sid))
        app.bus.publish(VoiceState(state=ListeningState.IDLE, correlation_id=sid))
        idle = await next_item(events, voice("idle"))
        assert (idle["text"], idle["settled"]) == ("", 0)
        writer.close()
    finally:
        await app.stop()


async def test_mic_clear_drops_the_text_and_keeps_listening():
    config = {"modules": {"enabled": ["temp_ui", "voice_in"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule, FakeVoiceIn], config)
    await app.start()
    port = ui_port(app)
    try:
        fake = app._lifecycle._active["voice_in"][0]
        events, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
        await next_item(events, voice("idle"))
        await post(port, "/mic", {"on": True})
        await next_item(events, voice("listening"))
        first = fake.session
        app.bus.publish(VoiceTranscript(session_id=first, text="someone else", correlation_id=first))
        await next_item(events, lambda i: i.get("kind") == "voice" and i["text"] == "someone else")

        assert (await post(port, "/mic", {"clear": True}))["ok"]
        assert (await next_item(events, voice("idle")))["text"] == ""  # the line clears
        listening = await next_item(events, voice("listening"))  # and the mic carries on, in a new session
        assert listening["text"] == "" and fake.session != first
        kinds = [type(c).__name__ + ("(discard)" if getattr(c, "discard", False) else "") for c in fake.commands]
        assert kinds == ["StartListening", "StopListening(discard)", "StartListening"]

        # Clear with nothing listening doesn't turn the mic on.
        fake.session = None
        fake.commands.clear()
        await post(port, "/mic", {"on": False})
        fake.commands.clear()
        assert (await post(port, "/mic", {"clear": True}))["ok"]
        assert [type(c).__name__ for c in fake.commands] == ["StopListening"]
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
        first = await next_item(events, voice("idle"))
        assert (first["available"], first["why"], first["retry"]) == (False, "The voice module is off", False)
        assert not (await post(port, "/mic", {"on": True}))["ok"]
        assert (await next_item(events, voice("failed")))["detail"] == "voice input is off"
        writer.close()
    finally:
        await app.stop()


def voice_item(match):
    return lambda i: i.get("kind") == "voice" and match(i)


async def test_mic_says_why_it_is_unavailable():
    config = {"modules": {"enabled": ["temp_ui", "voice_in"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule, FakeVoiceIn], config)
    await app.start()
    port = ui_port(app)
    try:
        events, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
        await next_item(events, voice_item(lambda i: i["available"]))

        # The voice module is reloaded: not clickable, through its starting, until it's active.
        app.bus.publish(ModuleStateChanged(module_id="voice_in", state=ModuleState.RELOADING))
        reloading = await next_item(events, voice_item(lambda i: not i["available"]))
        assert "being reloaded" in reloading["why"] and not reloading["retry"]
        app.bus.publish(ModuleStateChanged(module_id="voice_in", state=ModuleState.STARTING))
        app.bus.publish(ModuleStateChanged(module_id="voice_in", state=ModuleState.ACTIVE))
        assert (await next_item(events, voice_item(lambda i: True)))["available"]  # no "starting" in between

        # Another part of the app's session (voice notes) failing doesn't touch this button.
        app.bus.publish(VoiceState(state=ListeningState.STARTING, correlation_id="notes"))
        app.bus.publish(VoiceState(state=ListeningState.FAILED, reason="service_unavailable",
                                   detail="not ours", correlation_id="notes"))  # fmt: skip

        # The voice app isn't running: crossed out, but a click retries; the next start clears it.
        fake = app._lifecycle._active["voice_in"][0]
        fake.fail = ("service_unavailable", "voice service didn't start")
        await post(port, "/mic", {"on": True})
        down = await next_item(events, voice("failed"))
        assert down["why"] == "The voice app isn't running: voice service didn't start. Click to try starting it again"
        assert (down["available"], down["retry"]) == (False, True)
        fake.fail = None
        await post(port, "/mic", {"on": True})
        assert (await next_item(events, voice("starting")))["available"]
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
        # (Replay: the worker history first, then the chat.)
        assert [(i["pane"], i["kind"]) for i in items] == [
            ("worker", "task"),
            ("worker", "task"),
            ("talker", "permission"),
            ("talker", "answered"),
        ]
        assert items[2]["task_id"] == "t1" and items[2]["text"] == "Bash rm x"
        assert "asks permission: Bash rm x" in items[0]["text"]
        assert "permission allowed" in items[1]["text"]
    finally:
        await app.stop()


class FakeHub(ModuleProtocol):
    """Stands in for agent_hub: two big agents; SetFocus releases the helper's held card."""

    manifest = Manifest(id="agent_hub", handles=(ListAgents, SetFocus), publishes=(FocusChanged,))

    async def init(self, ctx: ModuleContext) -> None:
        self.ctx, self.focused = ctx, []
        ctx.handle(ListAgents, self.list_agents)
        ctx.handle(SetFocus, self.set_focus)

    async def list_agents(self, command: ListAgents) -> Result:
        return Result.ok([AgentInfo(agent_id="main_assistant", description="m"), AgentInfo(agent_id="helper", description="h", busy=True)])

    async def set_focus(self, command: SetFocus) -> Result:
        self.focused.append(command.agent_id)
        held = TaskInfo(id="t2", agent_id="helper", text="x", state=TaskState.WAITING_FOR_INPUT, question="Bash rm y", question_kind="permission", held=True)
        self.ctx.publish(FocusChanged(agent_id=command.agent_id, previous="main_assistant", released=(held,)))
        return Result.ok(command.agent_id)


async def test_agent_tabs_hold_cards_until_the_focus_moves():
    config = {"modules": {"enabled": ["agent_hub", "temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([FakeHub, TempUIModule], config)
    await app.start()
    port, ui = ui_port(app), app._lifecycle._active["temp_ui"][0]
    reader, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
    try:
        tabs = await next_item(reader, lambda i: i.get("kind") == "agents")
        assert [a["id"] for a in tabs["agents"]] == ["main_assistant", "helper"] and tabs["focus"] == "main_assistant"

        # Out of focus: the card is held behind the helper's !, only the worker pane logs it.
        app.bus.publish(TaskUpdated(task_id="t2", state=TaskState.WAITING_FOR_INPUT, kind=ReportKind.PERMISSION,
                                    text="Bash rm y", agent_id="helper", held=True))  # fmt: skip
        app.bus.publish(AgentActivity(agent_id="helper", text="→ Bash"))
        bang = await next_item(reader, lambda i: i.get("kind") == "agents")
        assert {a["id"]: a["held"] for a in bang["agents"]} == {"main_assistant": 0, "helper": 1}
        log = await next_item(reader, lambda i: i.get("pane") == "worker" and i["kind"] == "task")
        assert log["agent"] == "helper"
        assert (await next_item(reader, lambda i: i.get("kind") == "tool"))["agent"] == "helper"
        assert not [i for c in ui._chats.values() for i in c if i["kind"] == "permission"]

        # A tab click: SetFocus; the released card shows, named, and the ! clears.
        assert (await post(port, "/focus", {"agent": "helper"}))["ok"]
        card = await next_item(reader, lambda i: i.get("kind") == "permission")
        assert (card["pane"], card["agent"], card["task_id"], card["text"]) == ("talker", "helper", "t2", "Bash rm y")
        moved = await next_item(reader, lambda i: i.get("kind") == "agents")
        assert moved["focus"] == "helper" and all(a["held"] == 0 for a in moved["agents"])
        assert app._lifecycle._active["agent_hub"][0].focused == ["helper"]
    finally:
        writer.close()
        await app.stop()


async def _say(port: int, body: dict) -> None:
    data = json.dumps(body).encode()
    reader, writer = await request(port, b"POST /say HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(data), data))
    await reader.read()
    writer.close()


async def test_chats_are_kept_per_tab_and_say_names_its_tab():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    inputs: asyncio.Queue[InputReceived] = asyncio.Queue()
    app.bus.subscribe(InputReceived, inputs.put)
    await app.start()
    port = ui_port(app)
    try:
        ui = app._lifecycle._active["temp_ui"][0]
        ui._push("talker", "talker", "first", agent="helper")
        for n in range(CHAT_HISTORY + 20):  # one tab's flood
            ui._push("talker", "talker", f"line {n}", agent="main_assistant")
        assert len(ui._chats["main_assistant"]) == CHAT_HISTORY
        assert ui._chats["main_assistant"][0]["text"] == "line 20"
        assert [i["text"] for i in ui._chats["helper"]] == ["first"]  # not pushed out
        assert all(i["agent"] == "helper" for i in ui._chats["helper"])

        await _say(port, {"text": "to the helper", "agent": "helper"})
        said = await asyncio.wait_for(inputs.get(), 2)
        assert said.text == "to the helper" and said.agent_id == "helper"
        await _say(port, {"text": "no tab"})
        assert (await asyncio.wait_for(inputs.get(), 2)).agent_id == ui._focus  # the focus's
    finally:
        await app.stop()
