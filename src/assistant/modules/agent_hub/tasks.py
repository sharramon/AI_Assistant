"""The Agent Hub's task tracking: every task's record and the task state machine.

Task state changes only here, and only from the Hub's commands, so dropped events can't
corrupt it. Each task's recent `AgentActivity` is kept too, so a status check can say what
the agent is doing without interrupting it; that is only a view, not state.

The board never imports an agent module: the Hub gives it callables to find the running
agents, the focused agent, and the coordinator's feed. A question, reply or end from an
agent out of focus is stored once on its task and marked `held` until that agent is
focused (`release`).
"""

from __future__ import annotations

import logging
import os
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from assistant.contracts import (
    AgentActivity,
    AnswerPermission,
    CancelTask,
    GetTaskStatus,
    ITaskAgent,
    QuestionKind,
    ReportKind,
    ReportTask,
    Result,
    SendToTask,
    SetPermissionMode,
    StartTask,
    Status,
    Task,
    TaskInfo,
    TaskState,
    TaskUpdated,
)

RECENT_REPORTS = 10
RECENT_ACTIVITY = 15
RECENT_FINISHED = 5
RESULT_IN_FEED = 120  # characters of a finished task's result in the coordinator's feed


@dataclass
class TaskRecord:
    id: str
    agent_id: str
    text: str
    state: TaskState = TaskState.RUNNING
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_REPORTS))
    activity: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_ACTIVITY))
    question: str | None = None
    result: str | None = None
    parent_task_id: str | None = None
    held: bool = False
    reply: str | None = None  # a reply that waits behind the agent's ! (kept only while held)
    question_kind: QuestionKind = QuestionKind.NONE

    def ask(self, kind: ReportKind, text: str) -> None:
        """Open the task's question: the agent's text, and what it is (typed, principle 7)."""
        self.question, self.question_kind = text, QuestionKind.of(kind, text)

    def answered(self) -> None:
        """The question is closed; a held reply keeps its !."""
        self.question, self.question_kind, self.held = None, QuestionKind.NONE, self.reply is not None

    def info(self) -> TaskInfo:
        return TaskInfo(
            id=self.id, agent_id=self.agent_id, text=self.text, state=self.state,
            recent=tuple(self.recent), activity=tuple(self.activity),
            question=self.question, result=self.result,
            parent_task_id=self.parent_task_id, held=self.held, reply=self.reply,
            question_kind=self.question_kind,
        )


class TaskBoard:
    """Every task and its state: started, messaged, reported, answered, ended.

    `agents()` lists the running agents and `agent(id)` finds one; `focused()` is the agent
    you're talking to; `feed(line)` is a background line for the coordinator. At most
    `max_extra` agents besides the coordinator have an open task at once, and never two
    whose agents write the same folder."""

    def __init__(
        self,
        *,
        publish: Callable[[Any], None],
        log: logging.Logger,
        agents: Callable[[], list[ITaskAgent]],
        agent: Callable[[str], ITaskAgent | None],
        focused: Callable[[], str],
        feed: Callable[[str], None],
        coordinator: str,
        max_extra: int,
    ) -> None:
        self._publish, self._log = publish, log
        self._agents, self._agent, self._focused, self._feed = agents, agent, focused, feed
        self._coordinator, self._max_extra = coordinator, max_extra
        self._tasks: dict[str, TaskRecord] = {}  # insertion order is start order

    # --- reading ---

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def open_records(self) -> list[TaskRecord]:
        return [r for r in self._tasks.values() if not r.state.is_final]

    def open_task_of(self, agent_id: str) -> TaskRecord | None:
        return next((r for r in self.open_records() if r.agent_id == agent_id), None)

    def holds(self, agent_id: str) -> bool:
        """Whether something of `agent_id`'s waits behind its tab's !."""
        return any(r.held for r in self._tasks.values() if r.agent_id == agent_id)

    def release(self, agent_id: str) -> list[TaskInfo]:
        """`agent_id` is focused: what it held (questions, replies, ends, finished tasks too),
        no longer held. A held reply is said now; only the question stays until answered."""
        released = []
        for record in self._tasks.values():
            if record.agent_id == agent_id and record.held:
                record.held = False
                released.append(record.info())
                record.reply = None
        return released

    def may_steer(self, task_id: str, caller: str, anyone: bool = False) -> Result | None:
        """None if `caller` may message or cancel the task: with `anyone`, any task; otherwise
        its own child tasks."""
        record = self._tasks.get(task_id)
        if record is None:
            return Result.invalid_arguments(f"No task {task_id!r}")
        parent = self._tasks.get(record.parent_task_id) if record.parent_task_id else None
        if anyone or (parent is not None and parent.agent_id == caller):
            return None
        return Result.not_available(f"Task {task_id} isn't one of {caller or 'your'} child tasks")

    async def on_activity(self, event: AgentActivity) -> None:
        record = self._tasks.get(event.task_id) if event.task_id else None
        if record is not None:
            record.activity.append(event.text)

    # --- the commands ---

    async def start(self, command: StartTask) -> Result:
        agents = self._agents()
        if command.agent_id is not None:
            agents = [a for a in agents if a.info().agent_id == command.agent_id]
            if not agents:
                return Result.invalid_arguments(f"No agent {command.agent_id!r}")
        if not agents:
            return Result.not_available("No agent is running")
        open_records = self.open_records()
        extras = sum(1 for r in open_records if r.agent_id != self._coordinator)
        refusal = "Every agent is busy"
        for agent in agents:
            info = agent.info()
            if info.busy:
                refusal = f"{info.agent_id} is busy" if command.agent_id else refusal
                continue
            if info.agent_id != self._coordinator and extras >= self._max_extra:
                refusal = (f"{extras} extra agents are working, the most at once ({self._max_extra}; "
                           "max_extra_agents in [modules.agent_hub])")  # fmt: skip
                continue
            if clash := self._folder_clash(info.agent_id, info.write_folders, open_records):
                refusal = clash
                continue
            # Recorded before assigning, so a report that arrives at once finds it.
            record = TaskRecord(id=uuid4().hex[:8], agent_id=info.agent_id, text=command.text,
                                parent_task_id=command.parent_task_id)  # fmt: skip
            self._tasks[record.id] = record
            result = await agent.assign(Task(id=record.id, text=command.text, context=command.context))
            if result.is_ok:
                self._log.info("Task %s started on %s", record.id, info.agent_id)
                self._updated(record, None, "started")
                return Result.ok(record.id)
            del self._tasks[record.id]
            if result.status is not Status.NOT_AVAILABLE:
                return result
        return Result.not_available(refusal)

    async def status(self, command: GetTaskStatus) -> Result:
        if command.task_id is not None:
            record = self._tasks.get(command.task_id)
            if record is None:
                return Result.invalid_arguments(f"No task {command.task_id!r}")
            return Result.ok([record.info()])
        active = [r for r in self._tasks.values() if not r.state.is_final]
        finished = [r for r in self._tasks.values() if r.state.is_final][-RECENT_FINISHED:]
        return Result.ok([r.info() for r in (*finished, *active)])

    async def send(self, command: SendToTask) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        agent = self._agent(record.agent_id)
        if agent is None:
            self._finish(record, TaskState.FAILED, None, f"{record.agent_id} is no longer running")
            return Result.not_available(f"{record.agent_id} is no longer running")
        result = await agent.message(record.id, command.text, command.resume)
        if result.is_ok:
            record.state = TaskState.RUNNING if command.resume else TaskState.PAUSED
            record.answered()
            self._updated(record, None, command.text)
        return result

    async def cancel(self, command: CancelTask) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        agent = self._agent(record.agent_id)
        result = await agent.cancel(record.id) if agent else Result.ok()
        if result.is_ok:
            self._finish(record, TaskState.CANCELLED, None, "cancelled")
        return result

    async def report(self, command: ReportTask) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        record.recent.append(f"{command.kind}: {command.text}")
        match command.kind:
            case ReportKind.NEED | ReportKind.PERMISSION:
                record.state = TaskState.WAITING_FOR_INPUT
                record.ask(command.kind, command.text)
                record.held = record.held or record.agent_id != self._focused()  # waits behind its tab's !
            case ReportKind.REPLY if record.agent_id != self._focused():
                record.reply, record.held = command.text, True  # said in its own tab, when you open it
            case ReportKind.MILESTONE:
                if record.agent_id != self._coordinator:
                    self._feed(f"[{record.agent_id}] {command.text}")
            case ReportKind.DONE:
                self._finish(record, TaskState.DONE, command.kind, command.text, hold=True)
                return Result.ok()
            case ReportKind.FAILED:
                self._finish(record, TaskState.FAILED, command.kind, command.text, hold=True)
                return Result.ok()
        self._updated(record, command.kind, command.text)
        return Result.ok()

    async def answer(self, command: AnswerPermission) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        agent = self._agent(record.agent_id)
        if agent is None:
            return Result.not_available(f"{record.agent_id} is no longer running")
        result = await agent.answer_permission(record.id, command.allow)
        if result.is_ok:
            record.state = TaskState.RUNNING
            record.answered()
            self._updated(record, None, "permission allowed" if command.allow else "permission denied")
        return result

    async def set_mode(self, command: SetPermissionMode) -> Result:
        agent = self._agent(command.agent_id)
        if agent is None:
            return Result.invalid_arguments(f"No agent {command.agent_id!r}")
        result = await agent.set_permission_mode(command.mode)
        record = self.open_task_of(command.agent_id)
        if result.is_ok and result.value is True and record is not None:  # Auto answered its open card
            record.state = TaskState.RUNNING
            record.answered()
            self._updated(record, None, "permission allowed (Auto)")
        return result

    # --- inside ---

    def _open_task(self, task_id: str) -> TaskRecord | Result:
        """The unfinished task with this id, or an invalid_arguments Result."""
        record = self._tasks.get(task_id)
        if record is None:
            return Result.invalid_arguments(f"No task {task_id!r}")
        if record.state.is_final:
            return Result.invalid_arguments(f"Task {task_id!r} is already {record.state}")
        return record

    def _folder_clash(self, agent_id: str, folders: tuple[str, ...], open_records: list[TaskRecord]) -> str | None:
        """Why `agent_id` can't start: another open task's agent writes one of its folders."""
        mine = [_norm(f) for f in folders]
        for record in open_records:
            other = self._agent(record.agent_id) if record.agent_id != agent_id else None
            if other is None:
                continue
            for folder in other.info().write_folders:
                theirs = _norm(folder)
                if any(_inside(a, theirs) or _inside(theirs, a) for a in mine):
                    return f"{agent_id} would write {folder}, which {record.agent_id}'s open task {record.id} writes"
        return None

    def _finish(self, record: TaskRecord, state: TaskState, kind: ReportKind | None, text: str,
                hold: bool = False) -> None:  # fmt: skip
        """End the task. With `hold` (the agent's own done or failed), an end out of focus waits
        behind its tab's !, with any held reply."""
        record.state = state
        record.question, record.question_kind = None, QuestionKind.NONE
        record.held = hold and (record.reply is not None or record.agent_id != self._focused())
        if not record.held:
            record.reply = None
        record.result = text
        self._log.info("Task %s %s", record.id, state)
        self._updated(record, kind, text)
        if record.agent_id != self._coordinator:
            self._feed(f"[{record.agent_id}] task {state}: {' '.join(text.split())[:RESULT_IN_FEED]}")

    def _updated(self, record: TaskRecord, kind: ReportKind | None, text: str) -> None:
        self._publish(TaskUpdated(
            task_id=record.id, state=record.state, kind=kind, text=text,
            agent_id=record.agent_id, parent_task_id=record.parent_task_id, held=record.held,
            question_kind=record.question_kind,
        ))  # fmt: skip


def _norm(folder: str) -> Path:
    return Path(os.path.normcase(str(Path(folder).resolve())))


def _inside(path: Path, folder: Path) -> bool:
    """`path` is `folder` or inside it."""
    return path == folder or path.is_relative_to(folder)
