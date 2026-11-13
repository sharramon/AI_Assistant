"""The module lifecycle contract and the context the core hands to each module."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from assistant.contracts.messages import Command, Event, ModuleEvent, Result

if TYPE_CHECKING:
    from assistant.contracts.menu import Menu
    from assistant.contracts.permissions import AccessItem

_EVENT_NAME = re.compile(r"[A-Za-z_]\w*(\.\w+)+")
_EVENT_PATTERN = re.compile(r"[A-Za-z_]\w*(\.\w+)*\.\*")


def event_name_ok(name: str, pattern: bool = False) -> bool:
    """Whether `name` is a named event's name, `<module_id>.<what>` (`cv.job_finished`); with
    `pattern`, a trailing `.*` (`cv.*`: every event of one module) is allowed too."""
    if not isinstance(name, str):
        return False
    return bool(_EVENT_NAME.fullmatch(name) or (pattern and _EVENT_PATTERN.fullmatch(name)))


class SubscriptionHandle:
    """One subscription, as `ctx.subscribe` and `ctx.subscribe_named` return it: pass it to
    `ctx.unsubscribe` to drop just that one. Opaque; `what` (the event's class or name) is for logs."""

    __slots__ = ("what",)

    def __init__(self, what: str) -> None:
        self.what = what

    def __repr__(self) -> str:
        return f"SubscriptionHandle({self.what!r})"


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
    #: Contracts looked up at each call (`get_one` / `get_all`) that may be missing, with no
    #: start order: for providers that themselves use this module (the Hub's door and names,
    #: used by the agents the Hub uses), where `optional` would make a cycle.
    uses: tuple[type[Contract], ...] = ()
    #: Module ids this module can't run without (job_search needs cv): turned on first, and
    #: refused off while this one is on. Read from `needs = [...]` in the module's `module.toml`
    #: when it has the key (the core puts it here), so a module declares it in one place.
    needs: tuple[str, ...] = ()
    #: The pip packages this module's code (and its app) needs, as requirement strings
    #: (`"pymupdf>=1.24"`), read from `packages = [...]` in its `module.toml` the same way.
    #: Informational: nothing installs them; install them by hand from this list.
    packages: tuple[str, ...] = ()
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
    #: Named events (`ModuleEvent`) this module publishes, each `<its id>.<what>`.
    publishes_named: tuple[str, ...] = ()
    #: Named events this module listens to (`cv.job_finished`, or `cv.*` for all of one module).
    listens_named: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.isidentifier():
            raise ValueError(f"manifest id must be a Python identifier, got {self.id!r}")
        if self.id == "core":
            raise ValueError("manifest id 'core' is reserved for the core's own menu")
        if not isinstance(self.description, str) or "\n" in self.description:
            raise ValueError(f"{self.id}: description must be one line of text")
        for field, base in (("handles", Command), ("sends", Command), ("publishes", Event), ("listens", Event)):
            for item in getattr(self, field):
                if not (isinstance(item, type) and issubclass(item, base)):
                    raise TypeError(f"{self.id}: manifest.{field} takes {base.__name__} types, got {item!r}")
        for needed in self.needs:
            if not (isinstance(needed, str) and needed.isidentifier()) or needed == self.id:
                raise ValueError(f"{self.id}: manifest.needs takes other modules' ids, got {needed!r}")
        for package in self.packages:
            if not (isinstance(package, str) and package.strip()):
                raise ValueError(f"{self.id}: manifest.packages takes pip requirements, got {package!r}")
        for name in self.publishes_named:
            if not (event_name_ok(name) and name.startswith(f"{self.id}.")):
                raise ValueError(f"{self.id}: manifest.publishes_named takes '{self.id}.<what>' names, got {name!r}")
        for name in self.listens_named:
            if not event_name_ok(name, pattern=True):
                raise ValueError(f"{self.id}: manifest.listens_named takes '<module>.<what>' or '<module>.*', "
                                 f"got {name!r}")  # fmt: skip


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

    async def request_set(
        self, items: Sequence[AccessItem], reason: str = "", subject: str = "", wait: bool = False
    ) -> tuple[AccessItem, ...]:
        """Ask for a whole access list in one request (a task agent's folders, Python, Chrome),
        for `subject` (its agent, or a kind of helper; default: the module). Returns the items
        you allowed: the saved grant if the list is unchanged, else your answer on one card.
        Raises `AccessDenied` on Deny; with `wait=False`, raises `AccessPending` while the card
        is open (the handler turns the module on once you allow)."""
        raise NotImplementedError

    def own_agent(self, agent_id: str, subject: str) -> None:
        """Say that this module's agent `agent_id` holds `subject`'s grant (its kind), so the
        agent can ask for more access itself (`permissions.request` on the core's menu) and the
        answer widens that grant. Call it when the agent starts; does nothing by default."""

    def granted(self, item: AccessItem, agent_id: str) -> bool:
        """Whether this module's saved grant for `agent_id`'s kind (`helper_2` shares `helper`'s)
        holds `item`, so it goes without a card (the Hub's message gate: `message:<receiver>`)."""
        raise NotImplementedError

    async def ask(self, item: AccessItem, agent_id: str, reason: str = "") -> bool:
        """Ask you on a card whether `agent_id` may have `item` (Allow once, Always allow, Deny)
        and wait for the answer. True if allowed; Always also saves it under this module and
        the agent's kind. False on Deny or no answer in time. True at once if already granted."""
        raise NotImplementedError


class ModuleLogs(ABC):
    """Where a module writes its own log files, reached as `ctx.logs`.

    The core owns the paths (one folder per app launch, created at the first message), so a
    module never picks one and nothing reaches it through its config.
    """

    @abstractmethod
    def folder(self) -> Path:
        """This launch's log folder once it exists, else the logs root. Ask each time you
        write: it changes when the first message names the session."""

    @abstractmethod
    def sink(self, name: str) -> Any:
        """The log file `name` in this launch's folder, for `ClaudeSession(transcript=...)` or
        `.write()`: a `LogSink` that holds what's written until the folder exists, or, when
        the app runs without a log session (tests), a `Path` under the logs root."""


class ModuleContext(ABC):
    """A module's only access to the rest of the app.

    Everything registered through it (subscriptions, command handlers, provided
    contracts) is removed automatically when the module stops.
    """

    module_id: str
    config: dict[str, Any]
    log: Logger
    permissions: ModulePermissions
    logs: ModuleLogs
    #: What the previous instance's `export_state()` returned, when this one replaces it in a
    #: reload; None on a normal start. Take it in `init`.
    handover: Any = None

    @abstractmethod
    def subscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> SubscriptionHandle | None:
        """Receive every published event that is an instance of `event_type`. Any time while the
        module runs. Returns a handle for `unsubscribe` (the core's context always does)."""

    @abstractmethod
    def publish(self, event: Event) -> None:
        """Publish an event. Returns immediately; never waits on subscribers."""

    def publish_named(self, name: str, data: Mapping[str, Any] | None = None) -> None:
        """Publish a `ModuleEvent` named `name`, which must be `<this module's id>.<what>`, with
        `data` (plain JSON values only); the core sets its `source`. Returns immediately.
        Raises ValueError for another module's name or data that isn't JSON."""
        raise NotImplementedError

    def subscribe_named(self, name: str, handler: Callable[[ModuleEvent], Awaitable[None]]) -> SubscriptionHandle:
        """Receive every `ModuleEvent` named `name` (`cv.job_finished`), or every one of a module
        with a trailing `.*` (`cv.*`). Any time while the module runs; returns a handle for
        `unsubscribe`. Matched by name, so either side reloads on its own; one published while
        this module is off or reloading is missed (the bus keeps nothing)."""
        raise NotImplementedError

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        """Drop one subscription, typed or named, without stopping the module. Events still
        queued for it are dropped. Does nothing if it's already gone. Everything left is
        dropped at the module's stop anyway."""
        raise NotImplementedError

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

    def withdraw(self, contract: type[C], impl: C) -> None:
        """Stop offering one `impl` this module provided (e.g. one helper of several), without
        stopping the module. Does nothing if it isn't offered."""
        raise NotImplementedError

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
