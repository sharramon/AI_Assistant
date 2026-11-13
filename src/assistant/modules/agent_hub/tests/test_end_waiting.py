"""Rule 2 (docs/next-steps/auto-skips-cards.md): a task that's only waiting ends with a note.

A turn that ends with its card open, or with child tasks still open, ends the task waiting: its
agent drops it and is free, and the Hub's record is the note. The card's outcome, a child's end
or a message gives the same task back (`TaskBoard._answer`)."""

import asyncio
import logging

from assistant.contracts import (
    TURN_WAIT,
    AgentStateChanged,
    AnswerPermission,
    QuestionKind,
    ReloadModule,
    ReportKind,
    ReportTask,
    Result,
    StartTask,
    Task,
    TaskState,
)
from assistant.infra import SessionTaskAgent
from assistant.modules.agent_hub.delivery import Delivery
from assistant.modules.agent_hub.tasks import TaskBoard
from assistant.testkit import StubContext, StubSession

COORDINATOR = "main_assistant"


def _board(rig: "Rig") -> TaskBoard:
    return TaskBoard(publish=lambda event: None, log=logging.getLogger("test"),
                     agents=lambda: list(rig.agents.values()), agent=rig.agents.get, focused=lambda: "",
                     feed=rig.feed.append, coordinator=COORDINATOR, max_extra=3,
                     tell_parent=lambda agent_id, text, task_id="": rig.delivery.tell(agent_id, text, task_id))  # fmt: skip


class Rig:
    """A real TaskBoard and Delivery with `SessionTaskAgent`s on stub sessions."""

    def __init__(self) -> None:
        self.agents: dict[str, SessionTaskAgent] = {}
        self.sessions: dict[str, StubSession] = {}
        self.feed: list[str] = []
        self.ran: list[object] = []  # commands other than reports (a reload the user allowed)
        self.flushes: list[asyncio.Future] = []
        self.board = _board(self)
        self.delivery = Delivery(self.board, self.agents.get, logging.getLogger("test"))

    def add(self, agent_id: str) -> SessionTaskAgent:
        session, ctx = StubSession(), StubContext()

        async def send(command):
            if isinstance(command, ReportTask):
                return await self.board.report(command)
            self.ran.append(command)
            return Result.ok()

        def publish(event):
            if isinstance(event, AgentStateChanged):
                self.flushes.append(asyncio.ensure_future(self.delivery.flush()))

        ctx.send, ctx.publish = send, publish
        self.sessions[agent_id] = session
        self.agents[agent_id] = SessionTaskAgent(session, ctx, agent_id, f"the {agent_id}")
        return self.agents[agent_id]

    async def start(self, agent_id: str, parent: str | None = None, tell_parent: bool = True,
                    text: str = "") -> str:  # fmt: skip
        result = await self.board.start(StartTask(text=text or f"work for {agent_id}", agent_id=agent_id,
                                                  parent_task_id=parent, tell_parent=tell_parent))  # fmt: skip
        assert result.is_ok, result.error
        return result.value

    async def end_turn(self, agent_id: str, text: str = "Done for now.") -> None:
        session = self.sessions[agent_id]
        session.working = False
        session.on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
        session.on_event({"type": "result", "is_error": False, "result": text})
        await self.settle()

    async def settle(self) -> None:
        for _ in range(4):
            await asyncio.sleep(0.03)
            await asyncio.gather(*self.flushes)
            await self.delivery.drain()

    async def close(self) -> None:
        for agent in self.agents.values():
            await agent.close()


def _resumed(rig: Rig, agent_id: str, task_id: str) -> str:
    """The last text `agent_id`'s session got, checked to be `task_id` given back."""
    text = rig.sessions[agent_id].sent[-1]
    assert f"Answer to your question in task {task_id}" in text, text
    return text


async def test_a_turn_end_with_nothing_to_wait_on_is_done():
    rig = Rig()
    agent = rig.add("worker")
    task = await rig.start("worker")
    await rig.end_turn("worker")
    assert rig.board.get(task).state is TaskState.DONE and not agent.has_task
    await rig.close()


async def test_a_parent_waiting_on_its_child_ends_waiting_is_free_and_is_resumed_by_its_end():
    rig = Rig()
    parent_agent = rig.add("parent")
    rig.add("helper")
    parent = await rig.start("parent")
    child = await rig.start("helper", parent=parent)
    await rig.end_turn("parent", "Started a helper; waiting for it.")
    record = rig.board.get(parent)
    assert record.asked and record.question_kind is QuestionKind.WAIT and child in record.question
    assert not parent_agent.has_task and not parent_agent.info().active  # dropped: free
    other = await rig.start("parent", text="other work")  # it takes new work while it waits
    assert rig.board.get(parent).asked  # the waiting task isn't dropped for it
    await rig.end_turn("helper", "The helper's result.")
    assert rig.board.get(child).state is TaskState.DONE
    assert rig.board.get(parent).asked  # the parent's agent is in a turn: the result waits for it
    await rig.end_turn("parent", "Other work done.")
    assert rig.board.get(other).state is TaskState.DONE
    record = rig.board.get(parent)
    assert record.state is TaskState.ACTIVE and record.question_kind is QuestionKind.NONE
    text = _resumed(rig, "parent", parent)
    assert "Your child task" in text and "The helper's result." in text
    await rig.end_turn("parent", "All done with the helper's result.")
    assert rig.board.get(parent).state is TaskState.DONE  # no open child left
    await rig.close()


async def test_a_child_started_without_tell_parent_does_not_count():
    rig = Rig()
    rig.add("parent")
    rig.add("helper")
    parent = await rig.start("parent")
    await rig.start("helper", parent=parent, tell_parent=False)
    await rig.end_turn("parent")
    assert rig.board.get(parent).state is TaskState.DONE
    await rig.close()


async def test_the_coordinator_ends_waiting_on_a_helper_and_is_resumed_by_its_end():
    rig = Rig()
    coordinator = rig.add(COORDINATOR)
    rig.add("helper")
    parent = await rig.start(COORDINATOR)
    child = await rig.start("helper", parent=parent)
    await rig.end_turn(COORDINATOR, "Handed it to a helper.")
    record = rig.board.get(parent)
    assert record.asked and record.question_kind is QuestionKind.WAIT and child in record.question
    assert not coordinator.has_task
    await rig.end_turn("helper", "Helper finished.")
    assert rig.board.get(parent).state is TaskState.ACTIVE
    assert "Helper finished." in _resumed(rig, COORDINATOR, parent)
    await rig.close()


async def test_a_card_open_at_the_turn_end_ends_waiting_and_its_answer_resumes_the_task():
    rig = Rig()
    agent = rig.add("worker")  # Manual: a RELOAD: line asks on a card
    task = await rig.start("worker")
    await rig.end_turn("worker", "Changed the module.\nRELOAD: ghost")
    record = rig.board.get(task)
    assert record.asked and record.question_kind is QuestionKind.PERMISSION  # the card stays the question
    assert not agent.has_task and not agent.info().active
    assert (await rig.board.answer(AnswerPermission(task_id=task, allow=True))).is_ok
    await rig.settle()
    assert isinstance(rig.ran[-1], ReloadModule)
    assert "[App] Reload the ghost module" in _resumed(rig, "worker", task)  # given back with the outcome
    assert rig.board.get(task).state is TaskState.ACTIVE and agent.info().active
    await rig.close()


async def test_a_need_is_not_touched():
    rig = Rig()
    agent = rig.add("worker")
    task = await rig.start("worker")
    await rig.end_turn("worker", "Which one?\nNEED: Pick A or B?")
    record = rig.board.get(task)
    assert record.asked and record.question_kind is QuestionKind.NEED and not agent.has_task
    await rig.close()


async def test_two_waiting_tasks_on_one_agent_each_get_their_own_childs_end():
    rig = Rig()
    rig.add("parent")
    rig.add("helper1")
    rig.add("helper2")
    first = await rig.start("parent", text="first job")
    await rig.start("helper1", parent=first)
    await rig.end_turn("parent", "Waiting on helper1.")
    second = await rig.start("parent", text="second job")
    await rig.start("helper2", parent=second)
    await rig.end_turn("parent", "Waiting on helper2.")
    assert rig.board.get(first).asked and rig.board.get(second).asked
    await rig.end_turn("helper2", "Result two.")
    assert rig.board.get(second).state is TaskState.ACTIVE and rig.board.get(first).asked
    assert "Result two." in _resumed(rig, "parent", second)
    await rig.end_turn("parent", "Second job done.")
    assert rig.board.get(second).state is TaskState.DONE
    await rig.end_turn("helper1", "Result one.")
    assert rig.board.get(first).state is TaskState.ACTIVE
    assert "Result one." in _resumed(rig, "parent", first)
    await rig.close()


async def test_a_waiting_record_outlives_a_hub_reload():
    rig = Rig()
    rig.add("parent")
    rig.add("helper")
    parent = await rig.start("parent")
    child = await rig.start("helper", parent=parent)
    await rig.end_turn("parent", "Waiting on the helper.")
    copy = _board(rig)
    copy.restore(rig.board.export_questions())
    record = copy.get(parent)
    assert record is not None and record.asked and record.question_kind is QuestionKind.WAIT
    assert child in record.question
    await rig.close()


async def test_an_agent_told_to_wait_drops_the_task_keeps_its_card_and_resumes_in_the_live_session():
    session, ctx = StubSession(), StubContext()
    closes = []
    real_close = session.close

    async def close():
        closes.append(1)
        await real_close()

    async def send(command):
        if isinstance(command, ReportTask) and command.kind is ReportKind.TURN_END:
            return Result.ok(TURN_WAIT)
        return Result.ok()

    session.close, ctx.send = close, send
    agent = SessionTaskAgent(session, ctx, "worker", "a worker")
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    session.working = False
    text = "Changed it.\nRELOAD: ghost"
    session.on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    session.on_event({"type": "result", "is_error": False, "result": text})
    await asyncio.sleep(0.05)
    assert not agent.has_task and not agent.info().active
    assert agent._gate.parked == "t1"  # its card stays open for it
    assert (await agent.assign(Task(id="t1", text="the answer", question_key=""))).is_ok
    assert session.sent[-1] == "the answer" and not closes  # the live session, as for a NEED
    await agent.close()
