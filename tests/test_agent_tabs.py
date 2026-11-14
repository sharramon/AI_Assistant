"""The temp UI's agent tabs: the + opens your own helper (no launch card, a free name, the focus
follows), the × closes an agent after the page's warning (its task cancelled; a launched helper
closed, a module's agent by turning its module off), and the helpers turned on from the form."""

import asyncio

from assistant.contracts import (
    AnswerPermissionRequest,
    DeactivateModule,
    FocusChanged,
    GetTaskStatus,
    IAgentNames,
    ITaskAgent,
    ListModules,
    ModuleState,
    PermissionRequested,
    SetFocus,
)
from assistant.core import App
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.job_search import JobSearchModule
from assistant.modules.task_agents import TaskAgentsModule
from assistant.modules.task_agents.module import kind_configs
from assistant.modules.temp_ui import TempUIModule
from assistant.testkit import FAKE, agent_module, module_config, post, pre_grant, request, ui_port, wait_until


async def start(tmp_path, grant_helper: bool = True, helpers_on: bool = True) -> App:
    """The Hub, a fake coordinator, task_agents (kinds `helper`, and `scout` autostarted),
    the job agent, and the temp UI."""
    main_module, _ = agent_module("main_assistant", (str(tmp_path / "main"),))
    kinds = {"helper": {"program": FAKE, "workspace": str(tmp_path / "helpers"), "description": "A general helper"},
             "scout": {"program": FAKE, "workspace": str(tmp_path / "scouts"), "autostart": True}}  # fmt: skip
    job = {"program": FAKE, "workspace": str(tmp_path / "CV")}
    enabled = ["agent_hub", "main_assistant", "job_search", "temp_ui", *(["task_agents"] if helpers_on else [])]
    config = {"modules": {"enabled": enabled, "agent_hub": {"door": False}, "task_agents": {"agents": kinds},
                          "job_search": job, "temp_ui": {"port": 0, "window": "none"}},
              "core": {"permissions": {"you": ["temp_ui"]}}}  # as config/default.toml sets it; fmt: skip
    app = App([AgentHubModule, main_module, TaskAgentsModule, JobSearchModule, TempUIModule], config)
    seen = kind_configs(module_config("task_agents", {"agents": kinds}))  # over its module.toml kinds
    pre_grant(app, "task_agents", "scout", seen["scout"])
    if grant_helper:
        pre_grant(app, "task_agents", "helper", seen["helper"])
    pre_grant(app, "job_search", "job_search_agent", module_config("job_search", job))
    await app.start()
    return app


def hub(app: App):
    return app._lifecycle._active["agent_hub"][0]


def running(app: App) -> set[str]:
    return {a.info().agent_id for a in app.container.get_all(ITaskAgent)}


async def tasks_of(app: App, agent_id: str) -> list:
    return [t for t in (await app.router.send(GetTaskStatus())).value if t.agent_id == agent_id]


async def test_plus_opens_an_idle_helper_with_a_free_name_and_takes_the_focus(tmp_path):
    app = await start(tmp_path)
    port = ui_port(app)
    try:
        kinds = await post(port, "/agent-tabs", {"action": "kinds"})
        assert kinds["ok"] and {k["kind"]: k["free_name"] for k in kinds["value"]["kinds"]} == {
            "helper": "helper", "rezi": "rezi", "scout": "scout_2"}  # `scout` runs (autostart); `rezi` from its module.toml

        opened = await post(port, "/agent-tabs", {"action": "open", "kind": "helper", "name": "helper", "task": ""})
        assert opened["ok"] and opened["value"].startswith("Opening helper")  # no card for your own click
        await wait_until(lambda: hub(app)._focus.focused() == "helper", timeout=3)
        assert "helper" in running(app) and await tasks_of(app, "helper") == []  # idle: no task yet
        assert app.container.get_one(IAgentNames).taken()["helper"] == "task_agents"

        kinds = await post(port, "/agent-tabs", {"action": "kinds"})
        assert {k["kind"]: k["free_name"] for k in kinds["value"]["kinds"]}["helper"] == "helper_2"
        again = await post(port, "/agent-tabs", {"action": "open", "kind": "helper", "name": "helper"})
        assert not again["ok"] and "`helper_2` is free" in again["error"]  # the form fills it in
        bad = await post(port, "/agent-tabs", {"action": "open", "kind": "helper", "name": "Bad-Name"})
        assert not bad["ok"] and "isn't a valid" in bad["error"]

        # With a first task: it starts as your own task, with no parent.
        assert (await post(port, "/agent-tabs", {"action": "open", "kind": "helper", "name": "notes",
                                                 "task": "sort the notes"}))["ok"]  # fmt: skip
        await wait_until(lambda: hub(app)._focus.focused() == "notes", timeout=3)
        await wait_until(lambda: "notes" in running(app), timeout=3)
        task = (await tasks_of(app, "notes"))[0]
        assert task.text == "sort the notes" and task.parent_task_id is None
    finally:
        await app.stop()


async def test_a_denied_access_card_opens_nothing(tmp_path):
    app = await start(tmp_path, grant_helper=False)
    cards: list[PermissionRequested] = []

    async def record(event: PermissionRequested) -> None:
        cards.append(event)

    app.bus.subscribe(PermissionRequested, record)
    port = ui_port(app)
    try:
        assert (await post(port, "/agent-tabs", {"action": "open", "kind": "helper", "name": "helper"}))["ok"]
        await wait_until(lambda: cards, timeout=3)
        assert cards[0].subject == "helper"
        assert (await app.router.send(AnswerPermissionRequest(request_id=cards[0].request_id, allow=False))).is_ok
        await wait_until(lambda: not app._lifecycle._active["task_agents"][0]._opening, timeout=3)
        assert "helper" not in running(app) and "helper" not in app.container.get_one(IAgentNames).taken()
    finally:
        await app.stop()


async def test_close_cancels_the_task_then_closes_the_helper_or_its_module(tmp_path):
    app = await start(tmp_path)
    port = ui_port(app)
    close = lambda agent_id: post(port, "/agent-tabs", {"action": "close", "agent_id": agent_id})  # noqa: E731
    try:
        main = await close("main_assistant")
        assert not main["ok"] and "can't be closed" in main["error"]
        scout = await close("scout")  # autostarted: only with its module
        assert not scout["ok"] and "turn task_agents off" in scout["error"]

        assert (await post(port, "/agent-tabs", {"action": "open", "kind": "helper", "name": "slow",
                                                 "task": "SLOW sort everything"}))["ok"]  # fmt: skip
        await wait_until(lambda: hub(app)._focus.focused() == "slow", timeout=3)
        closed = await close("slow")
        assert closed["ok"] and "was cancelled" in closed["value"], closed
        assert "slow" not in running(app) and "slow" not in app.container.get_one(IAgentNames).taken()
        await wait_until(lambda: hub(app)._focus.focused() == "main_assistant", timeout=3)

        job = await close("job_search_agent")  # a module's agent: its module turns off
        assert job["ok"] and "job_search is off" in job["value"]
        modules = {m.id: m.state for m in (await app.router.send(ListModules())).value}
        assert modules["job_search"] is ModuleState.INACTIVE and "job_search_agent" not in running(app)
    finally:
        await app.stop()


async def test_when_the_tab_youre_on_goes_you_land_on_the_main_assistants(tmp_path):
    """Closed with ×, its module turned off: the Hub says so (`FocusChanged`), so the page moves.
    An agent you're not on going away moves nothing."""
    app = await start(tmp_path)
    moves: list[FocusChanged] = []

    async def record(event: FocusChanged) -> None:
        moves.append(event)

    app.bus.subscribe(FocusChanged, record)
    port = ui_port(app)
    ui = app._lifecycle._active["temp_ui"][0]
    try:
        assert (await post(port, "/agent-tabs", {"action": "open", "kind": "helper", "name": "helper"}))["ok"]
        await wait_until(lambda: ui._focus == "helper", timeout=3)
        assert (await post(port, "/agent-tabs", {"action": "close", "agent_id": "helper"}))["ok"]
        await wait_until(lambda: ui._focus == "main_assistant", timeout=3)
        assert (moves[-1].agent_id, moves[-1].previous) == ("main_assistant", "helper")

        assert (await app.router.send(SetFocus(agent_id="job_search_agent"))).is_ok
        await wait_until(lambda: ui._focus == "job_search_agent", timeout=3)
        assert (await app.router.send(DeactivateModule(module_id="job_search"))).is_ok
        await wait_until(lambda: ui._focus == "main_assistant", timeout=3)
        assert moves[-1].previous == "job_search_agent"

        count = len(moves)
        assert (await app.router.send(DeactivateModule(module_id="task_agents"))).is_ok  # `scout` goes, unfocused
        await wait_until(lambda: "scout" not in running(app), timeout=3)
        await asyncio.sleep(0.1)
        assert len(moves) == count and ui._focus == "main_assistant"
    finally:
        await app.stop()


async def test_the_form_turns_the_helpers_on(tmp_path):
    app = await start(tmp_path, helpers_on=False)
    port = ui_port(app)
    try:
        off = await post(port, "/agent-tabs", {"action": "kinds"})
        assert not off["ok"] and off["off"] is True
        assert (await post(port, "/agent-tabs", {"action": "turn_on"}))["ok"]
        assert (await post(port, "/agent-tabs", {"action": "kinds"}))["ok"]
    finally:
        await app.stop()


async def test_the_page_has_the_plus_and_the_close_warning(tmp_path):
    app = await start(tmp_path)
    port = ui_port(app)
    try:
        page = await get(port, "/")
        assert b'<script src="/agent-tabs.js"></script>' in page and b"window.agentTabsExtras" in page
        js = await get(port, "/agent-tabs.js")
        for text in (b"Close this agent?", b"Any task it's running will be cancelled.", b'textContent: "Close"',
                     b'textContent: "Cancel"', b"item.coordinator) continue", b"Open a new agent"):  # fmt: skip
            assert text in js, text
        # The boxes are display: flex, which beats the hidden attribute: without this rule both show,
        # empty, as a bar over the top buttons until + or × is pressed.
        assert b"#agent-panel[hidden], #agent-confirm[hidden] { display: none; }" in js
    finally:
        await app.stop()


async def get(port: int, path: str) -> bytes:
    reader, writer = await request(port, b"GET %s HTTP/1.1\r\n\r\n" % path.encode())
    async with asyncio.timeout(2):
        raw = await reader.read()
    writer.close()
    return raw.split(b"\r\n\r\n", 1)[1]
