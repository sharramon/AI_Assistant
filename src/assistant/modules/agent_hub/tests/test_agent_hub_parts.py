"""Chunk 13: the Agent Hub's parts on their own (`TaskBoard`, `Focus`) and the
Talker's two menu items (`hub.answer`, `hub.mode`), with their caller checks."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from assistant.contracts import (
    AgentInfo,
    FocusChanged,
    PermissionMode,
    QuestionKind,
    ReportKind,
    ReportTask,
    Result,
    SetFocus,
    StartTask,
    Status,
    TaskState,
    TaskUpdated,
)
from assistant.core.callers import RESERVED_AGENT_IDS, Callers
from assistant.modules.agent_hub.focus import Focus
from assistant.modules.agent_hub.module import AgentHubModule, menu
from assistant.modules.agent_hub.tasks import TaskBoard

LOG = logging.getLogger("hub-parts")


class FakeAgent:
    def __init__(self, agent_id: str, folders: tuple[str, ...] = ()) -> None:
        self.agent_id, self.folders = agent_id, folders
        self.notes: list[str] = []
        self.answers: list[bool] = []
        self.modes: list[PermissionMode] = []

    def info(self) -> AgentInfo:
        return AgentInfo(agent_id=self.agent_id, description="fake", write_folders=self.folders)

    async def assign(self, task) -> Result:
        return Result.ok()

    async def message(self, task_id: str, text: str, resume: bool) -> Result:
        return Result.ok()

    async def cancel(self, task_id: str) -> Result:
        return Result.ok()

    async def answer_permission(self, task_id: str, allow: bool) -> Result:
        self.answers.append(allow)
        return Result.ok()

    async def set_permission_mode(self, mode: PermissionMode) -> Result:
        self.modes.append(mode)
        return Result.ok(False)

    def note(self, text: str) -> None:
        self.notes.append(text)


class Rig:
    """A board and a focus wired the way the Hub wires them."""

    def __init__(self, *agents: FakeAgent, focus: str | None = None, max_extra: int = 3) -> None:
        self.agents = {a.agent_id: a for a in agents}
        self.published: list = []
        self.board = TaskBoard(
            publish=self.published.append, log=LOG, agents=lambda: list(self.agents.values()),
            agent=self.agents.get, focused=lambda: self.focus.focused(), feed=self.feed,
            coordinator="main", max_extra=max_extra,
        )  # fmt: skip
        self.focus = Focus(publish=self.published.append, log=LOG, coordinator="main", initial=focus,
                           agent=self.agents.get, release=self.board.release, feed=self.feed)  # fmt: skip

    def feed(self, line: str) -> None:
        if "main" in self.agents:
            self.agents["main"].note(line)


async def test_the_board_holds_a_question_out_of_focus_and_the_focus_releases_it() -> None:
    rig = Rig(FakeAgent("main"), FakeAgent("helper", ("C:/work/a",)))
    started = await rig.board.start(StartTask(text="do it", agent_id="helper"))
    task_id = started.value
    assert (await rig.board.report(ReportTask(task_id=task_id, kind=ReportKind.PERMISSION, text="Bash: ls"))).is_ok
    record = rig.board.get(task_id)
    assert record.state is TaskState.ACTIVE and record.held
    assert record.question_kind is QuestionKind.PERMISSION and rig.board.holds("helper")
    assert (await rig.focus.set(SetFocus(agent_id="helper"))).value == "helper"
    moved = [e for e in rig.published if isinstance(e, FocusChanged)][-1]
    assert [t.id for t in moved.released] == [task_id] and not rig.board.holds("helper")
    assert "[focus] the user is now talking to helper" in rig.agents["main"].notes


async def test_the_board_refuses_a_folder_clash_and_the_extra_limit() -> None:
    rig = Rig(FakeAgent("main"), FakeAgent("a", ("C:/work",)), FakeAgent("b", ("C:/work/sub",)), max_extra=1)
    assert (await rig.board.start(StartTask(text="x", agent_id="a"))).is_ok
    refused = await rig.board.start(StartTask(text="y", agent_id="b"))
    assert refused.status is Status.NOT_AVAILABLE and "extra agents" in refused.error
    rig.board._max_extra = 3
    clash = await rig.board.start(StartTask(text="y", agent_id="b"))
    assert clash.status is Status.NOT_AVAILABLE and "would write" in clash.error


async def test_the_board_lets_the_parent_or_anyone_steer_a_task() -> None:
    rig = Rig(FakeAgent("main"), FakeAgent("helper"))
    parent = (await rig.board.start(StartTask(text="lead", agent_id="main"))).value
    child = (await rig.board.start(StartTask(text="sub", agent_id="helper", parent_task_id=parent))).value
    assert rig.board.may_steer(child, "main") is None
    assert rig.board.may_steer(child, "helper").status is Status.NOT_AVAILABLE
    assert rig.board.may_steer(child, "anyone", anyone=True) is None
    assert rig.board.may_steer("nope", "main").status is Status.INVALID_ARGUMENTS


async def test_an_ending_task_out_of_focus_is_held_and_fed_to_the_coordinator() -> None:
    rig = Rig(FakeAgent("main"), FakeAgent("helper"))
    task_id = (await rig.board.start(StartTask(text="x", agent_id="helper"))).value
    await rig.board.report(ReportTask(task_id=task_id, kind=ReportKind.DONE, text="all   done"))
    record = rig.board.get(task_id)
    assert record.state is TaskState.DONE and record.held and record.result == "all   done"
    assert rig.agents["main"].notes[-1] == "[helper] task done: all done"
    assert isinstance(rig.published[-1], TaskUpdated) and rig.published[-1].held


async def test_the_focus_falls_back_to_the_coordinator_when_its_agent_is_gone() -> None:
    rig = Rig(FakeAgent("main"), focus="ghost")
    assert rig.focus.stored == "ghost"
    await rig.focus.check(None)
    assert rig.focus.focused() == "main" and rig.focus.stored == "main"
    moved = [e for e in rig.published if isinstance(e, FocusChanged)]
    assert len(moved) == 1 and moved[0].previous == "ghost"
    assert (await rig.focus.set(SetFocus(agent_id="ghost"))).status is Status.INVALID_ARGUMENTS


async def test_agent_names_claims_once_and_offers_a_free_id() -> None:
    names = Callers(lambda: ["agent_hub"], reserved=RESERVED_AGENT_IDS | {"main"})
    assert (await names.claim("scout", "task_agents")).is_ok
    assert (await names.claim("scout", "task_agents")).is_ok  # a repeat claim by its holder
    taken = await names.claim("scout", "job_search")
    assert taken.status is Status.INVALID_ARGUMENTS and "is free" in taken.error
    assert await names.check("agent_hub", "x") and await names.check("main", "x")  # a module, reserved
    names.release("scout", "job_search")  # not the holder: kept
    assert names.taken() == {"scout": "task_agents"}
    names.release("scout", "task_agents")
    assert names.taken() == {}


async def test_the_talkers_answer_and_mode_items_check_their_caller() -> None:
    helper = FakeAgent("helper")
    rig = Rig(FakeAgent("main"), helper)
    hub = AgentHubModule.__new__(AgentHubModule)
    hub._tasks = rig.board
    sent: list = []

    async def send(command) -> Result:  # the core's handler, stood in for
        sent.append(command)
        await helper.set_permission_mode(command.mode)
        return Result.ok()

    hub._ctx = SimpleNamespace(send=send)
    task_id = (await rig.board.start(StartTask(text="x", agent_id="helper"))).value
    await rig.board.report(ReportTask(task_id=task_id, kind=ReportKind.PERMISSION, text="Bash: ls"))

    refused = await menu.call(hub, "hub.answer", {"task_id": task_id, "allow": True}, caller="main")
    assert refused.status is Status.NOT_AVAILABLE and helper.answers == []
    assert (await menu.call(hub, "hub.answer", {"task_id": task_id, "allow": True}, caller="talker")).is_ok
    assert helper.answers == [True] and rig.board.get(task_id).state is TaskState.ACTIVE

    assert (await menu.call(hub, "hub.mode", {"agent_id": "helper", "mode": "manual"}, caller="main")).status \
        is Status.NOT_AVAILABLE  # fmt: skip
    auto = await menu.call(hub, "hub.mode", {"agent_id": "helper", "mode": "auto"}, caller="talker")
    assert auto.status is Status.NOT_AVAILABLE and helper.modes == []
    assert (await menu.call(hub, "hub.mode", {"agent_id": "helper", "mode": "manual"}, caller="talker")).is_ok
    assert helper.modes == [PermissionMode.MANUAL]


# --- its defaults in its module.toml ---


def test_its_defaults_are_in_its_module_toml_under_the_apps_section() -> None:
    from assistant.core import App
    from assistant.testkit import module_config

    defaults = module_config("agent_hub")
    assert defaults["needs"] == [] and defaults["packages"] == []
    # the same as the old [modules.agent_hub] in config/default.toml (the rest were comments)
    assert {k: v for k, v in defaults.items() if k not in ("needs", "packages")} == {
        "coordinator": "main_assistant", "max_extra_agents": 3}
    assert AgentHubModule.manifest.needs == ()
    app = App([AgentHubModule], {"modules": {"enabled": [], "agent_hub": {"max_extra_agents": 1}}, "core": {}})
    assert app._config_of("agent_hub") == {**defaults, "max_extra_agents": 1}  # yours wins, the rest unchanged
