"""The startup check before a restart: the real config builds the app the way `run_app` does.

It finds the modules (the repo's and any `[core] module_folders`), resolves the enabled list
and wires the core, without starting a module (that would launch real agents and windows).
A `StartupError` or `LoadError` here is what would stop the next launch.
"""

from __future__ import annotations

from assistant.core import App, configured_module_folders, find_modules
from assistant.infra import LogSession, load_config


def test_the_real_config_builds_the_app(tmp_path) -> None:
    config = load_config()
    config.setdefault("logging", {})
    logs = LogSession(str(tmp_path), app_log="assistant.log")
    try:
        app = App(find_modules(folders=configured_module_folders(config)), config, load_config, logs)
    finally:
        logs.finish()
    assert app.callers is not None
    assert app.menus is not None
