"""The Agent Hub: who is doing what. Holds the authoritative task state; not an AI, launches nothing.

Finds agents through `ITaskAgent` and never imports an agent module. Task state
changes only here, and only from commands, so dropped events can't corrupt it.
Each task's recent `AgentActivity` is kept too, so a status check can say what
the agent is doing without interrupting it; that is only a view, not state.
It also routes `SetPermissionMode` to the agent, until the permissions handler
takes that over.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from uuid import uuid4

from assistant.contracts import (
    AgentActivity,
    AnswerPermission,
    CancelTask,
    GetMenu,
    GetTaskStatus,
    IModuleDoor,
    InvokeTool,
    ITaskAgent,
    ListAgents,
    ListModules,
    Manifest,
    ModuleContext,
    ModuleProtocol,
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
from assistant.infra.mcp_door import DoorServer

RECENT_REPORTS = 10
RECENT_ACTIVITY = 15
RECENT_FINISHED = 5


@dataclass
class _TaskRecord:
    id: str
    agent_id: str
    text: str
    state: TaskState = TaskState.RUNNING
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_REPORTS))
    activity: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_ACTIVITY))
    question: str | None = None
    result: str | None = None

    def info(self) -> TaskInfo:
        return TaskInfo(
            id=self.id, agent_id=self.agent_id, text=self.text, state=self.state,
            recent=tuple(self.recent), activity=tuple(self.activity),
            question=self.question, result=self.result,
        )


CORE_LINE = {"id": "core", "description": "Module control: list, menu, on, off, reload, add", "state": "active"}


class _Door(IModuleDoor):
    """The hub's `IModuleDoor` part: the MCP config for the relay in front of its `DoorServer`."""

    def __init__(self, server: DoorServer) -> None:
        self._server = server

    def mcp_config(self) -> dict:
        return self._server.mcp_config()


class AgentHubModule(ModuleProtocol):
    manifest = Manifest(
        id="agent_hub",
        description="Task state and routing between the agents; hosts the agents' door to the module menus",
        provides=(IModuleDoor,),
        optional=(ITaskAgent,),
        handles=(ListAgents, StartTask, GetTaskStatus, SendToTask, CancelTask, ReportTask, AnswerPermission, SetPermissionMode,),
        sends=(ListModules, GetMenu, InvokeTool,),
        publishes=(TaskUpdated,),
        listens=(AgentActivity,),
    )

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        # The door's port and token survive a reload, so a running session's relay keeps working.
        handover = ctx.handover if isinstance(ctx.handover, dict) else {}
        self._door = DoorServer(
            ctx.send,
            {"list": ListModules, "menu": GetMenu, "call": InvokeTool},
            host=ctx.config.get("door_host", "127.0.0.1"),
            port=int(handover.get("door_port", ctx.config.get("door_port", 0))),
            token=handover.get("door_token"),
            core_line=CORE_LINE,
        )
        ctx.provide(IModuleDoor, _Door(self._door))
        self._tasks: dict[str, _TaskRecord] = {}  # insertion order is start order
        ctx.handle(ListAgents, self._list_agents)
        ctx.handle(StartTask, self._start_task)
        ctx.handle(GetTaskStatus, self._get_task_status)
        ctx.handle(SendToTask, self._send_to_task)
        ctx.handle(CancelTask, self._cancel_task)
        ctx.handle(ReportTask, self._report_task)
        ctx.handle(AnswerPermission, self._answer_permission)
        ctx.handle(SetPermissionMode, self._set_permission_mode)
        ctx.subscribe(AgentActivity, self._on_activity)

    async def start(self) -> None:
        if self._ctx.config.get("door", True):
            try:
                await self._door.start()
                self._ctx.log.info("The agents' module door is at %s", self._door.url)
            except OSError as exc:  # its port is taken: the agents just go without the door
                self._ctx.log.warning("Couldn't open the agents' module door: %s", exc)

    async def stop(self) -> None:
        await self._door.stop()

    def export_state(self) -> dict | None:
        """For a reload: the door's port and token, so the new copy opens the same door."""
        if not self._door.url:
            return None
        return {"door_port": int(self._door.url.rsplit(":", 1)[1]), "door_token": self._door.token}

    def busy(self) -> str | None:
        """A reload waits while tasks are open: their records would be lost (no handover yet)."""
        done = (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED)
        open_tasks = sum(1 for record in self._tasks.values() if record.state not in done)
        return f"{open_tasks} task(s) open" if open_tasks else None

    async def _on_activity(self, event: AgentActivity) -> None:
        record = self._tasks.get(event.task_id) if event.task_id else None
        if record is not None:
            record.activity.append(event.text)

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
            case ReportKind.PERMISSION:
                record.state = TaskState.WAITING_FOR_INPUT
                record.question = f"Permission: {command.text}"
            case ReportKind.DONE:
                self._finish(record, TaskState.DONE, command.kind, command.text)
                return Result.ok()
            case ReportKind.FAILED:
                self._finish(record, TaskState.FAILED, command.kind, command.text)
                return Result.ok()
        self._updated(record, command.kind, command.text)
        return Result.ok()

    async def _answer_permission(self, command: AnswerPermission) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        agent = self._agent(record.agent_id)
        if agent is None:
            return Result.not_available(f"{record.agent_id} is no longer running")
        result = await agent.answer_permission(record.id, command.allow)
        if result.is_ok:
            record.state = TaskState.RUNNING
            record.question = None
            self._updated(record, None, "permission allowed" if command.allow else "permission denied")
        return result

    async def _set_permission_mode(self, command: SetPermissionMode) -> Result:
        agent = self._agent(command.agent_id)
        if agent is None:
            return Result.invalid_arguments(f"No agent {command.agent_id!r}")
        return await agent.set_permission_mode(command.mode)

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
