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
    TURN_DONE,
    TURN_WAIT,
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
KEEP_FINISHED = 20  # finished records kept in memory; older ones go (not held, not an open task's parent)
RESULT_IN_FEED = 120  # characters of a finished task's result in the coordinator's feed
RESULT_TO_PARENT = 4000  # characters of a finished child task's result in its parent agent's message
CHILD_ENDED = "Your child task {id} on {agent} ended {state}: {result}"


@dataclass
class TaskRecord:
    id: str
    agent_id: str
    text: str
    state: TaskState = TaskState.ACTIVE
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_REPORTS))
    activity: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_ACTIVITY))
    question: str | None = None
    result: str | None = None
    parent_task_id: str | None = None
    held: bool = False
    reply: str | None = None  # a reply that waits behind the agent's ! (kept only while held)
    question_kind: QuestionKind = QuestionKind.NONE
    question_key: str = ""  # the question's context key, from its agent (cv: the job's folder)
    tell_parent: bool = True  # False: no message to the parent's agent at its end (`StartTask.tell_parent`)
    # The agent object that took the task. A reload provides a new object under the same id, which
    # never heard of this task: the board then closes it (`TaskBoard._close_replaced`).
    holder: Any = field(default=None, repr=False, compare=False)

    @property
    def asked(self) -> bool:
        """Its agent dropped it and is free; the record is its note: a question (a `need`), or
        what it ended waiting on (a child task, its card, an approval's outcome)."""
        if self.state is not TaskState.IDLE:
            return False
        dropped_card = self.question_kind is QuestionKind.PERMISSION and self.holder is None
        return dropped_card or self.question_kind in (QuestionKind.NEED, QuestionKind.RISKY, QuestionKind.WAIT)

    @property
    def paused(self) -> bool:
        """Stopped after a reply (`hub.send` with pause): its agent still holds it."""
        return self.state is TaskState.IDLE and not self.asked

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
            question_kind=self.question_kind, question_key=self.question_key,
        )

    def export(self) -> dict:
        """An asked record, for the next copy of the Hub (`TaskBoard.restore`)."""
        return {"id": self.id, "agent_id": self.agent_id, "text": self.text, "question": self.question,
                "question_kind": str(self.question_kind), "question_key": self.question_key,
                "parent_task_id": self.parent_task_id,
                "tell_parent": self.tell_parent, "held": self.held, "recent": list(self.recent)}  # fmt: skip


ANSWER = 'Answer to your question in task {id} ("{question}"): {text}'


class TaskBoard:
    """Every task and its state: started, messaged, reported, answered, ended.

    `agents()` lists the running agents and `agent(id)` finds one; `focused()` is the agent
    you're talking to; `feed(line)` is a background line for the coordinator;
    `tell_parent(agent_id, text, task_id)` messages an agent (the Hub's delivery: never into a
    running turn), into `task_id` when given: a finished child task's parent, or a task that
    ended waiting, given back with what it waited for. At most
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
        restricted: frozenset[str] = frozenset(),
        tell_parent: Callable[..., None] = lambda agent_id, text, task_id="": None,
    ) -> None:
        self._restricted = restricted  # agents a free-agent pick skips (started only when named)
        self._tell_parent = tell_parent
        self._publish, self._log = publish, log
        self._agents, self._agent, self._focused, self._feed = agents, agent, focused, feed
        self._coordinator, self._max_extra = coordinator, max_extra
        self._tasks: dict[str, TaskRecord] = {}  # insertion order is start order

    # --- reading ---

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def open_records(self) -> list[TaskRecord]:
        self._close_replaced()
        return [r for r in self._tasks.values() if not r.state.is_final]

    def _close_replaced(self) -> None:
        """End every open task whose agent was replaced (the module reloaded: a new agent object
        under the same id). Its old copy can't report any more, so the record would stay open,
        count the agent busy in the Hub's eyes, block the Hub's own reload, and catch the tab's
        messages meant for the agent's new task."""
        for record in [r for r in self._tasks.values() if not r.state.is_final and r.holder is not None]:
            current = self._agent(record.agent_id)
            if current is not None and current is not record.holder:
                self._finish(record, TaskState.FAILED, None, f"{record.agent_id} was reloaded; this task "
                                                             "ended with its old copy")  # fmt: skip

    def open_task_of(self, agent_id: str) -> TaskRecord | None:
        """`agent_id`'s newest open task it holds (a stale older one, left by a reload, never
        shadows it); else its newest task holding a question it asked."""
        records = [r for r in reversed(self.open_records()) if r.agent_id == agent_id]
        return next((r for r in records if not r.asked), records[0] if records else None)

    def held_records(self) -> list[TaskRecord]:
        """The open tasks an agent holds (active or paused), not the questions waiting on you."""
        return [r for r in self.open_records() if not r.asked]

    def export_questions(self) -> list[dict]:
        """The asked records, for the next copy of the Hub: a question outlives a Hub reload."""
        return [r.export() for r in self._tasks.values() if r.asked]

    def restore(self, questions: list[dict]) -> None:
        """Take back what a previous copy's `export_questions` handed over."""
        for q in questions:
            record = TaskRecord(id=q["id"], agent_id=q["agent_id"], text=q["text"], state=TaskState.IDLE,
                                question=q.get("question"), question_kind=QuestionKind(q["question_kind"]),
                                question_key=q.get("question_key", ""), parent_task_id=q.get("parent_task_id"),
                                tell_parent=q.get("tell_parent", True),
                                held=bool(q.get("held")))  # fmt: skip
            record.recent.extend(q.get("recent") or ())
            self._tasks[record.id] = record

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
        else:
            agents = [a for a in agents if a.info().agent_id not in self._restricted]
        if not agents:
            return Result.not_available("No agent is running")
        # Only active tasks count: an idle agent writes nothing, and a question waiting on you ties up no agent.
        open_records = [r for r in self.open_records() if r.state is TaskState.ACTIVE]
        extras = sum(1 for r in open_records if r.agent_id != self._coordinator)
        refusal = "Every agent is active"
        for agent in agents:
            info = agent.info()
            if info.active:
                refusal = f"{info.agent_id} is active" if command.agent_id else refusal
                continue
            if info.agent_id != self._coordinator and extras >= self._max_extra:
                refusal = (f"{extras} extra agents are working, the most at once ({self._max_extra}; "
                           "max_extra_agents in [modules.agent_hub])")  # fmt: skip
                continue
            if clash := self._folder_clash(info.agent_id, info.write_folders, open_records):
                refusal = clash
                continue
            self._drop_paused(info.agent_id)  # the agent drops a task it was stopped on for this one
            # Recorded before assigning, so a report that arrives at once finds it.
            record = TaskRecord(id=uuid4().hex[:8], agent_id=info.agent_id, text=command.text,
                                parent_task_id=command.parent_task_id, tell_parent=command.tell_parent,
                                holder=agent)  # fmt: skip
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
        if record.asked:
            return await self._answer(record, command.text)
        agent = self._agent(record.agent_id)
        if agent is None:
            self._finish(record, TaskState.FAILED, None, f"{record.agent_id} is no longer running")
            return Result.not_available(f"{record.agent_id} is no longer running")
        result = await agent.message(record.id, command.text, command.resume)
        if result.is_ok:
            record.state = TaskState.ACTIVE if command.resume else TaskState.IDLE
            record.answered()
            self._updated(record, None, command.text)
        elif result.status is Status.INVALID_ARGUMENTS:  # the agent doesn't hold it: a reload replaced it
            self._finish(record, TaskState.FAILED, None, f"{record.agent_id} no longer holds this task (reloaded)")
            return Result.not_available(f"Task {record.id} ended: {record.agent_id} no longer holds it (it was "
                                        "reloaded); start a new task")  # fmt: skip
        return result

    async def _answer(self, record: TaskRecord, text: str) -> Result:
        """The answer to the question `record` holds: the same task, given back to its agent
        (`not_available` while the agent is active or not running; the question stays open)."""
        agent = self._agent(record.agent_id)
        if agent is None:
            return Result.not_available(f"{record.agent_id} isn't running; the answer waits for it")
        if agent.info().active:
            return Result.not_available(f"{record.agent_id} is in a turn; the answer waits for it to end")
        kept = (record.question, record.question_kind, record.held)
        task = Task(id=record.id, text=ANSWER.format(id=record.id, question=record.info().question_line, text=text),
                    question_key=record.question_key)  # fmt: skip
        self._drop_paused(record.agent_id)
        record.state, record.holder = TaskState.ACTIVE, agent
        record.answered()
        result = await agent.assign(task)
        if not result.is_ok:  # still the question
            record.state, record.holder = TaskState.IDLE, None
            record.question, record.question_kind, record.held = kept
            return result
        if kept[1] is QuestionKind.PERMISSION:  # given back before its card was answered: the card stays open
            record.question, record.question_kind = kept[0], kept[1]
        self._log.info("Task %s answered; %s has it again", record.id, record.agent_id)
        self._updated(record, None, text)
        return Result.ok()

    def _drop_paused(self, agent_id: str) -> None:
        """`agent_id` takes other work: a task it was stopped on ends (the agent drops it too)."""
        for record in [r for r in self.open_records() if r.agent_id == agent_id and r.paused]:
            self._finish(record, TaskState.DONE, None, "stopped: a new task replaced it")

    async def cancel(self, command: CancelTask) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        if record.asked:  # its agent dropped it already
            self._finish(record, TaskState.CANCELLED, None, "cancelled")
            return Result.ok()
        agent = self._agent(record.agent_id)
        result = await agent.cancel(record.id) if agent else Result.ok()
        if result.is_ok:
            self._finish(record, TaskState.CANCELLED, None, "cancelled")
        elif result.status is Status.INVALID_ARGUMENTS:  # the agent doesn't hold it: a stale record, closed here
            self._finish(record, TaskState.CANCELLED, None, f"cancelled: {record.agent_id} no longer held it (reloaded)")
            return Result.ok()
        return result

    async def report(self, command: ReportTask) -> Result:
        record = self._open_task(command.task_id)
        if isinstance(record, Result):
            return record
        if command.kind is ReportKind.TURN_END:
            if not command.card_open and record.question_kind is QuestionKind.PERMISSION:
                record.answered()  # the agent closed it itself (a tool request timed out)
            return self._settle(record, command.key)
        record.recent.append(f"{command.kind}: {command.text}")
        match command.kind:
            case ReportKind.PROGRESS if record.asked:  # input for a task its agent dropped (an approval's outcome)
                self._log.info("Task %s gets what it waited for; it goes back to %s", record.id, record.agent_id)
                self._tell_parent(record.agent_id, command.text, record.id)
            case ReportKind.NEED:  # the agent dropped the task and is free; the record holds the question
                record.state, record.holder = TaskState.IDLE, None
                record.ask(command.kind, command.text)
                record.question_key = command.key or record.question_key
                record.held = record.held or record.agent_id != self._focused()  # waits behind its tab's !
            case ReportKind.PERMISSION:  # a card holds the agent in its turn
                record.ask(command.kind, command.text)
                record.held = record.held or record.agent_id != self._focused()
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
        dropped = record.asked and record.question_kind is QuestionKind.PERMISSION  # it ended waiting on this card
        result = await agent.answer_permission(record.id, command.allow)
        if result.is_ok and dropped:  # the outcome comes back as its `progress`, which starts it again
            record.question = f"waiting on the outcome of: {record.question}"
            record.question_kind, record.held = QuestionKind.WAIT, False
            self._updated(record, None, "permission allowed" if command.allow else "permission denied")
        elif result.is_ok:
            record.state = TaskState.ACTIVE
            record.answered()
            self._updated(record, None, "permission allowed" if command.allow else "permission denied")
        return result

    async def set_mode(self, command: SetPermissionMode) -> Result:
        agent = self._agent(command.agent_id)
        if agent is None:
            return Result.invalid_arguments(f"No agent {command.agent_id!r}")
        result = await agent.set_permission_mode(command.mode)
        record = next((r for r in self.open_records() if r.agent_id == command.agent_id
                       and r.question_kind is QuestionKind.PERMISSION), None)  # fmt: skip
        if result.is_ok and result.value is True and record is not None:  # Auto answered its open card
            record.state = TaskState.ACTIVE
            record.answered()
            self._updated(record, None, "permission allowed (Auto)")
        return result

    # --- inside ---

    def _settle(self, record: TaskRecord, key: str) -> Result:
        """A turn of `record`'s ended with no tag, or with its card open (`turn_end`). Waiting on
        its card, or on child tasks that will message it (`tell_parent`): the task ends waiting.
        Its agent drops it and is free; the record is its note (what it waits on, its context
        `key`), and the card's outcome, a child's end or a message gives it back (`_answer`). Else:
        done (the agent ends it with its own `done` report)."""
        card = record.question_kind is QuestionKind.PERMISSION
        waits = ["the user's answer to its card"] if card else []
        children = [f"{r.id} ({r.agent_id})" for r in self.open_records()
                    if r.parent_task_id == record.id and r.tell_parent]  # fmt: skip
        if children:
            waits.append(f"child task{'s' if len(children) > 1 else ''} {', '.join(children)}")
        if not waits:
            return Result.ok(TURN_DONE)
        line = f"waiting on {' and '.join(waits)}"
        record.state, record.holder = TaskState.IDLE, None
        record.question_key = key or record.question_key
        if not card:  # a card stays the question until it's answered
            record.question, record.question_kind = line, QuestionKind.WAIT
        record.recent.append(f"ended {line}")
        self._log.info("Task %s ended %s", record.id, line)
        self._updated(record, ReportKind.TURN_END, line)
        return Result.ok(TURN_WAIT)

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
        record.holder = None  # an ended task keeps no agent object alive (a reloaded module's old copy)
        self._log.info("Task %s %s", record.id, state)
        self._updated(record, kind, text)
        if record.agent_id != self._coordinator:
            self._feed(f"[{record.agent_id}] task {state}: {' '.join(text.split())[:RESULT_IN_FEED]}")
        if hold:
            self._to_parent(record, state, text)
        self._prune()

    def _to_parent(self, record: TaskRecord, state: TaskState, text: str) -> None:
        """The agent's own end (done or failed) of a child task: its parent's agent gets it as a
        message, unless that's the same agent, or the coordinator whose task isn't waiting on it
        (its feed line above is enough). A parent that ended waiting gets it in that task, which
        starts again from its note.
        A task started with `tell_parent=False` tells no one: its module reports the end itself."""
        parent = self._tasks.get(record.parent_task_id) if record.parent_task_id else None
        if parent is None or not record.tell_parent or parent.agent_id == record.agent_id:
            return
        waiting = parent.asked and parent.question_kind is QuestionKind.WAIT
        if parent.agent_id == self._coordinator and not waiting:
            return
        result = text if len(text) <= RESULT_TO_PARENT else text[:RESULT_TO_PARENT] + " …(cut)"
        self._log.info("Task %s ended %s; telling its parent's agent %s", record.id, state, parent.agent_id)
        self._tell_parent(parent.agent_id, CHILD_ENDED.format(id=record.id, agent=record.agent_id, state=state,
                                                              result=result), parent.id if waiting else "")  # fmt: skip

    def _prune(self) -> None:
        """Keep the last `KEEP_FINISHED` finished records. A held one (it waits behind its tab's !)
        and the parent of an open task (its child's steering checks it) always stay."""
        parents = {r.parent_task_id for r in self._tasks.values() if not r.state.is_final and r.parent_task_id}
        done = [r.id for r in self._tasks.values() if r.state.is_final and not r.held and r.id not in parents]
        for task_id in done[:-KEEP_FINISHED]:
            del self._tasks[task_id]

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
