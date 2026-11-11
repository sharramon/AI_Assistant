"""The Talker: fast `claude` sessions that talk with you and hand work to the Agent Hub.

One Talker per agent tab (agent talkers): this module is the router, and each tab's
conversation is a `TalkerSession` (`session.py`) whose partner is that tab's agent. The main
tab's partner is the coordinator (the Main Assistant); its session starts with the module and
is kept warm. A helper's starts on first use (its tab opened, a message for it, its held items
released) and closes when its agent is gone from `ListAgents` (the tab closed, its module off).
No idle timeout. Each session has its own `claude` process, inbox, history, cards, transcript
(`talker.jsonl`, `talker-<agent>.jsonl`), usage row (`talker`, `talker:<agent>` under its agent)
and context warning.

Routing: your input goes to `InputReceived.agent_id`'s session, else the focused tab's. A
`TaskUpdated` goes to its agent's session; the Hub holds an out-of-focus agent's questions,
replies and ends behind its tab's !, and `FocusChanged.released` brings them to that tab's
session ("[Focus] the user opened this tab."). Access cards, suggestions and snips go to the
focused tab. Each reply carries its tab (`ResponseReady.agent_id`).

Shared by every session, kept here: the open tasks (from `TaskUpdated`), the focus, the agents'
usage, the context watch, the viewer note (each session tells the latest once), the snips, the
mode notes per agent, and the session theme (once). The sessions reach them only through the
methods under "shared with the sessions". The restart is its own part, `RestartFlow`
(`restart.py`). A reload hands every tab's history to the new copy.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from assistant.contracts import (
    MAX_SNIPS,
    PASTED_FILE,
    AgentStateChanged,
    AnswerPermissionRequest,
    FocusChanged,
    FocusSuggested,
    IModuleDoor,
    InputReceived,
    InvokeTool,
    ListAgents,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ModuleStateChanged,
    PermissionChanged,
    PermissionModeChanged,
    PermissionRequested,
    QuestionKind,
    ReportKind,
    ResetRequested,
    ResponseReady,
    Result,
    SessionTheme,
    SessionUsage,
    ShutdownRequested,
    TaskState,
    TaskUpdated,
    ViewerClip,
    ViewerClipDropped,
    ViewerTabsChanged,
)
from assistant.infra import ContextWatch, theme_slug
from assistant.modules.talker.prompt import DOOR_NOTE, TALKER_PROMPT  # noqa: F401  (re-exported)
from assistant.modules.talker.restart import (  # noqa: F401  (the texts re-exported)
    AFTER_RESTART,
    APP_STATE_HEAD,
    RESTART_READY,
    WRITE_RESET_NOTE,
    RestartFlow,
)
from assistant.modules.talker.session import (  # noqa: F401  (split_tags, access_card_text re-exported)
    ACCESS_CARD,
    TALKER_ID,
    Item,
    TalkerSession,
    access_card_text,
    k_text,
    split_tags,
)

FOCUS_OPENED = "[Focus] the user opened this tab."
# MAX_SNIPS (snips waiting for your next message; the oldest dropped beyond it) and PASTED_FILE
# (a pasted image's ViewerClip.file) come from the contracts, shared with the temp UI.
# Task updates worth speaking about; progress stays with the Hub until you ask.
SPOKEN_UPDATES = {ReportKind.DONE, ReportKind.NEED, ReportKind.REPLY, ReportKind.FAILED, ReportKind.PERMISSION}


class TalkerModule(ModuleProtocol):
    manifest = Manifest(
        id="talker",
        description="Talks with you, one Talker per agent tab; hands work to the Agent Hub",
        optional=(IModuleDoor,),  # the agents' door to the module menus, from the Agent Hub
        sends=(InvokeTool, AnswerPermissionRequest, ListAgents,),  # the Hub through its menu (hub.*), one road
        publishes=(ResponseReady, SessionUsage, SessionTheme, ResetRequested, ShutdownRequested,),
        listens=(InputReceived, TaskUpdated, FocusChanged, FocusSuggested, SessionUsage, ResetRequested,
                 PermissionModeChanged, ViewerTabsChanged, ViewerClip, ViewerClipDropped,
                 PermissionRequested, PermissionChanged, AgentStateChanged, ModuleStateChanged,),
    )  # fmt: skip

    async def init(self, ctx: ModuleContext) -> None:
        self.ctx = ctx
        self.turn_timeout = ctx.config.get("turn_timeout", 120.0)
        self.worker_id = ctx.config.get("worker", "main_assistant")  # the coordinator: the main tab's agent
        handed = ctx.handover if isinstance(ctx.handover, dict) else {}  # from the copy before a reload
        self.open_tasks: dict[str, str] = dict(handed.get("open", {}))  # every open task's id → its agent
        self.usage: dict[str, SessionUsage] = {}  # each agent's latest own usage (not sub-agents')
        self._focus: str = handed.get("focus") or self.worker_id  # the tab you're in; the Hub's FocusChanged keeps it
        self._histories: dict[str, list[str]] = dict(handed.get("histories", {}))  # closed tabs' and handed-over histories
        self._theme_sent: bool = handed.get("theme_sent", False)  # SessionTheme goes out once, after the first input
        self._descriptions: dict[str, str] = {}  # agent → its description, for a helper tab's prompt
        self._sessions: dict[str, TalkerSession] = {}  # agent → its tab's Talker
        self._context_watch = ContextWatch(ctx.config.get("context_warning", 150_000))  # tokens; 0 = off
        self._viewer_note: str | None = None  # the viewer's open tabs; each session tells the latest once
        self._viewer_seq = 0
        self._mode_notes: dict[str, str] = {}  # agent → its new permission mode, told with your next message there
        self._snips: deque[ViewerClip] = deque(maxlen=MAX_SNIPS)  # sent with your next message
        note = ctx.config.get("restart_note")  # unset: restarts carry no note
        self.restart = RestartFlow(self, Path(note).resolve() if note else None,
                                   ctx.config.get("restart_timeout", 120.0))  # fmt: skip
        self._main = self._new_session(self.worker_id)
        for event_type, handler in (
            (InputReceived, self._on_input), (SessionUsage, self._on_usage), (ResetRequested, self._on_reset),
            (TaskUpdated, self._on_task_updated), (FocusChanged, self._on_focus), (FocusSuggested, self._on_suggestion),
            (PermissionModeChanged, self._on_mode), (ViewerTabsChanged, self._on_viewer_tabs),
            (ViewerClip, self._on_snip), (ViewerClipDropped, self._on_snip_dropped),
            (PermissionRequested, self._on_access_card), (PermissionChanged, self._on_access_changed),
            (AgentStateChanged, self._on_agents_changed), (ModuleStateChanged, self._on_agents_changed),
        ):  # fmt: skip
            ctx.subscribe(event_type, handler)

    async def start(self) -> None:
        self._main.start()
        await self._main.warm()
        if (note := self.restart.first_input()) is not None:  # the last launch restarted: its note comes first
            self._main.put(Item(note, restart_note=True))
        for agent in [a for a in self._histories if a != self.worker_id]:  # handed over by a reload: reopened
            self.session_for(agent)
        await self._refresh_agents()

    async def stop(self) -> None:
        await self.restart.close()
        for session in list(self._sessions.values()):
            await session.close()

    def busy(self) -> str | None:
        """A reload waits while a turn runs, so a reply isn't cut off."""
        return "replying to you" if any(s.busy() for s in self._sessions.values()) else None

    def export_state(self) -> dict[str, Any]:
        """Every tab's history, the focus, the open tasks: the next copy reopens the tabs on use."""
        histories = dict(self._histories) | {agent: list(s.history) for agent, s in self._sessions.items()}
        return {"histories": histories, "focus": self._focus, "open": dict(self.open_tasks),
                "theme_sent": self._theme_sent}  # fmt: skip

    def _command(self) -> list[str]:
        """The main tab's command line (what a `claude` Talker session runs)."""
        return self._main.command()

    # --- sessions ---

    def _new_session(self, agent: str) -> TalkerSession:
        session = TalkerSession(self, agent, self._histories.pop(agent, ()))
        self._sessions[agent] = session
        return session

    def session_for(self, agent: str) -> TalkerSession:
        """`agent`'s tab's Talker, made (not yet started) on first use."""
        agent = agent or self.worker_id
        if (session := self._sessions.get(agent)) is None:
            session = self._new_session(agent)
            session.start()
            self.ctx.log.info("Talker for %s's tab opened", agent)
        return session

    async def _on_agents_changed(self, event: AgentStateChanged | ModuleStateChanged) -> None:
        await self._refresh_agents()

    async def _refresh_agents(self) -> None:
        """Keep the agents' descriptions; close the Talkers whose agent is gone (its tab closed)."""
        result = await self.ctx.send(ListAgents())
        if not result.is_ok or not isinstance(result.value, list):
            return
        agents = {info.agent_id: info for info in result.value}
        self._descriptions = {agent: info.description for agent, info in agents.items()}
        for agent in [a for a in self._sessions if a != self.worker_id and a not in agents]:
            session = self._sessions.pop(agent, None)
            if session is not None:
                self._histories[agent] = list(session.history)  # back if the agent comes back
                self.ctx.log.info("Talker for %s's tab closed: its agent is gone", agent)
                await session.close()

    # --- shared with the sessions (and the restart): all they use of the module ---

    @property
    def focus(self) -> str:
        """The tab you're in."""
        return self._focus

    @property
    def main(self) -> TalkerSession:
        """The main tab's session."""
        return self._main

    def description(self, agent: str) -> str:
        return self._descriptions.get(agent, "")

    def name(self, agent: str) -> str:
        return "the Main Assistant" if agent == self.worker_id else agent

    def task_of(self, agent: str) -> str | None:
        return next((task for task, owner in self.open_tasks.items() if owner == agent), None)

    def task_started(self, task_id: str, agent: str) -> None:
        """A session's WORK started `task_id` on `agent`: it's open until its final update."""
        self.open_tasks[task_id] = agent

    def usage_of(self, agent: str) -> SessionUsage | None:
        """`agent`'s latest own usage as last seen, without the `usage` module."""
        return self.usage.get(agent)

    async def hub(self, name: str, **args: Any) -> Result:
        """One of the Hub's menu items (`hub.*`); the core fills in the caller, `talker`."""
        return await self.ctx.send(InvokeTool(name=name, args={k: v for k, v in args.items() if v is not None}))

    def notes_for(self, session: TalkerSession, item: Item) -> tuple[list[str], list[str]]:
        """The lines told before your message in `session`'s tab (mode, viewer, snips) and the
        snips' images. The snips go with this message and are cleared."""
        notes, images = [], []
        if (mode := self._mode_notes.pop(session.partner, None)) is not None:
            notes.append(mode)
        if self._viewer_note and session.viewer_seen < self._viewer_seq:
            notes.append(self._viewer_note)
            session.viewer_seen = self._viewer_seq
        self.ctx.log.info("Message %s: %d snip(s) attached %s, then cleared", item.input_id, len(self._snips),
                          [s.id for s in self._snips])  # fmt: skip
        for snip in self._snips:
            near = f', near "{snip.heading}"' if snip.heading else ""
            if snip.file == PASTED_FILE:
                notes.append(f"[Pasted] image (image attached; file: {snip.image_path})")
            else:
                notes.append(f"[Viewer] snip from {snip.file}{near} (image attached; file: {snip.image_path})")
            images.append(snip.image_path)
        self._snips.clear()
        return notes, images

    def send_theme(self, tags: list[tuple[str, str]], first_message: str) -> None:
        """Once, after the first input: the log folder's theme, which also creates the folder.
        The Talker's THEME tag, else the first message itself, else "chat"."""
        if self._theme_sent:
            return
        self._theme_sent = True
        themes = [argument for tag, argument in tags if tag == "THEME"] + [first_message]
        self.ctx.publish(SessionTheme(text=next((t for t in themes if theme_slug(t)), "chat")))

    def check_size(self, key: str, tokens: int, session: TalkerSession) -> None:
        """Warn once in `session`'s tab when a context (its own, or its agent's) passes the
        threshold; again only after it has come back under."""
        if not self._context_watch.crossed(key, tokens):
            return
        past = f"context is at {k_text(tokens)} tokens, past the {k_text(self._context_watch.limit)} warning"
        if key == session.id:
            session.status(f"Your own (the Talker's) {past}: every step now resends that much. "
                           "Tell the user in a sentence and offer to reset it.")  # fmt: skip
        else:  # the agent gets its own reminder (context_reminder) and hands off by itself
            whose = "The worker's" if session.main else f"{session.partner}'s"
            session.status(f"{whose} {past}. It has been reminded to find a reset point and hand off to a "
                           "fresh session by itself. Tell the user in a sentence; they don't need to reset it.")  # fmt: skip

    # --- events ---

    async def _on_input(self, event: InputReceived) -> None:
        self.session_for(event.agent_id or self._focus).put(
            Item(event.text, event.id, event.conversation_id, event.source))

    async def _on_task_updated(self, event: TaskUpdated) -> None:
        agent = event.agent_id or self.worker_id
        if event.state.is_final:
            self.open_tasks.pop(event.task_id, None)
        else:
            self.open_tasks[event.task_id] = agent
        session = self._sessions.get(agent)
        if event.kind is None and event.text.startswith("permission "):
            # Answered by someone else (e.g. the UI buttons): tell the Talker so it doesn't ask again.
            card = session.cards.pop(event.task_id, None) if session else None
            if session and event.task_id in session.answered:
                session.answered.discard(event.task_id)
            elif session and card is not None:
                session.status(f"The user answered {self.name(agent)}'s permission request in the app: {event.text}.")
            return
        if session and event.question_kind is not QuestionKind.PERMISSION:
            session.cards.pop(event.task_id, None)  # moved on: its card is gone
        if await self.restart.on_worker_update(event, agent):
            return
        if event.kind not in SPOKEN_UPDATES or event.held:
            return  # milestones are the coordinator's feed; held items wait behind their tab's !
        session = self.session_for(agent)
        if event.kind is ReportKind.PERMISSION:
            session.cards[event.task_id] = (agent, event.text)
        session.put(Item(f"[Task update: {event.kind}] {event.text}"))

    async def _on_focus(self, event: FocusChanged) -> None:
        self._focus = event.agent_id or self.worker_id
        lines: dict[str, list[str]] = {}
        for task in event.released:  # held until now: said in its own tab
            agent = task.agent_id or self._focus
            session, said = self.session_for(agent), lines.setdefault(agent, [])
            if task.reply:
                said.append(f"[Task update: {ReportKind.REPLY}] {task.reply}")
            if task.state.is_final:
                kind = ReportKind.DONE if task.state is TaskState.DONE else ReportKind.FAILED
                said.append(f"[Task update: {kind}] {task.result or ''}")
                continue
            question = task.question or ""
            if not question:
                continue
            kind = ReportKind.NEED
            if task.question_kind is QuestionKind.PERMISSION:
                kind = ReportKind.PERMISSION
                session.cards[task.id] = (agent, question)
            said.append(f"[Task update: {kind}] {question}")
        for agent, said in lines.items():
            if said:
                self.session_for(agent).put(Item("\n".join([FOCUS_OPENED, *said])))
        if self._focus != self.worker_id:
            self.session_for(self._focus)  # its tab is open: its Talker exists (it starts on its first turn)

    async def _on_suggestion(self, event: FocusSuggested) -> None:
        reason = f": {event.reason}" if event.reason else ""
        self.session_for(self._focus).put(Item(
            f"[Suggestion] {self.name(event.by or self.worker_id)} suggests the user talks to {event.agent_id} "
            f"directly{reason}. Ask them yes or no; if yes, FOCUS: {event.agent_id}.",
        ))  # fmt: skip

    async def _on_access_card(self, event: PermissionRequested) -> None:
        """A permissions handler card: said like a task's permission request, answered whole.
        It shows in the focused tab (as the temp UI puts it)."""
        session, name = self.session_for(self._focus), event.subject or event.module_id
        session.cards[ACCESS_CARD + event.request_id] = (name, access_card_text(event))
        session.put(Item(f"[Access card from {name}] {access_card_text(event)}"))

    async def _on_access_changed(self, event: PermissionChanged) -> None:
        key = ACCESS_CARD + event.request_id
        session = next((s for s in self._sessions.values() if key in s.cards), None)
        if not event.request_id or session is None:
            return
        session.cards.pop(key, None)
        if key in session.answered:
            session.answered.discard(key)
        else:
            session.status(f"The access card was answered in the app or closed: {event.text}")

    async def _on_mode(self, event: PermissionModeChanged) -> None:
        # Like the viewer note: not worth a turn of its own; it goes with your next message in that tab.
        when = " (from the next task)" if event.applies == "next_task" else ""
        self._mode_notes[event.agent_id] = f"[Mode] {event.agent_id}: {event.mode}{when}"  # the real agent, in any tab

    async def _on_viewer_tabs(self, event: ViewerTabsChanged) -> None:
        # Not worth a turn of its own: each tab's Talker hears it with your next message there.
        names = [f"{path} (showing)" if path == event.active else path for path in event.tabs]
        note = "[Viewer] open: " + ", ".join(names) if names else "[Viewer] no files open"
        if event.highlights:
            note += "; highlighted: " + ", ".join(f'"{text}" in {path}' for path, text in event.highlights)
        self._viewer_note, self._viewer_seq = note, self._viewer_seq + 1

    async def _on_usage(self, event: SessionUsage) -> None:
        if event.parent or event.agent_id == TALKER_ID or event.agent_id.startswith(TALKER_ID + ":"):
            return
        self.usage[event.agent_id] = event
        if (session := self._sessions.get(event.agent_id)) is not None:
            self.check_size(event.agent_id, event.context_tokens, session)

    async def _on_reset(self, event: ResetRequested) -> None:
        if event.agent_id == TALKER_ID:
            session = self._main
        elif event.agent_id.startswith(TALKER_ID + ":"):
            session = self._sessions.get(event.agent_id.removeprefix(TALKER_ID + ":"))
        else:
            return
        if session is not None:
            session.put(Item("", reset=True))  # not mid-turn: after the turn in progress

    async def _on_snip(self, event: ViewerClip) -> None:
        # Like the tabs note: it waits for your next message, which is likely "what is this?".
        # Every snip step is logged at info level, so a lost snip shows which step lost it.
        if len(self._snips) == MAX_SNIPS:
            self.ctx.log.info("Snip %s dropped: over the limit of %d", self._snips[0].id, MAX_SNIPS)
        self._snips.append(event)
        self.ctx.log.info("Snip %s received (%s); %d waiting", event.id, event.file, len(self._snips))

    async def _on_snip_dropped(self, event: ViewerClipDropped) -> None:
        held = any(s.id == event.id for s in self._snips)
        self._snips = deque((s for s in self._snips if s.id != event.id), maxlen=MAX_SNIPS)
        self.ctx.log.info("Snip %s dropped: the x on its thumbnail%s", event.id, "" if held else " (wasn't waiting)")
