# Modules

Writing a module. All items: `from assistant.contracts import ...`. Back to the [API index](README.md).

## `ModuleProtocol`

**Reusable** · Used by: every module; the core's loader and lifecycle · built 2026-11-05 (`Module` renamed)

`class ModuleProtocol(ABC)`

The one interface every module implements. Set the `manifest` class attribute and implement `init`; subclass it to get the do-nothing defaults for the other hooks. It's a **protocol**, not a [`Contract`](#contract): a class is a module by having these members, and nobody looks a module up through the container, so it has no `I` prefix ([principle 12](../architecture/principles.md)). It carries no behaviour: a module gets its behaviour from the parts it owns (a `CompanionApp`, a `SessionTaskAgent`, a [`Menu`](#menu)).

The core calls `init` for every module in dependency order, then `start` for each, and on shutdown `stop` in reverse order. `stop` is called for every module whose `init` succeeded, even if `start` never ran. If `init` or `start` raises, the module is skipped (see [lifecycle](../architecture/core.md#lifecycle)).

**Modules must be restartable.** A module can be [deactivated and activated](control.md) while the app runs. Each activation creates a **fresh instance** and calls `init` and `start` again, so `stop` must release everything the module started (processes, threads, windows, devices), and in-memory state doesn't survive deactivation. Load expensive resources in `start` or on first use. After `stop`, the old context drops `publish` and refuses `send`. A resource that can't be stopped (like a blocking `input()` thread) should be shared across instances, as `console_io` does.

**Attributes**
| Name | Type | Description |
|------|------|-------------|
| `manifest` | `ClassVar[Manifest]` | Required. Identifies the module and its dependencies |
| `menu` | `ClassVar[Menu \| None]` | Optional, default `None`. The actions others may call: a [`Menu`](#menu) the core links to the running copy |

### `ModuleProtocol.init`

`async init(self, ctx: ModuleContext) -> None`

Abstract. Subscribe to events, register command handlers, and provide contracts here. Keep `ctx` if the module needs it later. Don't start background work yet.

### `ModuleProtocol.start`

`async start(self) -> None`

Begin active work: listening for input, background loops. Default does nothing.

### `ModuleProtocol.stop`

`async stop(self) -> None`

Stop work and release resources. Default does nothing. Has `core.module_stop_timeout` seconds. Subscriptions, handlers, and provided contracts are removed by the core afterwards, so there's no need to undo them here.

**Example**

    class EchoOrchestrator(ModuleProtocol):
        manifest = Manifest(
            id="echo_orchestrator",
            description="Stand-in orchestrator: echoes, /tools",
            optional=(IToolProvider,),
            publishes=(ResponseReady,),
            listens=(InputReceived,),
        )

        async def init(self, ctx: ModuleContext) -> None:
            self._ctx = ctx
            ctx.subscribe(InputReceived, self._on_input)

        async def _on_input(self, event: InputReceived) -> None:
            self._ctx.publish(ResponseReady(text=f"Echo: {event.text}", correlation_id=event.id))

### `ModuleProtocol.busy`

`busy(self) -> str | None`

Why this module's code shouldn't be swapped right now (for example `"replying to you"`), or `None`. A [`ReloadModule`](control.md#reloadmodule) waits until it's `None` (up to `core.reload_idle_timeout`), unless it says `now`. Default `None`. Today: the Talker (a turn is running), the Agent Hub (tasks open), the Main Assistant (working on a task).

### `ModuleProtocol.export_state`

`export_state(self) -> Any`

Called before a reload stops this instance. What it returns reaches the new instance as [`ctx.handover`](#modulecontext) in `init` (and goes back to the old instance if the new code fails). Return plain data or `assistant.infra` / `app_kit` objects, which are never reloaded; never this module's own classes, which change with the code. Default `None`: the new instance starts clean. A hook that raises counts as `None`. Today: `voice_in` hands over its `CompanionApp`, so the voice app keeps running.

**Defined in:** `src/assistant/contracts/module.py`
**See also:** [`Manifest`](#manifest), [`ModuleContext`](#modulecontext), [adding a module](../architecture/core.md#adding-replacing-or-removing-a-module), [reloading](../architecture/core.md#reloading-a-modules-code)

## `Menu`

**Reusable** · Used by: `html_viewer`, `echo_orchestrator` (more modules as they're recoded); read by the core (`MenuTools`, `ScopedContext.link_menu`) and `scripts/build_docs.py` (the module library) · built 2026-11-05

`class Menu()` · `MenuItem(spec: ToolSpec, method: str)`

A module's menu: the actions an assistant or another module may call. Plain data built when the module's file is imported, so the core reads it without starting the module. Declare one per module class, decorate the methods that are its items, and set it as the class's `menu`. When the module is on, the core links the menu to that copy (after `init`) and offers its items through [`InvokeTool`](tools.md#invoketool); closing the module's context unlinks it. A reload re-imports the file, so the reloaded menu runs the new methods. The module never calls `ctx.provide(IToolProvider, ...)` for it.

| Method | What it does |
|--------|--------------|
| `item(name, description, properties=None, required=())` | Decorator for an async method taking the item's arguments as keywords and returning a `Result` (a plain value becomes `Result.ok`). `properties`: a JSON Schema per argument. Raises at import for a duplicate name, a description that isn't one line, or a `required` name not in `properties` |
| `specs()` / `names()` / `items()` | The items as `ToolSpec`s, names, or `MenuItem`s, in declaration order |
| `check(name, args)` | What's wrong with `args`, or `None`: a missing required argument, an unknown one, a wrong `type` (bool is not an integer), a value outside `enum`, a string shorter than `minLength` once trimmed |
| `async call(module, name, args)` | `check`, then run the item on `module`; `invalid_arguments` when the check fails |

**Example**

    menu = Menu()

    class HtmlViewerModule(ModuleProtocol):
        manifest = Manifest(id="html_viewer", description="View, edit, highlight and snip HTML")
        menu = menu

        @menu.item("viewer.open", "Open an HTML file in the viewer",
                   {"path": {"type": "string", "minLength": 1}, "front": {"type": "boolean"}}, required=["path"])
        async def show(self, path: str, front: bool = False) -> Result: ...

**Defined in:** `src/assistant/contracts/menu.py`
**See also:** [`MenuTools`](core.md#menutools), [tools offered today](tools.md#tools-offered-today), [the module library](../architecture/module-library.md)

## `Manifest`

**Reusable** · Used by: every module

`Manifest(id: str, provides: tuple = (), requires: tuple = (), optional: tuple = (), permissions: tuple[str, ...] = (), optional_permissions: tuple[str, ...] = (), description: str = "", handles: tuple = (), sends: tuple = (), publishes: tuple = (), listens: tuple = ())`

Frozen dataclass describing a module: who it is, what it needs, and its inputs and outputs. Plain data on the class, read without starting the module (for the dependency graph, and next for the directory and the generated [module library](../architecture/module-library.md)). Dependencies are on contracts, never on other modules. `permissions` and `optional_permissions` are declarations only until the permissions handler runs; the [`ctx.permissions`](#modulecontextpermissions) stand-in allows everything.

**Fields**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | yes | Unique id, used in `modules.enabled` and as the config section name |
| `provides` | `tuple[type[Contract], ...]` | no | Contracts this module provides via `ctx.provide` |
| `requires` | `tuple[type[Contract], ...]` | no | Contracts that must be provided by an enabled module, or startup fails |
| `optional` | `tuple[type[Contract], ...]` | no | Contracts used if present; only affects start order |
| `permissions` | `tuple[str, ...]` | no | [Permission names](../architecture/permissions.md#permission-names) the module can't run without |
| `optional_permissions` | `tuple[str, ...]` | no | Permissions it asks for in the moment; without them a feature is off (`voice_in`: `("microphone",)`) |
| `description` | `str` | no (every module in the app sets it) | One line saying what it does, for the directory and the module library |
| `handles` | `tuple[type[Command], ...]` | no | Commands it handles with `ctx.handle` (commands in) |
| `sends` | `tuple[type[Command], ...]` | no | Commands it sends (commands out) |
| `publishes` | `tuple[type[Event], ...]` | no | Events it publishes (events out) |
| `listens` | `tuple[type[Event], ...]` | no | Events it subscribes to (events in) |

Every type in `provides`, `requires` and `optional` must be a [`Contract`](#contract) from `assistant.contracts`, or startup fails.

**Raises** (when the manifest is made): `ValueError` if `id` isn't a Python identifier or `description` has a line break; `TypeError` if `handles` / `sends` hold anything but `Command` types, or `publishes` / `listens` anything but `Event` types.

**Defined in:** `src/assistant/contracts/module.py`

## `ModuleContext`

**Reusable** · Used by: every module

`class ModuleContext(ABC)`

A module's only access to the rest of the app, passed to `init`. Everything registered through it is removed automatically when the module stops.

**Attributes**
| Name | Type | Description |
|------|------|-------------|
| `module_id` | `str` | This module's id |
| `config` | `dict[str, Any]` | The `[modules.<id>]` config section, or `{}` |
| `log` | `logging.Logger` | Logger named `assistant.modules.<id>` |
| `permissions` | `ModulePermissions` | This module's permission checks; see below |
| `handover` | `Any` | After a reload, what the old instance's [`export_state`](#moduleprotocolexport_state) returned; otherwise `None` |

### `ModuleContext.permissions`

**Reusable** · Used by: `voice_in` first (`microphone`, built 2026-11-03); every module that needs a permission · built 2026-11-02 (stand-in)

`class ModulePermissions(ABC)`, in `assistant.contracts`.

| Member | Does |
|--------|------|
| `has(name) -> bool` | Whether this module may use `name` now, without asking |
| `async request(name, reason) -> bool` | Ask in the moment; `reason` is shown to you |

The caller's id is filled in by the core; a module never passes it. Until the [permissions handler](../architecture/permissions.md) runs, the stand-in ([`AllowAllPermissions`](core.md#allowallpermissions)) allows everything and logs a warning the first time each module uses each permission ("no permissions handler: allowing voice_in microphone (You clicked the mic)"), then debug lines. Required permissions aren't checked at start yet. The handler later plugs in behind the same calls.

    if not await ctx.permissions.request("microphone", reason="You clicked the mic"):
        return Result.failed("microphone not allowed")

### `ModuleContext.subscribe`

`subscribe(event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None`

Receive every published event that is an instance of `event_type` (subclasses included). The handler runs on this subscription's own worker, one event at a time, in order. It is cancelled after `core.event_handler_timeout`; exceptions are logged.

### `ModuleContext.publish`

`publish(event: Event) -> None`

Publish an event. Returns immediately and never waits on subscribers. Events are dropped for a subscriber whose queue is full.

### `ModuleContext.handle`

`handle(command_type: type[K], handler: Callable[[K], Awaitable[Result]]) -> None`

Become the single handler for `command_type`. The handler must return a [`Result`](messaging.md#result). List the type in `manifest.handles`: today the core logs a warning when it isn't there; refusing it is planned (module system, chunk 9).

**Raises:** `ValueError` if the command type already has a handler.

### `ModuleContext.send`

`async send(command: Command, timeout: float | None = None) -> Result`

Send a command to its handler and wait for the result. Never raises for handler problems; see [`Result`](messaging.md#result) for the outcomes.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `command` | `Command` | yes | The command to send |
| `timeout` | `float \| None` | no | Seconds. Defaults to `core.command_timeouts.<Class>`, then `core.command_timeout` |

**Example**

    result = await ctx.send(InvokeTool(name="add", args={"a": 1, "b": 2}))
    if result.is_ok:
        print(result.value)

### `ModuleContext.cancel`

`cancel(correlation_id: str) -> int`

Cancel in-flight commands whose `id` or `correlation_id` matches. Returns how many were cancelled. Their senders get `Status.CANCELLED`.

### `ModuleContext.provide`

`provide(contract: type[C], impl: C) -> None`

Offer `impl` as a provider of `contract`.

**Raises:** `ValueError` if `contract` isn't in `manifest.provides`, or if it is a single-provider contract that already has a provider. `TypeError` if `impl` doesn't implement `contract`.

### `ModuleContext.get_all`

`get_all(contract: type[C]) -> list[C]`

All current providers of `contract`, possibly empty. Call it when needed rather than caching, since providers can change.

### `ModuleContext.get_one`

`get_one(contract: type[C]) -> C | None`

The provider of a single-provider contract, or `None`.

**Defined in:** `src/assistant/contracts/module.py` (interface), `src/assistant/core/context.py` (implementation)

## `Contract`

`class Contract(ABC)`

Base for capability interfaces that modules provide and resolve. Subclasses must be defined under `assistant.contracts`; the core rejects any other type.

**Attributes**
| Name | Type | Description |
|------|------|-------------|
| `multiple` | `ClassVar[bool]` | Whether several modules may provide it at once. Default `False` |

**Defined in:** `src/assistant/contracts/module.py`
**See also:** [`IToolProvider`](tools.md#itoolprovider)
