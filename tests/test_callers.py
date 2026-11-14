"""R3: the Callers port. The App provides it as `IAgentNames`; each agent's mode lives in it; the
core's `SetPermissionMode` handler gives Auto only to you (or the core); a `SessionTaskAgent`
refuses Auto unless the port already says Auto; a released id goes back to Manual."""

from __future__ import annotations

from assistant.contracts import (
    IAgentNames,
    ITaskAgent,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    PermissionMode,
    Result,
    SetPermissionMode,
    Status,
    Task,
)
from assistant.core import App
from assistant.core.callers import Callers
from assistant.infra import SessionTaskAgent
from assistant.testkit import StubContext, StubSession, make_config


class ModeAgent(ITaskAgent):
    """An agent that only records the modes it is given."""

    def __init__(self) -> None:
        self.modes: list[PermissionMode] = []

    def info(self):
        from assistant.contracts import AgentInfo

        return AgentInfo(agent_id="worker", description="records modes")

    async def assign(self, task: Task) -> Result:
        return Result.ok()

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        return Result.ok()

    async def cancel(self, task_id: str) -> Result:
        return Result.ok()

    async def answer_permission(self, task_id: str, allow: bool) -> Result:
        return Result.ok()

    async def set_permission_mode(self, mode: PermissionMode) -> Result:
        self.modes.append(mode)
        return Result.ok(False)


AGENT = ModeAgent()


class WorkerModule(ModuleProtocol):
    manifest = Manifest(id="worker_mod", provides=(ITaskAgent,))

    async def init(self, ctx: ModuleContext) -> None:
        ctx.provide(ITaskAgent, AGENT)


def _sender(module_id: str) -> type:
    class Sender(ModuleProtocol):
        manifest = Manifest(id=module_id, sends=(SetPermissionMode,))

        async def init(self, ctx: ModuleContext) -> None:
            self.ctx = ctx

    return Sender


async def _app(you=("ui",)) -> App:
    AGENT.modes = []
    modules = [WorkerModule, _sender("ui"), _sender("plain")]
    app = App(modules, make_config(*(m.manifest.id for m in modules), permissions={"you": list(you)}))
    await app.start()
    return app


def _ctx(app: App, module_id: str) -> ModuleContext:
    return app._lifecycle._active[module_id][0].ctx


async def test_the_app_provides_its_callers_as_the_agent_names() -> None:
    app = await _app()
    try:
        assert app.container.get_one(IAgentNames) is app.callers
        assert app.callers.is_you("ui") and not app.callers.is_you("plain")
    finally:
        await app.stop()


async def test_auto_from_a_module_that_is_not_you_is_refused() -> None:
    app = await _app()
    try:
        result = await _ctx(app, "plain").send(SetPermissionMode(agent_id="worker", mode=PermissionMode.AUTO))
        assert result.status is Status.NOT_AVAILABLE
        assert AGENT.modes == [] and app.callers.mode("worker") is PermissionMode.MANUAL
    finally:
        await app.stop()


async def test_auto_from_you_is_applied_and_recorded() -> None:
    app = await _app()
    try:
        result = await _ctx(app, "ui").send(SetPermissionMode(agent_id="worker", mode=PermissionMode.AUTO))
        assert result.is_ok and AGENT.modes == [PermissionMode.AUTO]
        assert app.callers.mode("worker") is PermissionMode.AUTO
        # Manual from anyone, which puts it back
        back = await _ctx(app, "plain").send(SetPermissionMode(agent_id="worker", mode=PermissionMode.MANUAL))
        assert back.is_ok and app.callers.mode("worker") is PermissionMode.MANUAL
        assert AGENT.modes == [PermissionMode.AUTO, PermissionMode.MANUAL]
    finally:
        await app.stop()


async def test_the_core_itself_may_set_auto_and_an_unknown_agent_is_refused() -> None:
    app = await _app()
    try:
        assert (await app.router.send(SetPermissionMode(agent_id="worker", mode=PermissionMode.AUTO))).is_ok
        assert app.callers.mode("worker") is PermissionMode.AUTO
        ghost = await app.router.send(SetPermissionMode(agent_id="ghost", mode=PermissionMode.AUTO))
        assert ghost.status is Status.INVALID_ARGUMENTS and app.callers.mode("ghost") is PermissionMode.MANUAL
    finally:
        await app.stop()


async def test_an_agent_refuses_auto_that_did_not_come_through_the_core() -> None:
    callers = Callers(lambda: [])
    ctx = StubContext()
    ctx.provided[IAgentNames] = callers
    agent = SessionTaskAgent(StubSession(), ctx, "worker", "a worker")
    refused = await agent.set_permission_mode(PermissionMode.AUTO)
    assert refused.status is Status.NOT_AVAILABLE
    assert (await agent.set_permission_mode(PermissionMode.MANUAL)).is_ok
    callers.set_mode("worker", PermissionMode.AUTO)  # what the core's handler does first
    assert (await agent.set_permission_mode(PermissionMode.AUTO)).is_ok


async def test_release_puts_the_mode_back_to_manual_and_only_the_holder_releases() -> None:
    callers = Callers(lambda: [])
    assert (await callers.claim("scout", "task_agents")).is_ok
    callers.set_mode("scout", PermissionMode.AUTO)
    callers.release("scout", "someone_else")
    assert callers.mode("scout") is PermissionMode.AUTO
    callers.release("scout", "task_agents")
    assert callers.mode("scout") is PermissionMode.MANUAL and callers.taken() == {}


def test_is_you_and_who_may_set_auto() -> None:
    callers = Callers(lambda: [], you=["ui"], relays=["talker"])
    assert callers.is_you("ui") and not callers.is_you("talker")
    assert callers.may_set_auto("core") and callers.may_set_auto("ui") and not callers.may_set_auto("talker")
