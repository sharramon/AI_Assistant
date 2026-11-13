"""The host: wires the core together and runs the enabled modules."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

from app_kit import merge
from app_kit.module_docs import DOCS_DIR, doc_pages, page_title
from assistant.contracts import (
    ActivateModule,
    AddModule,
    DeactivateModule,
    GetMenu,
    InvokeTool,
    IToolProvider,
    ListModules,
    Manifest,
    ModuleProtocol,
    ModuleState,
    ModuleStateChanged,
    ReloadModule,
    Result,
    ShutdownRequested,
    TaskUpdated,
    ToolSpec,
)
from assistant.contracts.permissions import AnswerPermissionRequest
from assistant.core import loader
from assistant.core.bus import EventBus
from assistant.core.container import Container
from assistant.core.context import ScopedContext
from assistant.core.directory import CORE_ID, CoreMenu
from assistant.core.generated import GeneratedFiles
from assistant.core.lifecycle import LifecycleManager
from assistant.core.logs import SessionLogs
from assistant.core.permissions import PermissionsHandler, PermissionsMenu, PermissionsPort
from assistant.core.registry import resolve_modules
from assistant.core.router import CommandRouter
from assistant.core.tools import MenuTools, dispatch_tool

log = logging.getLogger(__name__)


class App:
    def __init__(
        self,
        available: Sequence[type[ModuleProtocol]],
        config: dict[str, Any],
        config_loader: Callable[[], dict[str, Any]] | None = None,
        logs: Any = None,
    ):
        """Validate the enabled modules. Raises StartupError before anything runs.

        `modules.enabled` are active at startup; every other module in `available`
        can be activated at runtime with `ActivateModule`. `config_loader`, if given,
        re-reads the config before `ReloadModule` and `AddModule`, so a reloaded or
        added module gets its current config section. `logs` is the launch's
        `LogSession`; every module reaches it as `ctx.logs`. Without one, `ctx.logs`
        gives plain paths under `logging.dir`.
        """
        core = config.get("core", {})
        self.logs = SessionLogs(logs, config.get("logging", {}).get("dir", "logs"))
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
        # The permissions handler: part of the core, always on (no module or agent turns it off).
        self.permissions = PermissionsHandler.from_config(
            core.get("permissions", {}), self.router.send, self.bus.publish, self.container.get_one
        )
        self._handlers = {
            AnswerPermissionRequest: self.permissions.answer,
            InvokeTool: partial(dispatch_tool, self.container, start_on_use=self._start_for_tool),
            ListModules: self._list_modules,
            GetMenu: self._get_menu,
            ActivateModule: self._activate_module,
            DeactivateModule: self._deactivate_module,
            ReloadModule: self._reload_module,
            AddModule: self._add_module,
        }
        # The core's own menu (module control), offered through InvokeTool under the id "core".
        self.core_menu = CoreMenu(self.router.send, PermissionsPort(CORE_ID, self.permissions), self._module_docs)
        self.core_menu_tools = MenuTools(CoreMenu.menu, self.core_menu)
        # The grant calls (permissions.*), on the same "core" menu.
        self.permissions_menu_tools = MenuTools(PermissionsMenu.menu, PermissionsMenu(self.permissions))
        # generated/: the live module list, directory and dependencies, written at start and on every change.
        self.generated = GeneratedFiles.from_config(core.get("generated_dir"), self._lifecycle, self._core_specs)
        self._started = False
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
        self.container.provide(IToolProvider, self.core_menu_tools, owner=CORE_ID)
        self.container.provide(IToolProvider, self.permissions_menu_tools, owner=CORE_ID)
        self.bus.subscribe(ShutdownRequested, self._on_shutdown_requested)
        self.bus.subscribe(TaskUpdated, self.permissions.on_task_updated, owner=CORE_ID)
        await self._lifecycle.start()
        self._started = True  # from here every state change rewrites generated/ (not once per startup step)
        self.generated.write()

    async def stop(self) -> None:
        """Cancel in-flight commands, stop modules in reverse order, then close the bus."""
        cancelled = self.router.cancel_all()
        if cancelled:
            log.info("Cancelled %d in-flight command(s)", cancelled)
        await self.permissions.close()
        await self._lifecycle.stop()
        for command_type, handler in self._handlers.items():
            self.router.unregister(command_type, handler)
        self.container.remove_owner(CORE_ID)
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

    async def _get_menu(self, command: GetMenu) -> Result:
        if command.module_id == CORE_ID:
            return Result.ok(self._core_specs())
        try:
            menu = self._lifecycle.menu(command.module_id)
        except KeyError:
            return Result.invalid_arguments(f"No module called {command.module_id!r}")
        return Result.ok(menu.specs() if menu else [])

    # Shielded: if the command times out or is cancelled, the transition still
    # finishes cleanly instead of leaving a module half started or half stopped.
    # Its outcome is still announced by ModuleStateChanged.
    async def _activate_module(self, command: ActivateModule) -> Result:
        return await asyncio.shield(self._lifecycle.activate(command.module_id))

    async def _start_for_tool(self, name: str) -> Result | None:
        """Start on use: turn on the module that is off, has tool `name` on its menu, and has
        `start_on_use = true` in its `[modules.<id>]` config, the same way as `ActivateModule`.
        None when no module qualifies. Several calls at once start it once (the lifecycle's
        lock queues them; the later ones find it on). A module you turned off starts too."""
        for info in self._lifecycle.modules():
            if info.state is ModuleState.ACTIVE or not self._config_of(info.id).get("start_on_use"):
                continue
            menu = self._lifecycle.menu(info.id)
            if menu is None or not any(spec.name == name for spec in menu.specs()):
                continue
            log.info("Starting %s on use (%s)", info.id, name)
            result = await asyncio.shield(self._lifecycle.activate(info.id))
            if not result.is_ok:
                return Result.failed(f"The {info.id} module couldn't start: {result.error}", retryable=True)
            return result
        return None

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
        if self._started:
            self.generated.write()

    @staticmethod
    def _core_specs() -> list[ToolSpec]:
        """The core's own menu: module control (`modules.*`) and the grant calls (`permissions.*`)."""
        return CoreMenu.menu.specs() + PermissionsMenu.menu.specs()

    def _config_of(self, module_id: str) -> dict[str, Any]:
        """A module's config: its own defaults (`module.toml` in its folder) with its `[modules.<id>]`
        section from the app's config merged over them."""
        section = self._module_config.get(module_id, {})
        try:
            cls = self._lifecycle.module_class(module_id)
        except KeyError:
            return section
        return merge(loader.module_defaults(cls), section)

    async def _module_docs(self, module_id: str) -> Result:
        """`modules.docs`: the module's own docs pages (title and path), read from its folder."""
        try:
            cls = self._lifecycle.module_class(module_id)
        except KeyError:
            return Result.invalid_arguments(f"No module called {module_id!r}")
        folder = loader.module_folder(cls)
        pages = doc_pages(folder / DOCS_DIR) if folder else []
        return Result.ok([{"title": page_title(p), "path": str(p)} for p in pages])

    def _make_context(self, manifest: Manifest, handover: Any = None) -> ScopedContext:
        return ScopedContext(
            manifest,
            self.router,
            self.bus,
            self.container,
            self._config_of(manifest.id),
            logging.getLogger(f"assistant.modules.{manifest.id}"),
            handover,
            self.logs,
            PermissionsPort(manifest.id, self.permissions),
        )
