"""Composition root: the only place that names concrete modules. Run with `python -m assistant`."""

from __future__ import annotations

import asyncio
import sys

from assistant.core import App, StartupError
from assistant.infra import load_config, setup_logging
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.assistant_view import AssistantViewModule
from assistant.modules.console_io import ConsoleIO
from assistant.modules.echo_orchestrator import EchoOrchestrator
from assistant.modules.main_assistant import MainAssistantModule
from assistant.modules.talker import TalkerModule

# Every module the app can run. Which ones actually start is set by
# `modules.enabled` in config.
MODULES = [ConsoleIO, EchoOrchestrator, AgentHubModule, MainAssistantModule, TalkerModule, AssistantViewModule]


def main() -> int:
    config = load_config()
    setup_logging(config.get("logging", {}))
    try:
        app = App(MODULES, config)
        asyncio.run(app.run())
    except StartupError as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
