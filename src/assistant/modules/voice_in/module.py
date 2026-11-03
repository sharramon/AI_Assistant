"""Voice input's handle in the app: the thin module in front of the voice service.

The voice service is its own app (`src/voice_service`, run alone with `python -m voice_service`).
This module imports nothing from it but `protocol`. It launches the service on the first mic
click (through `CompanionApp`), opens one WebSocket per mic session, and relays:
`StartListening` / `StopListening` in; `VoiceState` / `VoiceTranscript` out; and, with
`send_as_input`, the final text to the Talker as `InputReceived(source="voice")`.
Design: docs/architecture/voice.md#the-voice_in-module.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app_kit import CompanionApp
from assistant.contracts import (
    InputReceived,
    ListeningState,
    Manifest,
    Module,
    ModuleContext,
    Result,
    StartListening,
    Status,
    StopListening,
    VoiceState,
    VoiceTranscript,
)
from voice_service.protocol import (
    Error,
    ErrorCode,
    Final,
    MicBack,
    MicDropped,
    Partial,
    ProtocolError,
    Start,
    Started,
    Stop,
    dump,
    parse_service_message,
)

SERVICE = "voice_service"  # the package `python -m` runs, and the name its /health answers with


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
    ws: Any = None
    reader: asyncio.Task | None = None
    ended: bool = False
    result: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())


class VoiceInModule(Module):
    manifest = Manifest(id="voice_in", optional_permissions=("microphone",))

    async def init(self, ctx: ModuleContext) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise RuntimeError("voice_in needs the voice extra: pip install -e .[voice]") from exc
        self._connect = connect
        self._ctx = ctx
        host = ctx.config.get("host", "127.0.0.1")
        port = int(ctx.config.get("port", 8767))
        args = ["--host", host, "--port", str(port)]
        if ctx.config.get("service_config"):
            args += ["--config", str(ctx.config["service_config"])]
        self._app = CompanionApp(  # launched on the first click; quit at stop only if we launched it
            SERVICE, host, port, ping="/health", quit="/quit", args=args,
            start_timeout=float(ctx.config.get("start_timeout", 20.0)), log=ctx.log,
        )  # fmt: skip
        self._url = f"ws://{host}:{port}/ws/listen"
        self._reply_timeout = float(ctx.config.get("reply_timeout", 10.0))
        self._lock = asyncio.Lock()
        self._session: _Session | None = None
        ctx.handle(StartListening, self._start_listening)
        ctx.handle(StopListening, self._stop_listening)

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
        await self._app.stop()

    # --- the commands ---

    async def _start_listening(self, command: StartListening) -> Result:
        async with self._lock:
            if self._session is not None:  # already starting or listening: that session
                return Result.ok({"session_id": self._session.id})
            session = _Session(command.id, command.send_as_input)
            self._session = session
            self._state(session, ListeningState.STARTING)
            result = await self._open(session)
            if not result.is_ok and session.ws is not None:
                await self._close(session)
            return result

    async def _stop_listening(self, command: StopListening) -> Result:
        async with self._lock:
            session = self._session
            if session is None:
                return Result.ok(None)
            try:
                await session.ws.send(dump(Stop()))
            except Exception as exc:  # the socket closed: the reader ends the session
                self._ctx.log.debug("Couldn't send stop: %s", exc)
        try:
            return await asyncio.wait_for(asyncio.shield(session.result), self._reply_timeout)
        except TimeoutError:
            result = Result.failed("the voice service didn't send the final text", retryable=True)
            self._end(session, ListeningState.FAILED, "timed_out", "voice service didn't answer", result)
            if session.reader is not None:
                session.reader.cancel()
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
            await session.ws.send(dump(Start()))
            reply = parse_service_message(await asyncio.wait_for(session.ws.recv(), self._reply_timeout))
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
        self._state(session, ListeningState.LISTENING)
        session.reader = asyncio.create_task(self._read(session), name="voice_in:reader")
        log.info("Voice session %s started", session.id)
        return Result.ok({"session_id": session.id})

    async def _ensure_service(self) -> str | None:
        """Launch the service if it isn't running. A running one we reuse gets a quick `/health` check first.

        Returns the model's load error, if `/health` reports one. Raises `OSError` or `TimeoutError`
        if the service can't be started.
        """
        if await self._app.ensure_running():
            return None  # launched just now: CompanionApp has pinged it
        try:
            health = await self._app.call("GET", "/health", timeout=2)
        except (OSError, ValueError, TimeoutError):
            health = {}
        if health.get("app") != SERVICE:  # it went away since the ping: launch it again
            await self._app.ensure_running()
            return None
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
                    self._ctx.publish(VoiceTranscript(session_id=session.id, text=message.text, correlation_id=session.id))
                elif isinstance(message, MicDropped):
                    log.warning("The mic dropped (%s); waiting %.0f s for it", message.detail, message.wait_seconds)
                    self._state(session, ListeningState.DROPPED, "mic_dropped",
                                f"mic dropped, waiting {message.wait_seconds:.0f} s for it to come back")  # fmt: skip
                elif isinstance(message, MicBack):
                    log.info("The mic is back")
                    self._state(session, ListeningState.LISTENING)
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

    def _finish(self, session: _Session, final: Final) -> None:
        log, text = self._ctx.log, final.text
        if not final.complete:  # the mic didn't come back (or you stopped while it was dropped): drop the text
            log.warning("Voice session %s: mic lost; dropped %d chars", session.id, len(text))
            self._ctx.publish(VoiceTranscript(session_id=session.id, text="", final=True, correlation_id=session.id))
            self._fail(session, ErrorCode.MIC_LOST, "mic disconnected; what you said was dropped",
                       Result.failed("the mic was lost; the text was dropped"))  # fmt: skip
            return
        log.info("Voice session %s: %d chars, %d ms after the stop, ended by %s",
                 session.id, len(text), final.latency_ms, final.ended_by)  # fmt: skip
        self._ctx.publish(VoiceTranscript(session_id=session.id, text=text, final=True, correlation_id=session.id))
        if text and session.send_as_input:
            self._ctx.publish(InputReceived(text=text, source="voice"))
        silence = final.ended_by == "silence"
        self._end(session, ListeningState.IDLE, "silence" if silence else None,
                  "mic turned off after a long silence" if silence else None,
                  Result.ok({"text": text, "latency_ms": final.latency_ms}))  # fmt: skip

    # --- ending a session ---

    def _state(self, session: _Session, state: ListeningState, reason: str | None = None, detail: str | None = None) -> None:
        self._ctx.publish(VoiceState(state=state, reason=reason, detail=detail, correlation_id=session.id))

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
