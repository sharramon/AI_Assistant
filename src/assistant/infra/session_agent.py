"""An `ITaskAgent` backed by one `ClaudeSession`: the shared part every task agent is built from."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from enum import StrEnum
from pathlib import Path
from typing import Any

from assistant.contracts import (
    TURN_WAIT,
    AddModule,
    AgentActivity,
    AgentInfo,
    AgentState,
    AgentStateChanged,
    Command,
    ITaskAgent,
    ModuleContext,
    PermissionMode,
    PermissionModeChanged,
    ReloadModule,
    ReportKind,
    ReportTask,
    Result,
    SessionUsage,
    Task,
)
from assistant.infra.agent_profile import AUTO_ACCESS, CHROME_CLOSE_TAB, CHROME_TOOLS, MANUAL_ACCESS
from assistant.infra.agent_tags import LastLineTags, find_tags, last_line, status_lines
from assistant.infra.claude_session import ClaudeSession
from assistant.infra.context_watch import ContextWatch
from assistant.infra.handoff_keeper import (
    CHROME_FRESH,
    COMPACT,
    HANDED_OFF,
    HANDED_OFF_COMPACTED,
    WHILE_COMPACTING,
    HandoffKeeper,
)
from assistant.infra.milestone_feed import MilestoneFeed
from assistant.infra.permission_gate import CODE_LOADED, PermissionGate, summarize
from assistant.infra.show_pages import show_page
from assistant.infra.usage_meter import event_fields

NEW_TASK = "New task: {text}"
NEW_TASK_CONTEXT = "\n\nContext:\n{context}"
INTERRUPTED = (
    "[The user interrupted your task with a message. Answer it briefly; "
    "you'll be told when to continue.] {text}"
)
CONTINUE = "Continue the task from where you left off."
# The end-of-task check for an agent with Chrome whose last turn closed no tab
# (docs/next-steps/chrome-tabs-close.md).
CLOSE_TABS = (
    "[App] Before this task ends: you used Chrome in it. Close each of your Chrome tabs you don't "
    "need any more with tabs_close_mcp (tabs_context_mcp lists them); keep any the user should "
    "act on. Reply in one line, with no NEED:, HANDOFF: or other tag."
)
NEED_PREFIX = "NEED:"
HANDOFF_PREFIX = "HANDOFF:"
RELOAD_PREFIX = "RELOAD:"
ADD_MODULE_PREFIX = "ADD_MODULE:"
# Tools that edit a file, and where their input names it. scripts/hooks/edit_tracker.py
# keeps the same list (it's a standalone script and can't import this).
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
MODE_CHANGED = "The user changed your permission mode; the new rules are below."
MODE_RULES = "[App] The user switched you to {mode} mode. From now on:\n{access}"
CONTEXT_AGAIN = (
    "\n\n[App] This is a fresh session: you asked that question in an earlier one, which is gone. "
    "To pick the work up again:\n{notes}\n" + CHROME_FRESH.strip()
)
NOTE_HINT = "Your last handoff note for this work is {key}; read it first."


def default_context(key: str) -> str:
    """The notes for a question's key when its module has none of its own: the handoff note."""
    return NOTE_HINT.format(key=key) if key else ""


class _Mode(StrEnum):
    IDLE = "idle"
    WORKING = "working"            # in a turn on the task
    INTERRUPTING = "interrupting"  # interrupt sent for a message; waiting for the turn to end
    REPLYING = "replying"          # in a turn answering a message
    ASKING = "asking"              # asked the user (NEED) and dropped the task; idle once the Hub has it
    PAUSED = "paused"              # replied to a message and stays stopped (idle, still holding the task)
    CANCELLING = "cancelling"      # interrupt sent for a cancel; task already dropped
    COMPACTING = "compacting"      # a handoff kept in this session: `/compact` running, messages held
    CLOSING_TABS = "closing_tabs"  # the task's final reply is in; its Chrome tabs are being closed
    SETTLING = "settling"          # the turn ended (`turn_end` sent): the Hub says wait or done


_IDLE_MODES = (_Mode.IDLE, _Mode.PAUSED)


class SessionTaskAgent(ITaskAgent):
    """Turns the Hub's `assign`, `message`, and `cancel` into messages for a session, and the
    session's events into `ReportTask` commands, `AgentActivity`, and `AgentStateChanged`.

    The orchestrator of a task agent: it keeps the task's state machine and decides; its
    separate jobs are composed parts. `PermissionGate` holds the one open question to the user
    (tool requests, approvals, the Auto policy and the `git push` block); `HandoffKeeper`
    counts handoffs; a `LastLineTags` table maps a turn's last line (`NEED:`, `RELOAD:`,
    `ADD_MODULE:`, `HANDOFF:`) to its handler; `MilestoneFeed` holds the Hub's notes.

    Never waits on a turn: every method returns once its message or interrupt is
    written, and the rest happens as the session's events arrive. Sets itself
    as the session's `on_event`. One task at a time.

    With `fresh_sessions`, each task starts in a new `claude` process, so its
    context holds only that task. A turn whose last line is `HANDOFF: <note>`
    continues the same task in a fresh session told to read that note, up to
    `max_handoffs` times per task; then it asks the user (a `need` report).

    Two states outside: active or idle (`info().state`). A `NEED:` question ends the turn and
    drops the task: the agent is idle at once (once the Hub has the report) and takes new work;
    the Hub keeps the task, idle, holding the question and its context key (`set_context`'s
    `key(task_id)`, else the task's last handoff note). The answer comes back as that same task
    (`Task.question_key` set): into the live session if nothing ran since, else a fresh session
    with the module's notes for the key (`set_context`'s `notes(key)`, default the handoff note).
    Publishes `SessionUsage` whenever the session's usage changes (every call), and one
    per sub-agent whose tokens grew (`subagent_usage`).
    Opens the pages its text names with `<<SHOW: …>>` (`show_page`, through `InvokeTool`; the
    core turns the viewer on first if it's off).

    With `context_reminder` (tokens, 0 = off), the first time the session's context
    passes it during a task, the task gets the context reminder the way `message` sends
    any message (interrupt, then carry on), asking it to hand off at a safe point. Once
    per crossing: a fresh session re-arms it. While the task waits on the user (a
    question or a permission request), the reminder is held until it works again.

    With `edit_note`, the second edit to a file in a task (any of `EDIT_TOOLS`, counted
    across handoffs) gets one log line and one `AgentActivity`, once per file. It only
    reports: the note the agent reads comes from the edit hook, with the tool call, so it
    never interrupts. With `task_file`, the current task's id is written there at each
    `assign`, so tools outside the app (the edit hook) can count by task across sessions.

    Holds the `permission_mode` (in memory, Manual at every launch). The owning module
    builds each session's command for that mode (pass the session a callable). A switch
    applies at once to the running task: to Manual, a session started in Auto is switched
    to `manual_claude_mode` live; to Auto, the process keeps its Manual mode (the `git push`
    block is a launch flag) and the gate answers its permission requests, allowing
    all but `git push`. Either way the session is told the new rules with its next message
    (to Auto mid-turn: it's interrupted for them, then carries on). The next session starts
    in the mode for real.

    Working with other agents: `write_folders` (from its `AgentProfile`) goes into `info()`
    for the Hub's folder-clash check, and `named_only` for its free picks (skipped when True). Each `STATUS: <line>` in its text is reported as a
    `milestone`. `note(line)` (the Hub's feed: other agents' milestones, focus moves,
    callbacks) waits in a `MilestoneFeed` and is added, as one block, to the end of the next
    message it writes to its session: a new task, a message, or its own `Continue`.

    Chrome (`compact_handoffs`, `close_tabs`: on for an agent started with `--chrome`): a
    handoff compacts this session, so its tab group stays. At the task's end, if the task used
    Chrome tools and its last turn closed no tab, one more turn (`CLOSE_TABS`) asks it to close
    the tabs it no longer needs; the done report keeps the real final text. A message in that
    turn waits for it, then goes in as any message, and the task carries on. A question, a
    handoff, a cancel or a failure closes nothing.
    """

    def __init__(
        self,
        session: ClaudeSession,
        ctx: ModuleContext,
        agent_id: str,
        description: str,
        capabilities: tuple[str, ...] = (),
        cancel_timeout: float = 5.0,
        permission_timeout: float = 600.0,
        fresh_sessions: bool = True,
        max_handoffs: int = 3,
        manual_claude_mode: str = "acceptEdits",
        context_reminder: int = 0,
        edit_note: bool = False,
        task_file: str | Path | None = None,
        write_folders: tuple[str, ...] = (),
        compact_handoffs: Callable[[], bool] = lambda: False,
        close_tabs: Callable[[], bool] = lambda: False,
        named_only: bool = False,
    ):
        self._named_only = named_only  # `info().named_only`: a free pick skips it
        self._session = session
        self._close_tabs = close_tabs  # True for an agent with Chrome (chrome-tabs-close.md)
        self._chrome_used = False  # the task used a Chrome tool since its tabs were last checked
        self._closed_tab = False  # the current turn closed a Chrome tab
        self._done_text = ""  # the final reply, held while its tabs are closed
        # True for an agent with Chrome: a handoff compacts this session instead of starting a
        # new one, since its tab group belongs to the session id (chrome-tab-after-reset.md).
        self._compact_handoffs = compact_handoffs
        self._compact_note = ""  # the handoff note of the compact running now
        self._write_folders = tuple(write_folders)
        self._feed = MilestoneFeed()
        self._ctx = ctx
        self._agent_id = agent_id
        self._description = description
        self._capabilities = capabilities
        self._cancel_timeout = cancel_timeout
        self._fresh_sessions = fresh_sessions
        self._handoffs = HandoffKeeper(max_handoffs)
        self._asked: str | None = None  # the task whose question the live session still has
        self._ended: set[str] = set()  # tasks whose DONE / FAILED report the Hub hasn't taken yet
        self._last_note = ""  # the current task's latest handoff note
        self._question_key: Callable[[str], str] = lambda _task_id: ""
        self._context_notes: Callable[[str], str] = default_context
        self._manual_claude_mode = manual_claude_mode
        self._permission_mode = PermissionMode.MANUAL
        self._live_mode = PermissionMode.MANUAL  # what the running process is in now
        self._told_mode = PermissionMode.MANUAL  # the rules the running session was last given
        self._mode_note: PermissionMode | None = None  # new rules for its next message
        self._used = False  # the running session has had a message since it started
        self._session_lock = asyncio.Lock()  # one session start or restart at a time
        self._published_usage: tuple[int, int] | None = None  # context, used
        self._published_subagents: dict[str, int] = {}  # each sub-agent's tokens, as last published
        self._task: Task | None = None
        self._mode = _Mode.IDLE
        self._pending: list[str] = []  # messages waiting for the interrupt to land
        self._resume = True
        self._settled_outcome: str | None = None  # an approval's outcome that came while settling
        self._settle_closed_tab = False  # the settled turn closed a Chrome tab itself
        self._reports: asyncio.Queue[ReportTask] = asyncio.Queue()
        self._background: set[asyncio.Task] = set()
        self._report_worker: asyncio.Task | None = None
        self._published = AgentState.IDLE
        self._context_watch = ContextWatch(context_reminder)
        self._remind_at: int | None = None  # context size of a reminder due, sent once the task is working
        self._edit_note = edit_note
        self._task_file = Path(task_file) if task_file else None
        self._edits: dict[str, int] = {}  # edits per file in the current task
        self._gate = PermissionGate(
            session,
            timeout=permission_timeout,
            mode=lambda: self._permission_mode,
            task=lambda: self._task,
            activity=self._activity,
            report=self._report,
            send=self._send_outcome,
            spawn=self._spawn,
            log=ctx.log,
            parked=self._on_parked,
        )
        self._last_line = (
            LastLineTags()
            .add(NEED_PREFIX, self._on_need)
            .add(RELOAD_PREFIX, self._on_reload)
            .add(ADD_MODULE_PREFIX, self._on_add_module)
            .add(HANDOFF_PREFIX, self._on_handoff)
        )
        session.on_event = self._on_event

    @property
    def permission_mode(self) -> PermissionMode:
        """The mode the next session starts in."""
        return self._permission_mode

    @property
    def write_folders(self) -> tuple[str, ...]:
        """The folders it may write, for the Hub's folder-clash check (`info().write_folders`)."""
        return self._write_folders

    @write_folders.setter
    def write_folders(self, folders: tuple[str, ...]) -> None:
        """A live grant changed them (`ProfileAgent.set_access`): the next `info()` says so."""
        self._write_folders = tuple(folders)

    def set_context(self, key: Callable[[str], str], notes: Callable[[str], str]) -> None:
        """The owning module's hook for questions: `key(task_id)` is a question's context key (""
        for none: the task's last handoff note is used), `notes(key)` what a fresh session needs to
        pick the work up again when the answer comes ("" for nothing)."""
        self._question_key, self._context_notes = key, notes

    @property
    def state(self) -> AgentState:
        return AgentState.IDLE if self._mode in _IDLE_MODES else AgentState.ACTIVE

    @property
    def has_task(self) -> bool:
        """It holds a task (in a turn, or stopped on one): a reload or a restart would cut it."""
        return self._task is not None or self._mode is not _Mode.IDLE

    def info(self) -> AgentInfo:
        return AgentInfo(
            agent_id=self._agent_id,
            description=self._description,
            capabilities=self._capabilities,
            state=self.state,
            permission_mode=self._permission_mode,
            write_folders=self._write_folders,
            named_only=self._named_only,
        )

    def note(self, text: str) -> None:
        """A background line for the next message to the session; never interrupts or starts work."""
        self._feed.add(text)

    def _with_feed(self, text: str) -> str:
        """`text` with new permission rules (after a live mode switch) and the waiting feed
        lines at its end (at the end, so a message's start stays its own)."""
        if self._mode_note is not None:
            mode, self._mode_note = self._mode_note, None
            self._told_mode = mode
            access = AUTO_ACCESS if mode is PermissionMode.AUTO else MANUAL_ACCESS
            text = f"{text}\n\n{MODE_RULES.format(mode=str(mode).capitalize(), access=access)}"
        block = self._feed.take()
        return f"{text}\n\n{block}" if block else text

    async def assign(self, task: Task) -> Result:
        """A new task, or (with `question_key`) the answer to a question asked in `task.id`. A task
        it was stopped on (paused) is dropped for it."""
        if self._mode not in _IDLE_MODES:
            return Result.not_available(f"{self._agent_id} is active")
        live = task.question_key is not None and task.id == self._asked and self._session.running
        if self._mode is _Mode.PAUSED:
            self._ctx.log.info("%s drops its stopped task %s for %s", self._agent_id, self._task and self._task.id, task.id)
            self._task, self._mode = None, _Mode.IDLE
            self._gate.clear()  # a card it was paused on goes with it
        try:
            if not live:
                await self._fresh_session(restart=self._fresh_sessions)
        except Exception as exc:
            self._ctx.log.exception("Couldn't start the session")
            return Result.failed(f"{self._agent_id} couldn't start: {exc}")
        # Set before writing: the turn's events may arrive while send drains.
        self._task, self._mode, self._asked = task, _Mode.WORKING, None
        self._gate.unpark(task.id)  # given back before its approval's outcome came: it's this task's again
        if not live:
            self._handoffs.reset()
            self._edits = {}
            self._last_note = ""
            self._chrome_used = False
        self._write_task_file(task.id)
        try:
            await self._session.send(self._with_feed(self._first_text(task, live)))
            self._used = True
        except Exception as exc:
            self._task, self._mode = None, _Mode.IDLE
            return Result.failed(f"{self._agent_id} couldn't take the task: {exc}")
        self._publish_state()
        return Result.ok()

    def _first_text(self, task: Task, live: bool) -> str:
        """A new task's first message; an answer as it is (the live session has the question), or
        with the module's notes for its key (a fresh session doesn't)."""
        if task.question_key is None:
            return _task_text(NEW_TASK, task)
        if live:
            return task.text
        notes = self._context_notes(task.question_key) if task.question_key else ""
        return task.text + (CONTEXT_AGAIN.format(notes=notes) if notes else "")

    async def set_permission_mode(self, mode: PermissionMode) -> Result:
        """Set the mode; it applies at once (`now`). With no task, the next session starts in
        it. Mid-task, to Manual: a process started in Auto is switched live (`next_task` only
        if that fails); the agent stops answering requests itself, so cards come back. To
        Auto: an open tool request is answered (allowed, or refused for `git push`) and later
        ones too; mid-turn the session is interrupted to read the Auto rules, then carries on.
        The value is True when an open tool request was answered, so the Hub closes its card."""
        mode = PermissionMode(mode)
        self._permission_mode = mode
        applies, answered = "now", False
        live = self._task is not None and self._session.running
        if live and mode is PermissionMode.MANUAL and self._live_mode is not mode:
            try:
                await self._session.set_permission_mode(self._manual_claude_mode)
                self._live_mode = mode
            except Exception as exc:
                self._ctx.log.warning("Couldn't switch the running session to Manual: %s", exc)
                applies = "next_task"
        when = "" if applies == "now" else " (from the next task)"
        self._ctx.log.info("%s permission mode: %s%s", self._agent_id, mode, when)
        self._activity(f"permission mode: {mode}{when}")
        if live and applies == "now":
            if mode is PermissionMode.AUTO:  # before the interrupt, so the tool's turn ends cleanly
                answered = await self._gate.answer_open_in_auto()
            await self._tell_mode(mode)
        self._ctx.publish(PermissionModeChanged(agent_id=self._agent_id, mode=mode, applies=applies))
        return Result.ok(answered)

    async def _tell_mode(self, mode: PermissionMode) -> None:
        """Give the running session `mode`'s rules with its next message; to Auto mid-turn,
        interrupt it for them now (it then carries on)."""
        self._mode_note = None if mode is self._told_mode else mode
        if self._mode_note is PermissionMode.AUTO and self._task is not None and self._session.working \
                and self._mode in (_Mode.WORKING, _Mode.INTERRUPTING):
            await self.message(self._task.id, MODE_CHANGED)  # the rules ride on its delivery

    async def reset(self) -> Result:
        """Start fresh: when idle, close the session now (the next task starts a new one);
        with a task, ask it to write a handoff, which continues it in a fresh session."""
        if self._task is None:
            if self._mode is not _Mode.IDLE:
                return Result.not_available(f"{self._agent_id} is still stopping its last task")
            await self._session.close()
            self._used = False
            self._publish_usage()
            return Result.ok()
        return await self.message(self._task.id, HandoffKeeper.reset_request(self._task.id))

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        if self._mode is _Mode.ASKING and task_id == self._asked:  # its question is on the way to the Hub
            return Result.not_available(f"{self._agent_id} has just asked a question in {task_id}; try again")
        if task_id in self._ended:  # its end report is on the way: the Hub mustn't mark it failed
            return Result.not_available(f"{self._agent_id} has just ended {task_id}; try again")
        if not self._is_current(task_id):
            return Result.invalid_arguments(f"{task_id!r} is not {self._agent_id}'s current task")
        if self._mode is _Mode.COMPACTING:  # a compact can't take a message: it goes in after it
            self._pending.append(text)
            return Result.ok()
        if self._mode in (_Mode.CLOSING_TABS, _Mode.SETTLING):  # the task carries on with it after
            self._pending.append(text)
            self._resume = resume
            return Result.ok()
        try:
            in_turn = self._session.working or self._mode is _Mode.INTERRUPTING
            if self._mode in (_Mode.WORKING, _Mode.REPLYING, _Mode.INTERRUPTING) and in_turn:
                if not self._gate.approval_open():  # an approval outlives the turn; a tool request doesn't
                    self._gate.drop()  # the interrupt ends the turn, and the request with it
                self._pending.append(text)
                self._resume = resume
                if self._mode is not _Mode.INTERRUPTING:
                    self._mode = _Mode.INTERRUPTING
                    await self._session.interrupt()
            elif resume:  # paused: nothing to interrupt, the text is the next message
                self._mode = _Mode.WORKING
                await self._session.send(self._with_feed(text))
            else:
                self._resume = False
                self._mode = _Mode.REPLYING
                await self._session.send(self._with_feed(INTERRUPTED.format(text=text)))
        except Exception as exc:
            return Result.failed(f"Couldn't deliver the message: {exc}")
        self._publish_state()
        return Result.ok()

    async def cancel(self, task_id: str) -> Result:
        if not self._is_current(task_id):
            return Result.invalid_arguments(f"{task_id!r} is not {self._agent_id}'s current task")
        self._task = None
        self._pending.clear()
        self._gate.drop()
        if self._mode in (_Mode.PAUSED, _Mode.SETTLING):  # no turn running
            self._mode = _Mode.IDLE
        else:
            self._mode = _Mode.CANCELLING
            try:
                await self._session.interrupt()
            except Exception:
                await self._session.close()
                self._mode = _Mode.IDLE
            else:
                self._spawn(self._cancel_fallback())
        self._publish_state()
        return Result.ok()

    async def answer_permission(self, task_id: str, allow: bool) -> Result:
        if task_id == self._gate.parked and not self._is_current(task_id):  # it ended waiting on this card
            return await self._gate.answer_parked(task_id, allow)
        if not self._is_current(task_id):
            return Result.invalid_arguments(f"{task_id!r} is not {self._agent_id}'s current task")
        return await self._gate.answer(allow)

    async def request_approval(self, action: str, run: Callable[[], Awaitable[Result]]) -> Result:
        """Ask the user to allow `action` on the current task (the permission card); in Auto
        (this agent's own mode) it runs at once, no card. On Allow `run` runs; its outcome is the
        task's next message. Until then the task waits: a turn that ends meanwhile doesn't count
        as done."""
        if self._task is None:
            return Result.not_available(f"{self._agent_id} has no task to ask on")
        if self._gate.request is not None:
            return Result.not_available(f"{self._agent_id} already has a question open for the user")
        self._gate.ask(action, run)
        return Result.ok()

    async def close(self) -> None:
        """Stop the background work. The owning module closes the session itself."""
        self._gate.drop()
        tasks = [*self._background, *([self._report_worker] if self._report_worker else [])]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- session events ---

    def _on_event(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                self._on_block(block)
        elif kind == "result":
            self._on_result(event)
        elif kind == "control_request" and event.get("request", {}).get("subtype") == "can_use_tool":
            accepting = self._task is not None and self._mode in (_Mode.WORKING, _Mode.REPLYING, _Mode.CLOSING_TABS)
            self._gate.on_tool_request(event, accepting)
        elif kind == "exit":
            self._on_exit()
        self._publish_state()
        self._publish_usage()

    def _on_block(self, block: dict[str, Any]) -> None:
        if block.get("type") == "text" and block.get("text", "").strip():
            text = block["text"].strip()
            self._activity(text)
            self._show_tags(text)
            if self._mode is _Mode.WORKING:
                self._report(ReportKind.PROGRESS, text)
            for status in status_lines(text):
                self._report(ReportKind.MILESTONE, status)
        elif block.get("type") == "tool_use":
            self._activity(f"→ {block.get('name')} {summarize(block.get('input', {}))}")
            self._count_edit(block)
            self._note_chrome(block.get("name") or "")

    def _note_chrome(self, name: str) -> None:
        """Whether the task used Chrome, and whether this turn closed a tab (`CLOSE_TABS`)."""
        if self._task is not None and name.startswith(CHROME_TOOLS):
            self._chrome_used = True
            self._closed_tab = self._closed_tab or name == CHROME_CLOSE_TAB

    def _show_tags(self, text: str) -> None:
        """Open the pages the agent names with `<<SHOW: path>>` or `<<SHOW: path | "quote" | heading>>`,
        through `InvokeTool` (the core starts the viewer if it's off). Never waits on it."""
        for tag in find_tags(text, ("SHOW",)):
            if tag.argument:
                self._spawn(self._show(tag.argument))

    async def _show(self, argument: str) -> None:
        show, result = outcome = await show_page(self._ctx, argument)
        if not result.is_ok:
            self._ctx.log.warning("Couldn't show %s: %s", show.path, result.error)
            self._activity(f"couldn't show {show.path}: {result.error}")
        elif outcome.quote_missing:
            self._ctx.log.warning("Opened %s, but the text to highlight isn't on the page", show.path)

    def _count_edit(self, block: dict[str, Any]) -> None:
        """Log the second edit to a file in the task, once per file (the hook gives the agent its note)."""
        key = EDIT_TOOLS.get(block.get("name", ""))
        path = (block.get("input") or {}).get(key) if key else None
        if not self._edit_note or self._task is None or not path:
            return
        file = str(path).replace("\\", "/").rstrip("/").lower()
        self._edits[file] = count = self._edits.get(file, 0) + 1
        if count == 2:
            self._ctx.log.info("batching note for task %s: %s edited twice", self._task.id, path)
            self._activity(f"batching note: {file.rsplit('/', 1)[-1]}")

    def _write_task_file(self, task_id: str) -> None:
        if self._task_file is None:
            return
        try:
            self._task_file.parent.mkdir(parents=True, exist_ok=True)
            self._task_file.write_text(task_id, encoding="utf-8")
        except OSError as exc:
            self._ctx.log.warning("Couldn't write the task file %s: %s", self._task_file, exc)

    def _on_result(self, event: dict[str, Any]) -> None:
        text = (event.get("result") or "").strip()
        is_error = bool(event.get("is_error"))
        match self._mode:
            case _Mode.WORKING:
                self._finish_turn(text, is_error, event.get("subtype"))
            case _Mode.INTERRUPTING if is_error:  # the interrupt we sent ended the turn
                pending, self._pending = "\n".join(self._pending), []
                self._mode = _Mode.REPLYING
                self._spawn(self._send(INTERRUPTED.format(text=pending)))
            case _Mode.INTERRUPTING:  # the turn finished on its own before the interrupt landed
                self._ctx.log.warning("Turn ended before the interrupt; dropping message %r", self._pending)
                self._pending.clear()
                self._finish_turn(text, False, None)
            case _Mode.REPLYING:
                self._report(ReportKind.REPLY, text)
                if (note := last_line(text, HANDOFF_PREFIX)) is not None:  # e.g. asked to reset
                    self._mode = _Mode.WORKING
                    self._on_handoff(note)
                elif self._resume:
                    self._mode = _Mode.WORKING
                    outcome = self._gate.take_after_turn()  # an approval answered meanwhile
                    self._spawn(self._send(outcome or CONTINUE))
                else:
                    self._mode = _Mode.PAUSED
            case _Mode.CANCELLING:
                self._mode = _Mode.IDLE
            case _Mode.COMPACTING:
                self._after_compact(is_error)
            case _Mode.CLOSING_TABS:
                self._after_closing_tabs(is_error)
            case _:
                self._ctx.log.debug("Ignored a result while %s", self._mode)
        self._closed_tab = False  # the next turn starts with none closed

    def _finish_turn(self, text: str, is_error: bool, subtype: str | None) -> None:
        if is_error:
            self._report(ReportKind.FAILED, text or f"The turn ended with an error ({subtype})")
            self._end_task()
        elif (outcome := self._gate.take_after_turn()) is not None:  # an approval answered during the turn
            self._spawn(self._send(outcome))
        elif self._gate.waiting and self._gate.request is None:  # an approved action is running: wait
            self._activity("waiting for the approved action's outcome")
        elif self._gate.waiting:  # its card is still open: the task ends waiting on it
            self._settle(text)
        elif self._last_line.dispatch(text):
            if self._task is not None and self._gate.request is not None:  # its last line asked on a card
                self._settle(text)
        else:  # no tag: done, unless the Hub says it waits on a child task
            self._settle(text)

    def _settle(self, text: str) -> None:
        """The turn is over and nothing in it continues the task: report `turn_end` with the
        task's context key; the Hub answers wait or done (`_after_settle`). Messages meanwhile
        wait (`message`)."""
        self._mode, self._done_text, self._settle_closed_tab = _Mode.SETTLING, text, self._closed_tab
        key = self._question_key(self._task.id) or self._last_note if self._task else ""
        self._report(ReportKind.TURN_END, text, key=key, card_open=self._gate.request is not None)

    def _after_settle(self, task_id: str, result: Result) -> None:
        """The Hub's answer to `turn_end`. Wait: the task ends waiting (`_drop_waiting`). Done
        (or a refusal): the task ends as before; what came meanwhile (an approval's outcome, a
        message) carries it on instead."""
        if self._mode is not _Mode.SETTLING or not self._is_current(task_id):
            return  # cancelled meanwhile
        outcome, self._settled_outcome = self._settled_outcome, None
        held, self._pending = "\n".join(self._pending), []
        if result.is_ok and result.value == TURN_WAIT:
            self._drop_waiting(task_id, "\n\n".join(t for t in (outcome, held) if t))
            return
        if outcome is not None or held:
            texts = [t for t in (outcome, INTERRUPTED.format(text=held) if held else None) if t]
            self._mode = _Mode.WORKING if outcome is not None else _Mode.REPLYING
            self._spawn(self._send("\n\n".join(texts)))
            return
        if self._gate.waiting:  # its card was answered meanwhile and the action is running: as before
            self._mode = _Mode.WORKING
            self._activity("waiting for the approved action's outcome")
            return
        if self._chrome_used and not self._settle_closed_tab and self._close_tabs() and self._session.running:
            self._mode = _Mode.CLOSING_TABS
            self._activity("closing the Chrome tabs it no longer needs")
            self._spawn(self._send(CLOSE_TABS))
            return
        self._report(ReportKind.DONE, self._done_text)
        self._end_task()
        self._publish_state()

    async def _send_outcome(self, text: str) -> None:
        """An approval's outcome for the session (the gate's `send`): held while settling."""
        if self._mode is _Mode.SETTLING:
            self._settled_outcome = text
            return
        await self._send(text)

    def _drop_waiting(self, task_id: str, came: str) -> None:
        """The Hub ended the task waiting: drop it like a question (the live session kept, so the
        input that starts it again goes on here if nothing ran since) and be free. Its open
        approval stays in the gate for it. What came while it settled goes back to the Hub, which
        gives the task back with it."""
        self._activity("ended waiting: the Hub keeps its note, and starts it again when that comes")
        self._asked = task_id
        self._gate.park(task_id)
        self._task, self._mode = None, _Mode.IDLE
        self._pending.clear()
        self._publish_state()
        if came:
            self._on_parked(task_id, came)

    def _on_parked(self, task_id: str, text: str) -> None:
        """New input for a task this agent dropped waiting (an approval's outcome): to the Hub
        as that task's `progress`; the Hub gives the task back with it."""
        self._report(ReportKind.PROGRESS, text, task_id=task_id)

    def _after_closing_tabs(self, is_error: bool) -> None:
        """Report the task done with its real final text; a message that came meanwhile goes in
        as any message instead, and the task carries on."""
        if is_error:
            self._ctx.log.warning("%s couldn't close its Chrome tabs; the task ends anyway", self._agent_id)
        self._chrome_used = False  # checked: Chrome used after this asks again
        held, self._pending = "\n".join(self._pending), []
        if held:
            self._mode = _Mode.REPLYING
            self._spawn(self._send(INTERRUPTED.format(text=held)))
            return
        self._report(ReportKind.DONE, self._done_text)
        self._end_task()

    # --- last-line tags (the `_last_line` table) ---

    def _on_need(self, question: str) -> bool:
        self._ask_user(question, live=True)
        return True

    def _ask_user(self, question: str, live: bool) -> None:
        """Report the question with its context key and drop the task: the agent turns idle
        once the Hub has the report (`_send_reports`). With `live`, the answer may carry on in
        this session; otherwise it starts a fresh one."""
        task = self._task
        if task is None:
            return
        self._report(ReportKind.NEED, question, key=self._question_key(task.id) or self._last_note)
        self._asked = task.id if live else None
        self._task, self._mode = None, _Mode.ASKING
        self._pending.clear()
        self._gate.clear()

    def _on_reload(self, argument: str) -> bool:
        """`RELOAD: <module id> [now]`."""
        request = reload_request(argument)
        return request is not None and self._ask_to_load(*request)

    def _on_add_module(self, argument: str) -> bool:
        """`ADD_MODULE: <package>`."""
        request = add_module_request(argument)
        return request is not None and self._ask_to_load(*request)

    def _on_handoff(self, note: str) -> bool:
        """Continue the task in a fresh session that reads `note`, or ask the user after too many:
        a question like any other, whose answer starts a fresh session (with a fresh allowance)
        pointed at the note."""
        self._last_note = note
        if not self._handoffs.take():
            self._ask_user(self._handoffs.too_many(note), live=False)
            return True
        compact = self._can_compact()
        self._report(ReportKind.PROGRESS, self._handoffs.progress(note, compacted=compact))
        if compact:
            self._mode, self._compact_note = _Mode.COMPACTING, note  # now, so a message waits for it
            self._spawn(self._compact(note))
        else:
            self._spawn(self._continue_fresh(note))
        return True

    def _can_compact(self) -> bool:
        """Keep the session on a handoff: an agent with Chrome, a live session in the right mode."""
        stale = self._live_mode is not self._permission_mode
        return self._compact_handoffs() and self._session.running and not stale

    async def _compact(self, note: str) -> None:
        """`/compact` in this session (sent bare: a slash command takes no feed). Its result
        arrives in `_on_result` as `COMPACTING`, which goes on with `_after_compact`."""
        self._activity(f"compacting the context for the handoff in {note} (the Chrome tabs stay)")
        try:
            await self._session.send(COMPACT.format(note=note))
            self._used = True
        except Exception:
            self._ctx.log.exception("Couldn't compact the session; starting a fresh one")
            self._after_compact(is_error=True)

    def _after_compact(self, is_error: bool) -> None:
        """Carry on in the compacted session with the note and any messages that came meanwhile;
        a failed compact falls back to a fresh session (the tabs are lost, the note says where)."""
        note, task = self._compact_note, self._task
        held = "".join(WHILE_COMPACTING.format(text=text) for text in self._pending)
        self._pending.clear()
        if task is None:  # cancelled meanwhile
            return
        self._mode = _Mode.WORKING
        if is_error:
            self._ctx.log.warning("The compact for task %s failed; a fresh session reads %s", task.id, note)
            self._spawn(self._continue_fresh(note, held))
            return
        self._remind_at = None  # the compacted context is small again
        self._activity(f"context compacted, reading the handoff in {note}")
        self._spawn(self._send(_task_text(HANDED_OFF_COMPACTED, task, note=note) + held))

    def _ask_to_load(self, command: Command, action: str) -> bool:
        """Run a reload or add the agent asked for: at once in Auto, after the user allows it in
        Manual (the same permission card as a tool). The outcome goes back as the next message."""
        if isinstance(command, ReloadModule) and command.module_id == self._agent_id:
            self._spawn(self._send(CODE_LOADED.format(
                action=action, outcome="refused: you can't reload yourself during a task. Tell the user it's needed.",
            )))  # fmt: skip
            return True

        def run() -> Awaitable[Result]:
            return self._ctx.send(command)

        self._gate.ask(action, run)  # in Auto it runs at once (the gate's one check)
        return True

    async def _continue_fresh(self, note: str, held: str = "") -> None:
        task = self._task
        try:
            await self._fresh_session(restart=True)
        except Exception:
            self._ctx.log.exception("Couldn't start a fresh session for the handoff")
            self._on_exit()
            return
        if self._task is task and self._mode is _Mode.WORKING:  # not cancelled meanwhile
            self._activity(f"fresh session, reading the handoff in {note}")
            await self._send(_task_text(HANDED_OFF, task, note=note) + held)

    async def _fresh_session(self, restart: bool) -> None:
        """Make sure a session is running in the current mode; with `restart`, a new one if
        this one has been used. A session in another mode is always replaced."""
        async with self._session_lock:
            stale = self._live_mode is not self._permission_mode
            if self._session.running and (stale or (restart and self._used)):
                await self._session.close()
            if not self._session.running:
                await self._start_session()
        self._publish_usage()

    async def _start_session(self) -> None:
        await self._session.start()  # its command reads the current mode
        self._used = False
        self._live_mode = self._told_mode = self._permission_mode
        self._mode_note = None  # its prompt has the rules
        self._remind_at = None  # a new session starts small: a held reminder no longer applies

    async def restart_session(self) -> bool:
        """Close the session and start a new one so it re-reads its command, but only if no task has
        it: False when one arrived first. Holds the session lock, so a task assigned meanwhile waits
        for the new session and the two never close and start the same process at once."""
        async with self._session_lock:
            if self._mode is not _Mode.IDLE:
                return False
            await self._session.close()
            await self._start_session()
        self._publish_usage()
        return True

    def _on_exit(self) -> None:
        if self._task is not None and self._mode is _Mode.CLOSING_TABS:  # its work was done
            self._report(ReportKind.DONE, self._done_text)
        elif self._task is not None:
            self._report(ReportKind.FAILED, "The agent's claude process exited")
        self._end_task()

    def _end_task(self) -> None:
        self._task, self._mode = None, _Mode.IDLE
        self._pending.clear()
        self._gate.clear()

    # --- helpers ---

    def _is_current(self, task_id: str) -> bool:
        return self._task is not None and self._task.id == task_id

    async def _send(self, text: str) -> None:
        try:
            await self._session.send(self._with_feed(text))
            self._used = True
        except Exception:
            self._ctx.log.exception("Couldn't write to the session")
            self._on_exit()
        self._publish_state()

    async def _cancel_fallback(self) -> None:
        await asyncio.sleep(self._cancel_timeout)
        if self._mode is _Mode.CANCELLING:
            self._ctx.log.warning("Interrupt didn't stop the turn; closing the session")
            await self._session.close()
            self._mode = _Mode.IDLE
            self._publish_state()

    def _report(self, kind: ReportKind, text: str, key: str = "", card_open: bool = False,
                task_id: str = "") -> None:  # fmt: skip
        """Queue a report on the current task (or `task_id`, one it dropped). One worker sends
        them in order, so the Hub sees them as they happened."""
        task_id = task_id or (self._task.id if self._task else "")
        if not task_id:
            return
        if kind in (ReportKind.DONE, ReportKind.FAILED):
            self._ended.add(task_id)
        self._reports.put_nowait(ReportTask(task_id=task_id, kind=kind, text=text, key=key,
                                            card_open=card_open))  # fmt: skip
        if self._report_worker is None or self._report_worker.done():
            self._report_worker = asyncio.create_task(self._send_reports(), name=f"{self._agent_id}:reports")

    async def _send_reports(self) -> None:
        while True:
            report = await self._reports.get()
            result = await self._ctx.send(report)
            if report.kind in (ReportKind.DONE, ReportKind.FAILED):
                self._ended.discard(report.task_id)
            if not result.is_ok:
                self._ctx.log.warning("Hub refused %s report: %s", report.kind, result.error)
            if report.kind is ReportKind.TURN_END:
                self._after_settle(report.task_id, result)
            if report.kind is ReportKind.NEED and self._mode is _Mode.ASKING:  # the Hub has the question
                self._mode = _Mode.IDLE
                self._publish_state()

    def _activity(self, text: str) -> None:
        task_id = self._task.id if self._task else None
        self._ctx.publish(AgentActivity(agent_id=self._agent_id, task_id=task_id, text=text))

    def _publish_state(self) -> None:
        state = self.state
        if state is not self._published:
            self._published = state
            self._ctx.publish(AgentStateChanged(agent_id=self._agent_id, state=state))

    def _publish_usage(self) -> None:
        usage = session_usage(self._agent_id, self._session)
        numbers = (usage.context_tokens, usage.used_tokens)
        if numbers != self._published_usage:
            self._published_usage = numbers
            self._ctx.publish(usage)
        for sub in subagent_usage(self._agent_id, self._session):  # each sub-agent when its tally grows
            if self._published_subagents.get(sub.agent_id) != sub.used_tokens:
                self._published_subagents[sub.agent_id] = sub.used_tokens
                self._ctx.publish(sub)
        if self._context_watch.crossed(self._agent_id, usage.context_tokens):
            self._remind_at = usage.context_tokens
        if self._remind_at is not None and self._can_remind():
            tokens, self._remind_at = self._remind_at, None
            self._spawn(self._remind(tokens))

    def _can_remind(self) -> bool:
        """In a turn on the task, not waiting on the user's answer or permission."""
        return self._task is not None and self._mode is _Mode.WORKING and self._gate.request is None

    async def _remind(self, tokens: int) -> None:
        """Ask the task to find a reset point and hand off. Held again if it's no longer working."""
        if not self._can_remind():
            if self._task is not None:
                self._remind_at = tokens
            return
        task_id, size, limit = self._task.id, _k(tokens), _k(self._context_watch.limit)
        self._ctx.log.info("context %s past %s: reminded task %s to find a reset point", size, limit, task_id)
        self._activity(f"context reminder sent ({size})")
        result = await self.message(task_id, HandoffKeeper.reminder(size, limit, task_id))
        if not result.is_ok:
            self._ctx.log.warning("Couldn't send the context reminder: %s", result.error)

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)


def reload_request(argument: str) -> tuple[ReloadModule, str] | None:
    """`RELOAD: <module id> [now]`'s argument as a command and its description, or None if empty."""
    words = argument.replace("`", " ").split()
    if not words:
        return None
    now = len(words) > 1 and words[1].lower() == "now"
    action = f"Reload the {words[0]} module with its new code" + (", now (cuts in)" if now else "")
    return ReloadModule(module_id=words[0], now=now), action


def add_module_request(argument: str) -> tuple[AddModule, str] | None:
    """`ADD_MODULE: <package>`'s argument as a command and its description, or None if empty."""
    words = argument.replace("`", " ").split()
    return (AddModule(package=words[0]), f"Add the new module {words[0]}") if words else None


def session_usage(agent_id: str, session: ClaudeSession) -> SessionUsage:
    """`session`'s usage so far as a `SessionUsage` event; context 0 when it isn't running."""
    return SessionUsage(
        agent_id=agent_id,
        context_tokens=session.context_tokens if session.running else 0,
        session=session.id,
        **event_fields(session.used),
    )


def subagent_usage(agent_id: str, session: ClaudeSession) -> list[SessionUsage]:
    """One `SessionUsage` per sub-agent `session` has started (`kind="subagent"`, `parent` set,
    id `<agent_id>/<type> #<agentId>`): its tokens, with `session`'s id."""
    return [
        SessionUsage(
            agent_id=f"{agent_id}/{sub['type']} #{key}",
            parent=agent_id,
            kind="subagent",
            session=session.id,
            context_tokens=0,
            **event_fields(sub["used"]),
        )
        for key, sub in session.subagents.items()
    ]


def _k(tokens: int) -> str:
    return f"{round(tokens / 1000)}k"


def _task_text(template: str, task: Task, **fields: str) -> str:
    text = template.format(text=task.text, **fields)
    if task.context:
        text += NEW_TASK_CONTEXT.format(context=task.context)
    return text
