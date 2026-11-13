"""The Hub's message gate: an agent messaging another agent (not its own child task) asks the user
once per direction on a card (Allow once · Always allow · Deny); Always is saved under agent_hub and
the sender's kind; a revoke asks again and leaves agent_hub on; a message never interrupts a turn."""

from pathlib import Path

from assistant.contracts import (
    AnswerPermissionRequest,
    InvokeTool,
    ITaskAgent,
    ListModules,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ModuleState,
    PermissionChanged,
    PermissionRequested,
    ReportTask,
    StartTask,
)
from assistant.core import App
from assistant.modules.agent_hub import AgentHubModule
from assistant.testkit import FakeAgent, wait_until


class Agent(FakeAgent):
    """`working` (in a turn) is the fake's own flag; the Hub never delivers into a working agent."""


def agent_module(agent_id: str, folder: Path, kind: str = "") -> tuple[type, Agent]:
    agent = Agent(agent_id, (str(folder),))

    class AgentModule(ModuleProtocol):
        manifest = Manifest(id=f"{agent_id}_mod", description="A fake agent", provides=(ITaskAgent,),
                            sends=(ReportTask, InvokeTool))  # fmt: skip

        async def init(self, ctx: ModuleContext) -> None:
            agent.ctx = ctx
            ctx.provide(ITaskAgent, agent)

        async def start(self) -> None:
            if kind:
                agent.ctx.permissions.own_agent(agent_id, kind)

        async def stop(self) -> None: ...

    return AgentModule, agent


async def start(tmp_path: Path, *agents: tuple[str, str]) -> tuple[App, dict[str, Agent], list]:
    """An app with the Hub and one fake agent per (id, kind), grants in tmp_path."""
    modules, found = [AgentHubModule], {}
    for agent_id, kind in agents:
        module, found[agent_id] = agent_module(agent_id, tmp_path / agent_id, kind)
        modules.append(module)
    config = {"modules": {"enabled": [m.manifest.id for m in modules], "agent_hub": {"door": False}},
              "core": {"permissions": {"grants_file": str(tmp_path / "permissions.toml"), "reviewer": "",
                                       "you": ["temp_ui"]}}}  # fmt: skip
    app = App(modules, config)
    events: list = []

    async def record(event):
        events.append(event)

    for kind in (PermissionRequested, PermissionChanged):
        app.bus.subscribe(kind, record)
    await app.start()
    return app, found, events


def use(name: str, caller: str, **args) -> InvokeTool:
    return InvokeTool(name=name, args=args, caller=caller)


def cards(events: list) -> list[PermissionRequested]:
    return [e for e in events if isinstance(e, PermissionRequested)]


def texts(agent: Agent) -> list[str]:
    return [c[2] for c in agent.calls if c[0] in ("assign", "message")]


async def answer(app: App, events: list, allow: bool, remember: bool = True, nth: int = 0) -> None:
    await wait_until(lambda: len(cards(events)) > nth)
    card = cards(events)[nth]
    assert (await app.router.send(AnswerPermissionRequest(request_id=card.request_id, allow=allow,
                                                          remember=remember))).is_ok  # fmt: skip


async def test_allow_once_delivers_what_waited_saves_nothing_and_the_next_asks_again(tmp_path):
    app, agents, events = await start(tmp_path, ("job", ""), ("cv", ""))
    try:
        send = app.router.send
        first = await send(use("hub.send", "job", agent_id="cv", text="Acme JD attached"))
        assert first.value == {"agent_id": "cv", "how": "waiting on the user's card"}
        await wait_until(lambda: cards(events))
        card = cards(events)[0]
        assert card.action == "message" and card.caller == "job" and card.module_id == "agent_hub"
        assert [i.key for i in card.items] == ["message:cv"] and "Acme JD" in card.reason
        await send(use("hub.send", "job", agent_id="cv", text="and the 2024 CV"))  # behind the same card
        assert len(cards(events)) == 1 and texts(agents["cv"]) == []
        await answer(app, events, allow=True, remember=False)
        await wait_until(lambda: len(texts(agents["cv"])) == 2)
        assert texts(agents["cv"]) == ["[Message from job] Acme JD attached", "[Message from job] and the 2024 CV"]
        assert (await send(InvokeTool(name="permissions.grants"))).value == []
        await send(use("hub.send", "job", agent_id="cv", text="one more"))
        await wait_until(lambda: len(cards(events)) == 2)
    finally:
        await app.stop()


async def test_always_is_saved_per_direction_and_a_revoke_asks_again_with_the_hub_on(tmp_path):
    app, agents, events = await start(tmp_path, ("job", ""), ("cv", ""))
    try:
        send = app.router.send
        await send(use("hub.send", "job", agent_id="cv", text="hello"))
        await answer(app, events, allow=True, remember=True)
        await wait_until(lambda: texts(agents["cv"]))
        grants = (await send(InvokeTool(name="permissions.grants"))).value
        assert [(g["module_id"], g["subject"], g["granted"]) for g in grants] == [("agent_hub", "job", ["message:cv"])]
        sent = await send(use("hub.send", "job", agent_id="cv", text="again"))  # no card now
        assert sent.value["how"].startswith("message ") and len(cards(events)) == 1
        await send(use("hub.send", "cv", agent_id="job", text="the CV is ready"))  # the other way asks
        await wait_until(lambda: len(cards(events)) == 2)
        assert cards(events)[1].caller == "cv"

        revoked = await send(use("permissions.revoke", "temp_ui", module_id="agent_hub", subject="job"))
        assert revoked.is_ok and "stays on" in revoked.value
        infos = (await send(ListModules())).value
        assert next(i.state for i in infos if i.id == "agent_hub") is ModuleState.ACTIVE
        await send(use("hub.send", "job", agent_id="cv", text="after the revoke"))
        await wait_until(lambda: len(cards(events)) == 3)
    finally:
        await app.stop()


async def test_deny_sends_nothing_and_tells_the_sender(tmp_path):
    app, agents, events = await start(tmp_path, ("job", ""), ("cv", ""))
    try:
        await app.router.send(use("hub.send", "job", agent_id="cv", text="hello"))
        await answer(app, events, allow=False)
        await wait_until(lambda: agents["job"].notes)
        assert "didn't allow your message to cv" in agents["job"].notes[-1] and texts(agents["cv"]) == []
    finally:
        await app.stop()


async def test_a_helper_copy_uses_its_kinds_grant(tmp_path):
    app, agents, events = await start(tmp_path, ("helper", "helper"), ("helper_2", "helper"), ("cv", ""))
    try:
        await app.router.send(use("hub.send", "helper", agent_id="cv", text="from the first"))
        await answer(app, events, allow=True, remember=True)
        sent = await app.router.send(use("hub.send", "helper_2", agent_id="cv", text="from the copy"))
        assert sent.is_ok and sent.value["how"] != "waiting on the user's card" and len(cards(events)) == 1
    finally:
        await app.stop()


async def test_the_talker_and_a_parent_are_never_asked(tmp_path):
    app, agents, events = await start(tmp_path, ("job", ""), ("cv", ""))
    try:
        send = app.router.send
        assert (await send(use("hub.send", "talker", agent_id="cv", text="from you"))).is_ok
        assert texts(agents["cv"]) == ["from you"]
        await send(use("hub.cancel", "talker", task_id=agents["cv"].calls[0][1]))
        assert (await send(StartTask(text="apply to Acme", agent_id="job"))).is_ok
        child = await send(use("hub.start", "job", agent_id="cv", text="make the CV"))  # job's child task
        assert child.is_ok
        assert (await send(use("hub.send", "job", agent_id="cv", text="use the 2024 one"))).is_ok
        assert texts(agents["cv"])[-1] == "use the 2024 one" and not cards(events)  # straight in, no card
    finally:
        await app.stop()


async def test_a_message_never_interrupts_a_turn(tmp_path):
    app, agents, events = await start(tmp_path, ("job", ""), ("cv", ""))
    try:
        send = app.router.send
        await send(use("hub.send", "job", agent_id="cv", text="first"))
        await answer(app, events, allow=True, remember=True)
        await wait_until(lambda: texts(agents["cv"]))
        agents["cv"].working = True
        sent = await send(use("hub.send", "job", agent_id="cv", text="mid-turn"))
        assert sent.value["how"] == "pending" and texts(agents["cv"]) == ["[Message from job] first"]
        agents["cv"].working = False  # the turn ended: the Hub flushes on AgentStateChanged
        hub = app._lifecycle._active["agent_hub"][0]
        await hub._delivery.flush()
        assert texts(agents["cv"])[-1] == "[Message from job] mid-turn"
    finally:
        await app.stop()


async def test_unknown_or_self_or_no_target_is_refused(tmp_path):
    app, agents, events = await start(tmp_path, ("job", ""))
    try:
        send = app.router.send
        assert not (await send(use("hub.send", "job", agent_id="nobody", text="x"))).is_ok
        assert not (await send(use("hub.send", "job", agent_id="job", text="x"))).is_ok
        assert not (await send(use("hub.send", "job", text="x"))).is_ok
        assert not cards(events)
    finally:
        await app.stop()
