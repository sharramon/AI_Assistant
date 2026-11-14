"""The host: wires the core together and runs the enabled modules."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from app_kit import merge
from app_kit.module_docs import DOCS_DIR, doc_pages, page_title
from assistant.contracts import (
    ActivateModule,
    AddModule,
    DeactivateModule,
    GetMenu,
    IAgentNames,
    IModuleDoor,
    InvokeTool,
    ITaskAgent,
    ListModules,
    Manifest,
    ModuleInfo,
    ModuleProtocol,
    ModuleState,
    ModuleStateChanged,
    PermissionMode,
    ReloadModule,
    RemoveModule,
    Result,
    SetPermissionMode,
    ShutdownRequested,
    StartProvider,
    ToolSpec,
)
from assistant.contracts.permissions import AddCardNotes, AnswerPermissionRequest
from assistant.core import loader
from assistant.core.bus import EventBus
from assistant.core.callers import Callers
from assistant.core.container import Container
from assistant.core.context import ScopedContext
from assistant.core.directory import CORE_ID, CoreMenu
from assistant.core.door import CORE_LINE, CoreDoor
from assistant.core.generated import GeneratedFiles
from assistant.core.lifecycle import LifecycleManager
from assistant.core.logs import SessionLogs
from assistant.core.permissions import PermissionsHandler, PermissionsMenu, PermissionsPort
from assistant.core.permissions.handler import YOU
from assistant.core.registry import resolve_modules
from assistant.core.router import CommandRouter
from assistant.core.tools import MenuTable, MenuTools, dispatch_tool
from assistant.infra.config import config_folder, module_config_files
from assistant.infra.mcp_door import DoorServer

log = logging.getLogger(__name__)


class App:
    #: The events the core publishes: module states, and the permissions handler's card events.
    #: A test checks every `publish(X(...))` in the core is named here.
    PUBLISHES = (ModuleStateChanged, *PermissionsHandler.PUBLISHES)

    def __init__(
        self,
        available: Sequence[type[ModuleProtocol]],
        config: dict[str, Any],
        config_loader: Callable[[], dict[str, Any]] | None = None,
        logs: Any = None,
        config_dir: str | Path | None = None,
    ):
        """Validate the enabled modules. Raises StartupError before anything runs.

        `modules.enabled` are active at startup; every other module in `available`
        can be activated at runtime with `ActivateModule`. `config_loader`, if given,
        re-reads the config before `ReloadModule` and `AddModule`, so a reloaded or
        added module gets its current config section. `logs` is the launch's
        `LogSession`; every module reaches it as `ctx.logs`. Without one, `ctx.logs`
        gives plain paths under `logging.dir`. `config_dir` is where your choices files are
        (`config_folder`: else ASSISTANT_CONFIG_DIR, else `./config`); `RemoveModule` purges there, and the permissions
        handler protects it like `config/` (writes refused).
        """
        core = config.get("core", {})
        self._permission_config = core.get("permissions", {})  # `you` and `relays` for the control commands (R2)
        self._config_dir = config_folder(config_dir)
        self.logs = SessionLogs(logs, config.get("logging", {}).get("dir", "logs"))
        self._module_config = config.get("modules", {})
        self._config_loader = config_loader
        self._reload_idle_timeout = core.get("reload_idle_timeout", 300.0)
        self.router = CommandRouter(core.get("command_timeout", 30.0), core.get("command_timeouts", {}))
        self.bus = EventBus(core.get("event_queue_size", 100), core.get("event_handler_timeout", 10.0))
        self.container = Container()
        self.menus = MenuTable()  # the linked menus, core-private (G16): InvokeTool reaches them, nothing else
        self._lifecycle = LifecycleManager(
            available,
            resolve_modules(available, self._module_config.get("enabled", [])),
            self._make_context,
            core.get("module_stop_timeout", 5.0),
            self._on_module_state,
        )
        # The Callers port (D2): agent names, each agent's mode, and who is you, in one list.
        self.callers = Callers(lambda: [m.id for m in self._lifecycle.modules()],
                               you=self._permission_config.get("you", YOU),
                               relays=self._permission_config.get("relays", ()))  # fmt: skip
        # The permissions handler: part of the core, always on (no module or agent turns it off).
        self.permissions = PermissionsHandler.from_config(
            core.get("permissions", {}), self.router.send, self.bus.publish, self.container.get_one,
            mode_of=self.callers.mode, config_dir=self._config_dir,  # protected like config/
        )
        self._handlers = {
            AnswerPermissionRequest: self.permissions.answer,
            AddCardNotes: self.permissions.add_notes,  # a review's notes (D6: the reviewer is a listener)
            SetPermissionMode: self._set_mode,
            InvokeTool: partial(
                dispatch_tool, self.container, self.menus, start_on_use=self._start_for_tool, off_owner=self._off_owner,
                # The one ask-first gate: items marked `ask` show a confirm card (Auto never skips "always").
                confirm=lambda caller, what, run, risky: self.permissions.confirm(CORE_ID, caller, what, run, risky=risky),
            ),
            ListModules: self._list_modules,
            GetMenu: self._get_menu,
            ActivateModule: self._activate_module,
            StartProvider: self._start_provider,
            DeactivateModule: self._deactivate_module,
            ReloadModule: self._reload_module,
            AddModule: self._add_module,
            RemoveModule: self._remove_module,
            ShutdownRequested: self._on_shutdown_requested,  # a command (D5): only senders that declare it
        }
        # The core's own menu (module control), offered through InvokeTool under the id "core".
        self.core_menu = CoreMenu(self.router.send, PermissionsPort(CORE_ID, self.permissions), self._module_docs)
        self.core_menu_tools = MenuTools(CoreMenu.menu, self.core_menu)
        # The grant calls (permissions.*), on the same "core" menu.
        self.permissions_menu_tools = MenuTools(PermissionsMenu.menu, PermissionsMenu(self.permissions))
        # The agents' module door (D1), hosted by the core: `[core.door]` enabled, host, port (0: any free).
        door = core.get("door", {})
        self._door_on = bool(door.get("enabled", True))
        self.door = CoreDoor(
            DoorServer(self.router.send, {"list": ListModules, "menu": GetMenu, "call": InvokeTool},
                       host=door.get("host", "127.0.0.1"), port=int(door.get("port", 0)), core_line=CORE_LINE),
            lambda: self.callers.claims,
        )  # fmt: skip
        # The contracts the core provides itself (owner "core"), given to the container at start.
        self._provides = {IAgentNames: self.callers, IModuleDoor: self.door}
        # generated/: the live module list, directory and dependencies, written at start and on every change.
        self.generated = GeneratedFiles.from_config(core.get("generated_dir"), self._lifecycle, self.core_specs)
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
        self.menus.add(self.core_menu_tools)
        self.menus.add(self.permissions_menu_tools)
        for contract, provider in self._provides.items():
            self.container.provide(contract, provider, owner=CORE_ID)
        if self._door_on:  # before any module, so every agent's first session has the door
            try:
                await self.door.server.start()
                log.info("The agents' module door is at %s", self.door.server.url)
            except OSError as exc:  # its port is taken: the agents just go without the door
                log.warning("Couldn't open the agents' module door: %s", exc)
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
        await self.door.server.stop()
        for command_type, handler in self._handlers.items():
            self.router.unregister(command_type, handler)
        self.container.remove_owner(CORE_ID)
        self.menus.remove(self.core_menu_tools)
        self.menus.remove(self.permissions_menu_tools)
        await self.bus.close()
        log.info("Stopped")

    def request_shutdown(self) -> None:
        self._stopping.set()

    async def _on_shutdown_requested(self, command: ShutdownRequested) -> Result:
        log.info("Shutdown requested by %s%s: %s", command.sent_by or "core", " (restart)" if command.restart else "",
                 command.reason or "no reason given")  # fmt: skip
        self.restart_requested = self.restart_requested or command.restart
        self.request_shutdown()
        return Result.ok("Shutting down" + (" to restart" if command.restart else ""))

    async def _set_mode(self, command: SetPermissionMode) -> Result:
        """`SetPermissionMode` (D2): Auto only from you (the stamped sender); Manual from anyone.
        The Callers port records the mode first, so the agent's own check lets Auto in; a refusal
        puts the old mode back. The agent publishes `PermissionModeChanged`."""
        mode = PermissionMode(command.mode)
        if mode is PermissionMode.AUTO and not self.callers.may_set_auto(command.sent_by):
            log.warning("%s asked to switch %s to Auto: refused", command.sent_by, command.agent_id)
            return Result.not_available("Only the user switches an agent to Auto, with the app's button")
        agent = next((a for a in self.container.get_all(ITaskAgent) if a.info().agent_id == command.agent_id), None)
        if agent is None:
            return Result.invalid_arguments(f"No agent {command.agent_id!r}")
        previous = self.callers.mode(command.agent_id)
        self.callers.set_mode(command.agent_id, mode)
        result = await agent.set_permission_mode(mode)
        if not result.is_ok:
            self.callers.set_mode(command.agent_id, previous)
        return result

    async def _list_modules(self, command: ListModules) -> Result:
        return Result.ok(self._lifecycle.modules())

    async def _get_menu(self, command: GetMenu) -> Result:
        if command.module_id == CORE_ID:
            return Result.ok(self.core_specs())
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

        return await self._start_on_use(lambda info: self._has_tool(info.id, name), name)

    def _has_tool(self, module_id: str, name: str) -> bool:
        menu = self._lifecycle.menu(module_id)
        return menu is not None and any(spec.name == name for spec in menu.specs())

    def _off_owner(self, name: str) -> str | None:
        """The module that is off and has tool `name` on its menu, for the "isn't on" answer."""
        for info in self._lifecycle.modules():
            if info.state is not ModuleState.ACTIVE and self._has_tool(info.id, name):
                return info.id
        return None

    async def _start_provider(self, command: StartProvider) -> Result:
        """`StartProvider`: start on use by contract, for a caller that names no module."""
        started = await self._start_on_use(lambda info: command.contract in info.provides, command.contract)
        return started or Result.not_available(f"No module that provides {command.contract} is off and starts on use")

    async def _start_on_use(self, offers: Callable[[ModuleInfo], bool], what: str) -> Result | None:
        """Turn on the first module that is off, `offers` what's asked for, and allows start on use."""
        for info in self._lifecycle.modules():
            if info.state is ModuleState.ACTIVE or not self._config_of(info.id).get("start_on_use"):
                continue
            if not offers(info):
                continue
            log.info("Starting %s on use (%s)", info.id, what)
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

    async def _remove_module(self, command: RemoveModule) -> Result:
        return await asyncio.shield(self._remove(command.module_id, command.purge))

    async def _remove(self, module_id: str, purge: bool) -> Result:
        """`RemoveModule`: out of this run (never refused; the modules that need it stay on), then its
        settings purged or kept. Never touches its folder or `config/modules.toml`; the result says
        what's left to you."""
        self._refresh_config()
        enabled = list(self._module_config.get("enabled", []))
        try:
            folder = loader.module_folder(self._lifecycle.module_class(module_id))
        except KeyError:
            return Result.invalid_arguments(f"No module called {module_id!r}")
        result = await self._lifecycle.remove(module_id)
        if not result.is_ok:
            return result
        still_on = list(result.value or ())
        if self._started:
            self.generated.write()

        files = [p for p in module_config_files(self._config_dir, module_id) if p.is_file()]
        deleted, kept = [], []
        for path in files:
            if purge:
                try:
                    path.unlink()
                    deleted.append(str(path))
                except OSError as exc:
                    log.error("Couldn't delete %s: %s", path, exc)
                    kept.append(str(path))
            else:
                kept.append(str(path))
        lines = [f"Removed {module_id} from this run; modules.add brings it back."]
        if still_on:
            lines.append(f"Still on, and needing it: {', '.join(still_on)}.")
        if deleted:
            lines.append(f"Deleted its settings: {', '.join(deleted)}.")
        if kept:
            lines.append(f"Kept its settings: {', '.join(kept)}.")
        if not files:
            lines.append("It had no settings files in config/.")
        if module_id in enabled:
            lines.append("It's still in config/modules.toml's enabled list: take it out yourself, "
                         "or it starts again at the next launch.")
        lines.append(f"Its folder is yours to delete: {folder}." if folder else "It has no module folder.")
        return Result.ok({
            "module_id": module_id,
            "still_on": still_on,
            "deleted": deleted,
            "kept": kept,
            "folder": str(folder) if folder else None,
            "enabled": module_id in enabled,
            "message": " ".join(lines),
        })

    async def _swap(self, transition, *args) -> Result:
        """Run a code-loading transition with fresh config, holding commands sent to the module meanwhile."""
        self._refresh_config()
        with self.router.hold():
            return await transition(*args)

    def _refresh_config(self) -> None:
        """Re-read the config (when there's a loader), so a change since launch counts."""
        if self._config_loader:
            try:
                self._module_config = self._config_loader().get("modules", {})
            except Exception:
                log.exception("Couldn't re-read the config; keeping the one from launch")

    def _on_module_state(self, module_id: str, state: ModuleState) -> None:
        self.bus.publish(ModuleStateChanged(module_id=module_id, state=state))
        if self._started:
            self.generated.write()

    @staticmethod
    def core_specs() -> list[ToolSpec]:
        """The core's own menu: module control (`modules.*`) and the grant calls (`permissions.*`)."""
        return CoreMenu.menu.specs() + PermissionsMenu.menu.specs()

    def offers(self) -> dict[str, list[str]]:
        """What the core itself offers, by name, read from the tables `start` registers (not a
        second list): `handles` (its commands), `provides` (its contracts), `menu` (the `core`
        menu `GetMenu` answers) and `publishes` (`PUBLISHES`). The module library's core row is
        generated from it."""
        return {
            "handles": [c.__name__ for c in self._handlers],
            "provides": [c.__name__ for c in self._provides],
            "menu": [s.name for s in self.core_specs()],
            "publishes": [e.__name__ for e in self.PUBLISHES],
        }

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
            you=self.callers.you,
            relays=self.callers.relays,
            menus=self.menus,
        )
