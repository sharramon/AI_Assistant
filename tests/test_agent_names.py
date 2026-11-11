"""Agent names: the rules (`check_agent_id`, `free_agent_id`), the Hub's claims (`IAgentNames`),
the safety net for two agents with one id, launching a helper by name (`agents.launch`, which
only proposes), and `SessionTaskAgent.request_approval` (the card it puts to the user)."""

import logging

from assistant.contracts import (
    AgentStateChanged,
    AnswerPermission,
    DeactivateModule,
    GetTaskStatus,
    IAgentNames,
    InvokeTool,
    ITaskAgent,
    ListAgents,
    ListModules,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ModuleState,
    ReloadModule,
    ReportKind,
    Result,
    SendToTask,
    StartTask,
    Status,
)
from assistant.core import App
from assistant.infra import check_agent_id, free_agent_id
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.agent_hub.module import RESERVED_AGENT_IDS
from assistant.modules.job_search import JobSearchModule
from tests.support import pre_grant, wait_until
from tests.test_agents import FAKE, next_matching, report
from tests.test_multi_agent import FakeAgent
from tests.test_task_agents import agent, start_app

# --- the rules ---


def test_check_agent_id_form_reserved_and_module_ids():
    assert check_agent_id("flight_search") is None
    for bad in ("Flight", "flight-search", "2nd", "", "a" * 33):
        assert "isn't a valid agent id" in check_agent_id(bad)
    assert RESERVED_AGENT_IDS == {"talker", "core", "hub"}  # the Hub's; it adds its coordinator
    assert check_agent_id("talker") is None  # the shared rules reserve nothing themselves
    assert "reserved" in check_agent_id("talker", reserved=RESERVED_AGENT_IDS)
    assert check_agent_id("main_assistant", owner="main_assistant") is None  # its own module's agent
    assert "module's id" in check_agent_id("voice_in", module_ids=["voice_in"])
    assert check_agent_id("voice_in", owner="voice_in", module_ids=["voice_in"]) is None


def test_free_agent_id_counts_up_with_underscores():
    assert free_agent_id("helper", set()) == "helper"
    assert free_agent_id("helper", {"helper"}) == "helper_2"
    assert free_agent_id("helper", {"helper", "helper_2"}) == "helper_3"


# --- the Hub's claims ---


async def start_hub(*modules, config: dict | None = None) -> App:
    ids = ["agent_hub", *(m.manifest.id for m in modules)]
    app = App([AgentHubModule, *modules], {"modules": {"enabled": ids, "agent_hub": {"door": False}, **(config or {})},
                                          "core": {}})  # fmt: skip
    if job := (config or {}).get("job_search"):
        pre_grant(app, "job_search", "job_search_agent", job)
    await app.start()
    return app


async def test_claim_clash_module_ids_and_release():
    app = await start_hub()
    try:
        names = app.container.get_one(IAgentNames)
        assert (await names.claim("flight_search", "mod_a")).is_ok
        clash = await names.claim("flight_search", "mod_b")
        assert clash.status is Status.INVALID_ARGUMENTS
        assert clash.error == "`flight_search` is taken by mod_a; `flight_search_2` is free"
        assert names.taken() == {"flight_search": "mod_a"}  # the first keeps it
        assert (await names.claim("flight_search", "mod_a")).is_ok  # a repeat claim by its holder succeeds
        assert names.taken() == {"flight_search": "mod_a"}
        assert await names.check("flight_search", "mod_a")  # but check still says it's taken (no second agent)
        assert "module's id" in (await names.claim("agent_hub", "mod_a")).error
        assert (await names.claim("agent_hub", "agent_hub")).is_ok  # a module's own id, for its own agent
        assert "isn't a valid agent id" in (await names.claim("Bad-Name", "mod_a")).error
        names.release("flight_search", "mod_b")  # not the holder: no effect
        assert "flight_search" in names.taken()
        names.release("flight_search", "mod_a")
        assert await names.check("flight_search", "mod_b") is None

        assert (await app.router.send(ReloadModule(module_id="agent_hub"))).is_ok
        assert app.container.get_one(IAgentNames).taken() == {"agent_hub": "agent_hub"}  # survives a reload
    finally:
        await app.stop()


def job_config(tmp_path, **extra) -> dict:
    return {"job_search": {"program": FAKE, "workspace": str(tmp_path / "CV"), **extra}}


async def test_the_job_agent_claims_its_default_name_and_frees_it(tmp_path):
    app = await start_hub(JobSearchModule, config=job_config(tmp_path))
    try:
        names = app.container.get_one(IAgentNames)
        assert names.taken() == {"job_search_agent": "job_search"}
        assert (await app.router.send(DeactivateModule(module_id="job_search"))).is_ok
        assert names.taken() == {}
    finally:
        await app.stop()


async def test_a_module_id_as_agent_id_stops_the_module(tmp_path):
    app = App([AgentHubModule, JobSearchModule],
              {"modules": {"enabled": ["agent_hub", "job_search"], "agent_hub": {"door": False},
                           **job_config(tmp_path, agent_id="agent_hub")}, "core": {}})  # fmt: skip
    pre_grant(app, "job_search", "agent_hub", job_config(tmp_path)["job_search"])
    try:
        try:
            await app.start()
        except Exception:
            pass  # refused at start: either the start fails or the module is left failed
        modules = {m.id: m.state for m in (await app.router.send(ListModules())).value}
        assert modules["job_search"] is not ModuleState.ACTIVE
        assert "agent_hub" not in app.container.get_one(IAgentNames).taken()
    finally:
        await app.stop()


# --- the safety net: two agents with one id ---


async def test_two_agents_with_one_id_list_once_and_log_once(caplog):
    first, second = FakeAgent("twin", ()), FakeAgent("twin", ())

    class TwinsModule(ModuleProtocol):
        manifest = Manifest(id="twins", description="Two agents, one id", provides=(ITaskAgent,))

        async def init(self, ctx: ModuleContext) -> None:
            ctx.provide(ITaskAgent, first)
            ctx.provide(ITaskAgent, second)

        async def start(self) -> None: ...

        async def stop(self) -> None: ...

    app = await start_hub(TwinsModule)
    try:
        with caplog.at_level(logging.ERROR):
            for _ in range(2):
                agents = (await app.router.send(ListAgents())).value
                assert [a.agent_id for a in agents] == ["twin"]
            assert (await app.router.send(StartTask(text="x", agent_id="twin"))).is_ok
        assert first.calls and not second.calls  # the first keeps the id
        assert sum("share the id 'twin'" in r.getMessage() for r in caplog.records) == 1
    finally:
        await app.stop()


# --- launching a helper by name ---


async def launch_app(tmp_path):
    """task_agents with one kind, `helper` (not autostarted), and a coordinator with a task
    whose `request_approval` keeps the proposal instead of asking anyone."""
    app, main, events = await start_app(tmp_path, {"helper": {"autostart": False}})
    asked: list = []

    async def request_approval(action, run):
        asked.append((action, run))
        return Result.ok()

    main.request_approval = request_approval
    main_task = (await app.router.send(StartTask(text="plan a trip", agent_id="main_assistant"))).value
    return app, main_task, asked


def launch(name: str, task: str = "find flights", caller: str = "main_assistant", **args) -> InvokeTool:
    return InvokeTool(name="agents.launch", args={"name": name, "task": task, **args}, caller=caller)


async def test_a_launch_only_proposes_and_starts_on_allow(tmp_path):
    app, main_task, asked = await launch_app(tmp_path)
    try:
        kinds = (await app.router.send(InvokeTool(name="agents.kinds", caller="main_assistant"))).value
        assert [k["kind"] for k in kinds["kinds"]] == ["helper"] and kinds["running"] == []

        proposed = await app.router.send(launch("flight_search"))
        assert proposed.is_ok and "End your turn" in proposed.value
        action, run = asked[0]
        assert action == "Launch a new helper `flight_search` (helper) for: find flights"
        assert not any(a.info().agent_id == "flight_search" for a in app.container.get_all(ITaskAgent))  # not yet

        outcome = await run()  # the user allowed it
        assert outcome.is_ok and outcome.value.startswith("flight_search started on task ")
        task_id = outcome.value.rsplit(" ", 1)[1]
        info = (await app.router.send(GetTaskStatus(task_id=task_id))).value[0]
        assert info.agent_id == "flight_search" and info.parent_task_id == main_task
        assert app.container.get_one(IAgentNames).taken()["flight_search"] == "task_agents"
        assert agent(app, "flight_search").info().write_folders[0].endswith("flight_search")

        again = await app.router.send(launch("flight_search"))
        assert again.status is Status.INVALID_ARGUMENTS and "`flight_search_2` is free" in again.error

        await wait_until(lambda: not agent(app, "flight_search").info().active)
        states: list[AgentStateChanged] = []

        async def keep(event: AgentStateChanged) -> None:
            states.append(event)

        app.bus.subscribe(AgentStateChanged, keep)
        assert (await app.router.send(InvokeTool(name="agents.close", args={"agent_id": "flight_search"},
                                                 caller="main_assistant"))).is_ok  # fmt: skip
        assert "flight_search" not in app.container.get_one(IAgentNames).taken()
        assert not any(a.info().agent_id == "flight_search" for a in app.container.get_all(ITaskAgent))
        # The close is said at once, so the Talker closes that tab's session and usage marks it closed.
        await wait_until(lambda: any(s.agent_id == "flight_search" for s in states))
    finally:
        await app.stop()


async def test_a_launch_without_a_yes_does_nothing_and_needs_a_task(tmp_path):
    app, _, asked = await launch_app(tmp_path)
    try:
        assert (await app.router.send(launch("hotel_search"))).is_ok  # proposed, never allowed
        assert len(asked) == 1 and "hotel_search" not in app.container.get_one(IAgentNames).taken()

        talker = await app.router.send(launch("hotel_search", caller="talker"))
        assert talker.status is Status.NOT_AVAILABLE and "hand it to the Main Assistant" in talker.error
        for bad, why in ((launch("x", kind="ghost"), "No kind of helper"), (launch("core"), "reserved"),
                         (launch("Bad-Name"), "isn't a valid")):  # fmt: skip
            refused = await app.router.send(bad)
            assert refused.status is Status.INVALID_ARGUMENTS and why in refused.error
        assert len(asked) == 1
    finally:
        await app.stop()


# --- the card behind it: SessionTaskAgent.request_approval ---


async def test_request_approval_waits_for_the_answer_then_reports_the_outcome(tmp_path):
    from tests.test_agents import start_hub as start_main

    app, updates = await start_main(tmp_path)
    try:
        task_id = (await app.router.send(StartTask(text="SLOW job"))).value
        await next_matching(updates, lambda e: e.text == "started")
        main = next(a for a in app.container.get_all(ITaskAgent) if a.info().agent_id == "main_assistant")
        ran: list = []

        async def run() -> Result:
            ran.append(True)
            return Result.ok("helper_x started on task abc")

        assert (await main.request_approval("Launch a new helper `helper_x` (helper) for: y", run)).is_ok
        asked = await next_matching(updates, report(ReportKind.PERMISSION))
        assert asked.text == "Launch a new helper `helper_x` (helper) for: y"
        again = await main.request_approval("another", run)
        assert again.status is Status.NOT_AVAILABLE  # one open question at a time

        # A message meanwhile interrupts and is answered, but the turn ending doesn't finish the task.
        assert (await app.router.send(SendToTask(task_id=task_id, text="how is it going?"))).is_ok
        await next_matching(updates, report(ReportKind.REPLY))
        status = (await app.router.send(GetTaskStatus(task_id=task_id))).value[0]
        assert not status.state.is_final and not ran

        assert (await app.router.send(AnswerPermission(task_id=task_id, allow=True))).is_ok
        done = await next_matching(updates, report(ReportKind.DONE))
        assert ran and done.text.startswith("[App] Launch a new helper `helper_x` (helper) for: y: done. helper_x")
    finally:
        await app.stop()


async def test_request_approval_needs_a_task(tmp_path):
    from tests.test_agents import start_hub as start_main

    app, _ = await start_main(tmp_path)
    try:
        main = next(a for a in app.container.get_all(ITaskAgent) if a.info().agent_id == "main_assistant")
        refused = await main.request_approval("x", lambda: None)
        assert refused.status is Status.NOT_AVAILABLE
        assert (await FakeAgent("plain", ()).request_approval("x", lambda: None)).status is Status.NOT_AVAILABLE
    finally:
        await app.stop()
