"""The Talker with several agents (multi-agent, chunk 4): held questions said only on focus and
named, your words passed word for word to the focused agent, milestones never said, a
suggestion asked as yes or no, and permission cards answered per task."""

import asyncio

from assistant.contracts import (
    DeactivateModule,
    FocusSuggested,
    InputReceived,
    ReportKind,
    ReportTask,
    ResponseReady,
    SessionUsage,
    SetFocus,
    StartTask,
)
from assistant.core import App
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.talker import TalkerModule
from tests.support import wait_until
from tests.test_agents import FAKE, next_matching
from tests.test_multi_agent import agent_module


async def start_app(tmp_path):
    """The Hub, two fake agents (`main_assistant` the coordinator, `helper`) and the Talker (fake claude, an echo)."""
    main_module, main = agent_module("main_assistant", (str(tmp_path / "main"),))
    helper_module, helper = agent_module("helper", (str(tmp_path / "jobs"),))
    config = {
        "modules": {
            "enabled": ["agent_hub", "main_assistant", "helper", "talker"],
            "agent_hub": {"door": False},
            "talker": {"program": FAKE, "door": False},
        },
        "core": {},
    }
    app = App([AgentHubModule, main_module, helper_module, TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    return app, main, helper, replies


async def test_held_question_is_said_on_focus_and_your_words_pass_unchanged(tmp_path):
    app, main, helper, replies = await start_app(tmp_path)
    try:
        task = (await app.router.send(StartTask(text="find jobs", agent_id="helper"))).value
        await app.router.send(ReportTask(task_id=task, kind=ReportKind.MILESTONE, text="found 3 jobs"))
        helper.busy = False  # a NEED ends the agent's turn: it drops the task and is idle
        await app.router.send(ReportTask(task_id=task, kind=ReportKind.NEED, text="Which city?"))
        await asyncio.sleep(0.2)
        assert replies.empty()  # out of focus: no milestone, no question in the chat

        await app.router.send(SetFocus(agent_id="helper"))
        said = await next_matching(replies, lambda e: "Which city?" in e.text)
        assert said.text == "[Focus] the user opened this tab.\n[Task update: need] Which city?"
        assert said.agent_id == "helper"  # said by the helper's own Talker

        # Your words go to the focused tab's Talker; PASS sends them word for word to its agent.
        app.bus.publish(InputReceived(text="Berlin, remote is fine <<PASS>>", source="test"))
        echoed = await next_matching(replies, lambda e: "Berlin" in e.text)
        assert echoed.agent_id == "helper" and "[Focus]" not in echoed.text
        # The question was a message to an idle agent: the answer is the same task, given back to it.
        answer = f'Answer to your question in task {task} ("Which city?"): Berlin, remote is fine <<PASS>>'
        await wait_until(lambda: ("assign", task, answer) in helper.calls)
        assert not any(c[0] in ("assign", "message") for c in main.calls)

        await app.router.send(ReportTask(task_id=task, kind=ReportKind.REPLY, text="Searching Berlin"))
        reply = await next_matching(replies, lambda e: "Searching Berlin" in e.text)
        assert reply.text == "[Task update: reply] Searching Berlin" and reply.agent_id == "helper"  # its own tab
    finally:
        await app.stop()


async def test_a_suggestion_is_asked_and_focus_back_is_noted(tmp_path):
    app, main, helper, replies = await start_app(tmp_path)
    try:
        app.bus.publish(FocusSuggested(agent_id="helper", reason="it has the job list", by="main_assistant"))
        asked = await next_matching(replies, lambda e: e.text.startswith("[Suggestion]"))
        assert "talks to helper directly: it has the job list" in asked.text and "FOCUS: helper" in asked.text

        app.bus.publish(InputReceived(text="yes <<FOCUS: helper>>", source="test"))
        await next_matching(replies, lambda e: e.text == "yes")
        app.bus.publish(InputReceived(text="back please <<FOCUS: main_assistant>>", source="test"))
        await next_matching(replies, lambda e: "back please" in e.text)
        await asyncio.sleep(0.2)  # the reply is said before its FOCUS tag runs
        app.bus.publish(InputReceived(text="hi", source="test"))
        hi = await next_matching(replies, lambda e: e.text.endswith("hi"))
        assert hi.agent_id == "main_assistant" and "[Focus]" not in hi.text  # nothing released: no note
    finally:
        await app.stop()


async def test_a_bare_yes_with_two_cards_open_asks_which(tmp_path):
    app, main, helper, replies = await start_app(tmp_path)
    try:
        # Two cards in the same tab (the Main Assistant's): a bare yes can't tell which.
        own = (await app.router.send(StartTask(text="plan", agent_id="main_assistant"))).value
        await app.router.send(ReportTask(task_id=own, kind=ReportKind.PERMISSION, text="Bash git status"))
        await next_matching(replies, lambda e: e.text == "[Task update: permission] Bash git status")
        # A fake agent holds one task at a time, so the second card of the tab is put in directly.
        app._lifecycle._active["talker"][0]._sessions["main_assistant"].cards["t-extra"] = ("main_assistant", "Write cv.md")

        app.bus.publish(InputReceived(text="<<ALLOW>>", source="test"))
        which = await next_matching(replies, lambda e: e.text.startswith("[Status] More than one"))
        assert "Bash git status" in which.text and "Write cv.md" in which.text
        assert not any(c[0] == "permission" for c in main.calls + helper.calls)

        app.bus.publish(InputReceived(text=f"<<ALLOW: {own}>>", source="test"))
        await wait_until(lambda: ("permission", own, True) in main.calls)
    finally:
        await app.stop()


async def test_input_for_a_tab_is_that_tabs_and_its_reply_goes_there(tmp_path):
    app, main, helper, replies = await start_app(tmp_path)  # the focus stays on the Main Assistant
    try:
        app.bus.publish(InputReceived(text="look for jobs <<PASS>>", source="test", agent_id="helper"))
        said = await next_matching(replies, lambda e: "look for jobs" in e.text)
        assert said.agent_id == "helper"
        assert "[Focus]" not in said.text
        await wait_until(lambda: any(c[0] == "assign" for c in helper.calls))
        assert not any(c[0] in ("assign", "message") for c in main.calls)  # not passed to the focused agent

        app.bus.publish(InputReceived(text="hello there", source="test"))  # no tab: the focus's
        plain = await next_matching(replies, lambda e: "hello there" in e.text)
        assert plain.agent_id == "main_assistant" and not plain.text.startswith("[Focus]")
    finally:
        await app.stop()


async def test_a_bare_yes_answers_the_card_of_the_tab_it_was_said_in(tmp_path):
    app, main, helper, replies = await start_app(tmp_path)
    try:
        own = (await app.router.send(StartTask(text="plan", agent_id="main_assistant"))).value
        other = (await app.router.send(StartTask(text="find jobs", agent_id="helper"))).value
        await app.router.send(ReportTask(task_id=own, kind=ReportKind.PERMISSION, text="Bash git status"))
        await next_matching(replies, lambda e: e.text == "[Task update: permission] Bash git status")
        await app.router.send(ReportTask(task_id=other, kind=ReportKind.PERMISSION, text="Write cv.md"))
        await app.router.send(SetFocus(agent_id="helper"))  # releases the helper's held card
        await next_matching(replies, lambda e: "[Task update: permission] Write cv.md" in e.text and e.agent_id == "helper")

        # One card per tab: a bare yes in the helper's tab (the focus) is the helper's card, no question.
        app.bus.publish(InputReceived(text="<<ALLOW>>", source="test"))
        await wait_until(lambda: ("permission", other, True) in helper.calls)
        assert not any(c[0] == "permission" for c in main.calls)

        # And one in the Main Assistant's tab is its own.
        app.bus.publish(InputReceived(text="<<ALLOW>>", source="test", agent_id="main_assistant"))
        await wait_until(lambda: ("permission", own, True) in main.calls)
    finally:
        await app.stop()


async def test_a_helper_tabs_talker_starts_on_use_has_its_own_usage_row_and_closes_with_its_agent(tmp_path):
    app, main, helper, replies = await start_app(tmp_path)
    usage: list[SessionUsage] = []

    async def keep(event: SessionUsage) -> None:
        usage.append(event)

    app.bus.subscribe(SessionUsage, keep)
    try:
        talker = app._lifecycle._active["talker"][0]
        assert set(talker._sessions) == {"main_assistant"}  # only the main tab's, until a helper tab is used
        assert talker._sessions["main_assistant"].id == "talker"

        app.bus.publish(InputReceived(text="hello helper", source="test", agent_id="helper"))
        said = await next_matching(replies, lambda e: "hello helper" in e.text)
        assert said.agent_id == "helper"
        session = talker._sessions["helper"]
        assert session.id == "talker:helper" and session.session.running  # its own claude process
        await wait_until(lambda: any(u.agent_id == "talker:helper" for u in usage))
        row = next(u for u in usage if u.agent_id == "talker:helper")
        assert row.parent == "helper"  # nested under its agent in the usage tally

        await app.router.send(DeactivateModule(module_id="helper"))  # its agent is gone: its tab closes
        await wait_until(lambda: "helper" not in talker._sessions and not session.session.running)
        assert any("hello helper" in line for line in talker.export_state()["histories"]["helper"])
        assert "main_assistant" in talker._sessions  # the main tab's never closes
    finally:
        await app.stop()


async def test_restart_in_a_helper_tab_is_refused(tmp_path):
    app, main, helper, replies = await start_app(tmp_path)
    try:
        app.bus.publish(InputReceived(text="restart please <<RESTART>>", source="test", agent_id="helper"))
        refused = await next_matching(replies, lambda e: "Main Assistant's tab" in e.text)
        assert refused.agent_id == "helper"
        assert not any(c[0] == "assign" for c in main.calls)  # no reset instructions asked for
    finally:
        await app.stop()
