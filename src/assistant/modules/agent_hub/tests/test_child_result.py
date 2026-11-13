"""A finished child task's end goes to its parent's agent as a message (the Hub's delivery: never
into a running turn); the coordinator as parent gets only its feed line."""

import logging

from assistant.contracts import CancelTask, ReportKind, ReportTask, StartTask
from assistant.modules.agent_hub.delivery import Delivery
from assistant.modules.agent_hub.tasks import TaskBoard

from .test_delivery import Agent


def parts(running: dict[str, Agent], feed: list[str]) -> tuple[TaskBoard, Delivery]:
    log = logging.getLogger("test")
    holder: dict[str, Delivery] = {}
    board = TaskBoard(publish=lambda event: None, log=log, agents=lambda: list(running.values()),
                      agent=running.get, focused=lambda: "", feed=feed.append,
                      coordinator="main_assistant", max_extra=3,
                      tell_parent=lambda agent_id, text, task_id="": holder["d"].tell(agent_id, text, task_id))  # fmt: skip
    holder["d"] = Delivery(board, running.get, log)
    return board, holder["d"]


async def child_of(board: TaskBoard, parent_agent: str, running: dict[str, Agent]) -> tuple[str, str]:
    """The parent's task on `parent_agent`, and a child task on cv under it."""
    parent = (await board.start(StartTask(text="apply to Acme", agent_id=parent_agent))).value
    child = (await board.start(StartTask(text="tailor the CV", agent_id="cv", parent_task_id=parent))).value
    return parent, child


async def test_an_idle_parent_whose_task_ended_gets_the_result_as_a_new_task():
    running = {"job": Agent("job"), "cv": Agent("cv")}
    feed: list[str] = []
    board, delivery = parts(running, feed)
    parent, child = await child_of(board, "job", running)
    await board.report(ReportTask(task_id=parent, kind=ReportKind.DONE, text="handed the CV job over"))
    running["job"].current = None  # the job agent dropped its ended task
    await board.report(ReportTask(task_id=child, kind=ReportKind.DONE, text="CV_RESULT: ready"))
    await delivery.drain()
    assert running["job"].assigned[-1] == (f"[Message from agent_hub] Your child task {child} on cv ended done: "
                                           "CV_RESULT: ready")  # fmt: skip
    assert any("task done" in line for line in feed)  # the coordinator still gets its line


async def test_a_child_started_with_tell_parent_false_tells_no_one():
    """cv.task's case: its module reports the end itself (cv.job_finished), so the Hub stays quiet."""
    running = {"job": Agent("job"), "cv": Agent("cv")}
    feed: list[str] = []
    board, delivery = parts(running, feed)
    parent = (await board.start(StartTask(text="apply to Acme", agent_id="job"))).value
    child = (await board.start(StartTask(text="tailor the CV", agent_id="cv", parent_task_id=parent,
                                         tell_parent=False))).value  # fmt: skip
    await board.report(ReportTask(task_id=child, kind=ReportKind.DONE, text="CV_RESULT: ready"))
    await delivery.drain()
    assert running["job"].messages == [] and running["job"].assigned == ["apply to Acme"] and not delivery.waiting()
    assert any("task done" in line for line in feed)  # the coordinator still gets its line
    assert board.may_steer(child, "job") is None  # the parent link stays: the job agent may still message it


async def test_a_parent_in_a_turn_gets_it_when_the_turn_ends():
    running = {"job": Agent("job"), "cv": Agent("cv")}
    board, delivery = parts(running, [])
    parent, child = await child_of(board, "job", running)
    running["job"].working = True
    await board.report(ReportTask(task_id=child, kind=ReportKind.FAILED, text="the base CV is unreadable"))
    await delivery.drain()
    assert running["job"].messages == [] and len(delivery.waiting("job")) == 1
    running["job"].working = False
    await delivery.flush()
    assert running["job"].messages == [(parent, f"[Message from agent_hub] Your child task {child} on cv "
                                                "ended failed: the base CV is unreadable", False)]  # fmt: skip


async def test_the_coordinator_as_parent_gets_only_its_feed_line():
    running = {"main_assistant": Agent("main_assistant"), "cv": Agent("cv")}
    feed: list[str] = []
    board, delivery = parts(running, feed)
    _, child = await child_of(board, "main_assistant", running)
    await board.report(ReportTask(task_id=child, kind=ReportKind.DONE, text="CV_RESULT: ready"))
    await delivery.drain()
    assert running["main_assistant"].messages == [] and not delivery.waiting()
    assert feed == ["[cv] task done: CV_RESULT: ready"]


async def test_a_cancel_tells_no_one():
    running = {"job": Agent("job"), "cv": Agent("cv")}
    board, delivery = parts(running, [])
    _, child = await child_of(board, "job", running)
    await board.cancel(CancelTask(task_id=child))
    await delivery.drain()
    assert running["job"].messages == [] and not delivery.waiting()
