"""Task agents and the Agent Hub: the contract agents provide, and the Hub's commands and events.

The Hub handles the commands; agents provide `ITaskAgent` and report back with
`ReportTask`. The Hub's task state is authoritative; the events may be dropped.
"""

from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from assistant.contracts.messages import Command, Event, Result
from assistant.contracts.module import Contract


class Task(BaseModel):
    """A unit of work the Hub assigns. `id` is set by the Hub."""

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    context: str = ""


class PermissionMode(StrEnum):
    """What a task agent may do without asking. Every launch starts in `manual`; it isn't saved.

    `manual`: its standing rules, and you're asked about anything else. `auto`: full
    permissions with no prompts, except what the agent hard-blocks (`git push` for the
    Main Assistant); it pauses on its own to ask before very risky steps.
    """

    MANUAL = "manual"
    AUTO = "auto"


class AgentInfo(BaseModel):
    """Who an agent is. `busy`: it has an unfinished task. `working`: its session is in a turn now."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    description: str
    capabilities: tuple[str, ...] = ()
    busy: bool = False
    working: bool = False
    permission_mode: PermissionMode = PermissionMode.MANUAL


class TaskState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_FOR_INPUT = "waiting_for_input"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_final(self) -> bool:
        return self in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED)


class ReportKind(StrEnum):
    PROGRESS = "progress"
    REPLY = "reply"
    NEED = "need"
    PERMISSION = "permission"  # asks to use a tool it isn't allowed; answered with AnswerPermission
    DONE = "done"
    FAILED = "failed"


class TaskInfo(BaseModel):
    """A task as the Hub knows it. `recent` holds the latest reports, `activity` the agent's
    latest text and tool calls (from `AgentActivity`), both newest last."""

    model_config = ConfigDict(frozen=True)

    id: str
    agent_id: str
    text: str
    state: TaskState
    recent: tuple[str, ...] = ()
    activity: tuple[str, ...] = ()
    question: str | None = None
    result: str | None = None


class ITaskAgent(Contract):
    """An agent that takes tasks. Any number of modules may provide this; only the Hub calls it.

    None of the methods wait for the work: they return once the agent has
    accepted the task or delivered the message, and the agent reports back
    with `ReportTask`.
    """

    multiple = True

    @abstractmethod
    def info(self) -> AgentInfo:
        """Who this agent is and whether it's busy. Called on every lookup."""

    @abstractmethod
    async def assign(self, task: Task) -> Result:
        """Accept (`ok`) or refuse (`not_available` if busy, `failed` if it can't start) a task."""

    @abstractmethod
    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        """Interrupt, answer `text`, then continue the task unless `resume` is false."""

    @abstractmethod
    async def cancel(self, task_id: str) -> Result:
        """Stop the task, like Esc. The session and its memory survive."""

    @abstractmethod
    async def answer_permission(self, task_id: str, allow: bool) -> Result:
        """Answer the task's open permission request. `invalid_arguments` if none is open."""

    async def set_permission_mode(self, mode: PermissionMode) -> Result:
        """Switch what the agent may do, and publish `PermissionModeChanged`. Agents without
        modes keep this default, which refuses."""
        return Result.not_available("This agent has no permission modes")


class ListAgents(Command):
    """Every agent and whether it's busy or working. Result value: `list[AgentInfo]`."""


class StartTask(Command):
    """Give work to a free agent. Result value: the task id; `not_available` if none is free."""

    text: str
    context: str = ""


class GetTaskStatus(Command):
    """Task status without disturbing the agent. Result value: `list[TaskInfo]`.

    With no `task_id`: the unfinished tasks and the most recent finished ones.
    """

    task_id: str | None = None


class SendToTask(Command):
    """A question, extra instruction, or answer for a task. `resume=False` pauses it."""

    task_id: str
    text: str
    resume: bool = True


class CancelTask(Command):
    """Stop a task, like Esc."""

    task_id: str


class AnswerPermission(Command):
    """Allow or deny the task's open permission request (a `permission` report), once."""

    task_id: str
    allow: bool


class SetPermissionMode(Command):
    """Switch a task agent between Manual and Auto. Handled by the Agent Hub (later by the
    permissions handler). Only you switch to Auto (the UI button); the Talker may only
    switch to Manual. `invalid_arguments` for an unknown agent."""

    agent_id: str
    mode: PermissionMode


class ReportTask(Command):
    """Agent → Hub. A command, not an event, so the Hub's state never misses it."""

    task_id: str
    kind: ReportKind
    text: str


class TaskUpdated(Event):
    """A task's report or state changed. `kind` is None for changes the Hub made itself."""

    task_id: str
    state: TaskState
    kind: ReportKind | None = None
    text: str = ""


class AgentStateChanged(Event):
    """An agent's `busy` or `working` changed."""

    agent_id: str
    busy: bool
    working: bool


class PermissionModeChanged(Event):
    """A task agent's permission mode was set. `applies`: `now`, or `next_task` when the
    running session can't switch (to Auto mid-task, or a live switch that failed)."""

    agent_id: str
    mode: PermissionMode
    applies: Literal["now", "next_task"] = "now"


class AgentActivity(Event):
    """An agent's raw activity (its text and tool calls), for viewers."""

    agent_id: str
    task_id: str | None = None
    text: str


class SessionUsage(Event):
    """One agent's `claude` usage, so you know when to reset it and what it has cost.
    `agent_id` is "talker" or a task agent's id; agents are never added together.

    `context_tokens`: what each call sends now (the latest call's input, cached or not);
    0 when no session runs. The rest count every call since the app started, across fresh
    sessions and resets. `cost_usd` is `claude`'s own estimate (API prices).
    """

    agent_id: str
    context_tokens: int
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def used_tokens(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens + self.output_tokens


class ResetRequested(Event):
    """Asks the session behind `agent_id` to start fresh. The Talker keeps its last few
    exchanges; a task agent resets at once when idle, and hands off when it has a task."""

    agent_id: str
