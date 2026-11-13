"""A message waits while the agent is in a turn; the turn ends before its DONE report reaches the Hub.
The old task must end DONE (not "reloaded" FAILED) and the message must go in as a new task."""

import asyncio
import logging

from assistant.contracts import AgentStateChanged, DeliverMessage, ReportKind, ReportTask, StartTask, Task, TaskState
from assistant.infra import SessionTaskAgent
from assistant.modules.agent_hub.delivery import Delivery
from assistant.modules.agent_hub.tasks import TaskBoard
from tests.test_agents import _StubContext, _StubSession


async def test_a_turn_end_before_its_done_report_does_not_fail_the_task():
    session, ctx = _StubSession(), _StubContext()
    log = logging.getLogger("test")
    board = TaskBoard(publish=lambda event: None, log=log, agents=lambda: [agent], agent=lambda _id: agent,
                      focused=lambda: "", feed=lambda line: None, coordinator="main_assistant",
                      max_extra=3)  # fmt: skip
    delivery = Delivery(board, lambda _id: agent, log)
    release, flushes = asyncio.Event(), []

    async def send(command):  # the Hub gets the report late
        if isinstance(command, ReportTask):
            await release.wait()
            return await board.report(command)

    def publish(event):
        if isinstance(event, AgentStateChanged):
            flushes.append(asyncio.ensure_future(delivery.flush()))

    ctx.send, ctx.publish = send, publish
    agent = SessionTaskAgent(session, ctx, "worker", "a worker")
    old = (await board.start(StartTask(text="apply to Acme", agent_id="worker"))).value
    assert (await delivery.deliver(DeliverMessage(agent_id="worker", text="the CV is ready", sender="cv"))).value \
        == "pending"  # in its turn

    session.working = False
    session.on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": "All done."}]}})
    session.on_event({"type": "result", "is_error": False})
    await asyncio.sleep(0.05)  # idle is published; the DONE report is still on its way
    await asyncio.gather(*flushes)
    assert board.get(old).state is not TaskState.FAILED
    release.set()
    await asyncio.sleep(0.05)
    await asyncio.gather(*flushes)
    assert board.get(old).state is TaskState.DONE
    assert not delivery.waiting()
    new = board.open_task_of("worker")
    assert new is not None and new.id != old and "the CV is ready" in new.text
    await agent.close()


async def test_the_agent_says_not_available_for_a_task_it_just_ended():
    session, ctx = _StubSession(), _StubContext()
    gate = asyncio.Event()
    sent = []

    async def send(command):
        sent.append(command.kind)
        if command.kind is ReportKind.DONE:  # the Hub gets the end report late
            await gate.wait()
        return (await _StubContext.send(ctx, command))

    ctx.send = send
    agent = SessionTaskAgent(session, ctx, "worker", "a worker")
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    session.working = False
    session.on_event({"type": "result", "is_error": False})
    await asyncio.sleep(0.05)
    assert sent == [ReportKind.TURN_END, ReportKind.DONE]  # the Hub said done (nothing to wait on)
    assert (await agent.message("t1", "hello")).status.value == "not_available"
    gate.set()
    await asyncio.sleep(0.05)
    assert (await agent.message("t1", "hello")).status.value == "invalid_arguments"  # report sent: just not its task
    await agent.close()


async def test_a_message_while_the_turn_settles_carries_the_task_on():
    session, ctx = _StubSession(), _StubContext()
    gate = asyncio.Event()

    async def send(command):
        await gate.wait()  # the Hub's answer to turn_end comes late
        return (await _StubContext.send(ctx, command))

    ctx.send = send
    agent = SessionTaskAgent(session, ctx, "worker", "a worker")
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    session.working = False
    session.on_event({"type": "result", "is_error": False})
    await asyncio.sleep(0.05)
    assert agent.info().active  # settling: still active, so nothing new is given to it
    assert (await agent.message("t1", "one more thing")).is_ok  # held
    gate.set()
    await asyncio.sleep(0.05)
    assert "one more thing" in session.sent[-1] and agent.has_task  # it goes on with the message
    await agent.close()
