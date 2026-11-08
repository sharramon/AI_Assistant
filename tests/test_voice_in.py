"""The voice_in module against the real voice service app (fake engine, fake mic) on a local port.

No microphone and no model: the service runs in this process under Uvicorn, in a thread, with
`FakeEngine` and `FakeSource`. Only `voice_in` itself is held to importing just `protocol`.
"""

from __future__ import annotations

import ast
import asyncio
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from websockets.asyncio.client import connect

from assistant.contracts import (
    InputReceived,
    ListeningState,
    StartListening,
    Status,
    StopListening,
    VoiceState,
    VoiceTranscript,
)
from assistant.core import App
from assistant.modules.voice_in import VoiceInModule
from tests.support import wait_until
from voice_service.audio import FakeSource
from voice_service.config import ServiceConfig
from voice_service.engines.fake import FakeEngine
from voice_service.protocol import Error, ErrorCode, Final
from voice_service.server import create_app
from voice_service.session import ListenSession

CHUNK = bytes(1024)  # 32 ms of silence
TEXT = "hello big world"  # the fake engine: one word per two chunks


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def take(*sources):
    """A source factory handing these out in turn; the last one repeats."""
    pending = list(sources)
    return lambda: pending.pop(0) if len(pending) > 1 else pending[0]


class Service:
    """The real voice service app on a free local port, in a thread."""

    def __init__(self, engine=None, source=(), final=None, pieces=None, **audio) -> None:
        audio = {"stall_seconds": 0, **audio}  # fake sources go quiet after their chunks
        raw = {"engine": {"name": "fake", "partial_interval_ms": 0}, "audio": audio, "pieces": pieces or {}}
        config = ServiceConfig.model_validate(raw)
        factory = source if callable(source) else (lambda: FakeSource(list(source), interval=0.005))
        self.port = free_port()
        app = create_app(config, engine or FakeEngine(TEXT), factory, final_engine=final)
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, name="voice-service-test", daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            assert time.monotonic() < deadline, "the voice service didn't start"
            time.sleep(0.01)

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(10)


@pytest.fixture
def service():
    services: list[Service] = []

    def make(*args, **kwargs) -> Service:
        services.append(Service(*args, **kwargs))
        return services[-1]

    yield make
    for s in services:
        s.close()


@pytest.fixture
def fast_retry(monkeypatch):
    monkeypatch.setattr(ListenSession, "retry_seconds", 0.02)


class Probe(VoiceInModule):
    """voice_in, keeping a handle on the instance for the test."""

    last: Probe | None = None

    async def init(self, ctx) -> None:
        await super().init(ctx)
        Probe.last = self


class Recorder:
    def __init__(self, app: App) -> None:
        self.events: list = []
        for kind in (VoiceState, VoiceTranscript, InputReceived):
            app.bus.subscribe(kind, self._add)

    async def _add(self, event) -> None:
        self.events.append(event)

    def of(self, kind) -> list:
        return [e for e in self.events if isinstance(e, kind)]

    def states(self) -> list[str]:
        return [e.state.value for e in self.of(VoiceState)]

    async def wait(self, predicate, timeout: float = 5.0) -> None:
        await wait_until(lambda: predicate(self), timeout)


async def start_app(port: int, module=Probe, **settings) -> tuple[App, Recorder]:
    section = {"host": "127.0.0.1", "port": port, "reply_timeout": 3.0, "cleanup": False, **settings}
    app = App([module], {"modules": {"enabled": ["voice_in"], "voice_in": section}, "core": {}})
    recorder = Recorder(app)
    await app.start()
    return app, recorder


def last_state(rec: Recorder) -> VoiceState:
    return rec.of(VoiceState)[-1]


def has_text(text: str):
    return lambda rec: any(t.text == text for t in rec.of(VoiceTranscript))


# --- the main path ---


async def test_start_partials_stop_final_and_the_talker_gets_it(service):
    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    try:
        command = StartListening()
        assert (await app.router.send(command)).value == {"session_id": command.id}
        await rec.wait(has_text(TEXT))
        result = await app.router.send(StopListening())
        assert result.value["text"] == TEXT and result.value["latency_ms"] >= 0
        await rec.wait(lambda r: r.of(InputReceived) and r.states()[-1] == "idle")
        assert rec.states() == ["starting", "listening", "idle"]
        assert [(i.text, i.source, i.agent_id) for i in rec.of(InputReceived)] == [(TEXT, "voice", None)]  # None: the focus
        final = rec.of(VoiceTranscript)[-1]
        assert (final.text, final.final, final.session_id) == (TEXT, True, command.id)
        assert {e.correlation_id for e in rec.of(VoiceState) + rec.of(VoiceTranscript)} == {command.id}
    finally:
        await app.stop()


async def test_the_final_goes_to_the_tab_the_stop_was_pressed_in(service):
    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await rec.wait(has_text(TEXT))
        assert (await app.router.send(StopListening(agent_id="helper"))).value["text"] == TEXT
        await rec.wait(lambda r: r.of(InputReceived))
        assert [(i.text, i.agent_id) for i in rec.of(InputReceived)] == [(TEXT, "helper")]
    finally:
        await app.stop()


async def test_the_cleanup_gives_sentence_case_live_and_final(service, caplog):
    svc = service(FakeEngine("WHAT IS USD"), source=[CHUNK] * 6)
    app, rec = await start_app(svc.port, cleanup=True, terms=["USD"])
    try:
        await app.router.send(StartListening())
        await rec.wait(has_text("What is USD"))  # the live line: cleaned, no end mark
        with caplog.at_level("INFO"):
            result = await app.router.send(StopListening())
        assert result.value["text"] == "What is USD?"
        await rec.wait(lambda r: r.of(InputReceived))
        assert [i.text for i in rec.of(InputReceived)] == ["What is USD?"]
        assert all(t.text == t.text.capitalize() or "USD" in t.text for t in rec.of(VoiceTranscript))
        assert "raw: 'WHAT IS USD' -> clean: 'What is USD?'" in caplog.text
    finally:
        await app.stop()


async def test_send_as_input_off_keeps_the_text_from_the_talker(service):
    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening(send_as_input=False))
        await rec.wait(has_text(TEXT))
        assert (await app.router.send(StopListening())).value["text"] == TEXT
        await rec.wait(lambda r: r.states()[-1] == "idle")
        assert rec.of(InputReceived) == []
    finally:
        await app.stop()


def of_session(rec: Recorder, kind, command) -> list:
    return [e for e in rec.of(kind) if e.correlation_id == command.id]


async def test_a_second_start_takes_the_mic_and_the_first_text_is_dropped(service):
    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    try:
        assert (await app.router.send(StopListening())).value is None
        first = StartListening()  # the chat's mic: its text would go to the Talker
        await app.router.send(first)
        await rec.wait(lambda r: any(t.text for t in of_session(r, VoiceTranscript, first)))
        old = Probe.last._session
        second = StartListening(send_as_input=False)  # voice notes
        assert (await app.router.send(second)).value == {"session_id": second.id}
        await rec.wait(lambda r: of_session(r, VoiceState, first)[-1].state is ListeningState.IDLE)
        ended = of_session(rec, VoiceState, first)[-1]
        assert (ended.reason, ended.detail) == ("taken_over", "another part of the app took the mic")
        cleared = of_session(rec, VoiceTranscript, first)[-1]
        assert (cleared.text, cleared.final) == ("", True)
        Probe.last._finish(old, Final(text="late words", latency_ms=5))  # the cancelled session's late final
        await rec.wait(lambda r: any(t.text == TEXT for t in of_session(r, VoiceTranscript, second)))
        assert (await app.router.send(StopListening())).value["text"] == TEXT
        await rec.wait(lambda r: r.states()[-1] == "idle")
        assert rec.of(InputReceived) == []  # neither the cancelled text nor the notes' text
        assert not any(t.text == "late words" for t in rec.of(VoiceTranscript))
    finally:
        await app.stop()


async def test_a_stop_waiting_when_the_mic_is_taken_gets_taken_over(service):
    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        session = Probe.last._session

        async def swallow(_message) -> None:  # the stop never reaches the service: it waits for its final
            pass

        session.ws.send = swallow
        stop = asyncio.create_task(app.router.send(StopListening()))
        await asyncio.sleep(0.05)
        await app.router.send(StartListening(send_as_input=False))
        assert (await stop).value == {"text": "", "taken_over": True}
        assert rec.of(InputReceived) == []
    finally:
        await app.stop()


async def test_an_empty_final_clears_the_line_and_sends_nothing(service):
    svc = service(source=[])
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        assert (await app.router.send(StopListening())).value["text"] == ""
        await rec.wait(lambda r: r.states()[-1] == "idle")
        assert rec.of(VoiceTranscript)[-1].final is True and rec.of(InputReceived) == []
    finally:
        await app.stop()


# --- the clear button: StopListening(discard=True) ---


async def test_clear_drops_the_text_and_the_next_session_starts_at_once(service):
    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    try:
        first = StartListening()
        await app.router.send(first)
        await rec.wait(has_text(TEXT))
        result = await app.router.send(StopListening(discard=True))
        assert result.is_ok and result.value == {"text": "", "discarded": True}
        cleared = last_state(rec)
        assert (cleared.state, cleared.reason, cleared.correlation_id) == (ListeningState.IDLE, "cleared", first.id)
        final = rec.of(VoiceTranscript)[-1]
        assert (final.text, final.final, final.correlation_id) == ("", True, first.id)  # the line clears
        assert rec.of(InputReceived) == []

        # Carry on: a new session starts straight away (no `busy`), and its text is sent as usual.
        second = StartListening()
        assert (await app.router.send(second)).is_ok
        await rec.wait(lambda r: any(t.text == TEXT and t.correlation_id == second.id for t in r.of(VoiceTranscript)))
        assert (await app.router.send(StopListening())).value["text"] == TEXT
        await rec.wait(lambda r: r.of(InputReceived))
        assert [i.text for i in rec.of(InputReceived)] == [TEXT]
        assert rec.states() == ["starting", "listening", "idle", "starting", "listening", "idle"]
    finally:
        await app.stop()


async def test_a_final_after_the_clear_is_not_sent(service):
    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await rec.wait(has_text(TEXT))
        session = Probe.last._session
        await app.router.send(StopListening(discard=True))
        Probe.last._finish(session, Final(text="someone else talking", latency_ms=5))  # a late final
        assert rec.of(InputReceived) == []
        assert not any(t.text == "someone else talking" for t in rec.of(VoiceTranscript))
        assert rec.states()[-1] == "idle" and Probe.last._session is None
    finally:
        await app.stop()


async def test_clear_with_nothing_listening_is_ok_none(service):
    svc = service(source=[])
    app, rec = await start_app(svc.port)
    try:
        assert (await app.router.send(StopListening(discard=True))).value is None
        assert rec.events == []
    finally:
        await app.stop()


async def test_a_busy_start_right_after_a_clear_is_tried_once_more(service, monkeypatch):
    import assistant.modules.voice_in.module as voice_module

    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    monkeypatch.setattr(voice_module, "CLEAR_RETRY_WAIT", 0.01)
    replies = [Error(reason=ErrorCode.BUSY, detail="another app is listening")]
    real = Probe.last._send_start

    async def send_start(session):
        return replies.pop(0) if replies else await real(session)

    monkeypatch.setattr(Probe.last, "_send_start", send_start)
    try:
        Probe.last._cleared_at = time.monotonic()  # as if the ✕ was just clicked
        assert (await app.router.send(StartListening())).is_ok
        assert rec.states() == ["starting", "listening"]
    finally:
        await app.stop()


async def test_a_long_silence_ends_the_session_and_sends_the_text(service):
    svc = service(source=[CHUNK] * 2, silence_stop_seconds=0.3)
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await rec.wait(lambda r: r.states()[-1] == "idle")
        assert last_state(rec).reason == "silence"
        assert [i.text for i in rec.of(InputReceived)] == ["hello"]
    finally:
        await app.stop()


# --- the mic drop ---


async def test_a_dropped_mic_that_comes_back_carries_on(service, fast_retry):
    factory = take(FakeSource([CHUNK] * 2, lose_after=2), FakeSource(fail_on_open=True),
                   FakeSource([CHUNK] * 4, interval=0.005))  # fmt: skip
    svc = service(source=factory, mic_recovery_seconds=5)
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await rec.wait(lambda r: r.states()[-1:] == ["listening"] and "dropped" in r.states())
        dropped = next(s for s in rec.of(VoiceState) if s.state is ListeningState.DROPPED)
        assert dropped.reason == "mic_dropped" and "5 s" in dropped.detail
        await rec.wait(has_text(TEXT))
        assert (await app.router.send(StopListening())).value["text"] == TEXT
        await rec.wait(lambda r: r.of(InputReceived))
        assert rec.states() == ["starting", "listening", "dropped", "listening", "idle"]
    finally:
        await app.stop()


async def test_a_mic_that_doesnt_come_back_drops_the_text(service, fast_retry):
    svc = service(source=take(FakeSource([CHUNK] * 2, lose_after=2), FakeSource(fail_on_open=True)),
                  mic_recovery_seconds=0.2)  # fmt: skip
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await rec.wait(lambda r: r.states()[-1] == "failed")
        assert rec.states() == ["starting", "listening", "dropped", "failed"]
        assert last_state(rec).reason == "mic_lost"
        line = rec.of(VoiceTranscript)[-1]
        assert (line.text, line.final) == ("", True)  # the text so far is cleared, not sent
        assert rec.of(InputReceived) == []
        assert (await app.router.send(StopListening())).value is None  # the session is over
    finally:
        await app.stop()


async def test_stop_while_dropped_drops_the_text(service, fast_retry):
    svc = service(source=take(FakeSource([CHUNK] * 2, lose_after=2), FakeSource(fail_on_open=True)),
                  mic_recovery_seconds=30)  # fmt: skip
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await rec.wait(lambda r: "dropped" in r.states())
        result = await app.router.send(StopListening())
        assert result.status is Status.FAILED and "dropped" in result.error
        assert last_state(rec).reason == "mic_lost" and rec.of(InputReceived) == []
    finally:
        await app.stop()


# --- errors ---


async def test_busy_when_another_client_listens(service):
    svc = service(source=[CHUNK] * 2)
    app, rec = await start_app(svc.port)
    try:
        async with connect(f"ws://127.0.0.1:{svc.port}/ws/listen") as other:
            await other.send('{"type": "start"}')
            assert "started" in await other.recv()
            result = await app.router.send(StartListening())
            assert result.status is Status.FAILED
            assert (last_state(rec).state, last_state(rec).reason) == (ListeningState.FAILED, "busy")
    finally:
        await app.stop()


async def test_mic_unavailable(service):
    svc = service(source=lambda: FakeSource(fail_on_open=True))
    app, rec = await start_app(svc.port)
    try:
        result = await app.router.send(StartListening())
        assert (result.status, result.retryable) == (Status.NOT_AVAILABLE, True)
        assert last_state(rec).reason == "mic_unavailable" and "Windows" in last_state(rec).detail
    finally:
        await app.stop()


async def test_a_failed_model_is_caught_by_the_health_check(service):
    svc = service(FakeEngine(fail_on_load=True))
    app, rec = await start_app(svc.port)
    try:
        deadline = time.monotonic() + 5  # the model "load" runs in the service's background thread
        while (await Probe.last._app.call("GET", "/health"))["error"] is None:
            assert time.monotonic() < deadline
        Probe.last._connect = None  # a WebSocket attempt would raise TypeError and show as service_unavailable
        result = await app.router.send(StartListening())
        assert result.status is Status.NOT_AVAILABLE and "load failed" in result.error
        assert last_state(rec).reason == "engine_failed"
    finally:
        await app.stop()


async def test_an_engine_crash_mid_session(service):
    svc = service(FakeEngine(TEXT, fail_on_accept=True), source=[CHUNK])
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await rec.wait(lambda r: r.states()[-1] == "failed")
        assert last_state(rec).reason == "engine_failed" and rec.of(InputReceived) == []
        assert (await app.router.send(StartListening())).is_ok  # the next click works
    finally:
        await app.stop()


async def test_a_bad_message_changes_nothing(service):
    svc = service(source=[CHUNK] * 6)
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await Probe.last._session.ws.send("not json")  # the service answers error bad_message
        await rec.wait(has_text(TEXT))
        assert rec.states() == ["starting", "listening"]
        assert (await app.router.send(StopListening())).value["text"] == TEXT
    finally:
        await app.stop()


async def test_permission_denied():
    class Deny:
        def has(self, name: str) -> bool:
            return False

        async def request(self, name: str, reason: str = "") -> bool:
            return False

    class Denied(VoiceInModule):
        async def init(self, ctx) -> None:
            ctx.permissions = Deny()
            await super().init(ctx)

    app, rec = await start_app(free_port(), module=Denied)
    try:
        result = await app.router.send(StartListening())
        assert result.status is Status.FAILED and "not allowed" in result.error
        assert rec.states() == ["starting", "failed"] and last_state(rec).reason == "not_allowed"
    finally:
        await app.stop()


# --- the service's lifecycle ---


async def test_a_service_you_started_is_used_and_left_running(service):
    svc = service(source=[CHUNK] * 2)
    app, rec = await start_app(svc.port)
    await app.router.send(StartListening())
    await app.stop()  # aborts the open session: nothing to the Talker
    assert rec.states()[-1] == "idle" and last_state(rec).reason == "service_stopped"
    assert rec.of(InputReceived) == []
    assert not Probe.last._app.launched
    assert (await Probe.last._app.call("GET", "/health"))["app"] == "voice_service"  # still running


async def test_a_service_that_cannot_launch(service):
    app, rec = await start_app(free_port())
    try:
        Probe.last._app.module = "no_such_voice_service_module"  # python -m exits with 1
        result = await app.router.send(StartListening())
        assert (result.status, result.retryable) == (Status.NOT_AVAILABLE, True)
        assert (last_state(rec).reason, last_state(rec).detail) == ("service_unavailable", "voice service didn't start")
    finally:
        await app.stop()


async def test_a_service_that_never_answers(tmp_path, monkeypatch):
    (tmp_path / "sleepy_voice_service.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    app, rec = await start_app(free_port(), start_timeout=0.5)
    try:
        Probe.last._app.module = "sleepy_voice_service"
        result = await app.router.send(StartListening())
        assert result.status is Status.NOT_AVAILABLE
        assert (last_state(rec).reason, last_state(rec).detail) == ("service_unavailable", "voice service didn't answer")
    finally:
        await app.stop()  # kills the process it launched


async def test_a_service_that_dies_mid_session(service):
    svc = service(source=[CHUNK] * 2)
    app, rec = await start_app(svc.port)
    try:
        await app.router.send(StartListening())
        await rec.wait(lambda r: r.states()[-1] == "listening")
        svc.close()
        await rec.wait(lambda r: r.states()[-1] == "failed", timeout=10)
        assert last_state(rec).reason == "service_stopped" and rec.of(InputReceived) == []
    finally:
        await app.stop()


class StubService:
    """Stands in for CompanionApp: its one ping (`/health`) answers `health`, or fails with it."""

    def __init__(self, launched: bool, health) -> None:
        self.launched_now, self.health, self.calls, self.url = launched, health, [], "http://stub"
        self.last_answer: dict = {}

    async def ensure_running(self) -> bool:
        self.calls.append("ensure_running")
        if isinstance(self.health, Exception):
            raise self.health  # not answering and not starting
        self.last_answer = self.health
        return self.launched_now

    async def call(self, method, path, body=None, *, timeout=10):
        self.calls.append(f"{method} {path}")
        return {}

    async def stop(self) -> None:
        pass


@pytest.mark.parametrize(
    ("launched", "health", "reason"),
    [
        (True, {"app": "voice_service", "ready": True}, "service_unavailable"),  # launched now; no socket
        (False, {"app": "voice_service", "ready": False, "error": "no model"}, "engine_failed"),
        (False, OSError("gone"), "service_unavailable"),
    ],
)
async def test_the_one_ping_decides_and_health_is_not_called_twice(launched, health, reason):
    app, rec = await start_app(free_port())
    try:
        stub = StubService(launched, health)
        Probe.last._app = stub
        Probe.last._url = f"ws://127.0.0.1:{free_port()}/ws/listen"  # nothing listens: connecting fails
        result = await app.router.send(StartListening())
        assert not result.is_ok and stub.calls == ["ensure_running"] and last_state(rec).reason == reason
    finally:
        await app.stop()


# --- the boundary ---


def test_voice_in_imports_only_the_protocol_from_the_service():
    folder = Path(sys.modules[VoiceInModule.__module__].__file__).parent
    imported = set()
    for file in folder.glob("*.py"):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
    assert {m for m in imported if m.split(".")[0] == "voice_service"} == {"voice_service.protocol"}


async def test_a_reload_keeps_the_voice_app_and_leaves_the_chat_alone(service):
    from assistant.contracts import ReloadModule
    from assistant.modules.temp_ui import TempUIModule

    svc = service(source=[CHUNK] * 2)
    voice = {"host": "127.0.0.1", "port": svc.port, "reply_timeout": 3.0}
    config = {"modules": {"enabled": ["voice_in", "temp_ui"], "voice_in": voice,
                          "temp_ui": {"port": 0, "window": "none"}}, "core": {}}  # fmt: skip
    app = App([VoiceInModule, TempUIModule], config)
    await app.start()
    try:
        old, ui = app._lifecycle._active["voice_in"][0], app._lifecycle._active["temp_ui"][0]
        await wait_until(lambda: ui._voice["available"])
        result = await app.router.send(ReloadModule(module_id="voice_in"))
        assert result.is_ok, result.error
        new = app._lifecycle._active["voice_in"][0]
        assert new is not old and type(new) is not VoiceInModule  # fresh code
        assert new._app is old._app  # the same voice app, not quit
        assert app._lifecycle._active["temp_ui"][0] is ui  # the chat window wasn't touched
        await wait_until(lambda: ui._voice["available"])
        assert (await app.router.send(StartListening())).is_ok  # the new code listens
        assert (await app.router.send(StopListening())).is_ok
    finally:
        await app.stop()


# --- text on send (an engine without live text, or live_text = false) ---


class _SlowFinish:
    """A fake stream whose final takes `delay` seconds, like whisper decoding at the stop."""

    def __init__(self, inner, delay: float) -> None:
        self._inner, self._delay = inner, delay

    def accept(self, pcm: bytes) -> None:
        self._inner.accept(pcm)

    def partial(self) -> str:
        return self._inner.partial()

    def finish(self) -> str:
        time.sleep(self._delay)
        return self._inner.finish()


class OnSendEngine(FakeEngine):
    live_partials = False

    def __init__(self, *args, delay: float = 0.0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.delay = delay

    def new_stream(self):
        return _SlowFinish(super().new_stream(), self.delay)


async def test_live_text_off_sends_only_the_final_and_says_so(service):
    import asyncio

    svc = service(source=[CHUNK] * 6)  # a live engine, but voice_in asks for the text on send
    app, rec = await start_app(svc.port, live_text=False)
    try:
        assert (await app.router.send(StartListening())).is_ok
        assert last_state(rec).state.value == "listening"
        assert last_state(rec).detail == "text appears when you stop"
        await asyncio.sleep(0.2)
        assert (await app.router.send(StopListening())).value["text"] == TEXT
        await rec.wait(lambda r: r.of(InputReceived))
        assert [(t.text, t.final) for t in rec.of(VoiceTranscript)] == [(TEXT, True)]
    finally:
        await app.stop()


async def test_an_on_send_engine_gets_the_longer_final_wait(service):
    svc = service(OnSendEngine(TEXT, delay=1.0), source=[CHUNK] * 6)
    app, rec = await start_app(svc.port, reply_timeout=0.5, final_timeout_on_send=5)
    try:
        assert (await app.router.send(StartListening())).is_ok
        assert last_state(rec).detail == "text appears when you stop"  # the engine has no live text
        import asyncio

        await asyncio.sleep(0.2)  # let the six chunks arrive
        result = await app.router.send(StopListening())  # 1 s of decoding: past reply_timeout, within the on-send wait
        assert result.is_ok and result.value["text"] == TEXT
        assert [t.final for t in rec.of(VoiceTranscript)] == [True]
    finally:
        await app.stop()


# --- two passes: the final engine cleans the line piece by piece ---

FAST_PIECES = {"pause_seconds": 0.1, "min_seconds": 0.3, "max_seconds": 1.0, "cut_search_seconds": 0.2}


async def test_two_passes_settle_the_line_and_send_the_cleaned_text(service):
    import asyncio

    from tests.test_voice_pieces import TALK, LiveEngine, PieceEngine

    final = PieceEngine(slow={2}, slow_seconds=1.0)  # the last piece takes 1 s: past reply_timeout
    svc = service(LiveEngine(), source=TALK, final=final, pieces=FAST_PIECES)
    app, rec = await start_app(svc.port, reply_timeout=0.5, final_timeout_on_send=5)
    try:
        assert (await app.router.send(StartListening())).is_ok
        await rec.wait(lambda r: any(t.settled_chars for t in r.of(VoiceTranscript)))
        await asyncio.sleep(0.3)  # the rest of the talk arrives
        result = await app.router.send(StopListening())
        assert result.is_ok and result.value["text"] == "Piece0. Piece1. Piece2."
        await rec.wait(lambda r: r.of(InputReceived) and r.states()[-1] == "idle")
        assert rec.states() == ["starting", "listening", "finishing", "idle"]
        assert next(s for s in rec.of(VoiceState) if s.state.value == "finishing").detail == "cleaning up…"
        assert [i.text for i in rec.of(InputReceived)] == ["Piece0. Piece1. Piece2."]
        first = next(t for t in rec.of(VoiceTranscript) if t.settled_chars)
        assert first.text.startswith("Piece0.") and first.settled_chars == len("Piece0.") and not first.final
    finally:
        await app.stop()


async def test_a_failed_piece_keeps_its_live_words_in_the_sent_text(service, caplog):
    import asyncio

    from tests.test_voice_pieces import TALK, LiveEngine, PieceEngine

    svc = service(LiveEngine(), source=TALK, final=PieceEngine(fail={1}), pieces=FAST_PIECES)
    app, rec = await start_app(svc.port)
    try:
        assert (await app.router.send(StartListening())).is_ok
        await rec.wait(lambda r: any(t.settled_chars for t in r.of(VoiceTranscript)))
        await asyncio.sleep(0.3)  # the rest of the talk arrives (every partial after piece 0 is settled too)
        result = await app.router.send(StopListening())
        middle = " ".join(f"w{i}" for i in range(8, 16))  # piece 1's live words
        assert result.value["text"] == f"Piece0. {middle} Piece2."
        assert "kept its live words (failed)" in caplog.text
    finally:
        await app.stop()


async def test_without_websockets_init_names_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "websockets.asyncio.client", None)
    with pytest.raises(RuntimeError, match=r"pip install -e \.\[voice\]"):
        await VoiceInModule().init(None)
