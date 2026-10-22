"""The module lifecycle contract and the context the core hands to each module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from logging import Logger
from typing import Any, ClassVar, TypeVar

from assistant.contracts.messages import Command, Event, Result


class Contract(ABC):
    """Base for capability interfaces that modules provide and resolve through DI.

    Only subclasses defined under `assistant.contracts` are accepted, so modules
    can never resolve each other's concrete types.
    """

    #: Whether more than one module may provide this contract at once.
    multiple: ClassVar[bool] = False


C = TypeVar("C", bound=Contract)
E = TypeVar("E", bound=Event)
K = TypeVar("K", bound=Command)


@dataclass(frozen=True)
class Manifest:
    """What a module is and which contracts it provides and depends on."""

    id: str
    provides: tuple[type[Contract], ...] = ()
    requires: tuple[type[Contract], ...] = ()
    optional: tuple[type[Contract], ...] = ()


class ModuleContext(ABC):
    """A module's only access to the rest of the app.

    Everything registered through it (subscriptions, command handlers, provided
    contracts) is removed automatically when the module stops.
    """

    module_id: str
    config: dict[str, Any]
    log: Logger

    @abstractmethod
    def subscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        """Receive every published event that is an instance of `event_type`."""

    @abstractmethod
    def publish(self, event: Event) -> None:
        """Publish an event. Returns immediately; never waits on subscribers."""

    @abstractmethod
    def handle(self, command_type: type[K], handler: Callable[[K], Awaitable[Result]]) -> None:
        """Become the single handler for `command_type`."""

    @abstractmethod
    async def send(self, command: Command, timeout: float | None = None) -> Result:
        """Send a command to its handler and wait for the result."""

    @abstractmethod
    def cancel(self, correlation_id: str) -> int:
        """Cancel in-flight commands whose id or correlation id matches. Returns how many."""

    @abstractmethod
    def provide(self, contract: type[C], impl: C) -> None:
        """Offer `impl` as a provider of `contract`. Must be declared in `manifest.provides`."""

    @abstractmethod
    def get_all(self, contract: type[C]) -> list[C]:
        """All current providers of `contract`, possibly none."""

    @abstractmethod
    def get_one(self, contract: type[C]) -> C | None:
        """The provider of a single-provider `contract`, or None."""


class Module(ABC):
    """Base class for every module.

    The core calls `init` (in dependency order), then `start`, and on shutdown
    `stop` in reverse order. `stop` is called for every module whose `init`
    succeeded, even if `start` never ran.

    Modules can also be activated and deactivated while the app runs. Each
    activation creates a fresh instance, so `stop` must release everything the
    module started (processes, threads, windows, devices), and in-memory state
    doesn't survive deactivation. Load expensive resources in `start` or on
    first use, not at import.
    """

    manifest: ClassVar[Manifest]

    @abstractmethod
    async def init(self, ctx: ModuleContext) -> None:
        """Subscribe, register handlers, and provide contracts. Don't start work yet."""

    async def start(self) -> None:
        """Begin active work (listening for input, background loops)."""

    async def stop(self) -> None:
        """Stop work and release resources."""
