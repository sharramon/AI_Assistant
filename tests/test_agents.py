"""The agent runtime against a fake `claude`: ClaudeSession, the Main Assistant, the Hub, and the Talker."""

import asyncio
import json

import pytest

from assistant.contracts import (
    AgentActivity,
    AnswerPermission,
    CancelTask,
    GetTaskStatus,
    InputReceived,
    ListAgents,
    PermissionMode,
    QuestionKind,
    ReportKind,
    ResetRequested,
    ResponseReady,
    SendToTask,
    SessionUsage,
    SetPermissionMode,
    StartTask,
    Status,
    Task,
    TaskState,
)
from assistant.core import App
from assistant.infra import ClaudeSession, ContextWatch, SessionTaskAgent, claude_command
from assistant.infra.agent_profile import command_rules
from assistant.infra.claude_session import path_rule
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.main_assistant import MainAssistantModule
from assistant.modules.talker import TalkerModule
from assistant.testkit import (
    FAKE,
    TIMEOUT,
    StubContext,
    StubSession,
    next_matching,
    report,
    start_hub,
    wait_until,
)

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


async def test_session_writes_a_transcript(tmp_path):
    transcript = tmp_path / "logs" / "talker.jsonl"
    events: list[dict] = []
    session = ClaudeSession(FAKE, on_event=events.append, transcript=transcript)
    await session.start()
    await session.send("hello")
    await wait_until(lambda: any(e["type"] == "result" for e in events), TIMEOUT)
    await session.close()
    lines = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["dir"] == "in" and lines[0]["msg"]["type"] == "user"
    assert lines[-1]["dir"] == "out" and lines[-1]["msg"]["type"] == "result"


async def test_session_tracks_context_now_and_usage_across_restarts():
    events: list[dict] = []
    session = ClaudeSession(FAKE, on_event=events.append)

    async def turn(text: str) -> None:
        events.clear()
        await session.send(text)
        await wait_until(lambda: any(e["type"] == "result" for e in events), TIMEOUT)

    await session.start()
    assert session.context_tokens == 0 and sum(session.used.values()) == 0
    await turn("hello")
    events.clear()
    await session.send("SLOW")  # two lines of one call, counted once; ends when interrupted
    await wait_until(lambda: sum(e["type"] == "assistant" for e in events) == 2, TIMEOUT)
    await session.interrupt()
    await wait_until(lambda: any(e["type"] == "result" for e in events), TIMEOUT)
    # The fake: input 1000 per message so far, 25 output per turn (from the result, not the
    # streamed 10).
    assert session.context_tokens == 2000
    assert session.used == {"input": 4, "cache_write": 0, "cache_read": 2996, "output": 50}
    first_id = session.id
    await session.close()
    await session.start()  # a fresh process: context starts over, usage keeps adding up
    assert session.context_tokens == 0 and session.id == first_id  # same session object, same id
    await turn("again")
    assert session.context_tokens == 1000
    assert sum(session.used.values()) == 3000 + 1000 + 75
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
    assert "--allowedTools" not in command


def test_path_rules(tmp_path):
    rule = path_rule("Edit", tmp_path / "docs")
    assert rule.startswith("Edit(//") and rule.endswith("/docs/**)")
    assert "\\" not in rule and ":" not in rule
    command = claude_command(allowed=[rule, path_rule("Read", tmp_path)])
    assert command[command.index("--allowedTools") + 1].count("(//") == 2


def test_command_rules_allow_any_arguments():
    exact, with_args = command_rules(r".\.venv\Scripts\ruff check")
    assert exact.endswith(r"(.\.venv\Scripts\ruff check)")
    assert with_args.endswith(r"(.\.venv\Scripts\ruff check *)")
    assert exact.split("(")[0] in ("PowerShell", "Bash")


# --- Hub + Main Assistant ---


@pytest.fixture
async def hub(tmp_path):
    app, updates = await start_hub(tmp_path)
    yield app, updates
    await app.stop()


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
    assert [a.agent_id for a in agents] == ["main_assistant"] and not agents[0].active


async def test_the_answer_to_a_need_comes_back_as_the_same_task(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="ASKME then write"))).value
    need = await next_matching(updates, report(ReportKind.NEED))
    assert need.text == "Which style?" and need.state is TaskState.IDLE
    assert (await app.router.send(SendToTask(task_id=task_id, text="modern"))).is_ok
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.task_id == task_id  # the same task, not a new one
    assert done.text.startswith(f'Answer to your question in task {task_id} ("Which style?"): modern')


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
    assert status.state is TaskState.IDLE
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
        return not (await app.router.send(ListAgents())).value[0].active

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


async def test_permission_request_allowed(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="PERMIT a skill"))).value
    asked = await next_matching(updates, report(ReportKind.PERMISSION))
    assert asked.text == "Write .claude/skills/x/SKILL.md"
    assert asked.question_kind is QuestionKind.PERMISSION  # typed by the Hub, no prefix to parse
    status = (await app.router.send(GetTaskStatus(task_id=task_id))).value[0]
    assert status.state is TaskState.ACTIVE and status.question_kind is QuestionKind.PERMISSION
    assert status.question == asked.text and status.question_line == "Permission: " + asked.text
    assert (await app.router.send(AnswerPermission(task_id=task_id, allow=True))).is_ok
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.text == "allowed"


async def test_permission_request_denied_and_only_answered_once(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="PERMIT a skill"))).value
    await next_matching(updates, report(ReportKind.PERMISSION))
    assert (await app.router.send(AnswerPermission(task_id=task_id, allow=False))).is_ok
    again = await app.router.send(AnswerPermission(task_id=task_id, allow=True))
    assert again.status is Status.INVALID_ARGUMENTS
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.text == "denied: The user denied this."


async def test_unanswered_permission_is_denied(tmp_path):
    app, updates = await start_hub(tmp_path, permission_timeout=0.2)
    try:
        await app.router.send(StartTask(text="PERMIT a skill"))
        done = await next_matching(updates, report(ReportKind.DONE))
        assert done.text.startswith("denied: Nobody answered")
    finally:
        await app.stop()


# A `RELOAD:` last line sends ReloadModule; "ghost" isn't a module, so the core's answer proves it went.
RELOAD_GHOST = "[App] Reload the ghost module with its new code: "


async def test_reload_request_in_auto_runs_at_once_and_reports_back(hub):
    app, updates = hub
    assert (await app.router.send(SetPermissionMode(agent_id="main_assistant", mode=PermissionMode.AUTO))).is_ok
    await app.router.send(StartTask(text="RELOADME ghost"))
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.text.startswith(RELOAD_GHOST + "failed: No module called 'ghost'") and "Continue the task" in done.text


@pytest.mark.parametrize(("allow", "outcome"), [(True, "failed: No module called 'ghost'"), (False, "the user said no.")])
async def test_reload_request_in_manual_asks_you_first(hub, allow, outcome):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="RELOADME ghost"))).value
    asked = await next_matching(updates, report(ReportKind.PERMISSION))
    assert asked.text == "Reload the ghost module with its new code"
    assert (await app.router.send(AnswerPermission(task_id=task_id, allow=allow))).is_ok
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.text.startswith(RELOAD_GHOST + outcome)


async def test_the_main_assistant_cannot_reload_itself(hub):
    app, updates = hub
    await app.router.send(StartTask(text="RELOADME main_assistant"))
    done = await next_matching(updates, report(ReportKind.DONE))
    assert "refused: you can't reload yourself" in done.text


async def test_each_task_gets_a_fresh_session(hub):
    app, updates = hub
    sizes: asyncio.Queue[SessionUsage] = asyncio.Queue()
    app.bus.subscribe(SessionUsage, sizes.put)
    for used in (1025, 2050):
        await app.router.send(StartTask(text="a task"))
        await next_matching(updates, report(ReportKind.DONE))
        # The fake counts 1000 tokens per message its process has had: a fresh one is back at 1000,
        # while "used" keeps adding up across sessions.
        size = await next_matching(sizes, lambda e, used=used: e.used_tokens == used)
        assert size.agent_id == "main_assistant" and size.context_tokens == 1000


async def test_a_subagents_usage_is_published_once_under_its_parent(hub):
    app, updates = hub
    seen: list[SessionUsage] = []
    app.bus.subscribe(SessionUsage, seen.append)
    await app.router.send(StartTask(text="SUBAGENT task"))
    await next_matching(updates, report(ReportKind.DONE))
    await wait_until(lambda: any(e.parent for e in seen), TIMEOUT)
    subs = [e for e in seen if e.parent]
    assert len(subs) == 1  # published when its tally grows, not on every later change
    assert (subs[0].agent_id, subs[0].kind, subs[0].used_tokens) == (
        "main_assistant/general-purpose #a1b2", "subagent", 6 + 2874 + 5000 + 40)  # every call, not its last
    own = [e for e in seen if e.agent_id == "main_assistant"][-1]
    assert own.kind == "claude" and own.used_tokens < 2880  # the parent's own calls only


async def test_handoff_continues_the_task_in_a_fresh_session(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="HANDOFFONCE build two parts"))).value
    handed = await next_matching(updates, report(ReportKind.PROGRESS))
    while not handed.text.startswith("Handed off"):
        handed = await next_matching(updates, report(ReportKind.PROGRESS))
    assert handed.text == "Handed off to a fresh session (1): docs/next-steps/part.md"
    done = await next_matching(updates, report(ReportKind.DONE))
    assert done.task_id == task_id
    assert done.text.startswith("Task, continued in a fresh session: HANDOFFONCE build two parts")
    assert "handoff in docs/next-steps/part.md" in done.text


async def test_a_chrome_agents_handoff_compacts_the_same_session(tmp_path):
    """Its Chrome tab group belongs to the session id, which `/compact` keeps (chrome-tab-after-reset.md)."""
    app, updates = await start_hub(tmp_path, chrome=True)
    try:
        task_id = (await app.router.send(StartTask(text="HANDOFFONCE fill the form"))).value
        handed = await next_matching(updates, report(ReportKind.PROGRESS))
        while not handed.text.startswith("Handed off"):
            handed = await next_matching(updates, report(ReportKind.PROGRESS))
        assert handed.text == "Handed off in place, context compacted (1): docs/next-steps/part.md"
        done = await next_matching(updates, report(ReportKind.DONE))
        assert done.task_id == task_id  # the compact's own result didn't end the task
        assert done.text.startswith("Task, continued after your context was compacted: HANDOFFONCE fill the form")
        assert "handoff in docs/next-steps/part.md" in done.text and "Chrome tabs are still yours" in done.text
    finally:
        await app.stop()


async def test_a_message_during_the_compact_goes_in_after_it(tmp_path):
    app, updates = await start_hub(tmp_path, chrome=True)
    try:
        task_id = (await app.router.send(StartTask(text="HANDOFFONCE COMPACTWAIT fill the form"))).value
        await next_matching(updates, lambda e: e.text.startswith("Handed off in place"))
        assert (await app.router.send(SendToTask(task_id=task_id, text="use the work email"))).is_ok
        done = await next_matching(updates, report(ReportKind.DONE))
        assert done.text.startswith("Task, continued after your context was compacted")
        assert done.text.endswith("A message came while your context was being compacted: use the work email")
    finally:
        await app.stop()


async def test_a_failed_compact_falls_back_to_a_fresh_session(tmp_path):
    app, updates = await start_hub(tmp_path, chrome=True)
    try:
        task_id = (await app.router.send(StartTask(text="HANDOFFONCE COMPACTFAIL fill the form"))).value
        done = await next_matching(updates, report(ReportKind.DONE))
        assert done.task_id == task_id
        assert done.text.startswith("Task, continued in a fresh session: HANDOFFONCE COMPACTFAIL fill the form")
        assert "reopen the note's URLs" in done.text
    finally:
        await app.stop()


CLOSING = "closing the Chrome tabs it no longer needs"


async def run_chrome_task(tmp_path, text, chrome=True):
    """A task's done report and the agent's activity lines (chrome-tabs-close.md)."""
    app, updates = await start_hub(tmp_path, chrome=chrome)
    seen: list[AgentActivity] = []
    app.bus.subscribe(AgentActivity, seen.append)
    try:
        task_id = (await app.router.send(StartTask(text=text))).value
        done = await next_matching(updates, report(ReportKind.DONE))
        assert done.task_id == task_id
        return done, [e.text for e in seen]
    finally:
        await app.stop()


async def test_a_chrome_task_closes_its_tabs_before_it_ends(tmp_path):
    done, activity = await run_chrome_task(tmp_path, "CHROMEUSE read the ad")
    assert CLOSING in activity
    assert any("Close each of your Chrome tabs" in line for line in activity)  # the check turn went in
    assert done.text == "New task: CHROMEUSE read the ad"  # the real final reply, not "Closed 1 tab."


@pytest.mark.parametrize(("text", "chrome"), [
    ("CHROMEUSE CHROMECLOSE read the ad", True),  # its last turn closed a tab already
    ("CHROMEUSE read the ad", False),             # no Chrome: no check
    ("read the ad", True),                        # Chrome on, but not used in the task
])  # fmt: skip
async def test_no_close_turn_when_it_isnt_needed(tmp_path, text, chrome):
    done, activity = await run_chrome_task(tmp_path, text, chrome=chrome)
    assert CLOSING not in activity and done.text == f"New task: {text}"


async def test_a_message_during_the_close_turn_carries_the_task_on(tmp_path):
    app, updates = await start_hub(tmp_path, chrome=True)
    closing = asyncio.Event()
    app.bus.subscribe(AgentActivity, lambda e: closing.set() if e.text == CLOSING else None)
    try:
        task_id = (await app.router.send(StartTask(text="CHROMEUSE CLOSEWAIT read the ad"))).value
        await asyncio.wait_for(closing.wait(), TIMEOUT)
        assert (await app.router.send(SendToTask(task_id=task_id, text="one more thing"))).is_ok
        reply = await next_matching(updates, report(ReportKind.REPLY))
        assert reply.text.endswith("one more thing")
        done = await next_matching(updates, report(ReportKind.DONE))  # answered it, then carried on
        assert done.task_id == task_id and done.text.startswith("Continue the task from where you left off.")
    finally:
        await app.stop()


async def test_too_many_handoffs_ask_the_user(tmp_path):
    app, updates = await start_hub(tmp_path, max_handoffs=2)
    try:
        await app.router.send(StartTask(text="HANDOFFALWAYS"))
        need = await next_matching(updates, report(ReportKind.NEED))
        assert need.text.startswith("I've handed this task off 2 times")
        assert need.state is TaskState.IDLE
    finally:
        await app.stop()


async def test_an_answer_to_too_many_handoffs_gives_a_fresh_allowance(tmp_path):
    app, updates = await start_hub(tmp_path, max_handoffs=2)
    activity: asyncio.Queue[AgentActivity] = asyncio.Queue()
    app.bus.subscribe(AgentActivity, activity.put)
    try:
        task_id = (await app.router.send(StartTask(text="HANDOFFALWAYS"))).value
        await next_matching(updates, report(ReportKind.NEED))
        assert (await app.router.send(SendToTask(task_id=task_id, text="yes, carry on HANDOFFALWAYS"))).is_ok
        # The answered handoff goes ahead as the first of a new allowance; the next one is the
        # second, and only then is the user asked again.
        seen = []
        while (event := await next_matching(updates, lambda e: e.kind in (ReportKind.PROGRESS, ReportKind.NEED))):
            if event.kind is ReportKind.NEED:
                break
            if event.text.startswith("Handed off"):
                seen.append(event.text)
        assert seen == [f"Handed off to a fresh session ({n}): docs/next-steps/part.md" for n in (1, 2)]
        assert event.text.startswith("I've handed this task off 2 times")
        assert event.task_id == task_id  # the same task asked again
    finally:
        await app.stop()


async def test_reset_mid_task_hands_off(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="SLOW job"))).value
    await next_matching(updates, lambda e: e.text == "started")
    app.bus.publish(ResetRequested(agent_id="main_assistant"))
    handed = await next_matching(updates, lambda e: e.text.startswith("Handed off"))
    assert handed.text.endswith("docs/next-steps/reset.md") and handed.task_id == task_id
    await app.router.send(CancelTask(task_id=task_id))


async def test_reset_when_idle_closes_the_session(hub):
    app, updates = hub
    sizes: asyncio.Queue[SessionUsage] = asyncio.Queue()
    app.bus.subscribe(SessionUsage, sizes.put)
    await app.router.send(StartTask(text="quick"))
    await next_matching(updates, report(ReportKind.DONE))
    await next_matching(sizes, lambda e: e.context_tokens > 0)
    app.bus.publish(ResetRequested(agent_id="main_assistant"))
    after = await next_matching(sizes, lambda e: e.context_tokens == 0)
    assert after.used_tokens == 1025  # usage isn't reset
    assert (await app.router.send(StartTask(text="after the reset"))).is_ok  # starts a new session
    await next_matching(updates, report(ReportKind.DONE))


def test_context_watch_fires_once_per_crossing():
    watch = ContextWatch(1000)
    assert [watch.crossed("a", n) for n in (500, 1000, 1500)] == [False, True, False]
    assert watch.crossed("b", 2000)  # each key on its own
    assert not watch.crossed("a", 0) and watch.crossed("a", 1200)  # back under re-arms it
    assert not ContextWatch(0).crossed("a", 10**9)  # 0 = off


async def test_context_reminder_hands_off_once_per_session(tmp_path):
    # The fake's first call is 1000 tokens: past the reminder at once. It answers the reminder
    # with a HANDOFF; the fresh session starts small, so it re-arms and fires there once more.
    app, updates = await start_hub(tmp_path, context_reminder=1000, max_handoffs=1)
    activity: asyncio.Queue[AgentActivity] = asyncio.Queue()
    app.bus.subscribe(AgentActivity, activity.put)
    try:
        task_id = (await app.router.send(StartTask(text="SLOW job"))).value
        handed = await next_matching(updates, lambda e: e.text.startswith("Handed off"))
        assert handed.text == "Handed off to a fresh session (1): docs/next-steps/context.md"
        need = await next_matching(updates, report(ReportKind.NEED))  # the second session's handoff
        assert need.task_id == task_id and need.text.startswith("I've handed this task off 1 times")
        await asyncio.sleep(0.1)
        sent = []
        while not activity.empty():
            if (line := activity.get_nowait().text).startswith("context reminder sent"):
                sent.append(line)
        assert sent == ["context reminder sent (1k)"] * 2  # one per session, not one per call
    finally:
        await app.stop()


async def test_context_reminder_waits_for_an_open_permission_request():
    session = StubSession()
    agent = SessionTaskAgent(session, StubContext(), "worker", "a worker", context_reminder=1000)
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    session.on_event({"type": "control_request", "request": {"subtype": "can_use_tool", "tool_name": "Write"}})
    session.context_tokens = 1500
    session.on_event({"type": "assistant", "message": {"content": []}})
    await asyncio.sleep(0.05)
    assert session.interrupts == 0  # held: interrupting would drop the request

    assert (await agent.answer_permission("t1", True)).is_ok
    session.on_event({"type": "assistant", "message": {"content": []}})  # working again
    await asyncio.sleep(0.05)
    assert session.interrupts == 1
    session.on_event({"type": "assistant", "message": {"content": []}})  # still over: once per crossing
    session.on_event({"type": "result", "is_error": True})  # the interrupt ends the turn
    await asyncio.sleep(0.05)
    assert session.interrupts == 1
    assert session.sent[-1].startswith("[The user interrupted") and "[Context check]" in session.sent[-1]
    assert "past 1k" in session.sent[-1]
    await agent.close()


async def test_edit_note_logs_the_second_edit_to_a_file_once_without_interrupting(tmp_path, caplog):
    session, ctx, published = StubSession(), StubContext(), []
    ctx.publish = published.append
    task_file = tmp_path / "state" / "task.txt"
    agent = SessionTaskAgent(session, ctx, "worker", "a worker", edit_note=True, task_file=task_file)
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    assert task_file.read_text() == "t1"

    def edit(tool, **tool_input):
        block = {"type": "tool_use", "name": tool, "input": tool_input}
        session.on_event({"type": "assistant", "message": {"content": [block]}})

    with caplog.at_level("INFO", logger="test"):
        edit("Edit", file_path="C:\\r\\Docs\\a.md")
        edit("Read", file_path="C:/r/docs/a.md")
        edit("MultiEdit", file_path="c:/r/docs/a.md")  # the second edit, spelled differently
        edit("Write", file_path="C:/r/docs/a.md")  # third: no more
        edit("NotebookEdit", notebook_path="C:/r/n.ipynb")
    notes = [e.text for e in published if isinstance(e, AgentActivity) and e.text.startswith("batching note")]
    assert notes == ["batching note: a.md"]
    assert sum("batching note" in r.getMessage() for r in caplog.records) == 1
    assert session.interrupts == 0 and len(session.sent) == 1  # only the task itself
    await agent.close()


async def test_status_shows_recent_activity_without_interrupting(hub):
    app, updates = hub
    task_id = (await app.router.send(StartTask(text="SLOW job"))).value

    async def activity():
        return (await app.router.send(GetTaskStatus(task_id=task_id))).value[0].activity

    async with asyncio.timeout(TIMEOUT):
        while not any(line.startswith("→ Write slow.txt") for line in await activity()):
            await asyncio.sleep(0.01)
    assert (await app.router.send(GetTaskStatus(task_id=task_id))).value[0].state is TaskState.ACTIVE
    await app.router.send(CancelTask(task_id=task_id))


async def test_no_agent_means_not_available():
    app = App([AgentHubModule], {"modules": {"enabled": ["agent_hub"]}, "core": {}})
    await app.start()
    assert (await app.router.send(StartTask(text="x"))).status is Status.NOT_AVAILABLE
    await app.stop()


# --- the Talker with the Hub and a worker (the Talker alone: its own tests, modules/talker/tests) ---


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
