"""Agents working together: focus and held questions, the cap and the folder clash, the Hub's
menu and who may use it, and the STATUS milestones and notices that reach the coordinator."""

from pathlib import Path

from assistant.contracts import (
    AgentNotice,
    FocusChanged,
    FocusSuggested,
    InvokeTool,
    ITaskAgent,
    PermissionMode,
    ReportKind,
    ReportTask,
    SetFocus,
    StartTask,
    Status,
    TaskUpdated,
)
from assistant.core import App
from assistant.infra import AgentProfile, MilestoneFeed, status_lines
from assistant.infra.agent_profile import HELPER_BLOCK
from assistant.infra.milestone_feed import HEADER
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.main_assistant.module import COORDINATOR_BLOCK
from assistant.testkit import agent_module, next_matching, report, start_hub, status, wait_until


async def start_app(tmp_path: Path, helper_folder: Path | None = None, **hub_config):
    main_module, main = agent_module("main_assistant", (str(tmp_path / "main"),))
    helper_module, helper = agent_module("helper", (str(helper_folder or tmp_path / "jobs"),))
    config = {
        "modules": {"enabled": ["agent_hub", "main_assistant", "helper"], "agent_hub": {"door": False, **hub_config}},
        "core": {},
    }
    app = App([AgentHubModule, main_module, helper_module], config)
    events: list = []

    async def record(event):
        events.append(event)

    for kind in (FocusChanged, FocusSuggested):
        app.bus.subscribe(kind, record)
    await app.start()
    return app, main, helper, events


def use(name: str, caller: str, **args) -> InvokeTool:
    return InvokeTool(name=name, args=args, caller=caller)


async def test_a_question_out_of_focus_waits_until_you_focus_that_agent(tmp_path):
    app, main, helper, events = await start_app(tmp_path)
    try:
        task_id = (await app.router.send(StartTask(text="find jobs", agent_id="helper"))).value
        await app.router.send(ReportTask(task_id=task_id, kind=ReportKind.NEED, text="Which city?"))
        held = await status(app, task_id)
        assert held.held and held.question == "Which city?"  # stored once, on the task

        assert (await app.router.send(SetFocus(agent_id="helper"))).value == "helper"
        await wait_until(lambda: any(isinstance(e, FocusChanged) for e in events))
        changed = next(e for e in events if isinstance(e, FocusChanged))
        assert changed.agent_id == "helper" and changed.previous == "main_assistant"
        assert [t.id for t in changed.released] == [task_id] and changed.released[0].question == "Which city?"
        assert not (await status(app, task_id)).held
        assert "[focus] the user is now talking to helper" in main.notes

        # Now the coordinator's own question is the one that waits; empty focus is back to it.
        main_task = (await app.router.send(StartTask(text="plan", agent_id="main_assistant"))).value
        await app.router.send(ReportTask(task_id=main_task, kind=ReportKind.PERMISSION, text="Edit x"))
        assert (await status(app, main_task)).held
        assert (await app.router.send(SetFocus(agent_id=""))).value == "main_assistant"
        assert not (await status(app, main_task)).held
        assert (await app.router.send(SetFocus(agent_id="nobody"))).status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()


async def test_a_question_in_focus_is_not_held(tmp_path):
    app, main, helper, events = await start_app(tmp_path)
    try:
        task_id = (await app.router.send(StartTask(text="plan", agent_id="main_assistant"))).value
        await app.router.send(ReportTask(task_id=task_id, kind=ReportKind.NEED, text="Which one?"))
        assert not (await status(app, task_id)).held
    finally:
        await app.stop()


async def test_the_cap_counts_only_the_extra_agents(tmp_path):
    app, main, helper, events = await start_app(tmp_path, max_extra_agents=0)
    try:
        assert (await app.router.send(StartTask(text="plan", agent_id="main_assistant"))).is_ok  # the coordinator
        refused = await app.router.send(StartTask(text="find jobs", agent_id="helper"))
        assert refused.status is Status.NOT_AVAILABLE and "most at once" in refused.error
    finally:
        await app.stop()


async def test_two_agents_never_write_the_same_folder(tmp_path):
    app, main, helper, events = await start_app(tmp_path, helper_folder=tmp_path)  # holds main's folder
    try:
        assert (await app.router.send(StartTask(text="plan", agent_id="main_assistant"))).is_ok
        refused = await app.router.send(StartTask(text="find jobs", agent_id="helper"))
        assert refused.status is Status.NOT_AVAILABLE and "would write" in refused.error
    finally:
        await app.stop()


async def test_the_hub_menu_knows_its_callers(tmp_path):
    app, main, helper, events = await start_app(tmp_path)
    try:
        send = app.router.send
        # hub.focus: the Talker's only, after the user said so.
        assert (await send(use("hub.focus", "main_assistant", agent_id="helper"))).status is Status.NOT_AVAILABLE
        assert (await send(use("hub.focus", "talker", agent_id="helper"))).value == "helper"
        # hub.suggest_focus: the coordinator's only; the Talker gets the suggestion.
        assert (await send(use("hub.suggest_focus", "talker", agent_id="helper"))).status is Status.NOT_AVAILABLE
        assert (await send(use("hub.suggest_focus", "main_assistant", agent_id="helper", reason="jobs"))).is_ok
        await wait_until(lambda: any(isinstance(e, FocusSuggested) for e in events))
        assert next(e for e in events if isinstance(e, FocusSuggested)).by == "main_assistant"
        # hub.send with no task: the Talker's words go to the focused agent (a new task).
        assert (await send(use("hub.send", "main_assistant", text="hi"))).status is Status.NOT_AVAILABLE
        sent = await send(use("hub.send", "talker", text="find jobs in Seoul"))
        assert sent.value["agent_id"] == "helper" and helper.calls[0][0] == "assign"
        again = await send(use("hub.send", "talker", text="and Busan"))  # its open task this time
        assert again.value["task_id"] == sent.value["task_id"] and helper.calls[-1] == ("message", sent.value["task_id"], "and Busan")
        agents = (await send(use("hub.agents", "main_assistant"))).value
        assert {a["agent_id"]: a["focused"] for a in agents} == {"main_assistant": False, "helper": True}
    finally:
        await app.stop()


async def test_an_agents_child_task_is_its_own_to_steer(tmp_path):
    app, main, helper, events = await start_app(tmp_path)
    try:
        send = app.router.send
        parent = (await send(StartTask(text="plan", agent_id="main_assistant"))).value
        child = (await send(use("hub.start", "main_assistant", text="find jobs", agent_id="helper"))).value
        assert (await status(app, child)).parent_task_id == parent
        assert (await send(use("hub.cancel", "helper", task_id=parent))).status is Status.NOT_AVAILABLE
        assert (await send(use("hub.send", "helper", text="x", task_id=parent))).status is Status.NOT_AVAILABLE
        assert (await send(use("hub.send", "main_assistant", text="Seoul only", task_id=child))).is_ok
        assert (await send(use("hub.cancel", "main_assistant", task_id=child))).is_ok
    finally:
        await app.stop()


async def test_a_module_cannot_set_its_own_caller(tmp_path):
    app, main, helper, events = await start_app(tmp_path)
    try:
        # The context puts the sender's id in the caller; only the door's host passes one on.
        faked = await helper.ctx.send(use("hub.focus", "talker", agent_id="helper"))
        assert faked.status is Status.NOT_AVAILABLE
    finally:
        await app.stop()


async def test_milestones_ends_and_notices_reach_the_coordinator(tmp_path):
    app, main, helper, events = await start_app(tmp_path)
    try:
        task_id = (await app.router.send(StartTask(text="find jobs", agent_id="helper"))).value
        await app.router.send(ReportTask(task_id=task_id, kind=ReportKind.MILESTONE, text="found 3 jobs"))
        await app.router.send(ReportTask(task_id=task_id, kind=ReportKind.PROGRESS, text="routine"))
        await app.router.send(ReportTask(task_id=task_id, kind=ReportKind.DONE, text="Sent the list"))
        assert main.notes == ["[helper] found 3 jobs", "[helper] task done: Sent the list"]

        own = (await app.router.send(StartTask(text="plan", agent_id="main_assistant"))).value
        await app.router.send(ReportTask(task_id=own, kind=ReportKind.MILESTONE, text="mine"))
        assert "[main_assistant] mine" not in main.notes  # never its own

        notice = AgentNotice(agent_id="main_assistant", text="search finished", source="job_search")
        assert (await app.router.send(notice)).is_ok  # a command the Hub handles; a core send keeps `source`
        await wait_until(lambda: "[job_search] search finished" in main.notes)
        assert not helper.notes
    finally:
        await app.stop()


def test_the_feed_merges_older_lines():
    feed = MilestoneFeed()
    assert feed.take() == ""
    for n in range(7):
        feed.add(f"line {n}")
    block = feed.take(max_lines=5)
    assert block.splitlines() == [HEADER, "(+3 earlier)", "- line 3", "- line 4", "- line 5", "- line 6"]
    assert feed.take() == ""  # taking empties it


def test_status_lines():
    text = "Working.\nSTATUS: drafted the list\n**status:** `sent`\nNEED: which?\nnot STATUS: this"
    assert status_lines(text) == ["drafted the list", "sent"]
    assert status_lines("STATUS: " + "x" * 300, max_len=10) == ["x" * 9 + "…"]


def test_the_profile_gives_each_side_its_half_of_the_block(tmp_path):
    config = {"workspace": str(tmp_path / "w"), "write_dirs": [str(tmp_path / "out")]}
    helper = AgentProfile.from_config("helper", config)
    prompt = " ".join(helper.command("You find jobs.", PermissionMode.MANUAL))
    assert HELPER_BLOCK.strip() in prompt and COORDINATOR_BLOCK.strip() not in prompt
    coordinator = AgentProfile.from_config("main_assistant", config, COORDINATOR_BLOCK)
    assert COORDINATOR_BLOCK.strip() in " ".join(coordinator.command("You coordinate.", PermissionMode.AUTO))
    assert helper.write_folders() == (str((tmp_path / "w").resolve()), str((tmp_path / "out").resolve()))


# --- through a real SessionTaskAgent (the fake claude) ---


async def test_a_status_line_becomes_a_milestone(tmp_path):
    app, updates = await start_hub(tmp_path)
    try:
        task_id = (await app.router.send(StartTask(text="draft it\nSTATUS: drafted"))).value
        milestone = await next_matching(updates, report(ReportKind.MILESTONE))
        assert milestone.task_id == task_id and milestone.text == "drafted"
        await next_matching(updates, report(ReportKind.DONE))
    finally:
        await app.stop()


async def test_a_note_rides_at_the_end_of_the_next_message(tmp_path):
    app, updates = await start_hub(tmp_path)
    try:
        app.container.get_all(ITaskAgent)[0].note("[helper] found 3 jobs")
        await app.router.send(StartTask(text="write a poem"))
        done = await next_matching(updates, report(ReportKind.DONE))
        assert done.text.startswith("New task: write a poem")
        assert done.text.endswith(f"{HEADER}\n- [helper] found 3 jobs")
    finally:
        await app.stop()

async def test_a_reply_and_an_end_out_of_focus_are_held_until_you_focus_that_agent(tmp_path):
    app, main, helper, events = await start_app(tmp_path)
    updates: list[TaskUpdated] = []

    async def record(event):
        updates.append(event)

    app.bus.subscribe(TaskUpdated, record)
    try:
        task_id = (await app.router.send(StartTask(text="find jobs", agent_id="helper"))).value
        await app.router.send(ReportTask(task_id=task_id, kind=ReportKind.REPLY, text="Found 3"))
        held = await status(app, task_id)
        assert held.held and held.reply == "Found 3"
        await app.router.send(ReportTask(task_id=task_id, kind=ReportKind.DONE, text="All done"))
        held = await status(app, task_id)
        assert held.held and held.reply == "Found 3"  # the end keeps the hold and the reply
        await wait_until(lambda: len(updates) >= 2)
        assert [(u.kind, u.held) for u in updates if u.kind] == [(ReportKind.REPLY, True), (ReportKind.DONE, True)]

        await app.router.send(SetFocus(agent_id="helper"))
        await wait_until(lambda: any(isinstance(e, FocusChanged) for e in events))
        released = next(e for e in events if isinstance(e, FocusChanged)).released
        assert [t.id for t in released] == [task_id]
        assert released[0].reply == "Found 3" and released[0].state.is_final
        cleared = await status(app, task_id)
        assert not cleared.held and cleared.reply is None
    finally:
        await app.stop()


async def test_hub_send_names_the_agent_it_is_for(tmp_path):
    app, main, helper, events = await start_app(tmp_path)  # the focus is the Main Assistant
    try:
        send = app.router.send
        first = await send(use("hub.send", "talker", text="find jobs", agent_id="helper"))
        assert first.value["agent_id"] == "helper" and helper.calls[0][0] == "assign"  # a new task on it
        assert not main.calls
        again = await send(use("hub.send", "talker", text="and Busan", agent_id="helper"))
        assert again.value["task_id"] == first.value["task_id"]  # its open task
        assert helper.calls[-1] == ("message", first.value["task_id"], "and Busan") and not main.calls
    finally:
        await app.stop()
