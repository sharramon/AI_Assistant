"""Voice notes: speak into a page of notes you can edit and copy.

A small page in its own window (src/assistant/modules/voice_notes/docs/README.md): a blank notes area, Record / Stop,
a status line, and Copy; the page keeps the text in its local storage. While you speak, the
cleaned start of the live text (its `settled` characters) shows in the notes in normal type and
the not-yet-cleaned rest right after it, grey and italic; at Stop the final text replaces that
whole stretch.

It requires the voice contract (`IVoice`), so turning it on turns voice input on first. Record
calls `IVoice.listen(session_id, VoiceDestination.CALLER)` with an id it made, so the words go
only to this page, never to the Talker, and only its own sessions are followed. Stop calls
`IVoice.finish(session_id)`, which never ends another part's session. The provider is looked up
at each call, so a reload of `voice_in` is picked up. The second press wins: if another part of
the app (the temp UI's mic) takes the mic, this session ends with
`VoiceState(idle, reason="taken_over")`; the page says cancelled and drops those words.

Imports only `assistant.contracts` and `app_kit.window`.

Serves `page.html` on http://127.0.0.1:<port>/ (default 8770; standard library only):
- `GET /events`: Server-Sent Events: the `voice` item (state, detail, live text, settled) on connect
  and on each change, and a `final` item with each recording's text (empty: drop the stretch)
- `POST /record`: `{"on": true | false}` starts or stops a recording

The page server is copied, cut down, from the temp UI's for v1; a shared one comes with the refactor.
`window = "app"` opens it in its own Edge app window, `"browser"` a tab, `"none"` nothing.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import webbrowser
from pathlib import Path
from typing import Any
from uuid import uuid4

from app_kit.local_guard import local_request
from app_kit.window import close_app_windows, open_app_window, window_profile
from assistant.contracts import (
    IVoice,
    ListeningState,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    VoiceDestination,
    VoiceState,
    VoiceTranscript,
)

PAGE = Path(__file__).with_name("page.html")
TAKEN_OVER = "taken_over"  # VoiceState reason: another part of the app took the mic
ENDED = (ListeningState.IDLE, ListeningState.FAILED)


class VoiceNotesModule(ModuleProtocol):
    manifest = Manifest(
        id="voice_notes",
        description="Speak into a page of notes; the words never go to the Talker",
        requires=(IVoice,),
        listens=(VoiceState, VoiceTranscript,),
    )

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._host = ctx.config.get("host", "127.0.0.1")
        self._port = int(ctx.config.get("port", 8770))
        self._window = ctx.config.get("window", "app")
        self._profile = Path(ctx.config.get("window_profile", window_profile("voice_notes"))).resolve()
        self._edge: subprocess.Popen | None = None
        self._server: asyncio.Server | None = None
        self._connections: set[asyncio.Task] = set()
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._mine: set[str] = set()  # ids of the sessions this module opened
        self._session: str | None = None  # the followed session: the latest of ours that sent `starting`
        self._open = False  # it's starting or on: a stop has something to stop
        self._voice: dict[str, Any] = {
            "kind": "voice", "state": str(ListeningState.IDLE), "detail": None, "text": "", "settled": 0,
        }
        ctx.subscribe(VoiceState, self._on_voice_state)
        ctx.subscribe(VoiceTranscript, self._on_voice_text)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, self._host, self._port)
        self.url = f"http://{self._host}:{self._server.sockets[0].getsockname()[1]}/"
        self._ctx.log.info("Voice notes at %s", self.url)
        if self._window == "app":
            await asyncio.to_thread(self._open_app_window)
        elif self._window == "browser":
            webbrowser.open(self.url)

    def _open_app_window(self) -> None:
        close_app_windows(self._profile, self._ctx.log)  # one left from a previous launch
        self._edge = open_app_window(self.url, self._profile, log=self._ctx.log)

    async def stop(self) -> None:
        voice = self._ctx.get_one(IVoice)
        if self._open and voice is not None and self._session:  # don't leave the mic on for a page that's gone
            await voice.finish(self._session, discard=True)
        if self._edge and self._edge.poll() is None:
            await asyncio.to_thread(close_app_windows, self._profile, self._ctx.log)
        if self._server:
            self._server.close()
        for task in self._connections:
            task.cancel()
        await asyncio.gather(*self._connections, return_exceptions=True)

    # --- voice ---

    async def _on_voice_state(self, event: VoiceState) -> None:
        if event.correlation_id not in self._mine:
            return  # another part of the app's session (the temp UI's mic)
        if event.state is ListeningState.STARTING:
            self._session = event.correlation_id
        elif event.correlation_id != self._session:
            return  # a stale session's update
        self._open = event.state not in ENDED
        detail = event.detail
        if event.reason == TAKEN_OVER:
            detail = f"cancelled: {event.detail or 'another part of the app took the mic'}"
        changes: dict[str, Any] = {"state": str(event.state), "detail": detail}
        if event.state in ENDED or event.state is ListeningState.STARTING:
            changes.update(text="", settled=0)  # finishing keeps the line until the final
        self._set_voice(**changes)

    async def _on_voice_text(self, event: VoiceTranscript) -> None:
        if event.correlation_id != self._session or event.correlation_id not in self._mine:
            return
        if not event.final:  # the first `settled` characters are cleaned; the page shows them as notes
            self._set_voice(text=event.text, settled=event.settled_chars)
            return
        self._set_voice(text="", settled=0)
        # Sent even when empty (a cancelled or cleared session): the page then drops the recorded stretch.
        self._push({"kind": "final", "text": event.text})

    async def _record(self, on: bool) -> dict[str, Any]:
        voice = self._ctx.get_one(IVoice)  # at each call: a reloaded voice_in is a new provider
        if not on:
            if not self._open or voice is None or self._session is None:
                return {"ok": True, "error": None}  # nothing of ours is on (it ended, or was taken over)
            result = await voice.finish(self._session)  # ends only our session
            return {"ok": result.is_ok, "error": result.error}
        session_id = uuid4().hex
        self._mine.add(session_id)  # before listening: its first state comes while it opens
        if voice is None:  # voice input is mid-reload, or was turned off around us
            self._session, self._open = session_id, False
            self._set_voice(state=str(ListeningState.FAILED), detail="voice input is off", text="", settled=0)
            return {"ok": False, "error": "voice input is off"}
        result = await voice.listen(session_id, VoiceDestination.CALLER)  # the words go to this page only
        if not result.is_ok and self._session != session_id:  # no state came for it
            self._session, self._open = session_id, False
            self._set_voice(state=str(ListeningState.FAILED), detail=result.error, text="", settled=0)
        return {"ok": result.is_ok, "error": result.error}

    def _set_voice(self, **changes: Any) -> None:
        self._voice = {**self._voice, **changes}
        self._push(self._voice)

    def _push(self, item: dict[str, Any]) -> None:
        for queue in self._clients:
            if not queue.full():
                queue.put_nowait(item)

    # --- HTTP (cut down from the temp UI's page server) ---

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._connections.add(task)
        try:
            method, path, _ = (await reader.readline()).decode("latin-1").split(" ", 2)
            headers = {}
            while (line := await reader.readline()) not in (b"\r\n", b"\n", b""):
                name, _, value = line.decode("latin-1").partition(":")
                headers[name.strip().lower()] = value.strip()
            if not local_request(headers.get("host"), headers.get("origin")):  # G10: this machine's own page only
                await self._respond(writer, 403, "text/plain", b"Forbidden")
            elif method == "GET" and path == "/":
                await self._respond(writer, 200, "text/html; charset=utf-8", PAGE.read_bytes())
            elif method == "GET" and path == "/events":
                await self._stream(writer)
            elif method == "POST" and path == "/record":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                answer = await self._record(bool(body.get("on")))
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            else:
                await self._respond(writer, 404, "text/plain", b"Not found")
        except (ConnectionError, ValueError, KeyError, asyncio.IncompleteReadError):
            pass
        finally:
            self._connections.discard(task)
            writer.close()

    async def _respond(self, writer: asyncio.StreamWriter, status: int, content_type: str, body: bytes) -> None:
        reason = {200: "OK", 404: "Not Found"}[status]
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        )
        await writer.drain()

    async def _stream(self, writer: asyncio.StreamWriter) -> None:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n")
        writer.write(_sse(self._voice))
        await writer.drain()
        self._clients.add(queue)
        try:
            while True:
                try:
                    writer.write(_sse(await asyncio.wait_for(queue.get(), 15)))
                except TimeoutError:
                    writer.write(b": keep-alive\n\n")
                await writer.drain()
        finally:
            self._clients.discard(queue)


def _sse(item: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(item, ensure_ascii=False)}\n\n".encode()
