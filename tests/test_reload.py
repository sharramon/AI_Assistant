"""Hot-loading: ReloadModule swaps a module's code, AddModule loads a new one, without a restart."""

import asyncio
import importlib
import sys
import uuid

import pytest

from assistant.contracts import (
    AddModule,
    Command,
    InvokeTool,
    ListModules,
    Manifest,
    ModuleProtocol,
    ModuleState,
    ModuleStateChanged,
    ReloadModule,
    Result,
    Status,
)
from assistant.core import App
from assistant.core.loader import LoadError, check_reloadable
from assistant.core.router import CommandRouter
from assistant.testkit import Calculator, Speaker, make_config, wait_until

MODULE = """
from assistant.contracts import IToolProvider, Manifest, ModuleProtocol, Result, ToolSpec
from .version import VERSION


class VersionTool(ModuleProtocol, IToolProvider):
    manifest = Manifest(id="version_tool", provides=(IToolProvider,))

    async def init(self, ctx):
        self.ctx = ctx
        ctx.provide(IToolProvider, self)
{extra}
    def tools(self):
        return [ToolSpec(name="version", description="Which code runs")]

    async def invoke(self, name, args):
        return Result.ok(VERSION + self.ctx.config.get("suffix", ""))
"""


@pytest.fixture
def pkg(tmp_path):
    """A throwaway module package `hot_<id>.tool`, with a `write` helper to edit it."""
    top = f"hot_{uuid.uuid4().hex[:8]}"
    folder = tmp_path / top / "tool"
    folder.mkdir(parents=True)
    (tmp_path / top / "__init__.py").write_text("")

    def write(version="v1", extra="", module=None, init="from .module import VersionTool\n"):
        (folder / "__init__.py").write_text(init)
        (folder / "version.py").write_text(f"VERSION = {version!r}\n")
        (folder / "module.py").write_text(module if module is not None else MODULE.format(extra=extra))

    write()
    sys.path.insert(0, str(tmp_path))
    yield f"{top}.tool", write
    sys.path.remove(str(tmp_path))
    for name in [n for n in sys.modules if n == top or n.startswith(f"{top}.")]:
        del sys.modules[name]


async def version(app: App) -> str:
    result = await app.router.send(InvokeTool(name="version"))
    assert result.is_ok, result.error
    return result.value


def tool_class(package: str):
    return importlib.import_module(package).VersionTool


async def test_reload_runs_new_code_including_submodules(pkg):
    package, write = pkg
    app = App([tool_class(package)], make_config("version_tool"))
    states = []

    async def on_state(event: ModuleStateChanged) -> None:
        states.append(event.state)

    app.bus.subscribe(ModuleStateChanged, on_state)
    await app.start()
    assert await version(app) == "v1"

    write(version="v2, the new code")
    result = await app.router.send(ReloadModule(module_id="version_tool"))
    assert result.is_ok, result.error
    assert await version(app) == "v2, the new code"
    await wait_until(lambda: ModuleState.RELOADING in states and states[-1] is ModuleState.ACTIVE)
    await app.stop()


MENU_MODULE = """
from assistant.contracts import Manifest, Menu, ModuleProtocol, Result
from .version import VERSION

menu = Menu()


class VersionTool(ModuleProtocol):
    manifest = Manifest(id="version_tool")
    menu = menu

    async def init(self, ctx):
        pass

    @menu.item("version", "Which code runs")
    async def version(self):
        return Result.ok(VERSION)
"""


async def test_a_reloaded_menu_runs_the_new_method(pkg):
    package, write = pkg
    write(module=MENU_MODULE)
    app = App([tool_class(package)], make_config("version_tool"))
    await app.start()
    assert await version(app) == "v1"
    write(version="v2", module=MENU_MODULE)
    assert (await app.router.send(ReloadModule(module_id="version_tool"))).is_ok
    assert await version(app) == "v2"
    await app.stop()


async def test_broken_new_code_keeps_the_old_code_running(pkg):
    package, write = pkg
    app = App([tool_class(package)], make_config("version_tool"))
    await app.start()

    write(module="this is not python(\n")
    result = await app.router.send(ReloadModule(module_id="version_tool"))
    assert result.status is Status.FAILED
    assert "old code is running again" in result.error
    assert await version(app) == "v1"
    await app.stop()


async def test_new_code_failing_init_rolls_back(pkg):
    package, write = pkg
    app = App([tool_class(package)], make_config("version_tool"))
    await app.start()

    write(version="v2", extra="        raise RuntimeError('broken init')\n")
    result = await app.router.send(ReloadModule(module_id="version_tool"))
    assert result.status is Status.FAILED and "broken init" in result.error
    assert await version(app) == "v1"
    listed = (await app.router.send(ListModules())).value
    assert [m.state for m in listed] == [ModuleState.ACTIVE]
    await app.stop()


async def test_reload_reads_the_config_again(pkg):
    package, _ = pkg
    config = make_config("version_tool")
    fresh = {"modules": {"version_tool": {"suffix": " with new config"}}}
    app = App([tool_class(package)], config, lambda: fresh)
    await app.start()
    assert await version(app) == "v1"
    assert (await app.router.send(ReloadModule(module_id="version_tool"))).is_ok
    assert await version(app) == "v1 with new config"
    await app.stop()


async def test_add_module_loads_a_module_that_was_not_there_at_launch(pkg):
    package, _ = pkg
    app = App([], make_config(), lambda: {"modules": {"version_tool": {"suffix": "!"}}})
    await app.start()
    result = await app.router.send(AddModule(package=package))
    assert result.is_ok and result.value == "version_tool", result.error
    assert await version(app) == "v1!"

    again = await app.router.send(AddModule(package=package))
    assert again.status is Status.FAILED and "already loaded" in again.error
    await app.stop()


async def test_add_module_needing_a_new_contract_says_it_needs_a_restart(pkg):
    package, write = pkg
    write(module="from assistant.contracts import IWeatherThatDoesNotExist\n", init="from .module import *\n")
    app = App([], make_config())
    await app.start()
    result = await app.router.send(AddModule(package=package))
    assert result.status is Status.FAILED
    assert "restart" in result.error
    await app.stop()


async def test_shared_code_and_loose_classes_are_not_reloadable():
    app = App([Calculator], make_config("calculator"))  # lives in the test kit: shared code, no module's own
    await app.start()
    result = await app.router.send(ReloadModule(module_id="calculator"))
    assert result.status is Status.FAILED and "shared code (assistant.testkit)" in result.error
    await app.stop()
    with pytest.raises(LoadError, match="own package"):
        check_reloadable("tests")  # a loose class in a test file
    for shared in ("assistant.core", "assistant.contracts.voice", "assistant.infra", "app_kit", "assistant.modules",
                   "assistant.testkit"):  # fmt: skip
        with pytest.raises(LoadError):
            check_reloadable(shared)
    check_reloadable("assistant.modules.voice_in")


class NeedsSpeaker(ModuleProtocol):
    manifest = Manifest(id="needs_speaker", requires=(Speaker,))
    starts = 0

    async def init(self, ctx):
        NeedsSpeaker.starts += 1


async def test_reloading_a_provider_restarts_the_modules_that_require_it(pkg):
    package, write = pkg
    provider = """
from assistant.contracts import Manifest, ModuleProtocol
from assistant.testkit import Speaker


class SpeakerTool(ModuleProtocol, Speaker):
    manifest = Manifest(id="speaker_tool", provides=(Speaker,))

    async def init(self, ctx):
        ctx.provide(Speaker, self)
"""
    write(module=provider, init="from .module import SpeakerTool\n")
    cls = importlib.import_module(package).SpeakerTool
    NeedsSpeaker.starts = 0
    app = App([cls, NeedsSpeaker], make_config("speaker_tool", "needs_speaker"))
    await app.start()
    assert (await app.router.send(ReloadModule(module_id="speaker_tool"))).is_ok
    listed = {m.id: m.state for m in (await app.router.send(ListModules())).value}
    assert listed == {"speaker_tool": ModuleState.ACTIVE, "needs_speaker": ModuleState.ACTIVE}
    assert NeedsSpeaker.starts == 2
    await app.stop()


STATEFUL = """
from assistant.contracts import IToolProvider, Manifest, ModuleProtocol, Result, ToolSpec
from .version import VERSION


class VersionTool(ModuleProtocol, IToolProvider):
    manifest = Manifest(id="version_tool", provides=(IToolProvider,))
    busy_reason = None

    async def init(self, ctx):
        self.ctx = ctx
        self.calls = (ctx.handover or {}).get("calls", 0)
        ctx.provide(IToolProvider, self)
EXTRA
    def busy(self):
        return self.busy_reason

    def export_state(self):
        return {"calls": self.calls}

    def tools(self):
        return [ToolSpec(name="version", description="Which code runs")]

    async def invoke(self, name, args):
        self.calls += 1
        return Result.ok(f"{VERSION} call {self.calls}")
"""


def stateful(extra: str = "") -> str:
    return STATEFUL.replace("EXTRA\n", extra)


async def test_the_new_code_gets_the_old_instances_state(pkg):
    package, write = pkg
    write(module=stateful())
    app = App([tool_class(package)], make_config("version_tool"))
    await app.start()
    assert await version(app) == "v1 call 1"
    write(version="v2", module=stateful())
    assert (await app.router.send(ReloadModule(module_id="version_tool"))).is_ok
    assert await version(app) == "v2 call 2"
    await app.stop()


async def test_a_rollback_gives_the_state_back_to_the_old_code(pkg):
    package, write = pkg
    write(module=stateful())
    app = App([tool_class(package)], make_config("version_tool"))
    await app.start()
    assert await version(app) == "v1 call 1"
    write(version="v2", module=stateful("        raise RuntimeError('broken init')\n"))
    assert (await app.router.send(ReloadModule(module_id="version_tool"))).status is Status.FAILED
    assert await version(app) == "v1 call 2"
    await app.stop()


async def test_a_reload_waits_while_the_module_is_busy_and_now_cuts_in(pkg):
    package, write = pkg
    write(module=stateful())
    app = App([tool_class(package)], make_config("version_tool"))
    await app.start()
    app._lifecycle._active["version_tool"][0].busy_reason = "mid-task"

    timed_out = await app._lifecycle.reload("version_tool", idle_timeout=0.3)
    assert timed_out.status is Status.FAILED and "still busy (mid-task)" in timed_out.error and "now" in timed_out.error

    waiting = asyncio.create_task(app._lifecycle.reload("version_tool", idle_timeout=5))
    await asyncio.sleep(0.3)
    assert not waiting.done()
    app._lifecycle._active["version_tool"][0].busy_reason = None
    assert (await waiting).is_ok

    app._lifecycle._active["version_tool"][0].busy_reason = "mid-task"
    assert (await app.router.send(ReloadModule(module_id="version_tool", now=True))).is_ok
    await app.stop()


class Ping(Command):
    pass


async def test_a_command_sent_during_a_swap_waits_for_the_new_handler():
    router = CommandRouter(default_timeout=2.0)

    async def handler(command: Ping) -> Result:
        return Result.ok("pong")

    with router.hold():
        pending = asyncio.create_task(router.send(Ping()))
        await asyncio.sleep(0.05)
        assert not pending.done()
        router.register(Ping, handler)
    assert (await pending).value == "pong"
    # Without a hold, a missing handler fails at once.
    router.unregister(Ping, handler)
    assert (await router.send(Ping())).status is Status.NOT_AVAILABLE
