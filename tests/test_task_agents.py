"""The task_agents module: big helper agents from config profiles, running beside the
coordinator through the real SessionTaskAgent (the fake claude), within the Hub's cap."""

import json

import pytest

from assistant.contracts import (
    AnswerPermissionRequest,
    FocusChanged,
    InvokeTool,
    ITaskAgent,
    PermissionMode,
    PermissionRequested,
    ReportKind,
    SetFocus,
    StartTask,
    Status,
    TaskUpdated,
)
from assistant.core import App
from assistant.infra.agent_profile import path_rule
from assistant.infra.claude_session import ClaudeSession
from assistant.infra.mcp_door import CALLER_ENV, SERVER
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.task_agents import TaskAgentsModule
from assistant.modules.task_agents.module import agent_configs
from assistant.testkit import FAKE, agent_module, pre_grant_kinds, status, wait_until


async def start_app(tmp_path, agents: dict, door: bool = False, **hub_config):
    """The Hub, a fake coordinator (`main_assistant`), and task_agents with `agents`."""
    main_module, main = agent_module("main_assistant", (str(tmp_path / "main"),))
    profiles = {aid: {"program": FAKE, "workspace": str(tmp_path / aid), "autostart": True, **p}
                for aid, p in agents.items()}  # fmt: skip
    config = {
        "modules": {
            "enabled": ["agent_hub", "main_assistant", "task_agents"],
            "agent_hub": {"door": door, **hub_config},
            "task_agents": {"agents": profiles},
        },
        "core": {},
    }
    app = App([AgentHubModule, main_module, TaskAgentsModule], config)
    pre_grant_kinds(app, config["modules"]["task_agents"])
    events: list = []

    async def record(event):
        events.append(event)

    for kind in (TaskUpdated, FocusChanged, PermissionRequested):
        app.bus.subscribe(kind, record)
    await app.start()
    return app, main, events


def agent(app: App, agent_id: str):
    return next(a for a in app.container.get_all(ITaskAgent) if a.info().agent_id == agent_id)


def test_kinds_autostart_instances_and_reserved_names(tmp_path):
    configs = agent_configs({
        "permission_mode": "default",
        "agents": {"scout": {"workspace": str(tmp_path / "scouts"), "write_dirs": ["x"], "instances": 2,
                             "autostart": True},
                   "helper": {}},  # a kind without autostart: launched when needed, not at start
    })  # fmt: skip
    assert list(configs) == ["scout", "scout_2"]
    kind, scout_2 = configs["scout_2"]
    assert kind == "scout" and scout_2["workspace"] == str((tmp_path / "scouts" / "scout_2").resolve())
    scout = configs["scout"][1]
    assert scout["write_dirs"] == [] and str((tmp_path / "scouts").resolve()) in scout["read_dirs"]
    assert scout["permission_mode"] == "default"  # the module's defaults reach every kind
    with pytest.raises(ValueError):
        agent_configs({"agents": {"talker": {"autostart": True}}})  # would get the Talker's rights on the menu


async def test_two_agents_work_at_once(tmp_path):
    app, main, events = await start_app(tmp_path, {"helper": {}, "writer": {}})
    try:
        first = await app.router.send(StartTask(text="SLOW sort the notes", agent_id="helper"))
        second = await app.router.send(StartTask(text="SLOW draft the summary", agent_id="writer"))
        assert first.is_ok and second.is_ok
        await wait_until(lambda: agent(app, "helper").info().active and agent(app, "writer").info().active)
        assert {a.info().agent_id for a in app.container.get_all(ITaskAgent)} == {"main_assistant", "helper", "writer"}
    finally:
        await app.stop()


async def test_status_goes_to_the_coordinator_and_need_waits_behind_the_mark(tmp_path):
    app, main, events = await start_app(tmp_path, {"helper": {}, "writer": {}})
    try:
        await app.router.send(StartTask(text="sort the notes\nSTATUS: notes sorted", agent_id="helper"))
        await wait_until(lambda: any(n.startswith("[helper] task done") for n in main.notes))
        assert main.notes[0] == "[helper] notes sorted"  # one line, before its end

        asked = (await app.router.send(StartTask(text="ASKME then draft", agent_id="writer"))).value
        await wait_until(lambda: any(isinstance(e, TaskUpdated) and e.kind is ReportKind.NEED for e in events))
        held = await status(app, asked)
        assert held.held and held.question == "Which style?"  # out of focus: behind its tab's !
        assert not any("Which style" in n for n in main.notes)  # questions never go into the feed

        await app.router.send(SetFocus(agent_id="writer"))
        await wait_until(lambda: any(isinstance(e, FocusChanged) for e in events))
        changed = next(e for e in events if isinstance(e, FocusChanged))
        assert [t.id for t in changed.released] == [asked]
    finally:
        await app.stop()


async def test_the_cap_refuses_a_fourth_extra_agent(tmp_path):
    app, main, events = await start_app(tmp_path, {"helper": {"instances": 4}}, max_extra_agents=3)
    try:
        send = app.router.send
        assert (await send(StartTask(text="plan", agent_id="main_assistant"))).is_ok  # not counted
        for agent_id in ("helper", "helper_2", "helper_3"):
            assert (await send(StartTask(text="SLOW work", agent_id=agent_id))).is_ok
        refused = await send(StartTask(text="SLOW work", agent_id="helper_4"))
        assert refused.status is Status.NOT_AVAILABLE and "most at once (3" in refused.error
        assert (await send(StartTask(text="SLOW work"))).status is Status.NOT_AVAILABLE  # any free one: the same
    finally:
        await app.stop()


def test_only_the_coordinator_is_told_to_delegate_and_suggest(tmp_path):
    from assistant.contracts import PermissionMode
    from assistant.infra import AgentProfile
    from assistant.infra.agent_profile import prompt_block
    from assistant.modules.main_assistant.module import COORDINATOR_BLOCK

    coordinator, helper = prompt_block(COORDINATOR_BLOCK), prompt_block()
    for item in ("hub.start", "hub.send", "hub.suggest_focus", "only the user moves the focus"):
        assert item in coordinator and item not in helper
    profile = AgentProfile.from_config("main_assistant", {"workspace": str(tmp_path)}, COORDINATOR_BLOCK)
    assert "hub.suggest_focus" in " ".join(profile.command("You work.", PermissionMode.MANUAL))


async def test_each_agent_uses_the_door_under_its_own_name(tmp_path):
    app, main, events = await start_app(tmp_path, {"helper": {}}, door=True)
    try:
        command = agent(app, "helper")._session._command_source()
        door = json.loads(command[command.index("--mcp-config") + 1])
        assert door["mcpServers"][SERVER]["env"][CALLER_ENV] == "helper"
    finally:
        await app.stop()


def helpers(app: App) -> dict:
    return app._lifecycle._active["task_agents"][0]._agents


async def test_a_kinds_grant_reaches_all_of_its_helpers_live(tmp_path):
    app, main, events = await start_app(tmp_path, {"helper": {"instances": 2}})
    try:
        extra = str((tmp_path / "extra").resolve())
        asked = await app.router.send(InvokeTool(name="permissions.request", caller="helper_2", args={"read": [extra]}))
        assert asked.is_ok, asked.error
        await wait_until(lambda: any(isinstance(e, PermissionRequested) for e in events))
        card = next(e for e in events if isinstance(e, PermissionRequested))
        await app.router.send(AnswerPermissionRequest(request_id=card.request_id, allow=True, keep=(card.items[0].key,)))
        rule = path_rule("Read", extra)
        await wait_until(lambda: all(rule in ",".join(a.profile.command("p", PermissionMode.MANUAL)) for a in helpers(app).values()))
        assert set(helpers(app)) == {"helper", "helper_2"}
        assert helpers(app)["helper_2"].profile.write_folders() == (str((tmp_path / "helper" / "helper_2").resolve()),)
    finally:
        await app.stop()


@pytest.mark.parametrize("busy", [False, True])
async def test_an_idle_open_session_restarts_on_a_grant_and_a_busy_one_waits(tmp_path, monkeypatch, busy):
    app, main, events = await start_app(tmp_path, {"helper": {}})
    try:
        helper = helpers(app)["helper"]
        restarts: list[bool] = []

        async def restart() -> bool:
            restarts.append(True)
            return True

        monkeypatch.setattr(ClaudeSession, "running", property(lambda self: True))
        monkeypatch.setattr(helper.agent, "restart_session", restart)
        if busy:
            monkeypatch.setattr(type(helper.agent), "has_task", property(lambda self: True))  # holds a task
        config = {**helper._config, "read_dirs": [str(tmp_path / "more")]}
        helper.set_access(config)
        helper.set_access(config)  # a second change while the first restart runs: one restart
        if helper._regrant is not None:
            await helper._regrant
        assert restarts == ([] if busy else [True])
        assert path_rule("Read", str((tmp_path / "more").resolve())) in ",".join(helper.profile.command("p", PermissionMode.MANUAL))
    finally:
        await app.stop()
