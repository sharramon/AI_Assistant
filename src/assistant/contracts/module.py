"""The module lifecycle contract and the context the core hands to each module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from logging import Logger
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from assistant.contracts.messages import Command, Event, Result

if TYPE_CHECKING:
    from assistant.contracts.menu import Menu


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
    """Who a module is, what it needs, and its inputs and outputs.

    Plain data on the class, readable without starting the module: the core uses it
    for the dependency graph, the module directory and the generated module library.
    """

    id: str
    provides: tuple[type[Contract], ...] = ()
    requires: tuple[type[Contract], ...] = ()
    optional: tuple[type[Contract], ...] = ()
    #: Permission names the module can't run without (checked once a permissions handler exists).
    permissions: tuple[str, ...] = ()
    #: Permissions asked for in the moment; without them a feature is off.
    optional_permissions: tuple[str, ...] = ()
    #: One line saying what the module does, for the directory and the module library.
    description: str = ""
    #: Commands this module handles (`ctx.handle`). Commands in.
    handles: tuple[type[Command], ...] = ()
    #: Commands this module sends to other modules or the core. Commands out.
    sends: tuple[type[Command], ...] = ()
    #: Events this module publishes. Events out.
    publishes: tuple[type[Event], ...] = ()
    #: Events this module subscribes to. Events in.
    listens: tuple[type[Event], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.isidentifier():
            raise ValueError(f"manifest id must be a Python identifier, got {self.id!r}")
        if not isinstance(self.description, str) or "\n" in self.description:
            raise ValueError(f"{self.id}: description must be one line of text")
        for field, base in (("handles", Command), ("sends", Command), ("publishes", Event), ("listens", Event)):
            for item in getattr(self, field):
                if not (isinstance(item, type) and issubclass(item, base)):
                    raise TypeError(f"{self.id}: manifest.{field} takes {base.__name__} types, got {item!r}")


class ModulePermissions(ABC):
    """One module's permission checks, reached as `ctx.permissions`.

    The core binds it to the calling module, so a module never passes its own id
    and can't ask in another module's name.
    """

    @abstractmethod
    def has(self, name: str) -> bool:
        """Whether this module may use `name` now, without asking."""

    @abstractmethod
    async def request(self, name: str, reason: str = "") -> bool:
        """Ask for `name` in the moment; `reason` is shown to the user. True if allowed."""


class ModuleContext(ABC):
    """A module's only access to the rest of the app.

    Everything registered through it (subscriptions, command handlers, provided
    contracts) is removed automatically when the module stops.
    """

    module_id: str
    config: dict[str, Any]
    log: Logger
    permissions: ModulePermissions
    #: What the previous instance's `export_state()` returned, when this one replaces it in a
    #: reload; None on a normal start. Take it in `init`.
    handover: Any = None

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


class ModuleProtocol(ABC):
    """The one interface every module implements.

    A protocol, not a `Contract`: a class is a module by having these members, and
    nobody looks a module up through the container. It carries no behaviour; a
    module gets its behaviour from the parts it owns (principle 12). Subclass it to
    get the do-nothing defaults for the optional hooks.

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
    #: The actions others may call (a `Menu` part), or None. The core links it to the running
    #: copy and offers its items through `InvokeTool`; the module never provides it itself.
    menu: ClassVar[Menu | None] = None

    @abstractmethod
    async def init(self, ctx: ModuleContext) -> None:
        """Subscribe, register handlers, and provide contracts. Don't start work yet."""

    async def start(self) -> None:
        """Begin active work (listening for input, background loops)."""

    async def stop(self) -> None:
        """Stop work and release resources."""

    def busy(self) -> str | None:
        """Why this module shouldn't have its code swapped right now (e.g. "replying to you"),
        or None. A `ReloadModule` waits until it's None, unless it says `now`."""
        return None

    def export_state(self) -> Any:
        """Called before a reload stops this instance. What it returns reaches the new
        instance as `ctx.handover`. Return plain data, or objects from `assistant.infra`
        (never reloaded), never this module's own classes: those change with the code."""
        return None
