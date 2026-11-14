"""TEMPORARY UI: a local web page with the worker's activity on the left and the
Talker conversation on the right (permission requests show there, as Allow / Deny cards). A throwaway stand-in until the UI handler and
its configurations are designed.

Serves `page.html` on http://127.0.0.1:<port>/ (standard library only):
- `GET /events`: Server-Sent Events, a `hello` with this launch's id, then recent history
  (a page that sees a new launch id closes itself: the relaunched app opened a fresh window)
- `POST /say`: `{"text": ...}` becomes an `InputReceived`
- `POST /permission`: `{"task_id", "allow"}` sends `AnswerPermission` (the Allow / Deny buttons)
- the permissions handler's cards (`PermissionRequested`): an access card in the Talker pane with
  a tick box per item (the working folder has none), the warnings, "not reviewed" when the review
  didn't run, and the fixed rules; `POST /access-answer` `{"request_id", "allow", "keep"}` sends
  `AnswerPermissionRequest`, and `PermissionChanged` with its `request_id` settles the card
- ROUGH, THROWAWAY grants screen: `static/grants.js` (`GET /grants.js`, its own header button
  and panel) lists the saved grants and takes them back through `POST /grants`
  `{"action": "list" | "revoke", ...}`, which calls `permissions.grants` / `permissions.revoke`
  as `temp_ui` (you: a revoke applies at once)
- the agent tabs' **+** and **×** (`static/agent_tabs.js`, `GET /agent-tabs.js`; the server side
  is `agent_tabs.py`): `POST /agent-tabs` `{"action": "kinds" | "turn_on" | "open" | "close"}`
  calls `agents.kinds` / `modules.on task_agents` / `agents.launch` / a close (cancel the task,
  then `agents.close` or `modules.off` of the agent's module), as `temp_ui` (you). The helper
  you open takes the focus once its tab appears; closing the focused one focuses the Main Assistant
- `POST /permission-mode`: `{"mode": "manual" | "auto", "agent"}` sends `SetPermissionMode` for
  that agent, the tab it was pressed in (the worker when none is given; the Manual | Auto toggle in
  the Talker pane, a stand-in; the page confirms Auto first). Each agent's mode is an SSE state
  item `{"kind": "mode", "agent", "mode", "applies"}` (`PermissionModeChanged`; Manual until one
  arrives), each tab's button shows its own agent's, and each switch is logged in both panes of
  that agent's tab. A `need` starting with `Risky:` shows as an amber card
  with Go ahead / Don't, which send that answer through `/say`, as typing it would.
- `POST /open-logs`: opens the logs folder in Explorer
- `POST /open-in-viewer`: `{"path"}` opens it with `front` through the page-opener slot (`open_page`,
  `IPageOpener`: whichever add-on opens pages; none on: "No page viewer is on") (the Open in viewer
  button on an HTML path in a Talker message)
- snips from the HTML viewer (its named event `html_viewer.clip`, heard by name) show as thumbnails
  above the input until your next message (up to 3, like the Talker); `GET /snip/<id>` is the image,
  `POST /drop-snip` `{"id"}` drops one (this module's `temp_ui.clip_dropped`). A snip can be sent with
  nothing typed (the text is "(snip)"); the sent snips move into your message's bubble. Each step is
  logged at info level.
- a pasted image (Ctrl+V in the chat box) becomes a snip too: `POST /paste-image` (the PNG bytes,
  up to 10 MB) saves it as `<launch log folder>/snips/paste-<id>.png` and publishes this module's
  `temp_ui.clip` (a snip's data, `file="(pasted)"`); from there it is the snip path above.
- the header follows the selected tab: its worker's and its Talker's context now (`SessionUsage`,
  kept by agent id), and the tokens that pair used since launch (their tally rows); and one total
  since launch for every agent, in tokens (`Total 3.4M`): a click opens the THROWAWAY usage
  dropdown, one row per agent (the Talker its own row), sub-agents nested under their
  parent. Both come from the `usage` module's menu (`usage.total`,
  `usage.agents`), asked again shortly after each `SessionUsage` (the `tally` SSE item); with
  `usage` off the total says so. Each pane's Reset button sends
  `POST /reset` `{"agent": "worker" | "talker", "tab"}`, which resets one of the pair of the
  tab it was pressed in (`reset_target`): its worker (`ResetRequested`, a command the Hub
  handles), or its Talker (the Talker's `talker.reset` item, only for you)
  (`talker`, `talker:<agent>` in a helper's tab); with no `tab`, the main pair
- the mic button: `POST /mic` `{"on": true | false, "agent"}` sends `StartListening` /
  `StopListening(agent_id=<the tab you stopped in>)` (handled by `voice_in`; the final text goes
  to that tab's Talker even if you switch tabs while it's cleaned); the ✕ next to it, `{"clear": true}`, sends
  `StopListening(discard=True)` and then `StartListening`, so the mic carries on. Only sessions
  this page started are followed (by the `StartListening` command's id); another part of the app's
  session (voice notes) is ignored. When another part takes the mic (`idle`, `taken_over`), the
  line clears, the button says cancelled and stays live, and no stop is sent for that session.
  `VoiceState` and `VoiceTranscript` of the current own session (the latest that sent `starting`) make the `voice` SSE state item: the button's state, the live text with
  its `settled` length (two passes: the page shows the settled start normal, the rough rest
  dimmed; *finishing* keeps the text until the final clears it), and
  for *dropped* the countdown's end (`until`, read from the state's detail). Spoken input
  (`InputReceived(source="voice")`) shows as your message, marked spoken. The item also has
  `available`, `why` and `retry`: from `voice_in`'s `ModuleStateChanged` (off, starting,
  reloading, failed: unavailable with a reason, no click) and from a `failed` `VoiceState` with
  `service_unavailable` / `service_stopped` (the voice app isn't running: unavailable, but
  `retry` keeps it clickable). The page shows a crossed-out mic with `why` as its title
- big agents (multi-agent): every worker-pane item carries its `agent`. The `agents` SSE state
  item (`focus`, `coordinator`, and per agent `busy`, `working`, `held`, the number of held
  questions) is rebuilt from `ListAgents`, `AgentStateChanged`, `ModuleStateChanged`,
  `TaskUpdated.held` and `FocusChanged`. The page shows one tab per big agent above the worker
  feed (a **!** while one holds a question; the coordinator's in its own colour); a click
  posts `POST /focus` `{"agent"}`, which sends `SetFocus`, and the feed shows that agent's
  lines. A held permission card isn't shown until `FocusChanged` releases it; cards name
  their agent
- a chat per agent tab (agent talkers, chunk 1): every Talker-pane item carries its `agent`
  (your input's and the reply's `agent_id`, a card's agent; cards and notes without one go to
  the focused tab), the page shows only the selected tab's chat under a "Talker · <agent>"
  header in the tab's colour, and `POST /say` sends the tab (`{"text", "agent"}` →
  `InputReceived.agent_id`). Replay keeps the last `CHAT_HISTORY` items per tab. Chats last the
  app's run (not saved across a relaunch)

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

from app_kit.local_guard import local_request
from app_kit.window import close_app_windows, flash_window, open_app_window, window_profile
from assistant.contracts import (
    MAX_SNIPS,
    PASTED_FILE,
    RISKY_PREFIX,
    AgentActivity,
    AgentState,
    AgentStateChanged,
    AnswerPermission,
    AnswerPermissionRequest,
    CancelTask,
    FocusChanged,
    GetTaskStatus,
    IAgentNames,
    InputReceived,
    InvokeTool,
    IPageOpener,
    ListAgents,
    ListeningState,
    ListModules,
    Manifest,
    ModuleContext,
    ModuleEvent,
    ModuleProtocol,
    ModuleState,
    ModuleStateChanged,
    PermissionChanged,
    PermissionMode,
    PermissionModeChanged,
    PermissionRequested,
    QuestionKind,
    ReportKind,
    ResetRequested,
    ResponseReady,
    SessionUsage,
    SetFocus,
    SetPermissionMode,
    StartListening,
    StartProvider,
    Status,
    StopListening,
    TaskState,
    TaskUpdated,
    VoiceState,
    VoiceTranscript,
)
from assistant.infra import open_page

from .agent_tabs import AgentTabs

PAGE = Path(__file__).with_name("page.html")
GRANTS_JS = Path(__file__).with_name("static") / "grants.js"  # ROUGH, THROWAWAY grants screen
AGENT_TABS_JS = Path(__file__).with_name("static") / "agent_tabs.js"  # the tabs' + and ×
HISTORY = 500  # the worker pane's lines, every agent's
CHAT_HISTORY = 300  # the Talker pane's items, per agent tab, so a chatty tab can't push out another's
SENT_SNIPS = 30  # snips already sent whose image the chat's bubbles still show
SNIP_ONLY_TEXT = "(snip)"  # the message text when you send a snip with nothing typed
# Snips as named events (data `id`, `image_path`, `file`, `heading`): the HTML viewer's, heard by name
# (no import of it), and this module's own pasted images; a dropped snip is this module's (`id`).
VIEWER_CLIP = "html_viewer.clip"
PASTED_CLIP = "temp_ui.clip"
CLIP_DROPPED = "temp_ui.clip_dropped"


def snip_of(data: dict[str, Any]) -> dict[str, Any]:
    """A snip event's data as the page shows it: `id`, `image_path`, `file`, `heading` (or None)."""
    return {"id": str(data.get("id", "")), "image_path": str(data.get("image_path", "")),
            "file": str(data.get("file", "")), "heading": data.get("heading") or None}  # fmt: skip
MAX_PASTE = 10 * 1024 * 1024  # bytes: a bigger pasted image is refused
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"  # the page sends every pasted image as PNG
# MAX_SNIPS, PASTED_FILE, RISKY_PREFIX and QuestionKind come from the contracts: a task's question
# kind is typed (the Hub sets it), so nothing here parses a question's text to know what it is.
WAIT = re.compile(r"(\d+(?:\.\d+)?)\s*s\b")  # the wait in a dropped mic's detail ("waiting 15 s for it…")
VOICE_MODULE = "voice_in"
# Why the mic is unavailable, by the voice module's state (active: available). Not clickable.
MODULE_WHY = {
    ModuleState.RELOADING: "The voice module is being reloaded with new code; back in a moment",
    ModuleState.STARTING: "The voice module is starting",
    ModuleState.STOPPING: "The voice module is off",
    ModuleState.INACTIVE: "The voice module is off",
    ModuleState.FAILED: "The voice module failed to start",
}
APP_DOWN = ("service_unavailable", "service_stopped")  # VoiceState reasons: the voice app isn't running
TAKEN_OVER = "taken_over"  # VoiceState reason: another part of the app took the mic (the second press wins)
USAGE_MODULE = "usage"
USAGE_SETTLE = 0.2  # seconds after a SessionUsage before asking the ledger, so it has taken the event
# A task's report that flashes the app's taskbar button (when the window isn't in front): it ended,
# or it asks you something. A cancel (your own act), progress, milestones and replies don't.
FLASH_KINDS = (ReportKind.DONE, ReportKind.FAILED, ReportKind.NEED, ReportKind.PERMISSION)
WINDOW_TITLE = "Assistant"  # page.html's <title>: finds the window when Edge's pid doesn't own it


def reset_target(button: str, tab: str, coordinator: str) -> str | None:
    """The session a Reset button resets: the `worker` or `talker` of `tab` (the main tab when
    empty). A helper's Talker is `talker:<agent>`, as the Talker module names it. None for
    an unknown button."""
    tab = tab or coordinator
    if button == "worker":
        return tab
    if button == "talker":
        return "talker" if tab == coordinator else f"talker:{tab}"
    return None


class TempUIModule(ModuleProtocol):
    manifest = Manifest(
        id="temp_ui",
        description="Temporary two-pane page: worker and Talker, mic, usage, permissions",
        optional=(IAgentNames,),
        uses=(IPageOpener,),  # the Open in viewer button: whichever add-on opens pages
        sends=(ListModules, ListAgents, SetFocus, StartListening, StopListening, AnswerPermission, AnswerPermissionRequest, SetPermissionMode, InvokeTool, StartProvider, GetTaskStatus, CancelTask, ResetRequested,),
        publishes=(InputReceived,),
        listens=(InputReceived, ResponseReady, TaskUpdated, AgentActivity, AgentStateChanged, FocusChanged, PermissionModeChanged, SessionUsage, VoiceState, VoiceTranscript, ModuleStateChanged, PermissionRequested, PermissionChanged,),
        publishes_named=(PASTED_CLIP, CLIP_DROPPED),
        listens_named=(VIEWER_CLIP, PASTED_CLIP),
    )

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._host = ctx.config.get("host", "127.0.0.1")
        self._port = ctx.config.get("port", 8765)
        self._window = ctx.config.get("window", "app")
        self._profile = Path(ctx.config.get("window_profile", window_profile("temp_ui"))).resolve()
        self._edge: subprocess.Popen | None = None
        self._flash = self._flash_app_window  # () -> None, in a thread; swappable for tests
        self._flashes: set[asyncio.Task] = set()
        self._launch = uuid4().hex
        self._history: deque[dict[str, Any]] = deque(maxlen=HISTORY)
        self._chats: dict[str, deque[dict[str, Any]]] = {}  # the Talker pane's items, by agent tab
        self._card_tabs: dict[str, str] = {}  # an open access card's request id → the tab it shows in
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._server: asyncio.Server | None = None
        self._connections: set[asyncio.Task] = set()
        self._snips: dict[str, dict[str, Any]] = {}  # waiting for your next message, oldest first (snip_of)
        self._sent_snips: dict[str, dict[str, Any]] = {}  # shown in sent bubbles, newest SENT_SNIPS kept
        # The agent each pane shows, by pane; each agent's latest context (an SSE item), by agent id.
        self._agents = {"worker": ctx.config.get("worker", "main_assistant"), "talker": "talker"}
        self._usage: dict[str, dict[str, Any]] = {}
        # THROWAWAY usage dropdown (an SSE item): the usage module's total and rows, asked again after changes.
        self._tally: dict[str, Any] = {"kind": "tally", "available": False, "why": "no usage yet", "total": None, "agents": []}
        self._tally_task: asyncio.Task | None = None
        self._tally_again = False
        # The big agents' tabs (an SSE item): each agent's busy / working, its held task ids, the focus.
        self._agent_list: dict[str, dict[str, Any]] = {}
        self._held: dict[str, set[str]] = {}
        self._focus = self._agents["worker"]  # the Hub starts on the coordinator; FocusChanged moves it
        self._tabs = AgentTabs(ctx, self._agents["worker"])  # the tabs' + and ×
        # Each agent's permission mode (SSE items): Manual at every launch until told otherwise.
        worker = self._agents["worker"]
        self._modes: dict[str, dict[str, Any]] = {
            worker: {"kind": "mode", "agent": worker, "mode": str(PermissionMode.MANUAL), "applies": "now"}}
        # The mic button and live line (an SSE item), following one voice session at a time.
        self._voice_session: str | None = None
        self._voice_mine: set[str] = set()  # ids of the StartListening commands this page sent
        self._voice_open = False  # the followed session is starting or on: a stop has something to stop
        self._voice: dict[str, Any] = {"kind": "voice", "state": str(ListeningState.IDLE), "detail": None, "text": "", "settled": 0,
                                       "until": None, "available": True, "why": None, "retry": False}  # fmt: skip
        # Whether the mic can be used: the voice module's state, and whether the voice app is running.
        self._voice_module: ModuleState | None = None
        self._app_why: str | None = None
        ctx.subscribe(VoiceState, self._on_voice_state)
        ctx.subscribe(ModuleStateChanged, self._on_module_state)
        ctx.subscribe(VoiceTranscript, self._on_voice_text)
        ctx.subscribe(InputReceived, self._on_input)
        ctx.subscribe(SessionUsage, self._on_usage)
        ctx.subscribe_named(VIEWER_CLIP, self._on_snip)
        ctx.subscribe_named(PASTED_CLIP, self._on_snip)
        ctx.subscribe(ResponseReady, self._on_response)
        ctx.subscribe(TaskUpdated, self._on_task)
        ctx.subscribe(AgentActivity, self._on_activity)
        ctx.subscribe(AgentStateChanged, self._on_state)
        ctx.subscribe(FocusChanged, self._on_focus)
        ctx.subscribe(PermissionModeChanged, self._on_mode)
        ctx.subscribe(PermissionRequested, self._on_access_card)
        ctx.subscribe(PermissionChanged, self._on_access_changed)

    async def start(self) -> None:
        listed = await self._ctx.send(ListModules())  # the voice module's state now; changes come as events
        if listed.is_ok:
            state = next((m.state for m in listed.value if m.id == VOICE_MODULE), ModuleState.INACTIVE)
            self._voice_module_state(state)
        await self._refresh_agents()
        await self._refresh_tally()
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

    def _flash_app_window(self) -> None:
        """Flash the app window's taskbar button until you click it, unless it's in front."""
        if self._window == "app":
            flash_window(self._edge.pid if self._edge else None, WINDOW_TITLE)

    def _notice(self, why: str) -> None:
        """Something needs your eyes: flash the taskbar (nothing while you're in the window).
        In the background, so the panes' items keep their order."""

        async def flash() -> None:
            try:
                await asyncio.to_thread(self._flash)
            except Exception as exc:  # a flash must never break the pane
                self._ctx.log.warning("Couldn't flash the taskbar for %s: %s", why, exc)

        task = asyncio.create_task(flash())
        self._flashes.add(task)
        task.add_done_callback(self._flashes.discard)

    async def stop(self) -> None:
        if self._edge and self._edge.poll() is None:
            await asyncio.to_thread(close_app_windows, self._profile, self._ctx.log)
        if self._server:
            self._server.close()
        pending = [*self._connections, *self._flashes, *([self._tally_task] if self._tally_task else [])]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    # --- events → panes ---

    async def _on_input(self, event: InputReceived) -> None:
        # The waiting snips went to the Talker with this message: they move into its bubble, as confirmation.
        sent = list(self._snips.values())
        extra: dict[str, Any] = {"voice": True} if event.source == "voice" else {}
        if sent:
            extra["snips"] = [self._snip_info(s) for s in sent]
        self._push("talker", "you", event.text, agent=event.agent_id or self._focus, **extra)
        if sent:
            self._ctx.log.info("Snips %s moved into sent message %s", [s["id"] for s in sent], event.id)
            for snip in sent:  # still served by GET /snip/<id> for the bubble
                self._sent_snips[snip["id"]] = snip
            while len(self._sent_snips) > SENT_SNIPS:
                del self._sent_snips[next(iter(self._sent_snips))]
            self._snips.clear()
            self._push_snips()

    async def _on_snip(self, event: ModuleEvent) -> None:
        snip = snip_of(event.data)  # html_viewer.clip, or a pasted image (temp_ui.clip)
        self._snips[snip["id"]] = snip
        self._ctx.log.info("Snip %s shown (%s)", snip["id"], snip["file"])
        while len(self._snips) > MAX_SNIPS:
            oldest = next(iter(self._snips))
            del self._snips[oldest]
            self._ctx.log.info("Snip %s dropped: over the limit of %d", oldest, MAX_SNIPS)
        self._push_snips()

    async def _paste_image(self, data: bytes) -> dict[str, Any]:
        """A pasted image: keep it with this launch's logs, then publish it as a snip."""
        if not data.startswith(PNG_SIGNATURE):
            self._ctx.log.info("Paste refused: not a PNG image (%d bytes)", len(data))
            return {"ok": False, "error": "not a PNG image"}
        snip_id = "paste-" + uuid4().hex[:8]
        folder = self._ctx.logs.folder() / "snips"
        image = folder / f"{snip_id}.png"

        def keep() -> None:
            folder.mkdir(parents=True, exist_ok=True)
            image.write_bytes(data)

        try:
            await asyncio.to_thread(keep)
        except OSError as exc:
            self._ctx.log.warning("Paste refused: couldn't save it (%s)", exc)
            return {"ok": False, "error": f"couldn't save it: {exc}"}
        self._ctx.log.info("Image pasted as snip %s (%d bytes, %s)", snip_id, len(data), image)
        self._ctx.publish_named(PASTED_CLIP, {"id": snip_id, "image_path": str(image), "file": PASTED_FILE,
                                              "heading": None})  # fmt: skip
        return {"ok": True, "id": snip_id}

    @staticmethod
    def _snip_info(snip: dict[str, Any]) -> dict[str, Any]:
        return {"id": snip["id"], "file": snip["file"], "heading": snip["heading"]}

    def _snips_item(self) -> dict[str, Any]:
        return {"kind": "snips", "snips": [self._snip_info(s) for s in self._snips.values()]}

    def _push_snips(self) -> None:
        self._push_state(self._snips_item())

    def _push_state(self, item: dict[str, Any]) -> None:
        # Current state, not history: a page connecting later gets it once in `_stream`.
        for queue in self._clients:
            if not queue.full():
                queue.put_nowait(item)

    async def _on_usage(self, event: SessionUsage) -> None:
        """Every agent's own context, by its id: the page shows the selected tab's worker
        (`<id>`) and Talker (`talker`, or `talker:<id>` for a helper). Tokens used are in the tally."""
        self._schedule_tally()
        if event.kind != "claude":  # sub-agents and tools have no tab of their own
            return
        item = {"kind": "usage", "agent": event.agent_id, "context": event.context_tokens}
        self._usage[event.agent_id] = item
        self._push_state(item)

    # --- THROWAWAY usage dropdown: the usage module's numbers, nothing added up here ---

    def _schedule_tally(self) -> None:
        """Ask the ledger again soon; one ask at a time, one more if events came meanwhile."""
        if self._tally_task and not self._tally_task.done():
            self._tally_again = True
            return
        self._tally_task = asyncio.create_task(self._tally_soon())

    async def _tally_soon(self) -> None:
        self._tally_again = True
        while self._tally_again:
            self._tally_again = False
            await asyncio.sleep(USAGE_SETTLE)
            await self._refresh_tally()

    async def _refresh_tally(self) -> None:
        total = await self._ctx.send(InvokeTool(name="usage.total"))
        agents = await self._ctx.send(InvokeTool(name="usage.agents")) if total.is_ok else total
        if total.is_ok and agents.is_ok:
            self._tally = {"kind": "tally", "available": True, "why": None, "total": total.value, "agents": agents.value}
        else:
            why = "the usage module is off" if agents.status is Status.NOT_AVAILABLE else agents.error
            self._tally = {"kind": "tally", "available": False, "why": why, "total": None, "agents": []}
        self._push_state(self._tally)

    async def _on_mode(self, event: PermissionModeChanged) -> None:
        agent = event.agent_id
        self._modes[agent] = {"kind": "mode", "agent": agent, "mode": str(event.mode), "applies": event.applies}
        self._push_state(self._modes[agent])
        when = " from the next task" if event.applies == "next_task" else ""
        label = "Auto, no permission prompts" if event.mode is PermissionMode.AUTO else "Manual"
        name = "Main Assistant" if agent == self._agents["worker"] else agent
        self._push("talker", "note", f"{name}: {label}{when}", agent=agent)
        self._push("worker", "task", f"permission mode: {event.mode}{when}", agent=agent)

    # --- voice: the mic button and the live line ---

    async def _on_voice_state(self, event: VoiceState) -> None:
        if event.correlation_id not in self._voice_mine:
            return  # another part of the app's session (voice notes)
        if event.state is ListeningState.STARTING:  # a new session: follow it, forget the last one
            self._voice_session = event.correlation_id
            self._voice.update(text="", settled=0)
        elif event.correlation_id != self._voice_session:
            return  # a stale session's update
        self._voice_open = event.state not in (ListeningState.IDLE, ListeningState.FAILED)
        detail = event.detail
        if event.reason == TAKEN_OVER:
            detail = f"cancelled: {event.detail or 'another part of the app took the mic'}"
        until = None
        if event.state is ListeningState.DROPPED and (wait := WAIT.search(event.detail or "")):
            until = (time.time() + float(wait[1])) * 1000  # the page counts down to this (ms, like Date.now())
        if event.state in (ListeningState.IDLE, ListeningState.FAILED):  # FINISHING keeps the line
            self._voice.update(text="", settled=0)
        if event.state is ListeningState.FAILED and event.reason in APP_DOWN:
            self._app_why = f"The voice app isn't running: {event.detail}. Click to try starting it again"
        elif event.state in (ListeningState.STARTING, ListeningState.LISTENING):
            self._app_why = None
        self._set_voice(state=str(event.state), detail=detail, until=until, **self._availability())

    async def _on_module_state(self, event: ModuleStateChanged) -> None:
        if event.module_id == VOICE_MODULE:
            self._voice_module_state(event.state)
        if event.module_id == USAGE_MODULE and event.state in (ModuleState.ACTIVE, ModuleState.INACTIVE, ModuleState.FAILED):
            self._schedule_tally()
        if event.state in (ModuleState.ACTIVE, ModuleState.INACTIVE, ModuleState.FAILED):
            await self._refresh_agents()  # agents come and go with their modules

    def _voice_module_state(self, state: ModuleState) -> None:
        if state is ModuleState.STARTING and self._voice_module is ModuleState.RELOADING:
            return  # part of the reload: keep saying so
        self._voice_module = state
        self._app_why = None  # a new instance tries the voice app afresh
        self._set_voice(**self._availability())

    def _availability(self) -> dict[str, Any]:
        """The SSE item's `available`, `why`, and `retry` (clickable while unavailable: the click retries)."""
        module_why = MODULE_WHY.get(self._voice_module) if self._voice_module else None
        why = module_why or self._app_why
        return {"available": why is None, "why": why, "retry": module_why is None and why is not None}

    async def _on_voice_text(self, event: VoiceTranscript) -> None:
        if event.correlation_id == self._voice_session:
            if event.final:
                self._set_voice(text="", settled=0)
            else:
                self._set_voice(text=event.text, settled=event.settled_chars)

    def _set_voice(self, **changes: Any) -> None:
        self._voice = {**self._voice, **changes}
        self._push_state(self._voice)

    async def _mic(self, on: bool, clear: bool = False, agent: str | None = None) -> dict[str, Any]:
        """The mic button. `agent`: the tab it was pressed in; a stop sends its final text there."""
        if (clear or not on) and not self._voice_open:
            return {"ok": True, "error": None}  # nothing of ours is on (it ended, or was taken over): stop nothing
        if clear:  # the ✕: throw the session away, then carry on listening in a new one
            self._set_voice(text="", settled=0)
            result = await self._ctx.send(StopListening(discard=True))
            if not result.is_ok or result.value is None:  # failed, or nothing was listening: don't turn it on
                return {"ok": result.is_ok, "error": result.error}
            on = True
        command = StartListening() if on else StopListening(agent_id=agent)
        if on:
            self._voice_mine.add(command.id)  # before sending: its first state comes while it's handled
        result = await self._ctx.send(command)
        if on and not result.is_ok and self._voice_session != command.id:
            # No VoiceState came for it: nothing handled the command (voice_in is off), or it failed first.
            detail = "voice input is off" if result.status is Status.NOT_AVAILABLE else result.error
            self._voice_session = command.id
            self._set_voice(state=str(ListeningState.FAILED), detail=detail, text="", settled=0, until=None)
        return {"ok": result.is_ok, "error": result.error}

    async def _on_response(self, event: ResponseReady) -> None:
        self._push("talker", "talker", event.text, agent=event.agent_id or self._focus)

    async def _on_task(self, event: TaskUpdated) -> None:
        agent, held = event.agent_id, self._held.setdefault(event.agent_id, set())
        before = len(held)
        if event.held:  # waits behind the agent's ! until you focus it: no card yet
            held.add(event.task_id)
        elif event.kind not in (ReportKind.PROGRESS, ReportKind.MILESTONE):
            held.discard(event.task_id)
        if len(held) != before:
            self._push_state(self._agents_item())
        if event.kind in FLASH_KINDS or (event.kind is None and event.state is TaskState.FAILED):
            self._notice(f"task {event.task_id} ({event.kind or event.state})")
        # Progress (and the text in done/need) is already in the pane as activity; show a short marker.
        if event.kind is ReportKind.PROGRESS:
            return
        # Permission requests are answered on the Talker side; the worker pane only logs them.
        if event.kind is ReportKind.PERMISSION:
            if not event.held:
                self._push("talker", "permission", event.text, task_id=event.task_id, agent=agent)
            self._push("worker", "task", f"task {event.task_id} asks permission: {event.text}", state=event.state, agent=agent)
            return
        if event.kind is None and event.text.startswith("permission "):
            self._push("talker", "answered", event.text, task_id=event.task_id, agent=agent)
            self._push("worker", "task", f"task {event.task_id} {event.text}", state=event.state, agent=agent)
            return
        if event.kind is ReportKind.NEED and event.question_kind is QuestionKind.RISKY:
            what = event.text.removeprefix(RISKY_PREFIX).strip()
            if not event.held:
                self._push("talker", "risky", what, task_id=event.task_id, agent=agent)
            self._push("worker", "task", f"task {event.task_id} paused: risky step: {what[:117]}", state=event.state, agent=agent)
            return
        detail = ""
        if event.kind is not None and event.text:
            first = event.text.strip().splitlines()[0]
            detail = f": {first[:117]}..." if len(first) > 120 else f": {first}"
        self._push("worker", "task", f"task {event.task_id} {event.kind or event.state}{detail}", state=event.state, agent=agent)

    # --- the permissions handler's cards ---

    async def _on_access_card(self, event: PermissionRequested) -> None:
        card = event.model_dump(mode="json", include={"module_id", "subject", "action", "reason", "notes", "reviewed",
                                                      "rules", "caller"})  # fmt: skip
        card["items"] = [{"key": i.key, "label": i.label, "trimmable": i.trimmable} for i in event.items]
        self._card_tabs[event.request_id] = self._focus  # shown in the tab you're in, as the Talker says it
        self._push("talker", "access", event.reason, request_id=event.request_id, card=card, agent=self._focus)
        self._notice(f"card {event.request_id}")

    async def _on_access_changed(self, event: PermissionChanged) -> None:
        if event.request_id:
            tab = self._card_tabs.pop(event.request_id, self._focus)  # in its card's tab, so a replay settles it
            self._push("talker", "access_closed", event.text, request_id=event.request_id, agent=tab)

    async def _grants(self, body: dict[str, Any]) -> dict[str, Any]:
        """The ROUGH grants screen's calls: the core's permissions.* menu, as temp_ui (you)."""
        if body.get("action") == "revoke":
            args = {"module_id": str(body.get("module_id", "")), "subject": str(body.get("subject") or "")}
            if body.get("items"):
                args["items"] = [str(k) for k in body["items"]]
            result = await self._ctx.send(InvokeTool(name="permissions.revoke", args=args))
        else:
            result = await self._ctx.send(InvokeTool(name="permissions.grants", args={}))
        return {"ok": result.is_ok, "value": result.value, "error": result.error}

    async def _on_activity(self, event: AgentActivity) -> None:
        kind = "tool" if event.text.startswith("→") else "text"
        self._push("worker", kind, event.text, agent=event.agent_id)

    async def _on_state(self, event: AgentStateChanged) -> None:
        state = "working" if event.state is AgentState.ACTIVE else "idle"
        self._push("worker", "state", state, agent=event.agent_id)
        if event.agent_id in self._agent_list:
            self._agent_list[event.agent_id].update(state=str(event.state))
            self._push_state(self._agents_item())
        else:
            await self._refresh_agents()

    # --- big agents: the tabs, the !, the focus ---

    async def _refresh_agents(self) -> None:
        listed = await self._ctx.send(ListAgents())
        if listed.is_ok:
            before = set(self._agent_list)
            self._agent_list = {a.agent_id: {"id": a.agent_id, "state": str(a.state)} for a in listed.value}
            if before - set(self._agent_list):  # an agent is gone: its usage rows now say closed
                self._schedule_tally()
        self._push_state(self._agents_item())
        if (opened := self._tabs.to_focus) and opened in self._agent_list:  # the helper you opened with +
            self._tabs.to_focus = None
            self._push("worker", "task", f"{opened} opened")
            await self._ctx.send(SetFocus(agent_id=opened))

    async def _agent_tabs(self, body: dict[str, Any]) -> dict[str, Any]:
        answer = await self._tabs.handle(body)
        action = body.get("action")
        if answer["ok"] and action == "open":
            self._push("worker", "task", str(answer["value"]))
        elif answer["ok"] and action == "close":
            self._push("worker", "task", str(answer["value"]))
            await self._refresh_agents()  # the Hub moves the focus off a gone agent (FocusChanged)
        return answer

    def _agents_item(self) -> dict[str, Any]:
        coordinator = self._agents["worker"]
        ids = sorted(self._agent_list, key=lambda i: (i != coordinator, i))  # the coordinator first
        agents = [{**self._agent_list[i], "held": len(self._held.get(i, ()))} for i in ids]
        return {"kind": "agents", "focus": self._focus, "coordinator": coordinator, "agents": agents}

    async def _on_focus(self, event: FocusChanged) -> None:
        self._focus = event.agent_id
        for task in event.released:  # their questions are said by the Talker; cards show here
            self._held.get(task.agent_id, set()).discard(task.id)
            question = task.question or ""
            if task.question_kind is QuestionKind.PERMISSION:
                self._push("talker", "permission", question, task_id=task.id, agent=task.agent_id)
            elif task.question_kind is QuestionKind.RISKY:
                self._push("talker", "risky", question.removeprefix(RISKY_PREFIX).strip(), task_id=task.id, agent=task.agent_id)
        self._push_state(self._agents_item())

    def _push(self, pane: str, kind: str, text: str, **extra: Any) -> None:
        item = {"pane": pane, "kind": kind, "text": text, "t": datetime.now().strftime("%H:%M:%S"), **extra}
        if pane == "talker":  # each tab's chat: the focused tab's unless the item names one
            item["agent"] = item.get("agent") or self._focus
            self._chats.setdefault(item["agent"], deque(maxlen=CHAT_HISTORY)).append(item)
        else:
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
            if not local_request(headers.get("host"), headers.get("origin")):  # G10: this machine's own page only
                await self._respond(writer, 403, "text/plain", b"Forbidden")
            elif method == "GET" and path == "/":
                await self._respond(writer, 200, "text/html; charset=utf-8", PAGE.read_bytes())
            elif method == "GET" and path == "/events":
                await self._stream(writer)
            elif method == "POST" and path == "/say":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                text = str(body.get("text", "")).strip()
                tab = str(body.get("agent") or "") or self._focus  # the tab you typed in
                if text or self._snips:  # a waiting snip can go alone, with placeholder text
                    self._ctx.publish(InputReceived(text=text or SNIP_ONLY_TEXT, source=self.manifest.id, agent_id=tab))
                await self._respond(writer, 204, "text/plain", b"")
            elif method == "POST" and path == "/permission":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                result = await self._ctx.send(AnswerPermission(task_id=str(body["task_id"]), allow=bool(body["allow"])))
                answer = {"ok": result.is_ok, "error": result.error}
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            elif method == "POST" and path == "/access-answer":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                keep = body.get("keep")
                answer = AnswerPermissionRequest(request_id=str(body["request_id"]), allow=bool(body["allow"]),
                                                 keep=None if keep is None else tuple(str(k) for k in keep),
                                                 remember=bool(body.get("remember", True)))  # fmt: skip
                result = await self._ctx.send(answer)
                await self._respond(writer, 200, "application/json", json.dumps({"ok": result.is_ok, "error": result.error}).encode())
            elif method == "GET" and path == "/grants.js":
                await self._respond(writer, 200, "text/javascript; charset=utf-8", GRANTS_JS.read_bytes())
            elif method == "POST" and path == "/grants":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                answer = await self._grants(body)
                await self._respond(writer, 200, "application/json", json.dumps(answer, default=str).encode())
            elif method == "GET" and path == "/agent-tabs.js":
                await self._respond(writer, 200, "text/javascript; charset=utf-8", AGENT_TABS_JS.read_bytes())
            elif method == "POST" and path == "/agent-tabs":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                answer = await self._agent_tabs(body)
                await self._respond(writer, 200, "application/json", json.dumps(answer, default=str).encode())
            elif method == "POST" and path == "/permission-mode":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                mode = PermissionMode(str(body.get("mode")))
                agent = str(body.get("agent") or self._agents["worker"])  # the tab it was pressed in
                result = await self._ctx.send(SetPermissionMode(agent_id=agent, mode=mode))
                answer = {"ok": result.is_ok, "error": result.error}
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            elif method == "POST" and path == "/focus":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                result = await self._ctx.send(SetFocus(agent_id=str(body.get("agent", ""))))
                answer = {"ok": result.is_ok, "error": result.error}
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            elif method == "POST" and path == "/reset":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                agent = reset_target(str(body.get("agent")), str(body.get("tab") or ""), self._agents["worker"])
                if agent and agent.startswith("talker"):  # a Talker session: the Talker's own item
                    result = await self._ctx.send(InvokeTool(name="talker.reset", args={"session": agent}))
                elif agent:  # a task agent: the Hub resets it
                    result = await self._ctx.send(ResetRequested(agent_id=agent))
                if agent and not result.is_ok:
                    self._ctx.log.warning("Reset of %s: %s", agent, result.error)
                await self._respond(writer, 204, "text/plain", b"")
            elif method == "POST" and path == "/mic":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                agent = body.get("agent")
                answer = await self._mic(bool(body.get("on")), clear=bool(body.get("clear")),
                                         agent=str(agent) if agent else None)  # fmt: skip
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            elif method == "POST" and path == "/open-logs":
                self._open_logs()
                await self._respond(writer, 204, "text/plain", b"")
            elif method == "GET" and path.startswith("/snip/"):
                snip_id = path.removeprefix("/snip/")
                snip = self._snips.get(snip_id) or self._sent_snips.get(snip_id)
                image = Path(snip["image_path"]) if snip else None
                if image and image.is_file():
                    await self._respond(writer, 200, "image/png", await asyncio.to_thread(image.read_bytes))
                else:
                    await self._respond(writer, 404, "text/plain", b"Not found")
            elif method == "POST" and path == "/paste-image":
                size = int(headers.get("content-length", 0))
                if size > MAX_PASTE:  # not read: the connection is closed after the answer
                    self._ctx.log.info("Paste refused: %d bytes, over the limit of %d", size, MAX_PASTE)
                    answer = {"ok": False, "error": f"too big ({size // 1024 // 1024} MB; the limit is 10 MB)"}
                else:
                    answer = await self._paste_image(await reader.readexactly(size))
                await self._respond(writer, 200, "application/json", json.dumps(answer).encode())
            elif method == "POST" and path == "/drop-snip":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                if self._snips.pop(str(body.get("id")), None):
                    self._ctx.log.info("Snip %s dropped: the x on its thumbnail", body["id"])
                    self._ctx.publish_named(CLIP_DROPPED, {"id": str(body["id"])})
                    self._push_snips()
                await self._respond(writer, 204, "text/plain", b"")
            elif method == "POST" and path == "/open-in-viewer":
                body = json.loads(await reader.readexactly(int(headers.get("content-length", 0))) or b"{}")
                # Your click: the viewer comes to the front (an agent's own pages don't).
                result = await open_page(self._ctx, str(body["path"]), front=True)
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
        folder = self._ctx.logs.folder().resolve()  # the session folder exists only after the first message
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
        listed = await self._ctx.send(ListAgents())  # fresh for a page connecting (or reconnecting)
        if listed.is_ok:
            self._agent_list = {a.agent_id: {"id": a.agent_id, "state": str(a.state)} for a in listed.value}
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n")
        writer.write(_sse({"kind": "hello", "launch": self._launch}))
        for item in self._history:
            writer.write(_sse(item))
        for chat in self._chats.values():  # each tab's chat in order; tabs needn't interleave
            for item in chat:
                writer.write(_sse(item))
        writer.write(_sse(self._snips_item()))
        for item in self._usage.values():
            writer.write(_sse(item))
        writer.write(_sse(self._tally))
        for item in self._modes.values():  # the worker's first
            writer.write(_sse(item))
        writer.write(_sse(self._voice))
        writer.write(_sse(self._agents_item()))
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
