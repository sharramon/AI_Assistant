"""A task whose agent was reloaded (a new agent object under the same id, which never heard of it)
is closed by the Hub at the source: the record knows the agent that took it, so the old task ends,
never counts as open, and never catches a message meant for the agent's new task."""

import logging

from assistant.contracts import (
    AgentInfo,
    CancelTask,
    ITaskAgent,
    ReportKind,
    ReportTask,
    Result,
    SendToTask,
    StartTask,
    Status,
    TaskState,
)
from assistant.modules.agent_hub.tasks import KEEP_FINISHED, TaskBoard


class Agent(ITaskAgent):
    """A task agent that holds at most one task, like `SessionTaskAgent`; records its messages."""

    def __init__(self) -> None:
        self.current: str | None = None
        self.messages: list[tuple[str, str]] = []

    def info(self) -> AgentInfo:
        return AgentInfo(agent_id="worker", description="test worker")

    async def assign(self, task) -> Result:
        self.current = task.id
        return Result.ok()

    def _holds(self, task_id: str) -> Result | None:
        return None if task_id == self.current else Result.invalid_arguments(f"{task_id!r} is not worker's current task")

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        refused = self._holds(task_id)
        if refused is None:
            self.messages.append((task_id, text))
        return refused or Result.ok()

    async def cancel(self, task_id: str) -> Result:
        return self._holds(task_id) or Result.ok()

    async def answer_permission(self, task_id, allow):
        return Result.ok()

    async def set_permission_mode(self, mode):
        return Result.ok()

    async def request_approval(self, action, run):
        return Result.ok()

    def note(self, text: str) -> None:
        pass


def board(holder: dict) -> TaskBoard:
    return TaskBoard(publish=lambda event: None, log=logging.getLogger("test"), agents=lambda: [holder["agent"]],
                     agent=lambda agent_id: holder["agent"], focused=lambda: "", feed=lambda line: None,
                     coordinator="main_assistant", max_extra=3)  # fmt: skip


async def test_a_reload_closes_the_old_task_and_the_tabs_message_reaches_the_new_one():
    holder = {"agent": Agent()}
    tasks = board(holder)
    old = (await tasks.start(StartTask(text="old job", agent_id="worker"))).value
    assert tasks.get(old).state is TaskState.ACTIVE

    holder["agent"] = new_agent = Agent()  # the module was reloaded: a new agent under the same id
    assert [r.id for r in tasks.open_records()] == []  # the old task is closed at once, by the board
    assert tasks.get(old).state is TaskState.FAILED and "reloaded" in tasks.get(old).result

    new = (await tasks.start(StartTask(text="new job", agent_id="worker"))).value
    record = tasks.open_task_of("worker")  # what a message typed on the agent's tab goes to
    assert record.id == new
    assert (await tasks.send(SendToTask(task_id=record.id, text="I've signed in"))).is_ok
    assert new_agent.messages == [(new, "I've signed in")]


async def test_a_task_the_agent_still_holds_stays_open():
    holder = {"agent": Agent()}
    tasks = board(holder)
    task = (await tasks.start(StartTask(text="job", agent_id="worker"))).value
    assert [r.id for r in tasks.open_records()] == [task]
    assert (await tasks.send(SendToTask(task_id=task, text="hello"))).is_ok


async def test_a_refusal_from_the_agent_also_closes_a_record_it_doesnt_hold():
    """The backstop for a record without its holder: the agent says it doesn't hold the task."""
    holder = {"agent": Agent()}
    tasks = board(holder)
    old = (await tasks.start(StartTask(text="old job", agent_id="worker"))).value
    tasks.get(old).holder = None  # as if the board couldn't tell
    holder["agent"] = Agent()
    refused = await tasks.send(SendToTask(task_id=old, text="hello"))
    assert refused.status is Status.NOT_AVAILABLE and tasks.get(old).state is TaskState.FAILED
    other = (await tasks.start(StartTask(text="job", agent_id="worker"))).value
    tasks.get(other).holder = None
    holder["agent"] = Agent()
    assert (await tasks.cancel(CancelTask(task_id=other))).is_ok and tasks.get(other).state is TaskState.CANCELLED


async def test_an_ended_task_lets_go_of_its_agent_and_old_records_are_dropped():
    holder = {"agent": Agent()}
    tasks = board(holder)
    parent = (await tasks.start(StartTask(text="parent", agent_id="worker"))).value
    child = (await tasks.start(StartTask(text="child", agent_id="worker", parent_task_id=parent))).value
    await tasks.report(ReportTask(task_id=parent, kind=ReportKind.DONE, text="handed on"))
    assert tasks.get(parent).holder is None and tasks.get(child).holder is not None
    ids = []
    for n in range(KEEP_FINISHED + 5):  # many tasks end while the child is open
        ids.append((await tasks.start(StartTask(text=f"job {n}", agent_id="worker"))).value)
        await tasks.report(ReportTask(task_id=ids[-1], kind=ReportKind.DONE, text="done"))
        assert tasks.get(ids[-1]).held  # an end out of focus waits behind the tab's ! and is never dropped
        tasks.release("worker")  # the user opened the tab
    finished = [r for r in tasks._tasks.values() if r.state.is_final]
    assert len(finished) == KEEP_FINISHED + 2  # the last 20, the newest (held when it ended), the open task's parent
    assert tasks.get(parent) is not None and tasks.get(ids[0]) is None  # the oldest went; the parent stayed
    assert all(r.holder is None for r in finished) and tasks.get(child).state is TaskState.ACTIVE
