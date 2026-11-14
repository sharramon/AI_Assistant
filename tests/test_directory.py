"""The module directory: one line per module, then its menu, then a call; the core's own menu."""

import pytest

from assistant.contracts import (
    GetMenu,
    InvokeTool,
    ListModules,
    Manifest,
    ModuleProtocol,
    ModuleState,
    Status,
)
from assistant.core import App
from assistant.testkit import Speaker, make_config
from tests.test_menu import Counter


class SpeakerImpl(ModuleProtocol, Speaker):
    manifest = Manifest(id="speaker", description="Says things", provides=(Speaker,))

    async def init(self, ctx):
        ctx.provide(Speaker, self)

    def say(self, text):
        return text


class NeedsSpeaker(ModuleProtocol):
    manifest = Manifest(id="needs_speaker", requires=(Speaker,))

    async def init(self, ctx):
        pass


def test_core_is_a_reserved_id():
    with pytest.raises(ValueError):
        Manifest(id="core")


async def test_list_then_menu_then_call():
    app = App([Counter, SpeakerImpl], make_config("counter"))
    await app.start()
    try:
        lines = (await app.router.send(ListModules())).value
        assert [(m.id, m.description, m.state) for m in lines] == [
            ("counter", "Counts", ModuleState.ACTIVE),
            ("speaker", "Says things", ModuleState.INACTIVE),
        ]
        specs = (await app.router.send(GetMenu(module_id="counter"))).value
        assert [s.name for s in specs] == ["counter.add", "counter.peek"]
        assert (await app.router.send(InvokeTool(name="counter.add", args={"by": 3}))).value == 3
        # A module with no menu has an empty one; an unknown id is an argument error.
        assert (await app.router.send(GetMenu(module_id="speaker"))).value == []
        unknown = await app.router.send(GetMenu(module_id="nope"))
        assert unknown.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()


async def test_a_menu_is_readable_while_the_module_is_off():
    app = App([Counter], make_config())
    await app.start()
    try:
        specs = (await app.router.send(GetMenu(module_id="counter"))).value
        assert [s.name for s in specs] == ["counter.add", "counter.peek"]
        off = await app.router.send(InvokeTool(name="counter.add", args={"by": 1}))
        assert off.status is Status.NOT_AVAILABLE
        # The answer names the module that's off and how to turn it on, so the agent can ask the user.
        assert "The counter module isn't on" in off.error and "modules.on" in off.error
        unknown = await app.router.send(InvokeTool(name="nobody.has_this"))
        assert unknown.error == "No tool named 'nobody.has_this'"
    finally:
        await app.stop()


async def test_the_core_menu_controls_modules():
    app = App([Counter, SpeakerImpl, NeedsSpeaker], make_config())
    await app.start()
    try:
        names = [s.name for s in (await app.router.send(GetMenu(module_id="core"))).value]
        assert names == ["modules.list", "modules.menu", "modules.docs", "modules.on", "modules.off", "modules.reload", "modules.add",
                         "modules.remove", "permissions.grants", "permissions.grant", "permissions.request", "permissions.revoke"]

        listed = await app.router.send(InvokeTool(name="modules.list"))
        assert [m.id for m in listed.value] == ["counter", "speaker", "needs_speaker"]
        menu = await app.router.send(InvokeTool(name="modules.menu", args={"module_id": "counter"}))
        assert [s.name for s in menu.value] == ["counter.add", "counter.peek"]

        assert (await app.router.send(InvokeTool(name="modules.on", args={"module_id": "needs_speaker"}))).is_ok
        states = {m.id: m.state for m in (await app.router.send(ListModules())).value}
        assert states["speaker"] is ModuleState.ACTIVE  # pulled in by requires

        off = await app.router.send(InvokeTool(name="modules.off", args={"module_id": "speaker"}))
        assert off.is_ok and "needs_speaker" in off.value  # never refused; the reply names who stays on
        bad = await app.router.send(InvokeTool(name="modules.on", args={"module_id": ""}))
        assert bad.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()

# The risky items' ask-first gate: tests/test_risky_steps_ask.py.
