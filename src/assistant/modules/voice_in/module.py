"""Voice input's handle in the app: the thin module in front of the voice service.

The voice service is its own app (`app/voice_service` in this module's folder, which the core puts
on the import path; run it alone with `python -m voice_service` and that folder on `PYTHONPATH`).
This module imports nothing from it but `protocol`. It launches the service on the first mic
click (through `CompanionApp`), opens one WebSocket per mic session, and relays:
`StartListening` / `StopListening` in; `VoiceState` / `VoiceTranscript` out; and, with
`send_as_input`, the final text to the Talker as `InputReceived(source="voice")`.
`StopListening(discard=True)` (the clear button) closes the socket instead and sends nothing.
One session at a time, and the second press wins: a `StartListening` while one is open ends that
one the same way (`VoiceState(idle, reason="taken_over")`, an empty final), then starts.
`live_text = false` asks the service for the text on send only, even with a live engine; an engine
without live text (whisper) is on send anyway, and the final then gets `final_timeout_on_send`.
Two passes (`started.clean_pieces`): `cleaned` settles pieces of the line (`LiveLine`), `refining`
after stop is `FINISHING`, and the final's parts are cleaned one by one and joined; the stop
then waits `final_timeout_on_send` too.
Design: src/assistant/modules/voice_in/docs/voice-service.md#the-voice_in-module.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app_kit import CompanionHandover
from assistant.contracts import (
    InputReceived,
    IVoice,
    ListeningState,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    Result,
    StartListening,
    Status,
    StopListening,
    VoiceDestination,
    VoiceState,
    VoiceTranscript,
)
from voice_service.protocol import (
    Cleaned,
    Error,
    ErrorCode,
    Final,
    MicBack,
    MicDropped,
    Partial,
    ProtocolError,
    Refining,
    Start,
    Started,
    Stop,
    dump,
    parse_service_message,
)

from .line import LiveLine, Segment, render

SERVICE = "voice_service"  # the package `python -m` runs, and the name its /health answers with
CLEAR_RETRY_WINDOW = 2.0  # s after a clear in which a `busy` start is the old session still closing
CLEAR_RETRY_WAIT = 0.3  # s to wait before that one retry
TAKEN_OVER = "taken_over"  # VoiceState reason: a second StartListening ended this session (the second press wins)


def _unavailable(error: str) -> Result:
    return Result(status=Status.NOT_AVAILABLE, error=error, retryable=True)


# The service's error codes when they answer `start`: the button's sentence, and the command's result.
_START_ERRORS: dict[ErrorCode, tuple[str, Any]] = {
    ErrorCode.BUSY: ("another app is using the mic", Result.failed),
    ErrorCode.MIC_UNAVAILABLE: ("no microphone (or blocked in Windows settings)", _unavailable),
    ErrorCode.ENGINE_FAILED: ("speech model not installed", _unavailable),
}


@dataclass(eq=False)
class _Session:
    """One mic session: from `StartListening` to its final, failure, or abort."""

    id: str  # the StartListening command's id: every event's correlation_id
    send_as_input: bool
    agent_id: str | None = None  # the tab the stop was pressed in: where the final goes (None: the focus)
    ws: Any = None
    reader: asyncio.Task | None = None
    ended: bool = False
    partials: bool = True  # live text while you talk; False: the text comes when you stop
    clean_pieces: bool = False  # two passes: the final engine cleans the line piece by piece
    line: LiveLine = field(default_factory=LiveLine)
    result: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())


class _Voice(IVoice):
    """voice_in's `IVoice` part: the same sessions as the commands, each ended only by its id."""

    def __init__(self, module: VoiceInModule) -> None:
        self._module = module

    async def listen(self, session_id: str, destination: VoiceDestination = VoiceDestination.CALLER) -> Result:
        return await self._module._begin(session_id, VoiceDestination(destination) is VoiceDestination.TALKER)

    async def finish(self, session_id: str, discard: bool = False) -> Result:
        return await self._module._finish_session(session_id, discard)


class VoiceInModule(ModuleProtocol):
    manifest = Manifest(
        id="voice_in",
        description="Speech to text; launches the voice service app",
        provides=(IVoice,),
        optional_permissions=("microphone",),
        handles=(StartListening, StopListening,),
        publishes=(VoiceState, VoiceTranscript, InputReceived,),
    )

    async def init(self, ctx: ModuleContext) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise RuntimeError("voice_in needs its packages: " + "pip install the packages in voice_in's module.toml") from exc
        self._connect = connect
        self._ctx = ctx
        host = ctx.config.get("host", "127.0.0.1")
        port = int(ctx.config.get("port", 8767))
        args = ["--host", host, "--port", str(port)]
        if ctx.config.get("service_config"):
            args += ["--config", str(ctx.config["service_config"])]
        # A reload hands over the running voice app, so it isn't quit and its model isn't reloaded.
        # Only if it would be launched the same way; otherwise the old one was quit by the old copy.
        # Launched on the first click; quit at stop only if we launched it.
        self._companion = CompanionHandover(
            ctx.handover, SERVICE, host, port, args=args, label="voice service", log=ctx.log,
            ping="/health", quit="/quit", start_timeout=float(ctx.config.get("start_timeout", 20.0)),
        )  # fmt: skip
        self._app = self._companion.app
        self._url = f"ws://{host}:{port}/ws/listen"
        self._reply_timeout = float(ctx.config.get("reply_timeout", 10.0))
        self._live_text = bool(ctx.config.get("live_text", True))  # False: text on send, even with a live engine
        self._final_wait_on_send = float(ctx.config.get("final_timeout_on_send", 90.0))  # the engine decodes it all at the stop
        self._cleanup = bool(ctx.config.get("cleanup", True))  # sentence case for the engine's all-caps text
        self._terms = tuple(str(t) for t in ctx.config.get("terms", ()))
        self._lock = asyncio.Lock()
        self._session: _Session | None = None
        self._cleared_at = float("-inf")  # time.monotonic() of the last clear
        ctx.handle(StartListening, self._start_listening)
        ctx.handle(StopListening, self._stop_listening)
        ctx.provide(IVoice, _Voice(self))

    async def start(self) -> None:
        pass  # nothing to launch until the first click

    async def stop(self) -> None:
        session = self._session
        if session is not None:  # abort: close the socket, nothing to the Talker
            self._end(session, ListeningState.IDLE, "service_stopped", "voice input stopped",
                      Result.failed("voice input stopped"))  # fmt: skip
            if session.reader is not None:
                session.reader.cancel()
                await asyncio.gather(session.reader, return_exceptions=True)
            elif session.ws is not None:
                await self._close(session)
        await self._companion.stop()

    def export_state(self) -> dict | None:
        """For a reload: the voice app (an `app_kit` object, not reloaded) goes to the new copy,
        unless the voice service's own code changed: then `stop` quits it (even one it found
        running) and the new copy launches the new code on the first click (`CompanionHandover`).
        An open mic session still ends at `stop`, and its words are dropped."""
        return self._companion.export()

    # --- the commands ---

    async def _start_listening(self, command: StartListening) -> Result:
        return await self._begin(command.id, command.send_as_input)

    async def _stop_listening(self, command: StopListening) -> Result:
        return await self._finish_session(None, command.discard, command.agent_id)

    async def _begin(self, session_id: str, send_as_input: bool) -> Result:
        """Open a session (the command, or `IVoice.listen`)."""
        async with self._lock:
            if self._session is not None:  # the second press wins: end the open session, nothing sent from it
                await self._discard(self._session, TAKEN_OVER, "another part of the app took the mic")
            session = _Session(session_id, send_as_input)
            self._session = session
            self._state(session, ListeningState.STARTING)
            result = await self._open(session)
            if not result.is_ok and session.ws is not None:
                await self._close(session)
            return result

    async def _finish_session(self, session_id: str | None, discard: bool, agent_id: str | None = None) -> Result:
        """End the open session (`StopListening`), or only the one called `session_id` (`IVoice.finish`).
        `agent_id`: the tab the stop was pressed in; the final goes there."""
        async with self._lock:
            session = self._session
            if session_id is not None and (session is None or session.id != session_id):
                return Result.ok({"text": "", "ended": True})  # that session is over; another one is never touched
            if session is None:
                return Result.ok(None)
            if discard:
                return await self._discard(session)
            if agent_id:
                session.agent_id = agent_id
            try:
                await session.ws.send(dump(Stop()))
            except Exception as exc:  # the socket closed: the reader ends the session
                self._ctx.log.debug("Couldn't send stop: %s", exc)
        wait = self._reply_timeout if session.partials and not session.clean_pieces else self._final_wait_on_send
        try:
            return await asyncio.wait_for(asyncio.shield(session.result), wait)
        except TimeoutError:
            result = Result.failed("the voice service didn't send the final text", retryable=True)
            self._end(session, ListeningState.FAILED, "timed_out", "voice service didn't answer", result)
            if session.reader is not None:
                session.reader.cancel()
            return result

    async def _discard(self, session: _Session, reason: str = "cleared", detail: str = "cleared") -> Result:
        """The clear button, or a second start taking the mic (`taken_over`): close the socket (the
        service aborts: no final), send nothing anywhere. Ending the session first means a final that
        still arrives is ignored."""
        result = Result.ok({"text": "", "taken_over" if reason == TAKEN_OVER else "discarded": True})
        self._ctx.publish(VoiceTranscript(session_id=session.id, text="", final=True, correlation_id=session.id))
        self._end(session, ListeningState.IDLE, reason, detail, result)
        self._cleared_at = time.monotonic()
        if session.reader is not None:
            session.reader.cancel()  # its finally closes the socket
            await asyncio.gather(session.reader, return_exceptions=True)
        else:
            await self._close(session)
        self._ctx.log.info("Voice session %s %s; nothing was sent", session.id, reason)
        return result

    # --- opening a session ---

    async def _open(self, session: _Session) -> Result:
        log = self._ctx.log
        if not await self._ctx.permissions.request("microphone", reason="You clicked the mic"):
            return self._fail(session, "not_allowed", "microphone not allowed", Result.failed("microphone not allowed"))
        try:
            model_error = await self._ensure_service()
        except TimeoutError:  # before OSError: TimeoutError is one
            log.warning("The voice service didn't answer %s/health", self._app.url)
            return self._fail(session, "service_unavailable", "voice service didn't answer",
                              _unavailable("the voice service didn't answer"))  # fmt: skip
        except OSError as exc:
            log.warning("The voice service didn't start (run `python -m voice_service` to see why): %s", exc)
            return self._fail(session, "service_unavailable", "voice service didn't start",
                              _unavailable(f"the voice service didn't start: {exc}"))  # fmt: skip
        if model_error:
            log.warning("The voice service's model isn't ready: %s", model_error)
            detail, make = _START_ERRORS[ErrorCode.ENGINE_FAILED]
            return self._fail(session, ErrorCode.ENGINE_FAILED, detail, make(model_error))
        try:
            session.ws = await asyncio.wait_for(self._connect(self._url), self._reply_timeout)
        except Exception as exc:
            log.warning("Couldn't connect to %s: %s", self._url, exc)
            return self._fail(session, "service_unavailable", "voice service didn't answer",
                              _unavailable(f"couldn't connect to the voice service: {exc}"))  # fmt: skip
        try:
            reply = await self._send_start(session)
            if isinstance(reply, Error) and reply.reason is ErrorCode.BUSY and self._just_cleared():
                log.info("The voice service hadn't freed the mic after the clear yet; trying once more")
                await asyncio.sleep(CLEAR_RETRY_WAIT)
                reply = await self._send_start(session)
        except TimeoutError:
            log.warning("The voice service didn't answer start within %.0f s", self._reply_timeout)
            return self._fail(session, "timed_out", "voice service didn't answer",
                              _unavailable("the voice service didn't answer start"))  # fmt: skip
        except Exception as exc:  # the socket closed, or a frame we can't read
            log.warning("The voice service broke off the start: %s", exc)
            return self._fail(session, "service_stopped", "voice service stopped",
                              _unavailable(f"the voice service stopped: {exc}"))  # fmt: skip
        if isinstance(reply, Error):
            log.warning("The voice service couldn't start listening: %s (%s)", reply.reason, reply.detail)
            detail, make = _START_ERRORS.get(reply.reason, ("voice input failed", Result.failed))
            return self._fail(session, reply.reason, detail, make(reply.detail or detail))
        if not isinstance(reply, Started):
            log.warning("The voice service answered start with %s", reply.type)
            return self._fail(session, "service_stopped", "voice service stopped",
                              Result.failed(f"unexpected reply: {reply.type}"))  # fmt: skip
        session.partials = reply.partials
        session.clean_pieces = reply.clean_pieces
        self._listening(session)
        session.reader = asyncio.create_task(self._read(session), name="voice_in:reader")
        log.info("Voice session %s started (%s%s)", session.id, "live text" if session.partials else "text on send",
                 ", cleaned piece by piece" if session.clean_pieces else "")  # fmt: skip
        return Result.ok({"session_id": session.id})

    async def _send_start(self, session: _Session):
        await session.ws.send(dump(Start(partials=self._live_text)))
        return parse_service_message(await asyncio.wait_for(session.ws.recv(), self._reply_timeout))

    def _just_cleared(self) -> bool:
        return time.monotonic() - self._cleared_at < CLEAR_RETRY_WINDOW

    async def _ensure_service(self) -> str | None:
        """Launch the service if it isn't running. A running one we reuse: its ping is `/health`,
        so the ping's answer (`last_answer`) says whether its model loaded; no second call.

        Returns the model's load error, if `/health` reports one. Raises `OSError` or `TimeoutError`
        if the service can't be started.
        """
        if await self._app.ensure_running():
            return None  # launched just now: CompanionApp has pinged it
        health = self._app.last_answer
        if not health.get("ready") and health.get("error"):
            return str(health["error"])
        return None  # ready, or the model is still loading (the service buffers the audio)

    # --- the session's frames ---

    async def _read(self, session: _Session) -> None:
        log = self._ctx.log
        try:
            async for raw in session.ws:
                try:
                    message = parse_service_message(raw)
                except ProtocolError as exc:
                    log.warning("Skipped a frame from the voice service: %s", exc)
                    continue
                if isinstance(message, Partial):
                    session.line.set_live(message.text)
                    self._publish_line(session)
                elif isinstance(message, Cleaned):
                    if message.fallback:
                        log.warning("Voice piece %d kept its live words (%s)", message.piece, message.fallback)
                    session.line.settle(message.start, message.end, message.text, message.fallback)
                    self._publish_line(session)
                elif isinstance(message, Refining):
                    if message.text:
                        session.line.set_live(message.text)
                        self._publish_line(session)
                    log.info("Voice session %s: cleaning up the last of %d pieces", session.id, message.pending)
                    self._state(session, ListeningState.FINISHING, detail="cleaning up…")
                elif isinstance(message, MicDropped):
                    log.warning("The mic dropped (%s); waiting %.0f s for it", message.detail, message.wait_seconds)
                    self._state(session, ListeningState.DROPPED, "mic_dropped",
                                f"mic dropped, waiting {message.wait_seconds:.0f} s for it to come back")  # fmt: skip
                elif isinstance(message, MicBack):
                    log.info("The mic is back")
                    self._listening(session)
                elif isinstance(message, Final):
                    self._finish(session, message)
                    return
                elif message.reason is ErrorCode.BAD_MESSAGE:
                    log.error("The voice service says we sent a bad message: %s", message.detail)
                else:
                    log.warning("Voice session failed: %s (%s)", message.reason, message.detail)
                    detail = "speech engine error" if message.reason is ErrorCode.ENGINE_FAILED else "voice input failed"
                    self._fail(session, message.reason, detail, Result.failed(message.detail or detail))
                    return
        except Exception as exc:  # the socket broke
            log.debug("The voice socket closed: %s", exc)
        finally:
            if not session.ended:
                log.warning("The voice service stopped mid-session")
                self._fail(session, "service_stopped", "voice service stopped",
                           Result.failed("the voice service stopped", retryable=True))  # fmt: skip
            await self._close(session)

    def _render(self, segments: list[Segment], final: bool) -> tuple[str, int]:
        return render(segments, self._terms, final=final, cleanup=self._cleanup)

    def _publish_line(self, session: _Session) -> None:
        text, settled = self._render(session.line.segments(), final=False)
        self._ctx.publish(VoiceTranscript(session_id=session.id, text=text, settled_chars=settled,
                                          correlation_id=session.id))  # fmt: skip

    def _finish(self, session: _Session, final: Final) -> None:
        log, raw = self._ctx.log, final.text
        if session.ended:  # cleared (or aborted) before the final came: it goes nowhere
            log.info("Voice session %s: a final came after the session ended; dropped %d chars", session.id, len(raw))
            return
        if not final.complete:  # the mic didn't come back (or you stopped while it was dropped): drop the text
            log.warning("Voice session %s: mic lost; dropped %d chars", session.id, len(raw))
            self._ctx.publish(VoiceTranscript(session_id=session.id, text="", final=True, correlation_id=session.id))
            self._fail(session, ErrorCode.MIC_LOST, "mic disconnected; what you said was dropped",
                       Result.failed("the mic was lost; the text was dropped"))  # fmt: skip
            return
        parts = final.parts  # two passes: one per piece; empty with one engine
        segments = [Segment(p.text) for p in parts] if parts else [Segment(raw)]
        text, _ = self._render(segments, final=True)
        log.info("Voice session %s: %d chars, %d ms after the stop, ended by %s",
                 session.id, len(text), final.latency_ms, final.ended_by)  # fmt: skip
        if parts:  # each piece and whether the final engine cleaned it, kept for accuracy comparisons
            log.info("Voice session %s parts: %s", session.id,
                     [(p.text, "cleaned" if p.cleaned else p.fallback) for p in parts])  # fmt: skip
        if raw:  # the engine's own text, kept for accuracy comparisons
            log.info("Voice session %s raw: %r -> clean: %r", session.id, raw, text)
        self._ctx.publish(VoiceTranscript(session_id=session.id, text=text, final=True, correlation_id=session.id))
        if text and session.send_as_input:
            self._ctx.publish(InputReceived(text=text, source="voice", agent_id=session.agent_id))
        silence = final.ended_by == "silence"
        self._end(session, ListeningState.IDLE, "silence" if silence else None,
                  "mic turned off after a long silence" if silence else None,
                  Result.ok({"text": text, "latency_ms": final.latency_ms}))  # fmt: skip

    # --- ending a session ---

    def _state(self, session: _Session, state: ListeningState, reason: str | None = None, detail: str | None = None) -> None:
        self._ctx.publish(VoiceState(state=state, reason=reason, detail=detail, correlation_id=session.id))

    def _listening(self, session: _Session) -> None:
        self._state(session, ListeningState.LISTENING, detail=None if session.partials else "text appears when you stop")

    def _fail(self, session: _Session, reason: str, detail: str, result: Result) -> Result:
        self._end(session, ListeningState.FAILED, str(reason), detail, result)
        return result

    def _end(self, session: _Session, state: ListeningState, reason: str | None, detail: str | None, result: Result) -> None:
        """The session is over: publish its last state and settle a waiting `StopListening`. Once only."""
        if session.ended:
            return
        session.ended = True
        if self._session is session:
            self._session = None
        self._state(session, state, reason, detail)
        if not session.result.done():
            session.result.set_result(result)

    async def _close(self, session: _Session) -> None:
        try:
            await session.ws.close()
        except Exception:
            pass
