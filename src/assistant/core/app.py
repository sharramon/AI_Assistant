"""The host: wires the core together and runs the enabled modules."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

from assistant.contracts import (
    ActivateModule,
    AddModule,
    DeactivateModule,
    InvokeTool,
    ListModules,
    Manifest,
    ModuleProtocol,
    ModuleState,
    ModuleStateChanged,
    ReloadModule,
    Result,
    ShutdownRequested,
)
from assistant.core.bus import EventBus
from assistant.core.container import Container
from assistant.core.context import ScopedContext
from assistant.core.lifecycle import LifecycleManager
from assistant.core.registry import resolve_modules
from assistant.core.router import CommandRouter
from assistant.core.tools import dispatch_tool

log = logging.getLogger(__name__)


class App:
    def __init__(
        self,
        available: Sequence[type[ModuleProtocol]],
        config: dict[str, Any],
        config_loader: Callable[[], dict[str, Any]] | None = None,
    ):
        """Validate the enabled modules. Raises StartupError before anything runs.

        `modules.enabled` are active at startup; every other module in `available`
        can be activated at runtime with `ActivateModule`. `config_loader`, if given,
        re-reads the config before `ReloadModule` and `AddModule`, so a reloaded or
        added module gets its current config section.
        """
        core = config.get("core", {})
        self._module_config = config.get("modules", {})
        self._config_loader = config_loader
        self._reload_idle_timeout = core.get("reload_idle_timeout", 300.0)
        self.router = CommandRouter(core.get("command_timeout", 30.0), core.get("command_timeouts", {}))
        self.bus = EventBus(core.get("event_queue_size", 100), core.get("event_handler_timeout", 10.0))
        self.container = Container()
        self._lifecycle = LifecycleManager(
            available,
            resolve_modules(available, self._module_config.get("enabled", [])),
            self._make_context,
            core.get("module_stop_timeout", 5.0),
            self._on_module_state,
        )
        self._handlers = {
            InvokeTool: partial(dispatch_tool, self.container),
            ListModules: self._list_modules,
            ActivateModule: self._activate_module,
            DeactivateModule: self._deactivate_module,
            ReloadModule: self._reload_module,
            AddModule: self._add_module,
        }
        self._stopping = asyncio.Event()
        self.restart_requested = False  # a ShutdownRequested asked for a restart

    async def run(self) -> None:
        """Start, run until shutdown is requested (or the task is cancelled), then stop."""
        try:
            await self.start()
            await self._stopping.wait()
        finally:
            await self.stop()

    async def start(self) -> None:
        for command_type, handler in self._handlers.items():
            self.router.register(command_type, handler)
        self.bus.subscribe(ShutdownRequested, self._on_shutdown_requested)
        await self._lifecycle.start()

    async def stop(self) -> None:
        """Cancel in-flight commands, stop modules in reverse order, then close the bus."""
        cancelled = self.router.cancel_all()
        if cancelled:
            log.info("Cancelled %d in-flight command(s)", cancelled)
        await self._lifecycle.stop()
        for command_type, handler in self._handlers.items():
            self.router.unregister(command_type, handler)
        await self.bus.close()
        log.info("Stopped")

    def request_shutdown(self) -> None:
        self._stopping.set()

    async def _on_shutdown_requested(self, event: ShutdownRequested) -> None:
        log.info("Shutdown requested%s: %s", " (restart)" if event.restart else "", event.reason or "no reason given")
        self.restart_requested = self.restart_requested or event.restart
        self.request_shutdown()

    async def _list_modules(self, command: ListModules) -> Result:
        return Result.ok(self._lifecycle.modules())

    # Shielded: if the command times out or is cancelled, the transition still
    # finishes cleanly instead of leaving a module half started or half stopped.
    # Its outcome is still announced by ModuleStateChanged.
    async def _activate_module(self, command: ActivateModule) -> Result:
        return await asyncio.shield(self._lifecycle.activate(command.module_id))

    async def _deactivate_module(self, command: DeactivateModule) -> Result:
        return await asyncio.shield(self._lifecycle.deactivate(command.module_id, command.with_dependents))

    async def _reload_module(self, command: ReloadModule) -> Result:
        return await asyncio.shield(
            self._swap(self._lifecycle.reload, command.module_id, command.now, self._reload_idle_timeout)
        )

    async def _add_module(self, command: AddModule) -> Result:
        return await asyncio.shield(self._swap(self._lifecycle.add, command.package, command.activate))

    async def _swap(self, transition, *args) -> Result:
        """Run a code-loading transition with fresh config, holding commands sent to the module meanwhile."""
        if self._config_loader:
            try:
                self._module_config = self._config_loader().get("modules", {})
            except Exception:
                log.exception("Couldn't re-read the config; keeping the one from launch")
        with self.router.hold():
            return await transition(*args)

    def _on_module_state(self, module_id: str, state: ModuleState) -> None:
        self.bus.publish(ModuleStateChanged(module_id=module_id, state=state))

    def _make_context(self, manifest: Manifest, handover: Any = None) -> ScopedContext:
        return ScopedContext(
            manifest,
            self.router,
            self.bus,
            self.container,
            self._module_config.get(manifest.id, {}),
            logging.getLogger(f"assistant.modules.{manifest.id}"),
            handover,
        )
