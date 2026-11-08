"""Companion apps follow their module on a reload: handed over unless their own code changed."""

import pytest

from assistant.contracts import ReloadModule
from assistant.core import App
from assistant.modules.html_viewer import HtmlViewerModule
from assistant.modules.voice_in import VoiceInModule
from tests.test_voice_in import free_port


@pytest.mark.parametrize("module_id", ["voice_in", "html_viewer"])
async def test_a_reload_keeps_the_app_unless_its_code_changed(module_id):
    # Free ports: nothing answers there, so no real voice service or viewer is ever touched.
    modules = {
        "enabled": [module_id],
        "voice_in": {"port": free_port()},
        "html_viewer": {"port": free_port(), "window": "none"},
    }
    app = App([VoiceInModule, HtmlViewerModule], {"modules": modules, "core": {}})
    await app.start()
    try:
        first = app._lifecycle._active[module_id][0]
        assert (await app.router.send(ReloadModule(module_id=module_id))).is_ok
        second = app._lifecycle._active[module_id][0]
        assert second is not first and second._app is first._app  # unchanged code: handed over

        second._app.code_changed = lambda: True  # the companion app's own source was edited
        assert (await app.router.send(ReloadModule(module_id=module_id))).is_ok
        third = app._lifecycle._active[module_id][0]
        assert third._app is not second._app  # a fresh CompanionApp: the next start runs the new code
        assert second._companion._restart
    finally:
        await app.stop()
