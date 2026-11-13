"""The voice service's FastAPI app: `GET /health`, `POST /quit` (JSON only), and `WS /ws/listen`.

Every request must be addressed to this machine and, from a browser, come from its own origin
(`LocalOnly`, using app_kit.local_guard).

One listener at a time (the slot). With `config_path`, it watches that config file (and its
`.local` override): when the `[engine]` section changes, it waits until nothing is listening and
quits through `on_quit`, the same path as `/quit`; the next client relaunches it with the new
engine. A `[pieces]` change applies to the next session without a restart. Spec:
src/assistant/modules/voice_in/docs/voice-service.md#the-protocol, #the-voice-service-errors and #hot-swappable-engines.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.websockets import WebSocketClose

from app_kit import local_path, local_request

from .audio import AudioSource
from .config import ServiceConfig, load_service_config
from .engines import SttEngine
from .protocol import Error, ErrorCode, Final, ProtocolError, ServiceMessage, Start, Started, dump, parse_client_message
from .session import DONE, EngineLoader, ListenSession

log = logging.getLogger("voice_service.server")

APP_NAME = "voice_service"  # what /health answers as "app": CompanionApp's ping check


class _Slot:
    session: ListenSession | None = None


class LocalOnly:
    """ASGI guard: refuses requests and WebSockets addressed to another host or opened by a page
    from another origin (app_kit.local_guard), so a web page you visit can't open the mic or quit
    the service."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            if not local_request(headers.get("host"), headers.get("origin")):
                log.warning("refused a %s request from host %r, origin %r",
                            scope["type"], headers.get("host"), headers.get("origin"))  # fmt: skip
                if scope["type"] == "websocket":
                    await WebSocketClose(code=1008)(scope, receive, send)
                else:
                    await PlainTextResponse("Forbidden", status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _stamp(files: tuple[Path, ...]) -> tuple[int | None, ...]:
    """Each file's modification time, None if it's missing."""
    out: list[int | None] = []
    for f in files:
        try:
            out.append(f.stat().st_mtime_ns)
        except OSError:
            out.append(None)
    return tuple(out)


def create_app(
    config: ServiceConfig,
    engine: SttEngine,
    source_factory: Callable[[], AudioSource],
    *,
    final_engine: SttEngine | None = None,
    config_path: str | Path | None = None,
    watch_seconds: float = 2.0,
) -> FastAPI:
    """The service's app. `engine` (the live engine) and `final_engine` are loaded in the background
    at startup; `source_factory` makes each session's source.

    `final_engine` (two passes): cleans each piece of the live audio. Ignored, with a log line, if
    `engine` gives no live text. If it fails to load, sessions run on `engine` alone.

    `config_path`: the file `config` came from, watched every `watch_seconds` for an engine change
    (None: not watched). Set `app.state.on_quit` to what ends the server (`__main__` sets Uvicorn's
    `should_exit`).
    """
    if final_engine is not None and not engine.live_partials:
        log.warning("the %s engine gives no live text, so it can't be the live engine: running it alone", engine.name)
        final_engine = None
    loader = EngineLoader(engine)
    final_loader = EngineLoader(final_engine) if final_engine is not None else None
    slot = _Slot()

    async def abort_current() -> None:
        session, slot.session = slot.session, None
        if session is not None:
            await asyncio.to_thread(session.abort)

    async def watch_engine(path: Path) -> None:
        """Quit when the config's `[engine]` section differs from the running one, once nothing is listening."""
        files = (path, local_path(path))
        seen, changed = _stamp(files), None
        while True:
            await asyncio.sleep(watch_seconds)
            stamp = _stamp(files)
            if stamp != seen:
                seen = stamp
                try:
                    new = await asyncio.to_thread(load_service_config, path)
                except Exception as exc:  # a half-saved or broken file: keep running, look again on the next save
                    log.warning("the config changed but can't be read: %s", exc)
                    continue
                if new.pieces != config.pieces:
                    log.info("[pieces] changed: the next session uses %s", new.pieces)
                    config.pieces = new.pieces
                changed = new.engine if new.engine != config.engine else None
                if changed is not None and slot.session is not None:
                    log.info("engine config changed; restarting once the current session ends")
            if changed is not None and slot.session is None:
                log.info("engine changed: %s → %s; restarting", config.engine.name, changed.name)
                app.state.on_quit()
                return

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        threading.Thread(target=loader.load, name="voice-model-load", daemon=True).start()
        if final_loader is not None:
            threading.Thread(target=final_loader.load, name="voice-final-load", daemon=True).start()
        watcher = asyncio.create_task(watch_engine(Path(config_path))) if config_path is not None else None
        yield
        if watcher is not None:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        await abort_current()

    app = FastAPI(title="voice_service", lifespan=lifespan)
    app.add_middleware(LocalOnly)
    app.state.on_quit = lambda: None
    app.state.loader = loader
    app.state.final_loader = final_loader

    @app.get("/health")
    async def health() -> dict:
        return {
            "app": APP_NAME,
            "engine": engine.name,
            "ready": loader.ready,
            "error": loader.error,
            "final": final_engine.name if final_engine is not None else "",
            "final_ready": final_loader.ready if final_loader is not None else False,
            "final_error": final_loader.error if final_loader is not None else None,
        }

    @app.post("/quit")
    async def quit_service(request: Request):
        # JSON only: a web page can't send it here without the browser asking first (CORS).
        if not request.headers.get("content-type", "").startswith("application/json"):
            return JSONResponse({"ok": False, "error": "JSON only"}, status_code=415)
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

        def started(s: ListenSession) -> Started:
            return Started(partials=s.partials, clean_pieces=s.clean_pieces)

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
                        await send(started(session))  # already listening on this connection
                        continue
                    if active:
                        await forwarder  # this connection's last session is finishing
                    if slot.session is not None:
                        await send(Error(reason=ErrorCode.BUSY, detail="another app is listening"))
                        continue
                    if loader.error:
                        await send(Error(reason=ErrorCode.ENGINE_FAILED, detail=loader.error))
                        continue
                    session = ListenSession(
                        loader, source_factory, config, asyncio.get_running_loop(),
                        partials=message.partials, final_loader=final_loader,
                    )  # fmt: skip
                    slot.session = session
                    try:
                        await asyncio.to_thread(session.start)
                    except Exception as exc:
                        slot.session, session = None, None
                        log.warning("mic unavailable: %s", exc)
                        await send(Error(reason=ErrorCode.MIC_UNAVAILABLE, detail=str(exc)))
                        continue
                    await send(started(session))
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
