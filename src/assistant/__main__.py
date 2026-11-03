"""Composition root: the only place that names concrete modules. Run with `python -m assistant`."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from assistant.contracts import SessionTheme
from assistant.core import App, StartupError
from assistant.infra import LogSession, load_config, setup_logging
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.assistant_view import AssistantViewModule
from assistant.modules.console_io import ConsoleIO
from assistant.modules.echo_orchestrator import EchoOrchestrator
from assistant.modules.html_viewer import HtmlViewerModule
from assistant.modules.main_assistant import MainAssistantModule
from assistant.modules.talker import TalkerModule
from assistant.modules.temp_ui import TempUIModule
from assistant.modules.voice_in import VoiceInModule

# Every module the app can run. Which ones actually start is set by
# `modules.enabled` in config.
MODULES = [
    ConsoleIO,
    EchoOrchestrator,
    AgentHubModule,
    MainAssistantModule,
    TalkerModule,
    AssistantViewModule,
    TempUIModule,
    HtmlViewerModule,
    VoiceInModule,
]

log = logging.getLogger("assistant")


def main() -> int:
    config = load_config()
    logs = use_log_session(config)
    setup_logging(config["logging"], [logs.handler])
    try:
        app = App(MODULES, config)
        asyncio.run(_run(app, logs))
    except StartupError as exc:
        log.error("Startup failed: %s", exc)
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        logs.finish()
    return 0


def use_log_session(config: dict[str, Any]) -> LogSession:
    """Create the launch's LogSession and point the app log, every module's transcript, and
    the temp UI's Logs button at it. Nothing reaches disk before the first message's theme."""
    settings = config.setdefault("logging", {})
    logs = LogSession(settings.get("dir", "logs"), app_log=settings.pop("file", "assistant.log"))
    for module_id, section in config.get("modules", {}).items():
        if not isinstance(section, dict):
            continue
        if section.get("transcript"):
            section["transcript"] = logs.sink(section["transcript"])
        if module_id in ("temp_ui", "html_viewer"):
            section["logs_dir"] = logs.folder
    return logs


async def _run(app: App, logs: LogSession) -> None:
    async def on_theme(event: SessionTheme) -> None:
        logs.set_theme(event.text)

    app.bus.subscribe(SessionTheme, on_theme)
    await app.run()


if __name__ == "__main__":
    sys.exit(main())
