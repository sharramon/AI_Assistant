"""The per-module context: scopes every registration to its module so stop can undo it."""

from __future__ import annotations

from logging import Logger
from typing import Any

from assistant.contracts import Command, Contract, Event, Manifest, ModuleContext, Result
from assistant.core.bus import EventBus, Subscription
from assistant.core.container import Container
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
    ):
        self.module_id = manifest.id
        self.config = config
        self.log = log
        self._manifest = manifest
        self._router = router
        self._bus = bus
        self._container = container
        self._subscriptions: list[Subscription] = []
        self._handlers: list[tuple[type[Command], CommandHandler]] = []

    def subscribe(self, event_type, handler) -> None:
        self._subscriptions.append(self._bus.subscribe(event_type, handler, owner=self.module_id))

    def publish(self, event: Event) -> None:
        self._bus.publish(event)

    def handle(self, command_type, handler) -> None:
        self._router.register(command_type, handler)
        self._handlers.append((command_type, handler))

    async def send(self, command: Command, timeout: float | None = None) -> Result:
        return await self._router.send(command, timeout)

    def cancel(self, correlation_id: str) -> int:
        return self._router.cancel(correlation_id)

    def provide(self, contract: type[Contract], impl: Contract) -> None:
        if contract not in self._manifest.provides:
            raise ValueError(f"{self.module_id!r} must declare {contract.__name__} in manifest.provides")
        self._container.provide(contract, impl, owner=self.module_id)

    def get_all(self, contract):
        return self._container.get_all(contract)

    def get_one(self, contract):
        return self._container.get_one(contract)

    def close(self) -> None:
        """Remove everything this module registered."""
        for sub in self._subscriptions:
            self._bus.unsubscribe(sub)
        for command_type, handler in self._handlers:
            self._router.unregister(command_type, handler)
        self._container.remove_owner(self.module_id)
        self._subscriptions.clear()
        self._handlers.clear()
