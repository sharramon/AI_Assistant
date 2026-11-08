"""An `ITaskAgent` backed by one `ClaudeSession`: the shared part every task agent is built from."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from enum import StrEnum
from pathlib import Path
from typing import Any

from assistant.contracts import (
    AddModule,
    AgentActivity,
    AgentInfo,
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
from assistant.infra.agent_profile import AUTO_ACCESS, MANUAL_ACCESS
from assistant.infra.agent_tags import LastLineTags, find_tags, last_line, status_lines
from assistant.infra.claude_session import ClaudeSession
from assistant.infra.context_watch import ContextWatch
from assistant.infra.handoff_keeper import HANDED_OFF, HandoffKeeper
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
NEED_PREFIX = "NEED:"
HANDOFF_PREFIX = "HANDOFF:"
RELOAD_PREFIX = "RELOAD:"
ADD_MODULE_PREFIX = "ADD_MODULE:"
# Tools that edit a file, and where their input names it. scripts/hooks/edit_tracker.py
# keeps the same list (it's a standalone script and can't import this).
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
MODE_CHANGED = "The user changed your permission mode; the new rules are below."
MODE_RULES = "[App] The user switched you to {mode} mode. From now on:\n{access}"


class _Mode(StrEnum):
    IDLE = "idle"
    WORKING = "working"            # in a turn on the task
    INTERRUPTING = "interrupting"  # interrupt sent for a message; waiting for the turn to end
    REPLYING = "replying"          # in a turn answering a message
    WAITING = "waiting"            # asked the user something (NEED); turn ended
    PAUSED = "paused"              # replied to a message and stays stopped
    CANCELLING = "cancelling"      # interrupt sent for a cancel; task already dropped


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
    for the Hub's folder-clash check. Each `STATUS: <line>` in its text is reported as a
    `milestone`. `note(line)` (the Hub's feed: other agents' milestones, focus moves,
    callbacks) waits in a `MilestoneFeed` and is added, as one block, to the end of the next
    message it writes to its session: a new task, a message, or its own `Continue`.
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
    ):
        self._session = session
        self._write_folders = tuple(write_folders)
        self._feed = MilestoneFeed()
        self._ctx = ctx
        self._agent_id = agent_id
        self._description = description
        self._capabilities = capabilities
        self._cancel_timeout = cancel_timeout
        self._fresh_sessions = fresh_sessions
        self._handoffs = HandoffKeeper(max_handoffs)
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
        self._reports: asyncio.Queue[ReportTask] = asyncio.Queue()
        self._background: set[asyncio.Task] = set()
        self._report_worker: asyncio.Task | None = None
        self._published: tuple[bool, bool] = (False, False)
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
            send=self._send,
            spawn=self._spawn,
            log=ctx.log,
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

    def info(self) -> AgentInfo:
        return AgentInfo(
            agent_id=self._agent_id,
            description=self._description,
            capabilities=self._capabilities,
            busy=self._mode is not _Mode.IDLE,
            working=self._session.working,
            permission_mode=self._permission_mode,
            write_folders=self._write_folders,
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
        if self._mode is not _Mode.IDLE:
            return Result.not_available(f"{self._agent_id} is busy")
        try:
            await self._fresh_session(restart=self._fresh_sessions)
        except Exception as exc:
            self._ctx.log.exception("Couldn't start the session")
            return Result.failed(f"{self._agent_id} couldn't start: {exc}")
        # Set before writing: the turn's events may arrive while send drains.
        self._task, self._mode = task, _Mode.WORKING
        self._handoffs.reset()
        self._edits = {}
        self._write_task_file(task.id)
        try:
            await self._session.send(self._with_feed(_task_text(NEW_TASK, task)))
            self._used = True
        except Exception as exc:
            self._task, self._mode = None, _Mode.IDLE
            return Result.failed(f"{self._agent_id} couldn't take the task: {exc}")
        self._publish_state()
        return Result.ok()

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
        if not self._is_current(task_id):
            return Result.invalid_arguments(f"{task_id!r} is not {self._agent_id}'s current task")
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
            elif resume:  # waiting or paused: nothing to interrupt, the text is the next message
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
        if self._mode in (_Mode.WAITING, _Mode.PAUSED):
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
        if not self._is_current(task_id):
            return Result.invalid_arguments(f"{task_id!r} is not {self._agent_id}'s current task")
        return await self._gate.answer(allow)

    async def request_approval(self, action: str, run: Callable[[], Awaitable[Result]]) -> Result:
        """Ask the user to allow `action` on the current task (the permission card), even in
        Auto. On Allow `run` runs; its outcome is the task's next message. Until then the task
        waits: a turn that ends meanwhile doesn't count as done."""
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
            accepting = self._task is not None and self._mode in (_Mode.WORKING, _Mode.REPLYING)
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
            case _:
                self._ctx.log.debug("Ignored a result while %s", self._mode)

    def _finish_turn(self, text: str, is_error: bool, subtype: str | None) -> None:
        if is_error:
            self._report(ReportKind.FAILED, text or f"The turn ended with an error ({subtype})")
            self._end_task()
        elif (outcome := self._gate.take_after_turn()) is not None:  # an approval answered during the turn
            self._spawn(self._send(outcome))
        elif self._gate.waiting:  # the user hasn't answered yet (or `run` is running): wait
            self._activity("waiting for the user's answer")
        elif not self._last_line.dispatch(text):
            self._report(ReportKind.DONE, text)
            self._end_task()

    # --- last-line tags (the `_last_line` table) ---

    def _on_need(self, question: str) -> bool:
        self._report(ReportKind.NEED, question)
        self._mode = _Mode.WAITING
        return True

    def _on_reload(self, argument: str) -> bool:
        """`RELOAD: <module id> [now]`."""
        request = reload_request(argument)
        return request is not None and self._ask_to_load(*request)

    def _on_add_module(self, argument: str) -> bool:
        """`ADD_MODULE: <package>`."""
        request = add_module_request(argument)
        return request is not None and self._ask_to_load(*request)

    def _on_handoff(self, note: str) -> bool:
        """Continue the task in a fresh session that reads `note`, or ask the user after too many."""
        if not self._handoffs.take():
            self._report(ReportKind.NEED, self._handoffs.too_many(note))
            self._mode = _Mode.WAITING
            return True
        self._report(ReportKind.PROGRESS, self._handoffs.progress(note))
        self._spawn(self._continue_fresh(note))
        return True

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

        if self._permission_mode is PermissionMode.AUTO:
            self._gate.run_now(action, run)
        else:
            self._gate.ask(action, run)
        return True

    async def _continue_fresh(self, note: str) -> None:
        task = self._task
        try:
            await self._fresh_session(restart=True)
        except Exception:
            self._ctx.log.exception("Couldn't start a fresh session for the handoff")
            self._on_exit()
            return
        if self._task is task and self._mode is _Mode.WORKING:  # not cancelled meanwhile
            self._activity(f"fresh session, reading the handoff in {note}")
            await self._send(_task_text(HANDED_OFF, task, note=note))

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
        if self._task is not None:
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

    def _report(self, kind: ReportKind, text: str) -> None:
        """Queue a report. One worker sends them in order, so the Hub sees them as they happened."""
        if self._task is None:
            return
        self._reports.put_nowait(ReportTask(task_id=self._task.id, kind=kind, text=text))
        if self._report_worker is None or self._report_worker.done():
            self._report_worker = asyncio.create_task(self._send_reports(), name=f"{self._agent_id}:reports")

    async def _send_reports(self) -> None:
        while True:
            report = await self._reports.get()
            result = await self._ctx.send(report)
            if not result.is_ok:
                self._ctx.log.warning("Hub refused %s report: %s", report.kind, result.error)

    def _activity(self, text: str) -> None:
        task_id = self._task.id if self._task else None
        self._ctx.publish(AgentActivity(agent_id=self._agent_id, task_id=task_id, text=text))

    def _publish_state(self) -> None:
        state = (self._mode is not _Mode.IDLE, self._session.working)
        if state != self._published:
            self._published = state
            self._ctx.publish(AgentStateChanged(agent_id=self._agent_id, busy=state[0], working=state[1]))

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
