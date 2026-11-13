"""Every module found by folder can be reloaded, turned off and on again while the app runs.

The in-process half of the module system's final check (docs/next-steps/module-system.md,
"Restart test"); the live half runs the same swaps through the agents' door after a restart.
Safe settings: a fake claude, free ports, no windows, nothing that answers on the real ports.
"""

import pytest

from assistant.contracts import (
    ActivateModule,
    DeactivateModule,
    InvokeTool,
    IVoice,
    ListModules,
    ModuleState,
    ReloadModule,
)
from assistant.core import App, find_modules
from assistant.testkit import FAKE, free_port

SKIP = {"console_io"}  # reads the console; its off-and-on is covered in its own tests (modules/console_io/tests)


def config(tmp_path) -> dict:
    ids = [cls.manifest.id for cls in find_modules() if cls.manifest.id not in SKIP]
    none = {"window": "none", "port": 0}
    return {
        "core": {"reload_idle_timeout": 5.0},
        "modules": {
            "enabled": ids,
            "talker": {"program": FAKE},
            "main_assistant": {"program": FAKE, "workspace": str(tmp_path / "workspace")},
            "temp_ui": none,
            "voice_notes": none,
            "assistant_view": none,
            "html_viewer": {"port": free_port(), "window": "none"},
            "voice_in": {"port": free_port()},
        },
    }


@pytest.fixture
async def app(tmp_path):
    app = App(find_modules(), config(tmp_path))
    await app.start()
    try:
        yield app
    finally:
        await app.stop()


def states(listing) -> dict:
    return {m.id: m.state for m in listing}


async def test_every_module_reloads_and_turns_off_and_on(app):
    ids = [i for i, s in states((await app.router.send(ListModules())).value).items() if s is ModuleState.ACTIVE]
    assert len(ids) >= 9, ids
    for module_id in ids:
        result = await app.router.send(ReloadModule(module_id=module_id, now=True))
        assert result.is_ok, f"reload {module_id}: {result.error}"
    for module_id in ids:
        off = await app.router.send(DeactivateModule(module_id=module_id, with_dependents=True))
        assert off.is_ok, f"off {module_id}: {off.error}"
        on = await app.router.send(ActivateModule(module_id=module_id))
        assert on.is_ok, f"on {module_id}: {on.error}"
    after = states((await app.router.send(ListModules())).value)
    # Turning a provider off took its dependents with it; turning them on again brings them back.
    for module_id in ids:
        if after[module_id] is not ModuleState.ACTIVE:
            assert (await app.router.send(ActivateModule(module_id=module_id))).is_ok
    assert all(s is ModuleState.ACTIVE for i, s in states((await app.router.send(ListModules())).value).items()
               if i in ids)  # fmt: skip


async def test_modules_still_use_each_other_after_swaps(app):
    await app.router.send(ReloadModule(module_id="voice_in", now=True))
    await app.router.send(ReloadModule(module_id="html_viewer", now=True))
    assert app.container.get_one(IVoice) is not None  # voice notes' recorder, from the new voice_in
    # voice_in can't go while voice notes requires it
    assert not (await app.router.send(DeactivateModule(module_id="voice_in"))).is_ok
    # the menus are linked to the new copies
    assert (await app.router.send(InvokeTool(name="echo.say", args={"text": "hi"}))).value == "Echo: hi"
    assert (await app.router.send(InvokeTool(name="modules.list"))).is_ok
