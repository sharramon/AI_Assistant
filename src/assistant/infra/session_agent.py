"""An `ITaskAgent` backed by one `ClaudeSession`: the shared part every task agent is built from."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from enum import StrEnum
from typing import Any

from assistant.contracts import (
    AgentActivity,
    AgentInfo,
    AgentStateChanged,
    ITaskAgent,
    ModuleContext,
    PermissionMode,
    PermissionModeChanged,
    ReportKind,
    ReportTask,
    Result,
    SessionUsage,
    Task,
)
from assistant.infra.agent_tags import last_line
from assistant.infra.claude_session import ClaudeSession

NEW_TASK = "New task: {text}"
NEW_TASK_CONTEXT = "\n\nContext:\n{context}"
INTERRUPTED = (
    "[The user interrupted your task with a message. Answer it briefly; "
    "you'll be told when to continue.] {text}"
)
CONTINUE = "Continue the task from where you left off."
NEED_PREFIX = "NEED:"
HANDOFF_PREFIX = "HANDOFF:"
HANDED_OFF = (
    "Task, continued in a fresh session: {text}\n\n"
    "An earlier session worked on this and wrote a handoff in {note}. Read it first and "
    "carry on from there; don't redo the finished parts."
)
RESET_NOW = (
    "The user asked to reset your session. At a safe point, write what's done and what's "
    "next into this task's change note in docs/next-steps/ (or a short note "
    "docs/next-steps/handoff-{task_id}.md if it has none), then end with the line "
    "`HANDOFF: <that note's path>`."
)
TOO_MANY_HANDOFFS = "I've handed this task off {count} times (latest notes: {note}). Should I carry on?"


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

    Never waits on a turn: every method returns once its message or interrupt is
    written, and the rest happens as the session's events arrive. Sets itself
    as the session's `on_event`. One task at a time.

    With `fresh_sessions`, each task starts in a new `claude` process, so its
    context holds only that task. A turn whose last line is `HANDOFF: <note>`
    continues the same task in a fresh session told to read that note, up to
    `max_handoffs` times per task; then it asks the user (a `need` report).
    Publishes `SessionUsage` whenever the session's usage changes (every call).

    Holds the `permission_mode` (in memory, Manual at every launch). The owning module
    builds each session's command for that mode (pass the session a callable). A switch
    applies at the next session start; to Manual while a task runs it also applies at
    once, by switching the running process to `manual_claude_mode`.
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
    ):
        self._session = session
        self._ctx = ctx
        self._agent_id = agent_id
        self._description = description
        self._capabilities = capabilities
        self._cancel_timeout = cancel_timeout
        self._permission_timeout = permission_timeout
        self._fresh_sessions = fresh_sessions
        self._max_handoffs = max_handoffs
        self._manual_claude_mode = manual_claude_mode
        self._permission_mode = PermissionMode.MANUAL
        self._live_mode = PermissionMode.MANUAL  # what the running session is in now
        self._handoffs = 0  # in the current task
        self._used = False  # the running session has had a message since it started
        self._published_usage: tuple[int, int, float] | None = None  # context, used, cost
        self._permission: dict[str, Any] | None = None  # the open can_use_tool request
        self._permission_timer: asyncio.Task | None = None
        self._task: Task | None = None
        self._mode = _Mode.IDLE
        self._pending: list[str] = []  # messages waiting for the interrupt to land
        self._resume = True
        self._reports: asyncio.Queue[ReportTask] = asyncio.Queue()
        self._background: set[asyncio.Task] = set()
        self._report_worker: asyncio.Task | None = None
        self._published: tuple[bool, bool] = (False, False)
        session.on_event = self._on_event

    @property
    def permission_mode(self) -> PermissionMode:
        """The mode the next session starts in."""
        return self._permission_mode

    def info(self) -> AgentInfo:
        return AgentInfo(
            agent_id=self._agent_id,
            description=self._description,
            capabilities=self._capabilities,
            busy=self._mode is not _Mode.IDLE,
            working=self._session.working,
            permission_mode=self._permission_mode,
        )

    async def assign(self, task: Task) -> Result:
        if self._mode is not _Mode.IDLE:
            return Result.not_available(f"{self._agent_id} is busy")
        try:
            await self._fresh_session(restart=self._fresh_sessions)
        except Exception as exc:
            self._ctx.log.exception("Couldn't start the session")
            return Result.failed(f"{self._agent_id} couldn't start: {exc}")
        # Set before writing: the turn's events may arrive while send drains.
        self._task, self._mode, self._handoffs = task, _Mode.WORKING, 0
        try:
            await self._session.send(_task_text(NEW_TASK, task))
            self._used = True
        except Exception as exc:
            self._task, self._mode = None, _Mode.IDLE
            return Result.failed(f"{self._agent_id} couldn't take the task: {exc}")
        self._publish_state()
        return Result.ok()

    async def set_permission_mode(self, mode: PermissionMode) -> Result:
        """Set the mode. With no task it applies to the next one (`now`). Mid-task, Manual
        switches the running process; Auto waits for the next task or handoff session,
        since its prompt is fixed when a session starts (`next_task`)."""
        mode = PermissionMode(mode)
        self._permission_mode = mode
        applies = "now"
        if self._task is not None and self._session.running and self._live_mode is not mode:
            applies = "next_task"
            if mode is PermissionMode.MANUAL:
                try:
                    await self._session.set_permission_mode(self._manual_claude_mode)
                    self._live_mode, applies = mode, "now"
                except Exception as exc:
                    self._ctx.log.warning("Couldn't switch the running session to Manual: %s", exc)
        when = "" if applies == "now" else " (from the next task)"
        self._ctx.log.info("%s permission mode: %s%s", self._agent_id, mode, when)
        self._activity(f"permission mode: {mode}{when}")
        self._ctx.publish(PermissionModeChanged(agent_id=self._agent_id, mode=mode, applies=applies))
        return Result.ok()

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
        return await self.message(self._task.id, RESET_NOW.format(task_id=self._task.id))

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        if not self._is_current(task_id):
            return Result.invalid_arguments(f"{task_id!r} is not {self._agent_id}'s current task")
        try:
            if self._mode in (_Mode.WORKING, _Mode.REPLYING, _Mode.INTERRUPTING):
                self._drop_permission()  # the interrupt ends the turn, and the request with it
                self._pending.append(text)
                self._resume = resume
                if self._mode is not _Mode.INTERRUPTING:
                    self._mode = _Mode.INTERRUPTING
                    await self._session.interrupt()
            elif resume:  # waiting or paused: nothing to interrupt, the text is the next message
                self._mode = _Mode.WORKING
                await self._session.send(text)
            else:
                self._resume = False
                self._mode = _Mode.REPLYING
                await self._session.send(INTERRUPTED.format(text=text))
        except Exception as exc:
            return Result.failed(f"Couldn't deliver the message: {exc}")
        self._publish_state()
        return Result.ok()

    async def cancel(self, task_id: str) -> Result:
        if not self._is_current(task_id):
            return Result.invalid_arguments(f"{task_id!r} is not {self._agent_id}'s current task")
        self._task = None
        self._pending.clear()
        self._drop_permission()
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
        request = self._permission
        if request is None:
            return Result.invalid_arguments("No permission request is open")
        self._drop_permission()
        try:
            await self._session.answer_permission(request, allow)
        except Exception as exc:
            return Result.failed(f"Couldn't answer the permission request: {exc}")
        self._activity(f"permission {'allowed' if allow else 'denied'}: {_describe_request(request)}")
        return Result.ok()

    async def close(self) -> None:
        """Stop the background work. The owning module closes the session itself."""
        self._drop_permission()
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
            self._on_permission(event)
        elif kind == "exit":
            self._on_exit()
        self._publish_state()
        self._publish_usage()

    def _on_permission(self, event: dict[str, Any]) -> None:
        """The session wants a tool its rules don't allow: ask through the Hub, or refuse if no task owns it."""
        if self._task is None or self._mode not in (_Mode.WORKING, _Mode.REPLYING):
            self._spawn(self._session.answer_permission(event, False, "No task is running."))
            return
        self._drop_permission()
        self._permission = event
        self._permission_timer = asyncio.create_task(self._permission_expiry(event))
        self._activity(f"asks permission: {_describe_request(event)}")
        self._report(ReportKind.PERMISSION, _describe_request(event))

    async def _permission_expiry(self, event: dict[str, Any]) -> None:
        await asyncio.sleep(self._permission_timeout)
        if self._permission is event:
            self._permission = None
            self._activity(f"permission timed out, denied: {_describe_request(event)}")
            await self._session.answer_permission(event, False, "Nobody answered the permission request in time.")

    def _on_block(self, block: dict[str, Any]) -> None:
        if block.get("type") == "text" and block.get("text", "").strip():
            text = block["text"].strip()
            self._activity(text)
            if self._mode is _Mode.WORKING:
                self._report(ReportKind.PROGRESS, text)
        elif block.get("type") == "tool_use":
            self._activity(f"→ {block.get('name')} {_summarize(block.get('input', {}))}")

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
                    self._hand_off(note)
                elif self._resume:
                    self._mode = _Mode.WORKING
                    self._spawn(self._send(CONTINUE))
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
        elif (question := last_line(text, NEED_PREFIX)) is not None:
            self._report(ReportKind.NEED, question)
            self._mode = _Mode.WAITING
        elif (note := last_line(text, HANDOFF_PREFIX)) is not None:
            self._hand_off(note)
        else:
            self._report(ReportKind.DONE, text)
            self._end_task()

    def _hand_off(self, note: str) -> None:
        """Continue the task in a fresh session that reads `note`, or ask the user after too many."""
        if self._handoffs >= self._max_handoffs:
            self._report(ReportKind.NEED, TOO_MANY_HANDOFFS.format(count=self._handoffs, note=note))
            self._mode = _Mode.WAITING
            return
        self._handoffs += 1
        self._report(ReportKind.PROGRESS, f"Handed off to a fresh session ({self._handoffs}): {note}")
        self._spawn(self._continue_fresh(note))

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
        stale = self._live_mode is not self._permission_mode
        if self._session.running and (stale or (restart and self._used)):
            await self._session.close()
        if not self._session.running:
            await self._session.start()  # its command reads the current mode
            self._used = False
            self._live_mode = self._permission_mode
        self._publish_usage()

    def _on_exit(self) -> None:
        if self._task is not None:
            self._report(ReportKind.FAILED, "The agent's claude process exited")
        self._end_task()

    def _end_task(self) -> None:
        self._task, self._mode = None, _Mode.IDLE
        self._pending.clear()
        self._drop_permission()

    def _drop_permission(self) -> None:
        self._permission = None
        if self._permission_timer is not None:
            self._permission_timer.cancel()
            self._permission_timer = None

    # --- helpers ---

    def _is_current(self, task_id: str) -> bool:
        return self._task is not None and self._task.id == task_id

    async def _send(self, text: str) -> None:
        try:
            await self._session.send(text)
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
        numbers = (usage.context_tokens, usage.used_tokens, usage.cost_usd)
        if numbers != self._published_usage:
            self._published_usage = numbers
            self._ctx.publish(usage)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)


def session_usage(agent_id: str, session: ClaudeSession) -> SessionUsage:
    """`session`'s usage so far as a `SessionUsage` event; context 0 when it isn't running."""
    used = session.used
    return SessionUsage(
        agent_id=agent_id,
        context_tokens=session.context_tokens if session.running else 0,
        input_tokens=used["input"],
        cache_write_tokens=used["cache_write"],
        cache_read_tokens=used["cache_read"],
        output_tokens=used["output"],
        cost_usd=session.cost_usd,
    )


def _task_text(template: str, task: Task, **fields: str) -> str:
    text = template.format(text=task.text, **fields)
    if task.context:
        text += NEW_TASK_CONTEXT.format(context=task.context)
    return text


def _describe_request(event: dict[str, Any]) -> str:
    """`Write C:\\repo\\x.md` for a can_use_tool request."""
    request = event.get("request", {})
    return f"{request.get('tool_name', '?')} {_summarize(request.get('input', {}))}"


def _summarize(tool_input: dict[str, Any]) -> str:
    for key in ("file_path", "path", "pattern", "command", "url"):
        if key in tool_input:
            return str(tool_input[key])
    return json.dumps(tool_input)[:80]
