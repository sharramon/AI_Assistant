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
    ReportKind,
    ReportTask,
    Result,
    Task,
)
from assistant.infra.claude_session import ClaudeSession

NEW_TASK = "New task: {text}"
NEW_TASK_CONTEXT = "\n\nContext:\n{context}"
INTERRUPTED = (
    "[The user interrupted your task with a message. Answer it briefly; "
    "you'll be told when to continue.] {text}"
)
CONTINUE = "Continue the task from where you left off."
NEED_PREFIX = "NEED:"


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
    """

    def __init__(
        self,
        session: ClaudeSession,
        ctx: ModuleContext,
        agent_id: str,
        description: str,
        capabilities: tuple[str, ...] = (),
        cancel_timeout: float = 5.0,
    ):
        self._session = session
        self._ctx = ctx
        self._agent_id = agent_id
        self._description = description
        self._capabilities = capabilities
        self._cancel_timeout = cancel_timeout
        self._task: Task | None = None
        self._mode = _Mode.IDLE
        self._pending: list[str] = []  # messages waiting for the interrupt to land
        self._resume = True
        self._reports: asyncio.Queue[ReportTask] = asyncio.Queue()
        self._background: set[asyncio.Task] = set()
        self._report_worker: asyncio.Task | None = None
        self._published: tuple[bool, bool] = (False, False)
        session.on_event = self._on_event

    def info(self) -> AgentInfo:
        return AgentInfo(
            agent_id=self._agent_id,
            description=self._description,
            capabilities=self._capabilities,
            busy=self._mode is not _Mode.IDLE,
            working=self._session.working,
        )

    async def assign(self, task: Task) -> Result:
        if self._mode is not _Mode.IDLE:
            return Result.not_available(f"{self._agent_id} is busy")
        try:
            if not self._session.running:
                await self._session.start()
        except Exception as exc:
            self._ctx.log.exception("Couldn't start the session")
            return Result.failed(f"{self._agent_id} couldn't start: {exc}")
        text = NEW_TASK.format(text=task.text)
        if task.context:
            text += NEW_TASK_CONTEXT.format(context=task.context)
        # Set before writing: the turn's events may arrive while send drains.
        self._task, self._mode = task, _Mode.WORKING
        try:
            await self._session.send(text)
        except Exception as exc:
            self._task, self._mode = None, _Mode.IDLE
            return Result.failed(f"{self._agent_id} couldn't take the task: {exc}")
        self._publish_state()
        return Result.ok()

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        if not self._is_current(task_id):
            return Result.invalid_arguments(f"{task_id!r} is not {self._agent_id}'s current task")
        try:
            if self._mode in (_Mode.WORKING, _Mode.REPLYING, _Mode.INTERRUPTING):
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

    async def close(self) -> None:
        """Stop the background work. The owning module closes the session itself."""
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
        elif kind == "exit":
            self._on_exit()
        self._publish_state()

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
                if self._resume:
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
        elif (question := _need(text)) is not None:
            self._report(ReportKind.NEED, question)
            self._mode = _Mode.WAITING
        else:
            self._report(ReportKind.DONE, text)
            self._end_task()

    def _on_exit(self) -> None:
        if self._task is not None:
            self._report(ReportKind.FAILED, "The agent's claude process exited")
        self._end_task()

    def _end_task(self) -> None:
        self._task, self._mode = None, _Mode.IDLE
        self._pending.clear()

    # --- helpers ---

    def _is_current(self, task_id: str) -> bool:
        return self._task is not None and self._task.id == task_id

    async def _send(self, text: str) -> None:
        try:
            await self._session.send(text)
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

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)


def _need(text: str) -> str | None:
    """The question if the last line is `NEED: <question>`, else None."""
    lines = [line.strip().strip("*").strip() for line in text.splitlines() if line.strip()]
    if lines and lines[-1].upper().startswith(NEED_PREFIX):
        return lines[-1][len(NEED_PREFIX):].strip()
    return None


def _summarize(tool_input: dict[str, Any]) -> str:
    for key in ("file_path", "path", "pattern", "command", "url"):
        if key in tool_input:
            return str(tool_input[key])
    return json.dumps(tool_input)[:80]
