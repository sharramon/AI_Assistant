# Core host (internal)

The stable host in `assistant.core`. Modules never use these directly; they go through [`ModuleContext`](modules.md#modulecontext). Listed here so nothing gets rebuilt elsewhere. Back to the [API index](README.md). Design and behavior: [core architecture](../architecture/core.md).

## `App`

`App(available: Sequence[type[ModuleProtocol]], config: dict[str, Any], config_loader: Callable[[], dict] | None = None, logs: LogSession | None = None)`

Wires the core together and runs the enabled modules. Construction validates the module selection. Handles `InvokeTool` and the [module control](control.md) commands, including `ReloadModule` and `AddModule`.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `available` | `Sequence[type[ModuleProtocol]]` | yes | Every module the app can run: `__main__` passes [`find_modules()`](#loader) |
| `config` | `dict` | yes | From [`load_config`](infra.md#load_config) |
| `config_loader` | callable | no | Re-reads the config before a reload or add (`__main__` passes `load_config`) |
| `logs` | `LogSession` | no | The launch's log handler; every module reaches it as `ctx.logs` through a [`SessionLogs`](#sessionlogs) (`app.logs`). Without it, `ctx.logs` gives paths under `logging.dir` |

**Raises:** [`StartupError`](#startuperror) if the enabled modules can't run together.

**Attributes:** `router: CommandRouter`, `bus: EventBus`, `container: Container`.

| Method | Description |
|--------|-------------|
| `async run()` | `start()`, wait for shutdown (or task cancellation), then `stop()` |
| `async start()` | Register the `InvokeTool` handler, subscribe to `ShutdownRequested`, init and start modules. May raise `StartupError` |
| `async stop()` | Cancel in-flight commands, stop modules in reverse order, close the bus |
| `request_shutdown()` | Make `run()` proceed to `stop()` |

**Defined in:** `src/assistant/core/app.py`

## `StartupError`

`class StartupError(Exception)`

The configured modules can't run together: raised by [`resolve_modules`](#resolve_modules) or by [`LifecycleManager.start`](#lifecyclemanager) when a required provider fails.

**Defined in:** `src/assistant/core/registry.py`

## `resolve_modules`

`resolve_modules(available: Sequence[type[ModuleProtocol]], enabled: Sequence[str]) -> list[type[ModuleProtocol]]`

Select the `enabled` modules and return them in start order: providers before the modules that require or optionally use them, otherwise in `enabled` order.

**Raises:** `StartupError` for unknown or duplicate ids, non-shared contracts in a manifest, a missing required contract, more than one provider of a single-provider contract, or a circular dependency.

**Defined in:** `src/assistant/core/registry.py`

## `LifecycleManager`

`LifecycleManager(available: Sequence[type[ModuleProtocol]], start_order: list[type[ModuleProtocol]], make_context: Callable[[Manifest], ScopedContext], stop_timeout: float = 5.0, on_change: Callable[[str, ModuleState], None] | None = None)`

`available` is every module that may run; `start_order` is the validated list active at startup (from `resolve_modules`). `on_change` is called on every state transition; `App` publishes it as `ModuleStateChanged`. Transitions are serialized by a lock.

| Method | Description |
|--------|-------------|
| `async start()` | Instantiate and `init` each startup module, then `start` each, in order. A failing module is closed and marked `failed`; raises `StartupError` if another module requires a contract only it provides |
| `async stop()` | `stop` each active module in reverse activation order (with `stop_timeout`), then close its context |
| `modules() -> list[ModuleInfo]` | Every available module and its state |
| `async activate(module_id) -> Result` | Runtime activation; see [`ActivateModule`](control.md#activatemodule) |
| `async deactivate(module_id, with_dependents=False) -> Result` | Runtime deactivation; see [`DeactivateModule`](control.md#deactivatemodule) |
| `async reload(module_id) -> Result` | Swap a module's code, with rollback; see [`ReloadModule`](control.md#reloadmodule) |
| `async add(package, activate=True) -> Result` | Load a new module; see [`AddModule`](control.md#addmodule) |

**Defined in:** `src/assistant/core/lifecycle.py`

## `loader`

Functions for finding the modules by folder and loading a module's code fresh. Generic: they know no module by name.

| Function | Description |
|----------|-------------|
| `find_modules(root="assistant.modules") -> list[type[ModuleProtocol]]` | Every module under `root`, sorted by folder: one per sub-package whose one `ModuleProtocol` class has the folder's name as its id. A bad folder is skipped with a warning; `_` folders are ignored. Also exported as `assistant.core.find_modules` |
| `check_folder(cls, package, root="assistant.modules")` | Raises `LoadError` if a package directly under `root` holds a module with another id. `AddModule` uses it too |
| `package_of(cls) -> str` | The package a module class lives in |
| `check_reloadable(package)` | Raises `LoadError` for shared code (`assistant.core`, `.contracts`, `.infra`, `app_kit`), `assistant` / `assistant.modules` themselves, or a top-level name |
| `drop(package) -> dict` | Remove the package and its submodules from `sys.modules` (and their `__pycache__`); returns them |
| `restore(package, removed)` | Put back what `drop` removed |
| `import_fresh(package)` | Import from source; a missing contract becomes `LoadError` ("needs a restart") |
| `find_module_class(package, module_id=None)` | The one `ModuleProtocol` subclass the package exports |

**Defined in:** `src/assistant/core/loader.py`

## `ScopedContext`

`ScopedContext(manifest, router, bus, container, config, log, handover=None, logs=None)`

The [`ModuleContext`](modules.md#modulecontext) implementation. Records every subscription, handler, and provided contract made through it. Sets the module's [`ctx.permissions`](modules.md#modulecontextpermissions) to an [`AllowAllPermissions`](#allowallpermissions) bound to its module id, and its [`ctx.logs`](modules.md#modulecontextlogs) to the app's `SessionLogs` (a default one if none is given).

| Method | Description |
|--------|-------------|
| `close()` | Remove everything this module registered |

**Defined in:** `src/assistant/core/context.py`

## `SessionLogs`

`SessionLogs(session: LogSession | None = None, root: str | Path = "logs")` (a `ModuleLogs`)

The `ctx.logs` port. With a `LogSession`, `folder()` and `sink(name)` are the session's; without one (tests), `folder()` is `root` and `sink(name)` is `root / name`. `App` builds one for every module from its `logs` argument and `logging.dir`.

**Defined in:** `src/assistant/core/logs.py`

## `AllowAllPermissions`

`AllowAllPermissions(module_id: str)`

The `ctx.permissions` stand-in, a [`ModulePermissions`](modules.md#modulecontextpermissions): `has` and `request` always return `True`. The first use of each permission logs a warning on `assistant.core.permissions` ("no permissions handler: allowing voice_in microphone (You clicked the mic)"); later uses of the same one log at debug. Replaced by a forwarder to the [permissions handler](../architecture/permissions.md) once it exists.

**Defined in:** `src/assistant/core/permissions.py`

## `CommandRouter`

`CommandRouter(default_timeout: float = 30.0, timeouts: dict[str, float] | None = None)`

`timeouts` maps command class names to per-type timeouts.

| Method | Description |
|--------|-------------|
| `register(command_type, handler)` | Set the single handler. Raises `ValueError` if one exists |
| `unregister(command_type, handler)` | Remove it, only if it's still the registered handler |
| `async send(command, timeout=None) -> Result` | Run the handler as a task; map every outcome to a `Result` (see [internals](../architecture/core.md#communication-internals)) |
| `cancel(correlation_id) -> int` | Cancel in-flight commands whose `id` or `correlation_id` matches |
| `cancel_all() -> int` | Cancel every in-flight command |
| `hold()` | Context manager: while held (a module is being swapped), a command with no handler waits for one, up to its timeout, instead of returning `not_available` |

**Defined in:** `src/assistant/core/router.py`

## `EventBus`

`EventBus(queue_size: int = 100, handler_timeout: float | None = 10.0)`

| Method | Description |
|--------|-------------|
| `subscribe(event_type, handler, owner="core") -> Subscription` | Start a worker delivering matching events (subclasses included) from a bounded queue |
| `unsubscribe(sub)` | Stop delivery; queued events are dropped |
| `publish(event)` | Enqueue for each matching subscriber; never blocks. Drops and logs when a queue is full |
| `async close()` | Cancel and await all workers |

`Subscription` has `event_type`, `owner`, `task`, and `offer(event) -> bool`.

**Defined in:** `src/assistant/core/bus.py`

## `Container`

`Container()`

| Method | Description |
|--------|-------------|
| `provide(contract, impl, owner)` | Register a provider. `TypeError` if `contract` isn't shared or `impl` doesn't implement it; `ValueError` if a single-provider contract already has one |
| `remove_owner(owner)` | Remove everything `owner` provided |
| `get_all(contract) -> list` | All providers, possibly empty |
| `get_one(contract)` | First provider or `None` |

**Defined in:** `src/assistant/core/container.py`

## `is_shared_contract`

`is_shared_contract(t: object) -> bool`

True for `Contract` subclasses defined under `assistant.contracts` (excluding `Contract` itself).

**Defined in:** `src/assistant/core/container.py`

## `MenuTools`

`MenuTools(menu: Menu, module: ModuleProtocol)` (an `IToolProvider`)

The core's adapter from a module's [`Menu`](modules.md#menu) to `IToolProvider`, linked to one running copy. The lifecycle calls `ScopedContext.link_menu(module)` right after a module's `init` (at startup, on activate, on reload); it provides a `MenuTools` in the module's name, so closing the context removes it. `invoke` runs `menu.call`, which checks the arguments first.

**Defined in:** `src/assistant/core/tools.py`

## `dispatch_tool`

`async dispatch_tool(container: Container, command: InvokeTool) -> Result`

The `InvokeTool` handler. Looks up providers at call time; returns `not_available` for an unknown tool, `failed` for a name offered twice, else the provider's result.

**Defined in:** `src/assistant/core/tools.py`

## `CoreMenu`

`CoreMenu(send, permissions: ModulePermissions)`

The core's own [menu](../api/control.md#the-cores-menu) (`modules.*`), id `core` (`CORE_ID`; no module may use it). `App` builds one with the router's `send` and `AllowAllPermissions("core")` (as `app.core_menu`), and provides it through a `MenuTools` (`app.core_menu_tools`) in the name `core` from `start` to `stop`. `App` also handles `GetMenu`. Tests swap `app.core_menu.permissions` for one that refuses.

**Defined in:** `src/assistant/core/directory.py`
