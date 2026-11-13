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
| `item(name, description, properties=None, required=(), callers=())` | Decorator for an async method taking the item's arguments as keywords and returning a `Result` (a plain value becomes `Result.ok`). `properties`: a JSON Schema per argument. `callers`: the only module or agent ids allowed to use it (empty: anyone). A method with a `caller` parameter is passed the caller's id (`MenuItem.takes_caller`), so it can decide per caller itself; `caller` can't be one of the item's properties. Raises at import for a duplicate name, a description that isn't one line, or a `required` name not in `properties` |
| `specs()` / `names()` / `items()` | The items as `ToolSpec`s, names, or `MenuItem`s (`spec`, `method`, `callers`, `takes_caller`), in declaration order |
| `check(name, args)` | What's wrong with `args`, or `None`: a missing required argument, an unknown one, a wrong `type` (bool is not an integer), a value outside `enum`, a string shorter than `minLength` once trimmed |
| `allowed(name, caller) -> bool` | Whether `caller` may use the item |
| `async call(module, name, args, caller="")` | `not_available` for a caller the item doesn't allow, then `check`, then run the item on `module` (with `caller=` if it takes it); `invalid_arguments` when the check fails. The caller comes from [`InvokeTool.caller`](tools.md#invoketool) |

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

`Manifest(id: str, provides: tuple = (), requires: tuple = (), optional: tuple = (), uses: tuple = (), needs: tuple[str, ...] = (), packages: tuple[str, ...] = (), permissions: tuple[str, ...] = (), optional_permissions: tuple[str, ...] = (), description: str = "", handles: tuple = (), sends: tuple = (), publishes: tuple = (), listens: tuple = (), publishes_named: tuple[str, ...] = (), listens_named: tuple[str, ...] = ())`

Frozen dataclass describing a module: who it is, what it needs, and its inputs and outputs. Plain data on the class, read without starting the module (for the dependency graph, and next for the directory and the generated [module library](../architecture/module-library.md)). Code dependencies are on contracts, never on other modules; `needs` only says which modules must be on alongside it. `permissions` and `optional_permissions` are declarations: single names aren't checked yet ([`ctx.permissions`](#modulecontextpermissions) allows and logs them). `agent.access` says the module asks for its config's access list with `request_set` when turned on.

**Fields**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | yes | Unique id, used in `modules.enabled` and as the config section name |
| `provides` | `tuple[type[Contract], ...]` | no | Contracts this module provides via `ctx.provide` |
| `requires` | `tuple[type[Contract], ...]` | no | Contracts that must be provided by an enabled module, or startup fails |
| `optional` | `tuple[type[Contract], ...]` | no | Contracts used if present; only affects start order |
| `uses` | `tuple[type[Contract], ...]` | no | Contracts looked up at each call that may be missing, with **no** start order: for a provider that itself uses this module (the Hub's `IModuleDoor` and `IAgentNames`, used by the agents the Hub lists as optional), where `optional` would make a cycle (built 2026-11-08) |
| `needs` | `tuple[str, ...]` | no | Ids of the modules it can't run without (job_search needs cv). Turning it on turns them on first, at startup too; turning one off is refused while it's on, naming it. Usually set in the module's `module.toml` (`needs = [...]`): when the file has the key, the core puts it here as the module is loaded (`loader.apply_module_toml`). A needed id that doesn't exist fails startup (`StartupError`, the id named) or the activation (`not_available`). Not its own id (built 2026-11-13) |
| `packages` | `tuple[str, ...]` | no | The pip packages its code and its app need, as requirement strings (cv: `("pymupdf>=1.24",)`). Set in the module's `module.toml` (`packages = [...]`), read the same way as `needs`; each a non-empty string. Informational: nothing installs them, so install them by hand with pip from this list. No module's packages are in `pyproject.toml` (built 2026-11-13) |
| `permissions` | `tuple[str, ...]` | no | [Permission names](../architecture/permissions.md#permission-names) the module can't run without |
| `optional_permissions` | `tuple[str, ...]` | no | Permissions it asks for in the moment; without them a feature is off (`voice_in`: `("microphone",)`) |
| `description` | `str` | no (every module in the app sets it) | One line saying what it does, for the directory and the module library |
| `handles` | `tuple[type[Command], ...]` | no | Commands it handles with `ctx.handle` (commands in) |
| `sends` | `tuple[type[Command], ...]` | no | Commands it sends (commands out) |
| `publishes` | `tuple[type[Event], ...]` | no | Events it publishes (events out) |
| `listens` | `tuple[type[Event], ...]` | no | Events it subscribes to (events in) |
| `publishes_named` | `tuple[str, ...]` | no | [Named events](messaging.md#moduleevent) it publishes, each `<its id>.<what>` (built 2026-11-12; no module declares one now) |
| `listens_named` | `tuple[str, ...]` | no | Named events it listens to: `<module>.<what>`, or `<module>.*` for all of one module |

Every type in `provides`, `requires`, `optional` and `uses` must be a [`Contract`](#contract) from `assistant.contracts`, or startup fails. A subscription, lookup or named event the manifest doesn't declare is logged once ([`ScopedContext`](core.md#scopedcontext)).

**Raises** (when the manifest is made): `ValueError` if `id` isn't a Python identifier, `description` has a line break, a `publishes_named` name isn't `<id>.<what>`, or a `listens_named` name isn't `<module>.<what>` or `<module>.*`; `TypeError` if `handles` / `sends` hold anything but `Command` types, or `publishes` / `listens` anything but `Event` types.

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
| `logs` | `ModuleLogs` | This launch's log folder and files; see below |
| `handover` | `Any` | After a reload, what the old instance's [`export_state`](#moduleprotocolexport_state) returned; otherwise `None` |

### `ModuleContext.logs`

**Reusable** · Used by: `talker`, `main_assistant` (their transcripts), `temp_ui` (the Logs button), `html_viewer` (snips) · built 2026-11-05

`class ModuleLogs(ABC)`, in `assistant.contracts`.

| Member | Does |
|--------|------|
| `folder() -> Path` | This launch's log folder once it exists (after the first message), else the logs root. Ask each time you write |
| `sink(name) -> LogSink \| Path` | The log file `name` in that folder: a [`LogSink`](infra.md#logsink) that holds what's written until the folder exists. Pass it to `ClaudeSession(transcript=...)` or `.write()` to it. When the app runs without a log session (tests), a `Path` under `logging.dir` |

The core owns the paths ([logging](../architecture/core.md#logging)); a module never picks one, and nothing log-related is put into its config. A module's config only names its file:

    name = ctx.config.get("transcript")          # "talker.jsonl"
    transcript = ctx.logs.sink(name) if name else None

### `ModuleContext.permissions`

**Reusable** · Used by: `voice_in` first (`microphone`, built 2026-11-03); `job_search`, `task_agents` (`request_set`, through [`request_access`](infra.md#agent_access)); `agent_hub` (`granted` / `ask`, its message gate); the core's `CoreMenu`; every module that needs a permission · built 2026-11-02, backed by the core's handler since 2026-11-05

`class ModulePermissions(ABC)`, in `assistant.contracts`.

| Member | Does |
|--------|------|
| `has(name) -> bool` | Whether this module may use `name` now, without asking |
| `async request(name, reason) -> bool` | Ask in the moment; `reason` is shown to you |
| `own_agent(agent_id, subject)` | Say that this module's agent `agent_id` holds `subject`'s grant, so that agent may ask for more with `permissions.request` (called by [`ProfileAgent.start`](infra.md#profileagent) when given a `subject`). Non-abstract; does nothing by default |
| `async request_set(items, reason="", subject="", wait=False) -> tuple[AccessItem, ...]` | Ask for a whole access list ([`AccessItem`](messaging.md#accessitem)s) in one request, for `subject` (its agent's kind; default: the module). Returns the items you allowed: the saved grant if the list is unchanged, else your answer on one card. Raises [`AccessDenied`](messaging.md#accessdenied-accesspending) on Deny. With `wait=False` (a module's `start`), raises [`AccessPending`](messaging.md#accessdenied-accesspending) while the card is open, and the handler turns the module on after your Allow; with `wait=True` (inside an approved run) it waits for your answer |
| `granted(item, agent_id) -> bool` | Whether this module's saved grant for `agent_id`'s kind (`helper_2` shares `helper`'s) holds `item`, so it goes without a card. Non-abstract. Used by the Agent Hub's message gate with `message:<receiver>` (built 2026-11-10) |
| `async ask(item, agent_id, reason="") -> bool` | Ask you on a one-item card whether `agent_id` may have `item` (Allow once · Always allow · Deny) and wait. True if allowed, at once if already granted; Always also saves it under this module and the agent's kind. False on Deny or no answer in time. Cancelling the call closes the card. Non-abstract (built 2026-11-10) |

The caller's id is filled in by the core; a module never passes it. Every module's `ctx.permissions` is a [`PermissionsPort`](core.md#permissionsport) forwarding to the core's [permissions handler](../architecture/permissions.md). `request_set` is checked: a module that uses it declares `agent.access` in its manifest. `has` and `request` aren't checked yet: they allow, and log a warning the first time each module uses each name ("not checked yet: allowing voice_in microphone (You clicked the mic)"), then debug lines. Required permissions aren't checked at start yet.

    if not await ctx.permissions.request("microphone", reason="You clicked the mic"):
        return Result.failed("microphone not allowed")
    granted = await ctx.permissions.request_set(access_items(config), "its folders", subject="job_search_agent")

### `ModuleContext.subscribe`

`subscribe(event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> SubscriptionHandle`

Receive every published event that is an instance of `event_type` (subclasses included). The handler runs on this subscription's own worker, one event at a time, in order. It is cancelled after `core.event_handler_timeout`; exceptions are logged. Any time while the module runs. Returns a `SubscriptionHandle` for [`unsubscribe`](#modulecontextunsubscribe) (it returned `None` before 2026-11-12, so old callers are unaffected).

### `ModuleContext.publish`

`publish(event: Event) -> None`

Publish an event. Returns immediately and never waits on subscribers. Events are dropped for a subscriber whose queue is full.

### `ModuleContext.publish_named`

**Reusable** · Used by: cv (`cv.job_finished`, `cv.job_submitted`) · built 2026-11-12

`publish_named(name: str, data: Mapping[str, Any] | None = None) -> None`

Publish a [`ModuleEvent`](messaging.md#moduleevent) named `name`, which must be `<this module's id>.<what>`; the core sets its `source`. `data` is copied through JSON, so it holds plain values only and the listener never shares the publisher's objects. Returns immediately, like `publish`. A name not in `publishes_named` still goes out and is logged once.

**Raises:** `ValueError` for another module's name (or not a name), or data that isn't plain JSON (objects, NaN).

    self._ctx.publish_named("cv.job_finished", {"reply_to": "job_search_agent", "job_dir": "...", "state": "done"})

### `ModuleContext.subscribe_named`

**Reusable** · Used by: job_search (`cv.job_finished`, `cv.job_submitted`) · built 2026-11-12

`subscribe_named(name: str, handler: Callable[[ModuleEvent], Awaitable[None]]) -> SubscriptionHandle`

Receive every `ModuleEvent` named `name`, or every one of a module with a trailing `.*` (`cv.*`). A filter over one bus subscription to `ModuleEvent`, so delivery works as for `subscribe`. Matched by name, not class, so publisher and listener each reload on their own; an event published while this module is off or reloading is missed (the bus keeps nothing). A name not in `listens_named` still works and is logged once.

**Raises:** `ValueError` if `name` isn't `<module>.<what>` or `<module>.*`.

### `ModuleContext.unsubscribe`

**Reusable** · built 2026-11-12

`unsubscribe(handle: SubscriptionHandle) -> None`

Drop one subscription, typed or named, without stopping the module; events still queued for it are dropped. Does nothing if it's already gone. Everything left is dropped at the module's stop anyway.

### `ModuleContext.handle`

`handle(command_type: type[K], handler: Callable[[K], Awaitable[Result]]) -> None`

Become the single handler for `command_type`. The handler must return a [`Result`](messaging.md#result). List the type in `manifest.handles`: if it isn't there, `handle` raises `ValueError` and the module fails to start (strict since 2026-11-05).

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

### `ModuleContext.withdraw`

**Reusable** · Used by: `task_agents` (`agents.close`, and a launch that failed after providing its helper) · built 2026-11-05

`withdraw(contract: type[C], impl: C) -> None`

Stop offering one `impl` this module provided, without stopping the module (one helper of several). Does nothing if it isn't offered, or after the context is closed. Not abstract: the base raises `NotImplementedError`; the core's [`ScopedContext`](core.md#scopedcontext) implements it.

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
