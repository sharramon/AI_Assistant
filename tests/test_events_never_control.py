"""R6 (D5): events never control. A shutdown, an agent notice and a reset are commands now, each
sent by a module that declares it; publishing one on the bus does nothing."""

from assistant.contracts import (
    AgentNotice,
    InvokeTool,
    ITaskAgent,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ResetRequested,
    Result,
    ShutdownRequested,
    Status,
)
from assistant.core import App
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.talker import TalkerModule
from assistant.testkit import FAKE, FakeAgent, agent_module, make_config, wait_until


def sender(module_id: str, *sends: type) -> type:
    """A module that sends what it's asked to (`.ctx.send`), declaring `sends`."""

    class Sender(ModuleProtocol):
        manifest = Manifest(id=module_id, sends=sends)

        async def init(self, ctx: ModuleContext) -> None:
            self.ctx = ctx

    return Sender


def instance(app: App, module_id: str):
    return app._lifecycle._active[module_id][0]


async def test_a_declared_shutdown_command_sets_the_restart_flag():
    app = App([sender("restarter", ShutdownRequested)], make_config("restarter"))
    await app.start()
    try:
        result = await instance(app, "restarter").ctx.send(ShutdownRequested(reason="test", restart=True))
        assert result.is_ok and app.restart_requested
    finally:
        await app.stop()


async def test_a_module_that_does_not_declare_it_is_refused_and_a_published_one_does_nothing():
    app = App([sender("quiet")], make_config("quiet"))
    await app.start()
    try:
        refused = await instance(app, "quiet").ctx.send(ShutdownRequested(restart=True))
        assert refused.status is Status.INVALID_ARGUMENTS and not app.restart_requested
        app.bus.publish(ShutdownRequested(restart=True))  # type: ignore[arg-type]  # no longer an event
        await wait_until(lambda: True)
        assert not app.restart_requested and not app._stopping.is_set()
    finally:
        await app.stop()


class ResettableAgent(FakeAgent):
    async def reset(self) -> Result:
        self.calls.append(("reset",))
        return Result.ok()


async def hub_app(*extra: type):
    main_module, _ = agent_module("main_assistant", ())
    main = ResettableAgent("main_assistant", ())

    class MainModule(main_module):  # the testkit's module, providing the resettable agent instead
        async def init(self, ctx: ModuleContext) -> None:
            main.ctx = ctx
            ctx.provide(ITaskAgent, main)

    ids = ["agent_hub", "main_assistant", *(m.manifest.id for m in extra)]
    config = make_config(*ids)
    config["modules"]["agent_hub"] = {"door": False}
    app = App([AgentHubModule, MainModule, *extra], config)
    await app.start()
    return app, main


async def test_a_notice_goes_through_the_hub_to_the_agents_note_labelled_with_the_sender():
    app, main = await hub_app(sender("job_search", AgentNotice))
    try:
        notice = AgentNotice(agent_id="main_assistant", text="search finished", source="job.search")
        assert (await instance(app, "job_search").ctx.send(notice)).is_ok
        assert main.notes == ["[job_search] search finished"]  # the stamped sender, not `source`
        assert (await app.router.send(notice.model_copy(update={"agent_id": "nobody"}))).status is Status.NOT_AVAILABLE
    finally:
        await app.stop()


async def test_the_permissions_handlers_notices_keep_their_label():
    app, main = await hub_app()
    try:
        await app.permissions._notify("main_assistant", "your grant was saved")
        assert main.notes == ["[permissions] your grant was saved"]
    finally:
        await app.stop()


async def test_a_reset_through_the_hub_calls_the_agents_reset():
    app, main = await hub_app(sender("resetter", ResetRequested))
    try:
        assert (await instance(app, "resetter").ctx.send(ResetRequested(agent_id="main_assistant"))).is_ok
        assert main.calls == [("reset",)]
        missing = await instance(app, "resetter").ctx.send(ResetRequested(agent_id="nobody"))
        assert missing.status is Status.NOT_AVAILABLE
    finally:
        await app.stop()


async def test_talker_reset_is_refused_for_anyone_but_you():
    config = {"modules": {"enabled": ["talker"], "talker": {"program": FAKE}},
              "core": {"permissions": {"you": ["temp_ui"]}}}  # fmt: skip
    app = App([TalkerModule], config)
    await app.start()
    try:
        args = {"session": "talker"}
        refused = await app.router.send(InvokeTool(name="talker.reset", args=args, caller="main_assistant"))
        assert refused.status is Status.NOT_AVAILABLE
        allowed = await app.router.send(InvokeTool(name="talker.reset", args=args, caller="temp_ui"))
        assert allowed.is_ok
    finally:
        await app.stop()
