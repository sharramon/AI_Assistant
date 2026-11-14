"""The per-module context: scopes every registration to its module so stop can undo it."""

from __future__ import annotations

import json
from collections.abc import Iterable
from logging import Logger
from typing import Any

from assistant.contracts import (
    AddModule,
    AnswerPermission,
    AnswerPermissionRequest,
    Command,
    Contract,
    DeactivateModule,
    Event,
    InvokeTool,
    ITaskAgent,
    Manifest,
    ModuleContext,
    ModuleEvent,
    ModuleLogs,
    ModulePermissions,
    ReloadModule,
    RemoveModule,
    Result,
    SubscriptionHandle,
    event_name_ok,
)
from assistant.core.bus import EventBus, Subscription
from assistant.core.container import Container
from assistant.core.door import CoreDoor
from assistant.core.logs import SessionLogs
from assistant.core.permissions import PermissionsPort
from assistant.core.router import CommandHandler, CommandRouter
from assistant.core.tools import MenuTable, MenuTools

RELAY = "relay"  # a module relaying your answer to a card (`[core.permissions] relays`: the Talker's ALLOW / DENY)
AGENT = "agent"  # a task agent's module, sending the step you allowed on its own card (RELOAD: / ADD_MODULE:)

#: The control commands (decision D3): only the core and a `you` caller (`[core.permissions] you`)
#: send them, plus the others each one names. Auto is never set by anyone but you (G17).
#: `ActivateModule` isn't one: a module's own access card guards its start (job_search turns cv on).
#: `CancelTask` isn't either: it goes through the Hub's menu, which checks the caller.
#: `SetPermissionMode` isn't either (R3): its handler, the core's, lets Auto in only from you, and
#: Manual from anyone (the Talker's `hub.mode`).
CONTROL: dict[type[Command], frozenset[str]] = {
    DeactivateModule: frozenset(),
    RemoveModule: frozenset(),
    AnswerPermission: frozenset({RELAY}),
    AnswerPermissionRequest: frozenset({RELAY}),
    ReloadModule: frozenset({AGENT}),
    AddModule: frozenset({AGENT}),
}


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
        you: Iterable[str] = (),
        relays: Iterable[str] = (),
        menus: MenuTable | None = None,
    ):
        self._menus = menus if menus is not None else MenuTable()
        self._linked: list[MenuTools] = []
        self._you = frozenset(you)
        self._relays = frozenset(relays)
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
        self._subscriptions: dict[SubscriptionHandle, Subscription] = {}  # insertion order
        self._handlers: list[tuple[type[Command], CommandHandler]] = []
        self._closed = False
        m = manifest
        self._contracts = frozenset((*m.provides, *m.requires, *m.optional, *m.uses))
        self._undeclared: set[type | str] = set()  # logged once each

    def subscribe(self, event_type, handler) -> SubscriptionHandle:
        self._check_open()
        self._check_declared(event_type, self._manifest.listens, "listens")
        return self._keep(self._bus.subscribe(event_type, handler, owner=self.module_id), event_type.__name__)

    def publish_named(self, name: str, data=None) -> None:
        if not (event_name_ok(name) and name.startswith(f"{self.module_id}.")):
            raise ValueError(f"{self.module_id!r} may publish only '{self.module_id}.<what>' named events, "
                             f"got {name!r}")  # fmt: skip
        try:  # a JSON copy: plain values only, and the listener never shares the publisher's objects
            plain = json.loads(json.dumps(dict(data or {}), allow_nan=False))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name}: data must be plain JSON values ({error})") from None
        self._check_declared(name, self._manifest.publishes_named, "publishes_named")
        self._publish(ModuleEvent(name=name, source=self.module_id, data=plain))

    def subscribe_named(self, name: str, handler) -> SubscriptionHandle:
        self._check_open()
        if not event_name_ok(name, pattern=True):
            raise ValueError(f"Not an event name: {name!r} ('<module>.<what>' or '<module>.*')")
        declared = self._manifest.listens_named
        if not (name in declared or any(d.endswith(".*") and name.startswith(d[:-1]) for d in declared)):
            self._check_declared(name, declared, "listens_named")
        prefix = name[:-1] if name.endswith(".*") else None  # "cv." for "cv.*"

        async def only_named(event: ModuleEvent) -> None:
            if event.name == name or (prefix is not None and event.name.startswith(prefix)):
                await handler(event)

        return self._keep(self._bus.subscribe(ModuleEvent, only_named, owner=self.module_id), name)

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        sub = self._subscriptions.pop(handle, None)
        if sub is not None:
            self._bus.unsubscribe(sub)

    def _keep(self, sub: Subscription, what: str) -> SubscriptionHandle:
        handle = SubscriptionHandle(what)
        self._subscriptions[handle] = sub
        return handle

    def publish(self, event: Event) -> None:
        """Strict (R2): an event type the manifest's `publishes` doesn't list is dropped and logged as
        an error. A `ModuleEvent` only through `publish_named`, which stamps its source (G15)."""
        if isinstance(event, ModuleEvent):
            raise ValueError(f"{self.module_id!r}: publish a named event with ctx.publish_named, not a ModuleEvent")
        if not isinstance(event, self._manifest.publishes):
            self.log.error("%s published %s, which its manifest.publishes doesn't list: dropped",
                           self.module_id, type(event).__name__)  # fmt: skip
            return
        self._publish(event)

    def _publish(self, event: Event) -> None:
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
        """Strict (R2): the command's type must be in the manifest's `sends`, a control command
        (`CONTROL`) must come from a caller allowed to send it, and the sender is stamped (`sent_by`)."""
        if self._closed:
            return Result.not_available(f"{self.module_id!r} is not active")
        kind = type(command).__name__
        if not isinstance(command, self._manifest.sends):
            self.log.error("%s sent %s, which its manifest.sends doesn't list: refused", self.module_id, kind)
            return Result.invalid_arguments(f"{self.module_id!r} must list {kind} in manifest.sends")
        if not self._may_send(type(command)):
            self.log.warning("%s sent the control command %s: refused (only you may)", self.module_id, kind)
            return Result.failed(f"{kind} is a control command: only you (a UI of yours) may send it, "
                                 f"not {self.module_id!r}")  # fmt: skip
        update: dict[str, Any] = {"sent_by": self.module_id}
        if isinstance(command, InvokeTool):
            # The caller is always the sender (R4): only the core's door passes on the one its token proved.
            update["caller"] = self.module_id
        return await self._router.send(command.model_copy(update=update), timeout)

    def _may_send(self, command_type: type[Command]) -> bool:
        """Whether this module may send `command_type` (`CONTROL`)."""
        others = CONTROL.get(command_type)
        return (others is None or self.module_id in self._you
                or (RELAY in others and self.module_id in self._relays)
                or (AGENT in others and ITaskAgent in self._manifest.provides))  # fmt: skip

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
        """Core only: offer `module`'s menu through `InvokeTool` (the core's menu table, never the
        container: G16), until close."""
        self._check_open()
        menu = type(module).menu
        if menu is not None and menu.names():
            tools = MenuTools(menu, module)
            self._menus.add(tools)
            self._linked.append(tools)

    def get_all(self, contract):
        self._check_declared(contract, self._contracts, "requires / optional / uses")
        return [self._scoped(impl) for impl in self._container.get_all(contract)]

    def get_one(self, contract):
        self._check_declared(contract, self._contracts, "requires / optional / uses")
        return self._scoped(self._container.get_one(contract))

    def _scoped(self, impl):
        """The core's door, as this module may use it: only for itself and the agents it claimed (D1)."""
        return impl.for_module(self.module_id) if isinstance(impl, CoreDoor) else impl

    def _check_declared(self, kind: type | str, declared, field: str) -> None:
        """Principle 17: a module's manifest declares everything it uses. An undeclared
        subscription, lookup or named event still works; it's logged once, so the manifest gets fixed."""
        if kind in declared or kind in self._undeclared:
            return
        self._undeclared.add(kind)
        self.log.warning("%s uses %s without declaring it in its manifest (%s)", self.module_id,
                         getattr(kind, "__name__", kind), field)  # fmt: skip

    def close(self) -> None:
        """Remove everything this module registered. Afterwards publish is dropped and send is refused."""
        self._closed = True
        for sub in self._subscriptions.values():
            self._bus.unsubscribe(sub)
        for command_type, handler in self._handlers:
            self._router.unregister(command_type, handler)
        self._container.remove_owner(self.module_id)
        for tools in self._linked:
            self._menus.remove(tools)
        self._linked.clear()
        self._subscriptions.clear()
        self._handlers.clear()

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError(f"{self.module_id!r} has stopped; its context is closed")
