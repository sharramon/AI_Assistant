"""Task agents and the Agent Hub: the contract agents provide, and the Hub's commands and events.

The Hub handles the commands; agents provide `ITaskAgent` and report back with
`ReportTask`. The Hub's task state is authoritative; the events may be dropped.
Several agents may run at once, one task each. The Hub keeps which one you're talking
to (the focus); questions from the others are held until you focus them.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Awaitable, Callable
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
    """Who an agent is. `busy`: it has an unfinished task. `working`: its session is in a turn now.
    `write_folders`: the folders it may write, for the Hub's folder-clash check."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    description: str
    capabilities: tuple[str, ...] = ()
    busy: bool = False
    working: bool = False
    permission_mode: PermissionMode = PermissionMode.MANUAL
    write_folders: tuple[str, ...] = ()


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
    MILESTONE = "milestone"  # a `STATUS:` line: one short line for the coordinator's feed
    DONE = "done"
    FAILED = "failed"


RISKY_PREFIX = "Risky:"  # a NEED starting with this: the agent, in Auto, paused before a risky step


class QuestionKind(StrEnum):
    """What a task's open question is, typed, so no reader parses its text (principle 7). The Hub
    sets it from the report: `permission` (a tool request, answered with `AnswerPermission`),
    `risky` (a `need` starting with `Risky:`), `need` (any other question); `none` when none."""

    NONE = ""
    NEED = "need"
    RISKY = "risky"
    PERMISSION = "permission"

    @classmethod
    def of(cls, kind: ReportKind | None, text: str) -> QuestionKind:
        """The question kind of a report: the one place `Risky:` is read."""
        if kind is ReportKind.PERMISSION:
            return cls.PERMISSION
        if kind is ReportKind.NEED:
            return cls.RISKY if text.startswith(RISKY_PREFIX) else cls.NEED
        return cls.NONE


class TaskInfo(BaseModel):
    """A task as the Hub knows it. `recent` holds the latest reports, `activity` the agent's
    latest text and tool calls (from `AgentActivity`), both newest last. `question` is its
    open question or permission request; `held` means it, its `reply` or its end (`result`)
    waits behind the agent's **!** until you focus that agent. `reply`: the agent's latest
    reply, kept only while held. `parent_task_id`: the task that started it, if any.
    `question_kind`: what `question` is (`QuestionKind`); `question` is the agent's own text."""

    model_config = ConfigDict(frozen=True)

    id: str
    agent_id: str
    text: str
    state: TaskState
    recent: tuple[str, ...] = ()
    activity: tuple[str, ...] = ()
    question: str | None = None
    result: str | None = None
    parent_task_id: str | None = None
    held: bool = False
    reply: str | None = None
    question_kind: QuestionKind = QuestionKind.NONE

    @property
    def question_line(self) -> str:
        """The question for a person or an agent to read: `Permission: ` before a tool request."""
        if not self.question:
            return ""
        return f"Permission: {self.question}" if self.question_kind is QuestionKind.PERMISSION else self.question


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
        """Switch what the agent may do, and publish `PermissionModeChanged`. The value is
        True when the switch answered an open permission request (the Hub closes its card).
        Agents without modes keep this default, which refuses."""
        return Result.not_available("This agent has no permission modes")

    def note(self, text: str) -> None:
        """A background line for the agent's next turn (a milestone of another agent, a
        module's callback). Never interrupts and never starts work. The default drops it."""

    async def request_approval(self, action: str, run: Callable[[], Awaitable[Result]]) -> Result:
        """Ask you to allow `action` on this agent's open task: a `permission` report, so the
        same card and `AnswerPermission`. On Allow, `run` is called and its outcome reaches the
        agent as its next message; on Deny or no answer nothing runs. Always asks, even in Auto.
        Returns once the question is open (`ok`). Agents without tasks keep this default."""
        return Result.not_available("This agent can't ask you for approval")


class IAgentNames(Contract):
    """The agent ids in use, so no two agents share one. One provider (the Agent Hub).

    `owner` is the module that runs the agent. Rules: `check_agent_id` (infra); a module's
    own agent may carry its module's id. A refusal names a free id."""

    @abstractmethod
    async def check(self, agent_id: str, owner: str) -> str | None:
        """Why `owner` can't have `agent_id` now (with a free one to use), or None."""

    @abstractmethod
    async def claim(self, agent_id: str, owner: str) -> Result:
        """Take `agent_id` for `owner`: `ok`, or `invalid_arguments` with `check`'s reason. A
        repeat claim by the owner that holds it is `ok` (a different owner is still refused);
        `check` still calls it taken, so a module can't name a second agent with it."""

    @abstractmethod
    def release(self, agent_id: str, owner: str) -> None:
        """Free `agent_id` if `owner` holds it."""

    @abstractmethod
    def taken(self) -> dict[str, str]:
        """Every claimed id and the module that holds it."""


class ListAgents(Command):
    """Every agent and whether it's busy or working. Result value: `list[AgentInfo]`."""


class StartTask(Command):
    """Give work to a free agent. Result value: the task id; `not_available` if none is free,
    the cap on open tasks is reached, or the agent would write a folder another open task writes.

    `agent_id`: that agent only (`invalid_arguments` if there is none). `parent_task_id`: the
    task that starts this one (set by the Hub's `hub.start` for an agent's child task)."""

    text: str
    context: str = ""
    agent_id: str | None = None
    parent_task_id: str | None = None


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


class SetFocus(Command):
    """Move the focus (the agent you're talking to) to `agent_id`; empty means the coordinator.
    Handled by the Agent Hub, which publishes `FocusChanged`. Sent by a UI (a tab click) or by
    the Hub's own `hub.focus` item (the Talker, after you said so). `invalid_arguments` for an
    unknown agent. Result value: the focused agent's id."""

    agent_id: str = ""


class ReportTask(Command):
    """Agent → Hub. A command, not an event, so the Hub's state never misses it."""

    task_id: str
    kind: ReportKind
    text: str


class TaskUpdated(Event):
    """A task's report or state changed. `kind` is None for changes the Hub made itself.
    `held`: the task's question or permission request waits behind its agent's **!**.
    `question_kind`: what the task's open question is now (`QuestionKind`; `none` when none)."""

    task_id: str
    state: TaskState
    kind: ReportKind | None = None
    text: str = ""
    agent_id: str = ""
    parent_task_id: str | None = None
    held: bool = False
    question_kind: QuestionKind = QuestionKind.NONE


class FocusChanged(Event):
    """The focus moved to `agent_id` (from `previous`). `released`: that agent's tasks whose
    question, permission request, reply or end was held until now, so the Talker says it and
    the UI shows its card."""

    agent_id: str
    previous: str = ""
    released: tuple[TaskInfo, ...] = ()


class FocusSuggested(Event):
    """`by` (the coordinator) suggests you talk to `agent_id` directly, for `reason`. The
    Talker asks you; the focus moves only if you say yes."""

    agent_id: str
    reason: str = ""
    by: str = ""


class AgentNotice(Event):
    """A module's callback for an agent, e.g. a slow menu item's result (`agent_id` is the
    item's caller). The Hub passes it to that agent with `ITaskAgent.note`, for its next turn."""

    agent_id: str
    text: str
    source: str = ""


class AgentStateChanged(Event):
    """An agent's `busy` or `working` changed (`change="state"`), or an agent that isn't a module
    of its own appeared (`"opened"`) or went away (`"closed"`): a helper inside `task_agents`."""

    agent_id: str
    busy: bool
    working: bool
    change: Literal["state", "opened", "closed"] = "state"


class PermissionModeChanged(Event):
    """A task agent's permission mode was set. `applies`: `now` (mid-task too), or
    `next_task` when a live switch to Manual failed."""

    agent_id: str
    mode: PermissionMode
    applies: Literal["now", "next_task"] = "now"


class AgentActivity(Event):
    """An agent's raw activity (its text and tool calls), for viewers."""

    agent_id: str
    task_id: str | None = None
    text: str


class SessionUsage(Event):
    """One agent's (or one tool's) token usage, so you know when to reset it and what it has used.
    `agent_id` is "talker", a task agent's id, a sub-agent's (`<parent>/<type> #<agentId>`),
    or any id a module reports a wrapped tool's usage under. Tokens only: no money figure.

    `context_tokens`: the latest call's size (its input, cached or not), about what each next
    call resends; 0 when no session runs. The token fields are running totals of every call
    since the app started, across fresh sessions and resets, so cached context counts again
    on every call: a measure of work done, not of new text.

    `session`: the sender's session id (new for each fresh session); when it changes, the
    `usage` module's ledger keeps the old totals and adds the new ones. "" if unknown.
    `parent`: who started it (a sub-agent's agent, a tool's calling agent), "" for none; the
    ledger rolls it up into the parent's tally and still lists it apart.
    `kind`: `claude` (an agent's own session), `subagent`, or `tool`. A sender that only
    knows some token kinds leaves the rest at 0.
    """

    agent_id: str
    context_tokens: int
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    session: str = ""
    parent: str = ""
    kind: Literal["claude", "subagent", "tool"] = "claude"

    @property
    def used_tokens(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens + self.output_tokens


class ResetRequested(Event):
    """Asks the session behind `agent_id` to start fresh. The Talker keeps its last few
    exchanges; a task agent resets at once when idle, and hands off when it has a task."""

    agent_id: str
