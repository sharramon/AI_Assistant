"""The Agent Hub: who is doing what. Holds the authoritative task state; not an AI, launches nothing.

Finds agents through `ITaskAgent` and never imports an agent module. Task state
changes only here, and only from commands, so dropped events can't corrupt it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from uuid import uuid4

from assistant.contracts import (
    CancelTask,
    GetTaskStatus,
    ITaskAgent,
    ListAgents,
    Manifest,
    Module,
    ModuleContext,
    ReportKind,
    ReportTask,
    Result,
    SendToTask,
    StartTask,
    Status,
    Task,
    TaskInfo,
    TaskState,
    TaskUpdated,
)

RECENT_REPORTS = 10
RECENT_FINISHED = 5


@dataclass
class _TaskRecord:
    id: str
    agent_id: str
    text: str
    state: TaskState = TaskState.RUNNING
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_REPORTS))
    question: str | None = None
    result: str | None = None

    def info(self) -> TaskInfo:
        return TaskInfo(
            id=self.id, agent_id=self.agent_id, text=self.text, state=self.state,
            recent=tuple(self.recent), question=self.question, result=self.result,
        )


class AgentHubModule(Module):
    manifest = Manifest(id="agent_hub", optional=(ITaskAgent,))

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._tasks: dict[str, _TaskRecord] = {}  # insertion order is start order
        ctx.handle(ListAgents, self._list_agents)
        ctx.handle(StartTask, self._start_task)
        ctx.handle(GetTaskStatus, self._get_task_status)
        ctx.handle(SendToTask, self._send_to_task)
        ctx.handle(CancelTask, self._cancel_task)
        ctx.handle(ReportTask, self._report_task)

    async def _list_agents(self, command: ListAgents) -> Result:
        return Result.ok([agent.info() for agent in self._ctx.get_all(ITaskAgent)])

    async def _start_task(self, command: StartTask) -> Result:
        agents = self._ctx.get_all(ITaskAgent)
        if not agents:
            return Result.not_available("No agent is running")
        for agent in agents:
            info = agent.info()
            if info.busy:
                continue
            # Recorded before assigning, so a report that arrives at once finds it.
            record = _TaskRecord(id=uuid4().hex[:8], agent_id=info.agent_id, text=command.text)
            self._tasks[record.id] = record
            result = await agent.assign(Task(id=record.id, text=command.text, context=command.context))
            if result.is_ok:
                self._ctx.log.info("Task %s started on %s", record.id, info.agent_id)
                self._updated(record, None, "started")
                return Result.ok(record.id)
            del self._tasks[record.id]
            if result.status is not Status.NOT_AVAILABLE:
                return result
        return Result.not_available("Every agent is busy")

    async def _get_task_status(self, command: GetTaskStatus) -> Result:
        if command.task_id is not None:
            record = self._tasks.get(command.task_id)
            if record is None:
                return Result.invalid_arguments(f"No task {command.task_id!r}")
            return Result.ok([record.info()])
        active = [r for r in self._tasks.values() if not r.state.is_final]
        finished = [r for r in self._tasks.values() if r.state.is_final][-RECENT_FINISHED:]
        return Result.ok([r.info() for r in (*finished, *active)])

    async def _send_to_task(self, command: SendToTask) -> Result:
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
            record.question = None
            self._updated(record, None, command.text)
        return result

    async def _cancel_task(self, command: CancelTask) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        agent = self._agent(record.agent_id)
        result = await agent.cancel(record.id) if agent else Result.ok()
        if result.is_ok:
            self._finish(record, TaskState.CANCELLED, None, "cancelled")
        return result

    async def _report_task(self, command: ReportTask) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        record.recent.append(f"{command.kind}: {command.text}")
        match command.kind:
            case ReportKind.NEED:
                record.state = TaskState.WAITING_FOR_INPUT
                record.question = command.text
            case ReportKind.DONE:
                self._finish(record, TaskState.DONE, command.kind, command.text)
                return Result.ok()
            case ReportKind.FAILED:
                self._finish(record, TaskState.FAILED, command.kind, command.text)
                return Result.ok()
        self._updated(record, command.kind, command.text)
        return Result.ok()

    def _open_task(self, task_id: str) -> _TaskRecord | Result:
        """The unfinished task with this id, or an invalid_arguments Result."""
        record = self._tasks.get(task_id)
        if record is None:
            return Result.invalid_arguments(f"No task {task_id!r}")
        if record.state.is_final:
            return Result.invalid_arguments(f"Task {task_id!r} is already {record.state}")
        return record

    def _agent(self, agent_id: str) -> ITaskAgent | None:
        return next((a for a in self._ctx.get_all(ITaskAgent) if a.info().agent_id == agent_id), None)

    def _finish(self, record: _TaskRecord, state: TaskState, kind: ReportKind | None, text: str) -> None:
        record.state = state
        record.question = None
        record.result = text
        self._ctx.log.info("Task %s %s", record.id, state)
        self._updated(record, kind, text)

    def _updated(self, record: _TaskRecord, kind: ReportKind | None, text: str) -> None:
        self._ctx.publish(TaskUpdated(task_id=record.id, state=record.state, kind=kind, text=text))
