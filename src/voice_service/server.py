"""The voice service's FastAPI app: `GET /health`, `POST /quit`, and `WS /ws/listen`.

One listener at a time (the slot). Spec: docs/architecture/voice.md#the-protocol and
#the-voice-service-errors.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .audio import AudioSource
from .config import ServiceConfig
from .engines import SttEngine
from .protocol import Error, ErrorCode, Final, ProtocolError, ServiceMessage, Start, Started, dump, parse_client_message
from .session import DONE, EngineLoader, ListenSession

log = logging.getLogger("voice_service.server")

APP_NAME = "voice_service"  # what /health answers as "app": CompanionApp's ping check


class _Slot:
    session: ListenSession | None = None


def create_app(config: ServiceConfig, engine: SttEngine, source_factory: Callable[[], AudioSource]) -> FastAPI:
    """The service's app. `engine` is loaded in the background at startup; `source_factory` makes each session's source.

    Set `app.state.on_quit` to what ends the server (`__main__` sets Uvicorn's `should_exit`).
    """
    loader = EngineLoader(engine)
    slot = _Slot()

    async def abort_current() -> None:
        session, slot.session = slot.session, None
        if session is not None:
            await asyncio.to_thread(session.abort)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        threading.Thread(target=loader.load, name="voice-model-load", daemon=True).start()
        yield
        await abort_current()

    app = FastAPI(title="voice_service", lifespan=lifespan)
    app.state.on_quit = lambda: None
    app.state.loader = loader

    @app.get("/health")
    async def health() -> dict:
        return {"app": APP_NAME, "engine": engine.name, "ready": loader.ready, "error": loader.error}

    @app.post("/quit")
    async def quit_service() -> dict:
        log.info("quit requested")
        await abort_current()
        app.state.on_quit()
        return {"ok": True}

    @app.websocket("/ws/listen")
    async def listen(ws: WebSocket) -> None:
        await ws.accept()
        session: ListenSession | None = None
        forwarder: asyncio.Task | None = None

        async def send(message: ServiceMessage) -> None:
            await ws.send_text(dump(message))

        async def forward(s: ListenSession) -> None:
            try:
                while (item := await s.outbox.get()) is not DONE:
                    if isinstance(item, Final | Error) and slot.session is s:
                        slot.session = None  # free the slot before the client hears the session is over
                    await send(item)
            except Exception as exc:  # the client went away mid-send
                log.debug("forwarding stopped: %s", exc)
            finally:
                if slot.session is s:
                    slot.session = None

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    message = parse_client_message(raw)
                except ProtocolError as exc:
                    await send(Error(reason=ErrorCode.BAD_MESSAGE, detail=str(exc)))
                    continue
                active = forwarder is not None and not forwarder.done()
                # Listening: this connection's session holds the slot (it's freed as soon as the session ends itself).
                listening = active and session is not None and slot.session is session
                if isinstance(message, Start):
                    if listening and not session.stopping:
                        await send(Started())  # already listening on this connection
                        continue
                    if active:
                        await forwarder  # this connection's last session is finishing
                    if slot.session is not None:
                        await send(Error(reason=ErrorCode.BUSY, detail="another app is listening"))
                        continue
                    if loader.error:
                        await send(Error(reason=ErrorCode.ENGINE_FAILED, detail=loader.error))
                        continue
                    session = ListenSession(loader, source_factory, config, asyncio.get_running_loop())
                    slot.session = session
                    try:
                        await asyncio.to_thread(session.start)
                    except Exception as exc:
                        slot.session, session = None, None
                        log.warning("mic unavailable: %s", exc)
                        await send(Error(reason=ErrorCode.MIC_UNAVAILABLE, detail=str(exc)))
                        continue
                    await send(Started())
                    forwarder = asyncio.create_task(forward(session))
                elif not listening or session is None:
                    await send(Final(text="", latency_ms=0))  # stop with nothing listening
                else:
                    await asyncio.to_thread(session.stop)  # the forwarder sends the final
        except WebSocketDisconnect:
            log.info("client disconnected")
        finally:
            if forwarder is not None and not forwarder.done() and session is not None:
                if slot.session is session:
                    slot.session = None
                await asyncio.to_thread(session.abort)
                forwarder.cancel()

    return app
