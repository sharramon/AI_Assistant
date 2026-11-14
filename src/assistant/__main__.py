"""Composition root. Run with `python -m assistant`. It names no module: the core finds them
by folder (`src/assistant/modules/<id>/`, then the folders `[core] module_folders` names), and
`modules.enabled` in config says which start.

`python -m assistant` is a small launcher: it runs the app as a child process in the same
console and starts it again whenever it exits with the restart code (`core.restart_exit_code`,
75), which it does after a `ShutdownRequested(restart=True)`. A new process loads new code.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from assistant.contracts import SessionTheme
from assistant.core import App, LoadError, StartupError, configured_module_folders, find_modules
from assistant.infra import LogSession, load_config, setup_logging

log = logging.getLogger("assistant")

CHILD_ENV = "ASSISTANT_APP_CHILD"  # set for the app process the launcher runs
RESTART_EXIT_CODE = 75


def main() -> int:
    if os.environ.get(CHILD_ENV) == "1":
        return run_app()
    return launch()


def launch(popen: Callable[..., subprocess.Popen] = subprocess.Popen) -> int:
    """Run the app as a child process; start it again while it exits with the restart code."""
    restart_code = load_config().get("core", {}).get("restart_exit_code", RESTART_EXIT_CODE)
    env = {**os.environ, CHILD_ENV: "1"}
    while True:
        child = popen([sys.executable, "-m", "assistant", *sys.argv[1:]], env=env)
        while True:
            try:
                code = child.wait()
                break
            except KeyboardInterrupt:
                continue  # the child got Ctrl+C too and is stopping cleanly
        if code != restart_code:
            return code
        print("Restarting the assistant...", flush=True)


def run_app() -> int:
    """The app itself. Returns the restart code after a ShutdownRequested(restart=True)."""
    config = load_config()
    logs = use_log_session(config)
    setup_logging(config["logging"], [logs.handler])
    app = None
    try:
        # The repo's modules, then those in the folders `[core] module_folders` names (outside the repo).
        app = App(find_modules(folders=configured_module_folders(config)), config, load_config, logs)
        asyncio.run(_run(app, logs))
    except (StartupError, LoadError) as exc:
        log.error("Startup failed: %s", exc)
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        logs.finish()
    if app is not None and app.restart_requested:
        return config.get("core", {}).get("restart_exit_code", RESTART_EXIT_CODE)
    return 0


def use_log_session(config: dict[str, Any]) -> LogSession:
    """Create the launch's LogSession, which the app log writes to and every module reaches
    as `ctx.logs`. Nothing reaches disk before the first message's theme."""
    settings = config.setdefault("logging", {})
    return LogSession(settings.get("dir", "logs"), app_log=settings.pop("file", "assistant.log"))


async def _run(app: App, logs: LogSession) -> None:
    async def on_theme(event: SessionTheme) -> None:
        logs.set_theme(event.text)

    app.bus.subscribe(SessionTheme, on_theme)
    await app.run()


if __name__ == "__main__":
    sys.exit(main())
