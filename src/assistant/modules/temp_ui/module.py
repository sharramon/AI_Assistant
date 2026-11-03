"""TEMPORARY UI: a local web page with the worker's activity on the left and the
Talker conversation on the right (permission requests show there, as Allow / Deny cards). A throwaway stand-in until the UI handler and
its configurations are designed.

Serves `page.html` on http://127.0.0.1:<port>/ (standard library only):
- `GET /events`: Server-Sent Events, a `hello` with this launch's id, then recent history
  (a page that sees a new launch id closes itself: the relaunched app opened a fresh window)
- `POST /say`: `{"text": ...}` becomes an `InputReceived`
- `POST /permission`: `{"task_id", "allow"}` sends `AnswerPermission` (the Allow / Deny buttons)
- `POST /permission-mode`: `{"mode": "manual" | "auto"}` sends `SetPermissionMode` for the worker
  (the Manual | Auto toggle in the Talker pane, a stand-in; the page confirms Auto first). The
  worker's mode is an SSE state item (`PermissionModeChanged`; Manual until one arrives), and
  each switch is logged in both panes. A `need` starting with `Risky:` shows as an amber card
  with Go ahead / Don't, which send that answer through `/say`, as typing it would.
- `POST /open-logs`: opens the logs folder in Explorer
- `POST /open-in-viewer`: `{"path"}` sends `InvokeTool viewer.open` with `front` (the Open in viewer button on
  an HTML path in a Talker message)
- snips from the HTML viewer (`ViewerClip`) show as thumbnails above the input until your next
  message (up to 3, like the Talker); `GET /snip/<id>` is the image, `POST /drop-snip` `{"id"}`
  drops one (`ViewerClipDropped`)
- the header shows the worker's and the Talker's usage side by side, live (`SessionUsage`:
  context now, used since launch, ~$); each pane's Reset button sends
  `POST /reset` `{"agent": "worker" | "talker"}`, which publishes `ResetRequested`
- the mic button: `POST /mic` `{"on": true | false}` sends `StartListening` / `StopListening`
  (handled by `voice_in`). `VoiceState` and `VoiceTranscript` of the current session (the one
  that sent `starting`) make the `voice` SSE state item: the button's state, the live text, and
  for *dropped* the countdown's end (`until`, read from the state's detail). Spoken input
  (`InputReceived(source="voice")`) shows as your message, marked spoken

`window = "app"` opens it in its own window (Edge app mode: no tabs or address
bar); `"browser"` opens a browser tab; `"none"` opens nothing.

The app window runs on its own Edge profile (`window_profile`), so it is its own Edge
process: at startup the app closes any window left from a previous launch (a relaunch
kills the app, not the window, and Edge won't let the page close itself), and it closes
its window when it stops.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app_kit.window import close_app_windows, open_app_window
from assistant.contracts import (
    AgentActivity,
    AgentStateChanged,
    AnswerPermission,
    InputReceived,
    InvokeTool,
    ListeningState,
    Manifest,
    Module,
    ModuleContext,
    PermissionMode,
    PermissionModeChanged,
    ReportKind,
    ResetRequested,
    ResponseReady,
    SessionUsage,
    SetPermissionMode,
    StartListening,
    Status,
    StopListening,
    TaskUpdated,
    ViewerClip,
    ViewerClipDropped,
    VoiceState,
    VoiceTranscript,
)

PAGE = Path(__file__).with_name("page.html")
HISTORY = 500
MAX_SNIPS = 3  # as many as the Talker sends with one message
RISKY = "Risky:"  # a need starting with this is the worker pausing before a risky step (Auto)
WAIT = re.compile(r"(\d+(?:\.\d+)?)\s*s\b")  # the wait in a dropped mic's detail ("waiting 15 s for it…")


class TempUIModule(Module):
    manifest = Manifest(id="temp_ui")

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._host = ctx.config.get("host", "127.0.0.1")
        self._port = ctx.config.get("port", 8765)
        self._window = ctx.config.get("window", "app")
        # A folder, or a callable returning one (the session folder exists only after the first message).
        self._logs_dir = ctx.config.get("logs_dir", "logs")
        default_profile = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AI_Assistant" / "temp_ui_window"
        self._profile = Path(ctx.config.get("window_profile", default_profile)).resolve()
        self._edge: subprocess.Popen | None = None
        self._launch = uuid4().hex
        self._history: deque[dict[str, Any]] = deque(maxlen=HISTORY)
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._server: asyncio.Server | None = None
        self._connections: set[asyncio.Task] = set()
        self._snips: dict[str, ViewerClip] = {}  # waiting for your next message, oldest first
        # The agent each pane shows, by pane, and its latest usage (an SSE item).
        self._agents = {"worker": ctx.config.get("worker", "main_assistant"), "talker": "talker"}
        self._usage: dict[str, dict[str, Any]] = {}
        # The worker's permission mode (an SSE item): Manual at every launch until told otherwise.
        self._mode = {"kind": "mode", "mode": str(PermissionMode.MANUAL), "applies": "now"}
        # The mic button and live line (an SSE item), following one voice session at a time.
        self._voice_session: str | None = None
        self._voice: dict[str, Any] = {"kind": "voice", "state": str(ListeningState.IDLE), "detail": None, "text": "", "until": None}
        ctx.subscribe(VoiceState, self._on_voice_state)
        ctx.subscribe(VoiceTranscript, self._on_voice_text)
        ctx.subscribe(InputReceived, self._on_input)
        ctx.subscribe(SessionUsage, self._on_usage)
        ctx.subscribe(ViewerClip, self._on_snip)
        ctx.subscribe(ResponseReady, self._on_response)
        ctx.subscribe(TaskUpdated, self._on_task)
        ctx.subscribe(AgentActivity, self._on_activity)
        ctx.subscribe(AgentStateChanged, self._on_state)
        ctx.subscribe(PermissionModeChanged, self._on_mode)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, self._host, self._port)
        self.url = f"http://{self._host}:{self._server.sockets[0].getsockname()[1]}/"
        self._ctx.log.info("Temp UI at %s", self.url)
        if self._window == "app":
            await asyncio.to_thread(self._open_app_window)
        elif self._window == "browser":
            webbrowser.open(self.url)

    def _open_app_window(self) -> None:
        """Close any window left from a previous launch, then open the page in its own window.

        Falls back to a browser tab without Edge.
        """
        close_app_windows(self._profile, self._ctx.log)
        self._edge = open_app_window(self.url, self._profile, log=self._ctx.log)

    async def stop(self) -> None:
        if self._edge and self._edge.poll() is None:
            await asyncio.to_thread(close_app_windows, self._profile, self._ctx.log)
        if self._server:
            self._server.close()
        for task in self._connections:
            task.cancel()
        await asyncio.gather(*self._connections, return_exceptions=True)

    # --- events → panes ---

    async def _on_input(self, event: InputReceived) -> None:
        self._push("talker", "you", event.text, **({"voice": True} if event.source == "voice" else {}))
        if self._snips:  # they went to the Talker with this message
            self._snips.clear()
            self._push_snips()

    async def _on_snip(self, event: ViewerClip) -> None:
        self._snips[event.id] = event
        while len(self._snips) > MAX_SNIPS:
            del self._snips[next(iter(self._snips))]
        self._push_snips()

    def _snips_item(self) -> dict[str, Any]:
        return {"kind": "snips", "snips": [{"id": s.id, "file": s.file, "heading": s.heading} for s in self._snips.values()]}

    def _push_snips(self) -> None:
        self._push_state(self._snips_item())

    def _push_state(self, item: dict[str, Any]) -> None:
        # Current state, not history: a page connecting later gets it once in `_stream`.
        for queue in self._clients:
            if not queue.full():
                queue.put_nowait(item)

    async def _on_usage(self, event: SessionUsage) -> None:
        pane = next((p for p, agent in self._agents.items() if agent == event.agent_id), None)
        if pane is None:
            return
        item = {
            "kind": "usage", "agent": pane, "context": event.context_tokens, "used": event.used_tokens,
            "cost": event.cost_usd, "input": event.input_tokens, "cache_write": event.cache_write_tokens,
            "cache_read": event.cache_read_tokens, "output": event.output_tokens,
        }
        self._usage[pane] = item
        self._push_state(item)

    async def _on_mode(self, event: PermissionModeChanged) -> None:
        if event.agent_id != self._agents["worker"]:
            return
        self._mode = {"kind": "mode", "mode": str(event.mode), "applies": event.applies}
        self._push_state(self._mode)
        when = " from the next task" if event.applies == "next_task" else ""
        label = "Auto, no permission prompts" if event.mode is PermissionMode.AUTO else "Manual"
        self._push("talker", "note", f"Main Assistant: {label}{when}")
        self._push("worker", "task", f"permission mode: {event.mode}{when}")

    # --- voice: the mic button and the live line ---

    async def _on_voice_state(self, event: VoiceState) -> None:
        if event.state is ListeningState.STARTING:  # a new session: follow it, forget the last one
            self._voice_session = event.correlation_id
            self._voice["text"] = ""
        elif event.correlation_id != self._voice_session:
            return  # a stale session's update
        until = None
        if event.state is ListeningState.DROPPED and (wait := WAIT.search(event.detail or "")):
            until = (time.time() + float(wait[1])) * 1000  # the page counts down to this (ms, like Date.now())
        if event.state in (ListeningState.IDLE, ListeningState.FAILED):
            self._voice["text"] = ""
        self._set_voice(state=str(event.state), detail=event.detail, until=until)

    async def _on_voice_text(self, event: VoiceTranscript) -> None:
        if event.correlation_id == self._voice_session:
            self._set_voice(text="" if event.final else event.text)

    def _set_voice(self, **changes: Any) -> None:
        self._voice = {**self._voice, **changes}
        self._push_state(self._voice)

    async def _mic(self, on: bool) -> dict[str, Any]:
        command = StartListening() if on else StopListening()
        result = await self._ctx.send(command)
        if on and not result.is_ok and self._voice_session != command.id:
            # No VoiceState came for it: nothing handled the command (voice_in is off), or it failed first.
            detail = "voice input is off" if result.status is Status.NOT_AVAILABLE else result.error
            self._voice_session = command.id
            self._set_voice(state=str(ListeningState.FAILED), detail=detail, text="", until=None)
        return {"ok": result.is_ok, "error": result.error}

    async def _on_response(self, event: ResponseReady) -> None:
        self._push("talker", "talker", event.text)

    async def _on_task(self, event: TaskUpdated) -> None:
        # Progress (and the text in done/need) is already in the pane as activity; show a short marker.
        if event.kind is ReportKind.PROGRESS:
            return
        # Permission requests are answered on the Talker side; the worker pane only logs them.
        if event.kind is ReportKind.PERMISSION:
            self._push("talker", "permission", event.text, task_id=event.task_id)
            self._push("worker", "task", f"task {event.task_id} asks permission: {event.text}", state=event.state)
            return
        if event.kind is None and event.text.startswith("permission "):
            self._push("talker", "answered", event.text, task_id=event.task_id)
            self._push("worker", "task", f"task {event.task_id} {event.text}", state=event.state)
            return
        if event.kind is ReportKind.NEED and event.text.startswith(RISKY):
            what = event.text.removeprefix(RISKY).strip()
            self._push("talker", "risky", what, task_id=event.task_id)
            self._push("worker", "task", f"task {event.task_id} paused: risky step: {what[:117]}", state=event.state)
            return
        detail = ""
        if event.kind is not None and event.text:
            first = event.text.strip().splitlines()[0]
            detail = f": {first[:117]}..." if len(first) > 120 else f": {first}"
        self._push("worker", "task", f"task {event.task_id} {event.kind or event.state}{detail}", state=event.state)

    async def _on_activity(self, event: AgentActivity) -> None:
        kind = "tool" if event.text.startswith("→") else "text"
        self._push("worker", kind, event.text)

    async def _on_state(self, event: AgentStateChanged) -> None:
        state = "working" if event.working else "waiting" if event.busy else "idle"
        self._push("worker", "state", state)

    def _push(self, pane: str, kind: str, text: str, **extra: Any) -> None:
        item = {"pane": pane, "kind": kind, "text": text, "t": datetime.now().strftime("%H:%M:%S"), **extra}
        self._history.append(item)
        for queue in self._clients:
            if queue.full():
                continue
            queue.put_nowait(item)

    # --- HTTP ---

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._connections.add(task)
        try:
            request = await reader.readline()
            method, path, _ = request.decode("latin-1").split(" ", 2)
            headers = {}
            while (line := await reader.readline()) not in (b"\r\n", b"\n", b""):
                name, _, value = line.decode("latin-1").partition(":")
                headers[name.strip().lower()] = value.strip()
            if method == "GET" and path == "/":
                await self._respond(writer, 200, "text/html; charset=utf-8", PAGE.read_bytes())
            elif method == "GET" and path == "/events":
                await self._stream(writer)
            elif method == "POST" and path == "/say":
                body = await reader.readexactly(int(headers.get("content-length", 0)))
                text = str(json.loads(body or b"{}").get("text", "")).strip()
                if text:
                    self._ctx.publish(InputReceived(text=text, source=self.manifest.id))
                await self._respond(writer, 204, "text/plain", b"")
            elif method == "POST" and path == "/permission":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                result = await self._ctx.send(AnswerPermission(task_id=str(body["task_id"]), allow=bool(body["allow"])))
                answer = {"ok": result.is_ok, "error": result.error}
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            elif method == "POST" and path == "/permission-mode":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                mode = PermissionMode(str(body.get("mode")))
                result = await self._ctx.send(SetPermissionMode(agent_id=self._agents["worker"], mode=mode))
                answer = {"ok": result.is_ok, "error": result.error}
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            elif method == "POST" and path == "/reset":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                agent = self._agents.get(str(body.get("agent")))
                if agent:
                    self._ctx.publish(ResetRequested(agent_id=agent))
                await self._respond(writer, 204, "text/plain", b"")
            elif method == "POST" and path == "/mic":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                answer = await self._mic(bool(body.get("on")))
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            elif method == "POST" and path == "/open-logs":
                self._open_logs()
                await self._respond(writer, 204, "text/plain", b"")
            elif method == "GET" and path.startswith("/snip/"):
                snip = self._snips.get(path.removeprefix("/snip/"))
                image = Path(snip.image_path) if snip else None
                if image and image.is_file():
                    await self._respond(writer, 200, "image/png", await asyncio.to_thread(image.read_bytes))
                else:
                    await self._respond(writer, 404, "text/plain", b"Not found")
            elif method == "POST" and path == "/drop-snip":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                if self._snips.pop(str(body.get("id")), None):
                    self._ctx.publish(ViewerClipDropped(id=str(body["id"])))
                    self._push_snips()
                await self._respond(writer, 204, "text/plain", b"")
            elif method == "POST" and path == "/open-in-viewer":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                # Your click: the viewer comes to the front (an agent's own pages don't).
                result = await self._ctx.send(InvokeTool(name="viewer.open", args={"path": str(body["path"]), "front": True}))
                answer = {"ok": result.is_ok, "error": result.error}
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            else:
                await self._respond(writer, 404, "text/plain", b"Not found")
        except (ConnectionError, ValueError, KeyError, asyncio.IncompleteReadError):
            pass
        finally:
            self._connections.discard(task)
            writer.close()

    def _open_logs(self) -> None:
        folder = Path(self._logs_dir() if callable(self._logs_dir) else self._logs_dir).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    async def _respond(self, writer: asyncio.StreamWriter, status: int, content_type: str, body: bytes) -> None:
        reason = {200: "OK", 204: "No Content", 404: "Not Found"}[status]
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        )
        await writer.drain()

    async def _stream(self, writer: asyncio.StreamWriter) -> None:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n")
        writer.write(_sse({"kind": "hello", "launch": self._launch}))
        for item in self._history:
            writer.write(_sse(item))
        writer.write(_sse(self._snips_item()))
        for item in self._usage.values():
            writer.write(_sse(item))
        writer.write(_sse(self._mode))
        writer.write(_sse(self._voice))
        await writer.drain()
        self._clients.add(queue)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), 15)
                    writer.write(_sse(item))
                except TimeoutError:
                    writer.write(b": keep-alive\n\n")
                await writer.drain()
        finally:
            self._clients.discard(queue)


def _sse(item: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(item, ensure_ascii=False)}\n\n".encode()
