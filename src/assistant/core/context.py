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
        self._closed = False

    def subscribe(self, event_type, handler) -> None:
        self._check_open()
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
        self._router.register(command_type, handler)
        self._handlers.append((command_type, handler))

    async def send(self, command: Command, timeout: float | None = None) -> Result:
        if self._closed:
            return Result.not_available(f"{self.module_id!r} is not active")
        return await self._router.send(command, timeout)

    def cancel(self, correlation_id: str) -> int:
        return self._router.cancel(correlation_id)

    def provide(self, contract: type[Contract], impl: Contract) -> None:
        self._check_open()
        if contract not in self._manifest.provides:
            raise ValueError(f"{self.module_id!r} must declare {contract.__name__} in manifest.provides")
        self._container.provide(contract, impl, owner=self.module_id)

    def get_all(self, contract):
        return self._container.get_all(contract)

    def get_one(self, contract):
        return self._container.get_one(contract)

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
