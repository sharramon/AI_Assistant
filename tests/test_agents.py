"""The agent runtime against a fake `claude`: ClaudeSession, the Main Assistant, the Hub, and the Talker."""

import asyncio
import sys
from pathlib import Path

import pytest

from assistant.contracts import (
    CancelTask,
    GetTaskStatus,
    InputReceived,
    ListAgents,
    ReportKind,
    ResponseReady,
    SendToTask,
    StartTask,
    Status,
    TaskState,
    TaskUpdated,
)
from assistant.core import App
from assistant.infra import ClaudeSession, claude_command
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.main_assistant import MainAssistantModule
from assistant.modules.talker import TalkerModule
from assistant.modules.talker.module import split_tags
from tests.support import wait_until

FAKE = [sys.executable, str(Path(__file__).parent / "fake_claude.py")]
TIMEOUT = 10.0


async def next_matching(queue: asyncio.Queue, predicate):
    async with asyncio.timeout(TIMEOUT):
        while not predicate(event := await queue.get()):
            pass
    return event


# --- ClaudeSession ---


async def test_session_runs_a_turn_and_tracks_working():
    events: list[dict] = []
    session = ClaudeSession(FAKE, on_event=events.append)
    await session.start()
    assert session.running and not session.working
    await session.send("hello")
    assert session.working
    await wait_until(lambda: any(e["type"] == "result" for e in events), TIMEOUT)
    assert not session.working
    assert events[-1]["result"] == "hello"
    await session.close()
    assert not session.running


async def test_session_interrupt_ends_the_turn_with_an_error():
    events: list[dict] = []
    session = ClaudeSession(FAKE, on_event=events.append)
    await session.start()
    await session.send("SLOW")
    await wait_until(lambda: any(e["type"] == "assistant" for e in events), TIMEOUT)
    await session.interrupt()
    await wait_until(lambda: any(e["type"] == "result" for e in events), TIMEOUT)
    assert events[-1]["is_error"] and not session.working
    await session.close()


async def test_session_reports_an_unexpected_exit():
    events: list[dict] = []
    session = ClaudeSession(FAKE, on_event=events.append)
    await session.start()
    await session.send("CRASH")
    await wait_until(lambda: any(e["type"] == "exit" for e in events), TIMEOUT)
    assert not session.running
    await session.close()


def test_claude_command_always_skips_mcp_connectors():
    command = claude_command(model="sonnet", tools="")
    assert command[:2] == ["claude", "-p"]
    assert "--strict-mcp-config" in command
    assert command[command.index("--tools") + 1] == ""


# --- Hub + Main Assistant ---


@pytest.fixture
async def hub(tmp_path):
    config = {
        "modules": {
            "enabled": ["agent_hub", "main_assistant"],
            "main_assistant": {"program": FAKE, "workspace": str(tmp_path)},
        },
        "core": {},
    }
    app = App([AgentHubModule, MainAssistantModule], config)
    updates: asyncio.Queue[TaskUpdated] = asyncio.Queue()
    app.bus.subscribe(TaskUpdated, updates.put)
    await app.start()
    yield app, updates
    await app.stop()


def report(kind: ReportKind):
    return lambda event: event.kind is kind


async def test_task_runs_to_done(hub):
    app, updates = hub
    result = await app.router.send(StartTask(text="write a poem", context="User: hi"))
    assert result.is_ok
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.task_id == result.value and "New task: write a poem" in done.text
    assert "Context:\nUser: hi" in done.text
    status = await app.router.send(GetTaskStatus(task_id=result.value))
    assert status.value[0].state is TaskState.DONE
    agents = (await app.router.send(ListAgents())).value
    assert [a.agent_id for a in agents] == ["main_assistant"] and not agents[0].busy


async def test_need_waits_for_your_answer(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="ASKME then write"))).value
    need = await next_matching(updates, report(ReportKind.NEED))
    assert need.text == "Which style?" and need.state is TaskState.WAITING_FOR_INPUT
    assert (await app.router.send(SendToTask(task_id=task_id, text="modern"))).is_ok
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.text == "modern"


async def test_message_interrupts_replies_and_continues(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="SLOW job"))).value
    await next_matching(updates, lambda e: e.text == "started")
    assert (await app.router.send(SendToTask(task_id=task_id, text="old API?"))).is_ok
    reply = await next_matching(updates, report(ReportKind.REPLY))
    assert reply.text.startswith("[The user interrupted your task") and reply.text.endswith("old API?")
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.text == "Continue the task from where you left off."


async def test_pause_then_carry_on(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="SLOW job"))).value
    await app.router.send(SendToTask(task_id=task_id, text="stop for now", resume=False))
    await next_matching(updates, report(ReportKind.REPLY))
    status = (await app.router.send(GetTaskStatus(task_id=task_id))).value[0]
    assert status.state is TaskState.PAUSED
    await app.router.send(SendToTask(task_id=task_id, text="carry on"))
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.text == "carry on"


async def test_cancel_keeps_the_agent_usable(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="SLOW job"))).value
    busy = await app.router.send(StartTask(text="another"))
    assert busy.status is Status.NOT_AVAILABLE
    assert (await app.router.send(CancelTask(task_id=task_id))).is_ok
    status = (await app.router.send(GetTaskStatus(task_id=task_id))).value[0]
    assert status.state is TaskState.CANCELLED

    async def free():
        return not (await app.router.send(ListAgents())).value[0].busy

    async with asyncio.timeout(TIMEOUT):
        while not await free():
            await asyncio.sleep(0.01)
    assert (await app.router.send(StartTask(text="next"))).is_ok
    await next_matching(updates, report(ReportKind.DONE))


async def test_crash_fails_the_task(hub):
    app, updates = hub
    await app.router.send(StartTask(text="CRASH"))
    failed = await next_matching(updates, report(ReportKind.FAILED))
    assert failed.state is TaskState.FAILED


async def test_finished_tasks_refuse_messages(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="quick"))).value
    await next_matching(updates, report(ReportKind.DONE))
    result = await app.router.send(SendToTask(task_id=task_id, text="more"))
    assert result.status is Status.INVALID_ARGUMENTS


async def test_no_agent_means_not_available():
    app = App([AgentHubModule], {"modules": {"enabled": ["agent_hub"]}, "core": {}})
    await app.start()
    assert (await app.router.send(StartTask(text="x"))).status is Status.NOT_AVAILABLE
    await app.stop()


# --- Talker ---


def test_split_tags():
    text, tags = split_tags("On it! <<WORK: write\ntwo poems>> I'll tell you. <<LOOK>>")
    assert text == "On it!  I'll tell you."
    assert tags == [("WORK", "write\ntwo poems"), ("LOOK", "")]
    assert split_tags("Just chatting.") == ("Just chatting.", [])


async def test_talker_hands_off_work_and_relays_the_question(tmp_path):
    config = {
        "modules": {
            "enabled": ["agent_hub", "main_assistant", "talker"],
            "main_assistant": {"program": FAKE, "workspace": str(tmp_path)},
            "talker": {"program": FAKE},
        },
        "core": {},
    }
    app = App([AgentHubModule, MainAssistantModule, TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        # The fake Talker repeats what it's sent, so the input is its reply.
        said = InputReceived(text="Sure. <<WORK: poems ASKME>>", source="test")
        app.bus.publish(said)
        first = await next_matching(replies, lambda e: True)
        assert first.text == "Sure." and first.correlation_id == said.id

        question = await next_matching(replies, lambda e: True)
        assert question.text == "[Task update: need] Which style?" and question.correlation_id is None

        app.bus.publish(InputReceived(text="<<ASK: modern>>", source="test"))
        done = await next_matching(replies, lambda e: e.text.startswith("[Task update: done]"))
        assert done.text.endswith("modern")
    finally:
        await app.stop()


@pytest.mark.claude
async def test_real_claude_session():
    events: list[dict] = []
    session = ClaudeSession(claude_command(model="sonnet", tools=""), on_event=events.append)
    await session.start()
    await session.send("Reply with just the word PONG.")
    await wait_until(lambda: any(e["type"] == "result" for e in events), 60)
    assert "PONG" in events[-1]["result"]
    await session.close()
