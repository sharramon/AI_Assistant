import asyncio

import pytest

from assistant.contracts import (
    Command,
    InputReceived,
    InvokeTool,
    Manifest,
    Module,
    ModuleContext,
    ResponseReady,
    Result,
    ShutdownRequested,
    Status,
    ToolProvider,
)
from assistant.core import App, StartupError
from assistant.modules.echo_orchestrator import EchoOrchestrator
from tests.support import Calculator, Speaker, make_config


class ShoutOrchestrator(Module):
    """A second, unrelated orchestrator implementation."""

    manifest = Manifest(id="shout_orchestrator")

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        ctx.subscribe(InputReceived, self._on_input)

    async def _on_input(self, event: InputReceived) -> None:
        self._ctx.publish(ResponseReady(text=event.text.upper(), correlation_id=event.id))


async def ask(app: App, text: str) -> ResponseReady:
    responses: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, responses.put)
    event = InputReceived(text=text, source="test")
    app.bus.publish(event)
    response = await asyncio.wait_for(responses.get(), 1)
    assert response.correlation_id == event.id
    return response


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [("echo_orchestrator", "Echo: hi"), ("shout_orchestrator", "HI")],
)
async def test_orchestrator_is_replaceable_by_config_alone(enabled, expected):
    """Acceptance test: swapping the orchestrator changes no core code, only `modules.enabled`."""
    app = App([EchoOrchestrator, ShoutOrchestrator], make_config(enabled))
    await app.start()
    assert (await ask(app, "hi")).text == expected
    await app.stop()


async def test_orchestrator_discovers_tools_without_knowing_them():
    app = App([EchoOrchestrator, Calculator], make_config("echo_orchestrator", "calculator"))
    await app.start()
    assert (await ask(app, "/tools")).text == "Tools: add"
    await app.stop()


async def test_invoke_tool_routing():
    class Calculator2(Calculator):
        manifest = Manifest(id="calculator2", provides=(ToolProvider,))

    app = App([Calculator, Calculator2], make_config("calculator"))
    await app.start()
    assert (await app.router.send(InvokeTool(name="add", args={"a": 1, "b": 2}))).value == 3
    assert (await app.router.send(InvokeTool(name="add", args={"a": 1}))).status is Status.INVALID_ARGUMENTS
    assert (await app.router.send(InvokeTool(name="nope"))).status is Status.NOT_AVAILABLE
    await app.stop()

    app = App([Calculator, Calculator2], make_config("calculator", "calculator2"))
    await app.start()
    assert (await app.router.send(InvokeTool(name="add", args={"a": 1, "b": 2}))).status is Status.FAILED
    await app.stop()


class Busy(Command):
    pass


class Everything(Module, ToolProvider):
    """Registers one of each kind of thing, to check that stop removes them all."""

    manifest = Manifest(id="everything", provides=(ToolProvider,))

    async def init(self, ctx: ModuleContext) -> None:
        ctx.subscribe(InputReceived, self._on_input)
        ctx.handle(Busy, self._busy)
        ctx.provide(ToolProvider, self)

    async def _on_input(self, event):
        pass

    async def _busy(self, command: Busy) -> Result:
        await asyncio.sleep(10)
        return Result.ok()

    def tools(self):
        return []

    async def invoke(self, name, args):
        return Result.ok()


async def test_stop_removes_all_registrations_and_cancels_commands():
    app = App([Everything], make_config("everything"))
    await app.start()
    pending = asyncio.create_task(app.router.send(Busy()))
    await asyncio.sleep(0.01)
    await app.stop()
    assert (await pending).status is Status.CANCELLED
    assert app.router._handlers == {}
    assert app.bus._subs == []
    assert app.container._providers == {}


async def test_shutdown_requested_event_ends_run():
    app = App([EchoOrchestrator], make_config("echo_orchestrator"))
    run = asyncio.create_task(app.run())
    await asyncio.sleep(0.01)
    app.bus.publish(ShutdownRequested(reason="test"))
    await asyncio.wait_for(run, 1)


class Broken(Module):
    manifest = Manifest(id="broken", provides=(Speaker,))

    async def init(self, ctx):
        raise RuntimeError("cannot init")


class NeedsSpeaker(Module):
    manifest = Manifest(id="needs_speaker", requires=(Speaker,))

    async def init(self, ctx):
        pass


async def test_failed_optional_module_is_skipped():
    app = App([Broken, EchoOrchestrator], make_config("broken", "echo_orchestrator"))
    await app.start()
    assert (await ask(app, "hi")).text == "Echo: hi"
    await app.stop()


async def test_failed_required_provider_aborts_startup():
    app = App([Broken, NeedsSpeaker], make_config("broken", "needs_speaker"))
    with pytest.raises(StartupError, match="require"):
        await app.start()
    await app.stop()


async def test_provide_requires_declaring_the_contract():
    class Undeclared(Module, ToolProvider):
        manifest = Manifest(id="undeclared")

        async def init(self, ctx):
            ctx.provide(ToolProvider, self)

        def tools(self):
            return []

        async def invoke(self, name, args):
            return Result.ok()

    app = App([Undeclared], make_config("undeclared"))
    await app.start()  # init fails, module is skipped
    assert app.container.get_all(ToolProvider) == []
    await app.stop()
