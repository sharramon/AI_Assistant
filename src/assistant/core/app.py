"""The host: wires the core together and runs the enabled modules."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from functools import partial
from typing import Any

from assistant.contracts import InvokeTool, Manifest, Module, ShutdownRequested
from assistant.core.bus import EventBus
from assistant.core.container import Container
from assistant.core.context import ScopedContext
from assistant.core.lifecycle import LifecycleManager
from assistant.core.registry import resolve_modules
from assistant.core.router import CommandRouter
from assistant.core.tools import dispatch_tool

log = logging.getLogger(__name__)


class App:
    def __init__(self, available: Sequence[type[Module]], config: dict[str, Any]):
        """Validate the enabled modules. Raises StartupError before anything runs."""
        core = config.get("core", {})
        self._module_config = config.get("modules", {})
        self.router = CommandRouter(core.get("command_timeout", 30.0), core.get("command_timeouts", {}))
        self.bus = EventBus(core.get("event_queue_size", 100), core.get("event_handler_timeout", 10.0))
        self.container = Container()
        self._lifecycle = LifecycleManager(
            resolve_modules(available, self._module_config.get("enabled", [])),
            self._make_context,
            core.get("module_stop_timeout", 5.0),
        )
        self._tool_handler = partial(dispatch_tool, self.container)
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        """Start, run until shutdown is requested (or the task is cancelled), then stop."""
        try:
            await self.start()
            await self._stopping.wait()
        finally:
            await self.stop()

    async def start(self) -> None:
        self.router.register(InvokeTool, self._tool_handler)
        self.bus.subscribe(ShutdownRequested, self._on_shutdown_requested)
        await self._lifecycle.start()

    async def stop(self) -> None:
        """Cancel in-flight commands, stop modules in reverse order, then close the bus."""
        cancelled = self.router.cancel_all()
        if cancelled:
            log.info("Cancelled %d in-flight command(s)", cancelled)
        await self._lifecycle.stop()
        self.router.unregister(InvokeTool, self._tool_handler)
        await self.bus.close()
        log.info("Stopped")

    def request_shutdown(self) -> None:
        self._stopping.set()

    async def _on_shutdown_requested(self, event: ShutdownRequested) -> None:
        log.info("Shutdown requested: %s", event.reason or "no reason given")
        self.request_shutdown()

    def _make_context(self, manifest: Manifest) -> ScopedContext:
        return ScopedContext(
            manifest,
            self.router,
            self.bus,
            self.container,
            self._module_config.get(manifest.id, {}),
            logging.getLogger(f"assistant.modules.{manifest.id}"),
        )
