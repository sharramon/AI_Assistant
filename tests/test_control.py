"""Runtime module control: activating and deactivating modules while the app runs."""

import asyncio
import queue
import threading

from assistant.contracts import (
    ActivateModule,
    DeactivateModule,
    InputReceived,
    InvokeTool,
    IToolProvider,
    ListModules,
    Manifest,
    Module,
    ModuleContext,
    ModuleState,
    ModuleStateChanged,
    Status,
)
from assistant.core import App
from assistant.modules.console_io import ConsoleIO
from assistant.modules.console_io import module as console_module
from tests.support import Calculator, Speaker, make_config, wait_until


class Tracked(Module):
    """Records every instance and lifecycle call, to check fresh instances and clean stops."""

    manifest = Manifest(id="tracked")
    instances: list["Tracked"] = []

    async def init(self, ctx: ModuleContext) -> None:
        self.calls = ["init"]
        Tracked.instances.append(self)

    async def start(self) -> None:
        self.calls.append("start")

    async def stop(self) -> None:
        self.calls.append("stop")


class SpeakerImpl(Module, Speaker):
    manifest = Manifest(id="speaker", provides=(Speaker,))

    async def init(self, ctx):
        ctx.provide(Speaker, self)


class OtherSpeaker(SpeakerImpl):
    manifest = Manifest(id="other_speaker", provides=(Speaker,))


class NeedsSpeaker(Module):
    manifest = Manifest(id="needs_speaker", requires=(Speaker,))

    async def init(self, ctx):
        pass


class FailsToStart(Module):
    manifest = Manifest(id="fails_to_start")
    should_fail = True

    async def init(self, ctx):
        pass

    async def start(self):
        if FailsToStart.should_fail:
            raise RuntimeError("no microphone")


def states(app: App) -> dict[str, ModuleState]:
    return {info.id: info.state for info in app._lifecycle.modules()}


async def send(app: App, command):
    return await app.router.send(command)


async def test_list_modules_includes_inactive_ones():
    app = App([Calculator, Tracked], make_config("calculator"))
    await app.start()
    result = await send(app, ListModules())
    assert {info.id: info.state for info in result.value} == {
        "calculator": ModuleState.ACTIVE,
        "tracked": ModuleState.INACTIVE,
    }
    assert result.value[0].provides == ("IToolProvider",)
    await app.stop()


async def test_deactivate_then_activate_uses_a_fresh_instance():
    Tracked.instances.clear()
    app = App([Tracked], make_config("tracked"))
    await app.start()
    assert (await send(app, DeactivateModule(module_id="tracked"))).is_ok
    assert states(app)["tracked"] is ModuleState.INACTIVE
    assert (await send(app, ActivateModule(module_id="tracked"))).is_ok
    assert states(app)["tracked"] is ModuleState.ACTIVE
    await app.stop()

    first, second = Tracked.instances
    assert first is not second
    assert first.calls == ["init", "start", "stop"]
    assert second.calls == ["init", "start", "stop"]


async def test_deactivated_module_tools_disappear_and_return():
    app = App([Calculator], make_config("calculator"))
    await app.start()
    add = InvokeTool(name="add", args={"a": 1, "b": 2})
    await send(app, DeactivateModule(module_id="calculator"))
    assert (await send(app, add)).status is Status.NOT_AVAILABLE
    await send(app, ActivateModule(module_id="calculator"))
    assert (await send(app, add)).value == 3
    await app.stop()


async def test_activate_starts_the_sole_required_provider_first():
    app = App([SpeakerImpl, NeedsSpeaker], make_config())
    await app.start()
    assert (await send(app, ActivateModule(module_id="needs_speaker"))).is_ok
    assert states(app) == {"speaker": ModuleState.ACTIVE, "needs_speaker": ModuleState.ACTIVE}
    await app.stop()


async def test_activate_refuses_ambiguous_or_missing_providers():
    app = App([SpeakerImpl, OtherSpeaker, NeedsSpeaker], make_config())
    await app.start()
    result = await send(app, ActivateModule(module_id="needs_speaker"))
    assert result.status is Status.FAILED
    assert "speaker, other_speaker" in result.error
    await app.stop()

    app = App([NeedsSpeaker], make_config())
    await app.start()
    assert (await send(app, ActivateModule(module_id="needs_speaker"))).status is Status.NOT_AVAILABLE
    await app.stop()


async def test_activate_refuses_a_second_single_provider():
    app = App([SpeakerImpl, OtherSpeaker], make_config("speaker"))
    await app.start()
    result = await send(app, ActivateModule(module_id="other_speaker"))
    assert result.status is Status.FAILED
    assert "'speaker' already provides Speaker" in result.error
    await app.stop()


async def test_unknown_module_is_invalid():
    app = App([Tracked], make_config())
    await app.start()
    assert (await send(app, ActivateModule(module_id="nope"))).status is Status.INVALID_ARGUMENTS
    assert (await send(app, DeactivateModule(module_id="nope"))).status is Status.INVALID_ARGUMENTS
    await app.stop()


async def test_deactivate_respects_dependents():
    app = App([SpeakerImpl, NeedsSpeaker], make_config("speaker", "needs_speaker"))
    await app.start()
    result = await send(app, DeactivateModule(module_id="speaker"))
    assert result.status is Status.FAILED
    assert "required by needs_speaker" in result.error
    assert states(app)["speaker"] is ModuleState.ACTIVE

    assert (await send(app, DeactivateModule(module_id="speaker", with_dependents=True))).is_ok
    assert states(app) == {"speaker": ModuleState.INACTIVE, "needs_speaker": ModuleState.INACTIVE}
    await app.stop()


async def test_deactivate_allowed_when_another_provider_remains():
    class SharedTools(Calculator):
        manifest = Manifest(id="shared_tools", provides=(IToolProvider,))

    class NeedsTools(Module):
        manifest = Manifest(id="needs_tools", requires=(IToolProvider,))

        async def init(self, ctx):
            pass

    app = App([Calculator, SharedTools, NeedsTools], make_config("calculator", "shared_tools", "needs_tools"))
    await app.start()
    assert (await send(app, DeactivateModule(module_id="calculator"))).is_ok
    assert states(app)["needs_tools"] is ModuleState.ACTIVE
    await app.stop()


async def test_failed_activation_can_be_retried():
    FailsToStart.should_fail = True
    app = App([FailsToStart], make_config())
    await app.start()
    result = await send(app, ActivateModule(module_id="fails_to_start"))
    assert result.status is Status.FAILED
    assert "no microphone" in result.error
    assert states(app)["fails_to_start"] is ModuleState.FAILED

    FailsToStart.should_fail = False
    assert (await send(app, ActivateModule(module_id="fails_to_start"))).is_ok
    assert states(app)["fails_to_start"] is ModuleState.ACTIVE
    await app.stop()


async def test_state_changes_are_published():
    app = App([Tracked], make_config())
    seen: list[tuple[str, ModuleState]] = []

    async def record(event: ModuleStateChanged) -> None:
        seen.append((event.module_id, event.state))

    app.bus.subscribe(ModuleStateChanged, record)
    await app.start()
    await send(app, ActivateModule(module_id="tracked"))
    await send(app, DeactivateModule(module_id="tracked"))
    await wait_until(lambda: len(seen) == 4)
    assert [state for _, state in seen] == [
        ModuleState.STARTING,
        ModuleState.ACTIVE,
        ModuleState.STOPPING,
        ModuleState.INACTIVE,
    ]
    await app.stop()


async def test_shutdown_stops_runtime_activated_modules():
    Tracked.instances.clear()
    app = App([Tracked], make_config())
    await app.start()
    await send(app, ActivateModule(module_id="tracked"))
    await app.stop()
    assert Tracked.instances[0].calls == ["init", "start", "stop"]
    assert states(app)["tracked"] is ModuleState.INACTIVE


async def test_closed_context_stops_publishing():
    class Leaky(Module):
        """Keeps its context after stop, like a leftover thread would."""

        manifest = Manifest(id="leaky")
        last: "Leaky"

        async def init(self, ctx):
            self.ctx = ctx
            Leaky.last = self

    app = App([Leaky], make_config("leaky"))
    inputs: list[InputReceived] = []

    async def record(event: InputReceived) -> None:
        inputs.append(event)

    app.bus.subscribe(InputReceived, record)
    await app.start()
    await send(app, DeactivateModule(module_id="leaky"))
    Leaky.last.ctx.publish(InputReceived(text="ghost", source="leaky"))
    assert (await Leaky.last.ctx.send(ListModules())).status is Status.NOT_AVAILABLE
    await asyncio.sleep(0.02)
    assert inputs == []
    await app.stop()


async def test_console_io_restart_reuses_one_input_thread(monkeypatch):
    lines: queue.Queue[str | None] = queue.Queue()

    def fake_input() -> str:
        line = lines.get()
        if line is None:
            raise EOFError
        return line

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(console_module, "_stdin", console_module._StdinReader())
    app = App([ConsoleIO], make_config("console_io"))
    inputs: list[str] = []

    async def record(event: InputReceived) -> None:
        inputs.append(event.text)

    app.bus.subscribe(InputReceived, record)
    await app.start()
    await send(app, DeactivateModule(module_id="console_io"))
    await send(app, ActivateModule(module_id="console_io"))
    lines.put("hello")
    await wait_until(lambda: inputs == ["hello"])
    assert sum(t.name == "console-input" for t in threading.enumerate()) == 1
    await app.stop()
    lines.put(None)  # end the reader thread


async def test_activation_finishes_even_if_the_command_times_out():
    class SlowStart(Module):
        manifest = Manifest(id="slow_start")

        async def init(self, ctx):
            pass

        async def start(self):
            await asyncio.sleep(0.1)

    app = App([SlowStart], make_config())
    await app.start()
    result = await app.router.send(ActivateModule(module_id="slow_start"), timeout=0.01)
    assert result.status is Status.TIMED_OUT
    await wait_until(lambda: states(app)["slow_start"] is ModuleState.ACTIVE)
    await app.stop()
    assert states(app)["slow_start"] is ModuleState.INACTIVE
