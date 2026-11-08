"""The module directory: one line per module, then its menu, then a call; the core's own menu."""

import pytest

from assistant.contracts import (
    GetMenu,
    InvokeTool,
    ListModules,
    Manifest,
    ModulePermissions,
    ModuleProtocol,
    ModuleState,
    Status,
)
from assistant.core import App
from tests.support import Speaker, make_config
from tests.test_menu import Counter


class Deny(ModulePermissions):
    def __init__(self):
        self.asked: list[str] = []

    def has(self, name):
        return False

    async def request(self, name, reason=""):
        self.asked.append(name)
        return False


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
    finally:
        await app.stop()


async def test_the_core_menu_controls_modules():
    app = App([Counter, SpeakerImpl, NeedsSpeaker], make_config())
    await app.start()
    try:
        names = [s.name for s in (await app.router.send(GetMenu(module_id="core"))).value]
        assert names == ["modules.list", "modules.menu", "modules.docs", "modules.on", "modules.off", "modules.reload", "modules.add",
                         "permissions.grants", "permissions.grant", "permissions.request", "permissions.revoke"]

        listed = await app.router.send(InvokeTool(name="modules.list"))
        assert [m.id for m in listed.value] == ["counter", "speaker", "needs_speaker"]
        menu = await app.router.send(InvokeTool(name="modules.menu", args={"module_id": "counter"}))
        assert [s.name for s in menu.value] == ["counter.add", "counter.peek"]

        assert (await app.router.send(InvokeTool(name="modules.on", args={"module_id": "needs_speaker"}))).is_ok
        states = {m.id: m.state for m in (await app.router.send(ListModules())).value}
        assert states["speaker"] is ModuleState.ACTIVE  # pulled in by requires

        refused = await app.router.send(InvokeTool(name="modules.off", args={"module_id": "speaker"}))
        assert refused.status is Status.FAILED and "needs_speaker" in refused.error
        bad = await app.router.send(InvokeTool(name="modules.on", args={"module_id": ""}))
        assert bad.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()


async def test_the_risky_core_items_ask_first():
    app = App([SpeakerImpl, NeedsSpeaker], make_config("speaker", "needs_speaker"))
    app.core_menu.permissions = deny = Deny()
    await app.start()
    try:
        off = await app.router.send(
            InvokeTool(name="modules.off", args={"module_id": "speaker", "with_dependents": True})
        )
        assert off.status is Status.FAILED and "Not allowed" in off.error
        add = await app.router.send(InvokeTool(name="modules.add", args={"package": "assistant.modules.echo_orchestrator"}))
        assert add.status is Status.FAILED and "Not allowed" in add.error
        assert deny.asked == ["modules.off_with_dependents", "modules.add"]
        states = {m.id: m.state for m in (await app.router.send(ListModules())).value}
        assert states == {"speaker": ModuleState.ACTIVE, "needs_speaker": ModuleState.ACTIVE}
        # Plain off (no dependents to take down) doesn't ask.
        assert (await app.router.send(InvokeTool(name="modules.off", args={"module_id": "needs_speaker"}))).is_ok
        assert deny.asked == ["modules.off_with_dependents", "modules.add"]
    finally:
        await app.stop()
