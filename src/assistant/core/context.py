"""The per-module context: scopes every registration to its module so stop can undo it."""

from __future__ import annotations

from logging import Logger
from typing import Any

from assistant.contracts import (
    Command,
    Contract,
    Event,
    IModuleDoor,
    InvokeTool,
    IToolProvider,
    Manifest,
    ModuleContext,
    ModuleLogs,
    ModulePermissions,
    Result,
)
from assistant.core.bus import EventBus, Subscription
from assistant.core.container import Container
from assistant.core.logs import SessionLogs
from assistant.core.permissions import PermissionsPort
from assistant.core.router import CommandHandler, CommandRouter


class ScopedContext(ModuleContext):
    def __init__(
        self,
        manifest: Manifest,
        router: CommandRouter,
        bus: EventBus,
        container: Container,
        config: dict[str, Any],
        log: Logger,
        handover: Any = None,
        logs: ModuleLogs | None = None,
        permissions: ModulePermissions | None = None,
    ):
        self.module_id = manifest.id
        self.config = config
        self.log = log
        self.handover = handover
        self.permissions = permissions or PermissionsPort(manifest.id)
        self.logs = logs or SessionLogs()
        self._manifest = manifest
        self._router = router
        self._bus = bus
        self._container = container
        self._subscriptions: list[Subscription] = []
        self._handlers: list[tuple[type[Command], CommandHandler]] = []
        self._closed = False
        m = manifest
        self._contracts = frozenset((*m.provides, *m.requires, *m.optional, *m.uses))
        self._undeclared: set[type] = set()  # logged once each

    def subscribe(self, event_type, handler) -> None:
        self._check_open()
        self._check_declared(event_type, self._manifest.listens, "listens")
        self._subscriptions.append(self._bus.subscribe(event_type, handler, owner=self.module_id))

    def publish(self, event: Event) -> None:
        # Dropped after close, so leftovers of a deactivated module (a thread, a
        # late callback) can't keep talking to the app.
        if self._closed:
            self.log.debug("Dropped %s published after %s stopped", type(event).__name__, self.module_id)
            return
        self._bus.publish(event)

    def handle(self, command_type, handler) -> None:
        self._check_open()
        if command_type not in self._manifest.handles:
            # Strict since module system chunk 9: a module's inputs are what its manifest says.
            raise ValueError(f"{self.module_id!r} must list {command_type.__name__} in manifest.handles")
        self._router.register(command_type, handler)
        self._handlers.append((command_type, handler))

    async def send(self, command: Command, timeout: float | None = None) -> Result:
        if self._closed:
            return Result.not_available(f"{self.module_id!r} is not active")
        if isinstance(command, InvokeTool) and not (command.caller and IModuleDoor in self._manifest.provides):
            # The caller is the sender; only the door's host passes on the one its token proved.
            command = command.model_copy(update={"caller": self.module_id})
        return await self._router.send(command, timeout)

    def cancel(self, correlation_id: str) -> int:
        return self._router.cancel(correlation_id)

    def provide(self, contract: type[Contract], impl: Contract) -> None:
        self._check_open()
        if contract not in self._manifest.provides:
            raise ValueError(f"{self.module_id!r} must declare {contract.__name__} in manifest.provides")
        self._container.provide(contract, impl, owner=self.module_id)

    def withdraw(self, contract: type[Contract], impl: Contract) -> None:
        if not self._closed:
            self._container.remove(contract, impl, owner=self.module_id)

    def link_menu(self, module: Any) -> None:
        """Core only: offer `module`'s menu through `InvokeTool`, in its name, until close."""
        self._check_open()
        menu = type(module).menu
        if menu is not None and menu.names():
            from assistant.core.tools import MenuTools  # core.tools imports nothing from here

            self._container.provide(IToolProvider, MenuTools(menu, module), owner=self.module_id)

    def get_all(self, contract):
        self._check_declared(contract, self._contracts, "requires / optional / uses")
        return self._container.get_all(contract)

    def get_one(self, contract):
        self._check_declared(contract, self._contracts, "requires / optional / uses")
        return self._container.get_one(contract)

    def _check_declared(self, kind: type, declared, field: str) -> None:
        """Principle 17: a module's manifest declares everything it uses. An undeclared
        subscription or lookup still works; it's logged once, so the manifest gets fixed."""
        if kind in declared or kind in self._undeclared:
            return
        self._undeclared.add(kind)
        self.log.warning("%s uses %s without declaring it in its manifest (%s)", self.module_id, kind.__name__, field)

    def close(self) -> None:
        """Remove everything this module registered. Afterwards publish is dropped and send is refused."""
        self._closed = True
        for sub in self._subscriptions:
            self._bus.unsubscribe(sub)
        for command_type, handler in self._handlers:
            self._router.unregister(command_type, handler)
        self._container.remove_owner(self.module_id)
        self._subscriptions.clear()
        self._handlers.clear()

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError(f"{self.module_id!r} has stopped; its context is closed")
