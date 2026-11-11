"""The Hub's delivery (`DeliverMessage`): a message never interrupts a turn; an idle agent gets it into
its open task, or as a new task; one in a turn or not running gets it later, in order."""

import logging

from assistant.contracts import AgentInfo, AgentState, DeliverMessage, ITaskAgent, Result, SendToTask, StartTask, Status
from assistant.modules.agent_hub.delivery import Delivery
from assistant.modules.agent_hub.tasks import TaskBoard


class Agent(ITaskAgent):
    """Holds at most one task, like `SessionTaskAgent`; `working` says it's in a turn."""

    def __init__(self, agent_id: str = "job", refuse: Result | None = None) -> None:
        self.agent_id, self.refuse = agent_id, refuse
        self.current: str | None = None
        self.working = False
        self.assigned: list[str] = []
        self.messages: list[tuple[str, str, bool]] = []  # task, text, sent mid-turn (an interrupt)

    def info(self) -> AgentInfo:
        state = AgentState.ACTIVE if self.working else AgentState.IDLE
        return AgentInfo(agent_id=self.agent_id, description="test", state=state)

    async def assign(self, task) -> Result:
        if self.refuse is not None:
            return self.refuse
        if self.current is not None:
            return Result.not_available(f"{self.agent_id} is busy")
        self.current = task.id
        self.assigned.append(task.text)
        return Result.ok()

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        if task_id != self.current:
            return Result.invalid_arguments("not mine")
        self.messages.append((task_id, text, self.working))
        return Result.ok()

    async def cancel(self, task_id: str) -> Result:
        return Result.ok()

    async def answer_permission(self, task_id, allow):
        return Result.ok()

    async def set_permission_mode(self, mode):
        return Result.ok()

    async def request_approval(self, action, run):
        return Result.ok()

    def note(self, text: str) -> None:
        pass


def parts(running: dict[str, Agent]) -> tuple[TaskBoard, Delivery]:
    log = logging.getLogger("test")
    board = TaskBoard(publish=lambda event: None, log=log, agents=lambda: list(running.values()),
                      agent=running.get, focused=lambda: "", feed=lambda line: None,
                      coordinator="main_assistant", max_extra=3)  # fmt: skip
    return board, Delivery(board, running.get, log)


def message(text: str = "the CV is ready", to: str = "job") -> DeliverMessage:
    return DeliverMessage(agent_id=to, text=text, sender="cv")


async def test_an_idle_agent_gets_it_into_its_open_task_which_answers_its_question():
    running = {"job": Agent()}
    board, delivery = parts(running)
    task = (await board.start(StartTask(text="apply to Acme", agent_id="job"))).value
    sent = await delivery.deliver(message())
    assert sent.value == f"message {task}"
    assert running["job"].messages == [(task, "[Message from cv] the CV is ready", False)]


async def test_an_agent_with_no_task_gets_a_new_one():
    running = {"job": Agent()}
    board, delivery = parts(running)
    sent = await delivery.deliver(message())
    assert sent.is_ok and sent.value.startswith("task ") and board.open_task_of("job").id == sent.value.split()[1]
    assert running["job"].assigned == ["[Message from cv] the CV is ready"]


async def test_an_agent_in_a_turn_gets_it_when_the_turn_ends_never_as_an_interrupt():
    running = {"job": Agent()}
    board, delivery = parts(running)
    task = (await board.start(StartTask(text="apply to Acme", agent_id="job"))).value
    running["job"].working = True
    assert (await delivery.deliver(message())).value == "pending"
    await delivery.flush()  # still in its turn
    assert running["job"].messages == [] and len(delivery.waiting("job")) == 1
    running["job"].working = False  # the turn ended (the Hub flushes on AgentStateChanged)
    await delivery.flush()
    assert running["job"].messages == [(task, "[Message from cv] the CV is ready", False)] and not delivery.waiting()


async def test_an_agent_not_running_gets_it_when_it_starts_and_the_order_is_kept():
    running: dict[str, Agent] = {}
    board, delivery = parts(running)
    assert (await delivery.deliver(message("first"))).value == "pending"
    running["job"] = Agent()
    assert (await delivery.deliver(message("second"))).value == "pending"  # queued behind the first
    await delivery.flush()
    agent = running["job"]
    assert agent.assigned == ["[Message from cv] first"]  # a new task, then the second into it
    assert [m[1] for m in agent.messages] == ["[Message from cv] second"] and not delivery.waiting()


async def test_what_waits_is_handed_over_to_the_next_copy():
    running: dict[str, Agent] = {}
    board, delivery = parts(running)
    await delivery.deliver(message("one"))
    await delivery.deliver(message("two", to="other"))
    again = Delivery(board, running.get, logging.getLogger("test"), delivery.export())
    assert again.waiting() == delivery.waiting() and [w.agent_id for w in again.waiting()] == ["job", "other"]


async def test_a_refusal_for_good_fails_and_nothing_waits():
    running = {"job": Agent(refuse=Result.failed("the job start can't read the base CV"))}
    _, delivery = parts(running)
    sent = await delivery.deliver(message())
    assert sent.status is Status.FAILED and "base CV" in sent.error and not delivery.waiting()


async def test_a_parents_own_send_still_interrupts_its_child():
    """Unchanged: `hub.send` to your own child task goes straight in, mid-turn too."""
    running = {"job": Agent()}
    board, _ = parts(running)
    task = (await board.start(StartTask(text="apply", agent_id="job"))).value
    running["job"].working = True
    assert (await board.send(SendToTask(task_id=task, text="stop and use the 2024 CV"))).is_ok
    assert running["job"].messages == [(task, "stop and use the 2024 CV", True)]
