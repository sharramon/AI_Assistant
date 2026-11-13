# Core host (internal)

The stable host in `assistant.core`. Modules never use these directly; they go through [`ModuleContext`](modules.md#modulecontext). Listed here so nothing gets rebuilt elsewhere. Back to the [API index](README.md). Design and behavior: [core architecture](../architecture/core.md).

## `App`

`App(available: Sequence[type[ModuleProtocol]], config: dict[str, Any], config_loader: Callable[[], dict] | None = None, logs: LogSession | None = None)`

Wires the core together and runs the enabled modules. Construction validates the module selection. Handles `InvokeTool` and the [module control](control.md) commands, including `ReloadModule` and `AddModule`. A module's `ctx.config` is its own `module.toml` defaults with its `[modules.<id>]` section merged over them ([`loader.module_defaults`](#loader), [`merge`](app_kit.md#merge)); `modules.docs` reads its own `docs/` folder.

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
| `module_class(module_id) -> type` | The module's current class, on or off (the new one after a reload). `KeyError` if unknown. `App` uses it to find the module's folder (its `module.toml` and `docs/`) |

**Defined in:** `src/assistant/core/lifecycle.py`

## `loader`

Functions for finding the modules by folder and loading a module's code fresh. Generic: they know no module by name.

| Function | Description |
|----------|-------------|
| `find_modules(root="assistant.modules") -> list[type[ModuleProtocol]]` | Every module under `root`, sorted by folder: one per sub-package whose one `ModuleProtocol` class has the folder's name as its id. A bad folder is skipped with a warning; `_` folders are ignored. Puts the modules' `app/` folders on the import path first (`add_app_folders`). Also exported as `assistant.core.find_modules` |
| `app_folders(root="assistant.modules") -> list[Path]` | Every module's `app/` folder (`APP_FOLDER`), found by folder with no names, resolved and sorted: where the modules' companion apps' packages live (`cv/app/cv_tool`) |
| `add_app_folders(root="assistant.modules") -> list[Path]` | ♻ **Reusable** · Used by: `find_modules` (startup), `import_fresh` (a reload or `AddModule`), the root `conftest.py` (the test setup); built 2026-11-13. Appends each `app/` folder to `sys.path` once, so an app's package imports by its own name; returns the folders added now. Also exported as `assistant.core.add_app_folders`. A launch passes the folder on with [`launch_env`](app_kit.md#companionapp) |
| `check_folder(cls, package, root="assistant.modules")` | Raises `LoadError` if a package directly under `root` holds a module with another id. `AddModule` uses it too |
| `package_of(cls) -> str` | The package a module class lives in |
| `module_folder(cls) -> Path \| None` | The folder of that package, where the module keeps its own config defaults and docs; `None` if it can't be found |
| `module_defaults(cls) -> dict` | The module's own config defaults, `module.toml` in its folder, read fresh each time (a reload picks up new defaults). `{}` if none; an unreadable file is logged and counts as none. `App` merges the `[modules.<id>]` section over it for `ctx.config` |
| `check_reloadable(package)` | Raises `LoadError` for shared code (`assistant.core`, `.contracts`, `.infra`, `.testkit`, `app_kit`), `assistant` / `assistant.modules` themselves, or a top-level name |
| `drop(package) -> dict` | Remove the package and its submodules from `sys.modules` (and their `__pycache__`); returns them |
| `restore(package, removed)` | Put back what `drop` removed |
| `import_fresh(package)` | Import from source (a new module's `app/` folder on the path first); a missing contract becomes `LoadError` ("needs a restart") |
| `find_module_class(package, module_id=None)` | The one `ModuleProtocol` subclass the package exports |

**Defined in:** `src/assistant/core/loader.py`

## `ScopedContext`

`ScopedContext(manifest, router, bus, container, config, log, handover=None, logs=None, permissions=None)`

The [`ModuleContext`](modules.md#modulecontext) implementation. Records every subscription, handler, and provided contract made through it. Sets the module's [`ctx.permissions`](modules.md#modulecontextpermissions) to `permissions`: `App` passes a [`PermissionsPort`](#permissionsport) bound to the module's id and the app's handler (without one, a bare `PermissionsPort(module_id)`). Sets its [`ctx.logs`](modules.md#modulecontextlogs) to the app's `SessionLogs` (a default one if none is given).

| Method | Description |
|--------|-------------|
| `withdraw(contract, impl)` | Take back one provider this module gave ([`Container.remove`](#container)); nothing once closed |
| `close()` | Remove everything this module registered |

**Undeclared uses are logged** (principle 17, built 2026-11-08). A `subscribe` to an event not in the manifest's `listens`, or a `get_one` / `get_all` of a contract not in `provides`, `requires`, `optional` or `uses`, still works but logs one warning per type (`<id> uses <Type> without declaring it in its manifest (...)`), so the manifest gets fixed. `handle` and `provide` stay strict (they raise).

**Defined in:** `src/assistant/core/context.py` · **Tests:** `tests/test_honest_manifests.py`

## `SessionLogs`

`SessionLogs(session: LogSession | None = None, root: str | Path = "logs")` (a `ModuleLogs`)

The `ctx.logs` port. With a `LogSession`, `folder()` and `sink(name)` are the session's; without one (tests), `folder()` is `root` and `sink(name)` is `root / name`. `App` builds one for every module from its `logs` argument and `logging.dir`.

**Defined in:** `src/assistant/core/logs.py`

## `PermissionsHandler`

`PermissionsHandler(send, publish, find, grants_file=GRANTS_FILE, reviewer=REVIEWER, review_timeout=90.0, answer_timeout=600.0, you=YOU, log=None)` (`REVIEWER = ""`, `YOU = ()`: the core names no module, principle 21; `config/default.toml` sets `reviewer = "main_assistant"` and `you = ["temp_ui"]` under `[core.permissions]`) · `PermissionsHandler.from_config(config, send, publish, find)`

The [permissions handler](../architecture/permissions.md#part-of-the-core), part of the core and always on (its first piece: access lists). `send`, `publish`, `find`: the router's `send`, the bus's `publish` and the container's `get_one`; it uses nothing else of the app and imports no module. `App` builds it from `[core.permissions]` (every key optional: `grants_file`, `reviewer`, `review_timeout`, `answer_timeout`, `you`) as `app.permissions`, handles `AnswerPermissionRequest` with `answer`, subscribes `on_task_updated` to `TaskUpdated`, and calls `close()` in `stop()`.

| Method | Description |
|--------|-------------|
| `async request_set(module_id, subject, items, reason="", wait=False) -> tuple[AccessItem, ...]` | What `ctx.permissions.request_set` forwards. The saved grant when the fingerprint matches; otherwise a card (refusals, rule warnings, the review, then `PermissionRequested`). `wait=False` raises `AccessPending` and turns the module on after Allow; `wait=True` awaits your answer. Raises `AccessDenied` on Deny or no answer |
| `async answer(cmd: AnswerPermissionRequest) -> Result` | Your answer to an open card. `invalid_arguments` for no such card, or a `keep` key not on it |
| `async on_task_updated(event)` | Takes the reviewer's final `TaskUpdated` |
| `grants() -> list[dict]` | Every saved grant and every list waiting on a card: `module_id`, `subject`, `granted`, `labels`, `asked`, `denied`, `date`, `matches`, `waiting` |
| `async grant(module_id, keys, subject="", caller="") -> Result` | Widen a grant with asked-for keys. From `you`: applied (a module that's off is turned on). From an agent: a card, and the answer reaches it as an `AgentNotice` |
| `async revoke(module_id, subject="", keys=None, caller="") -> Result` | Take back all or some items; the module turns off and its running tasks are cancelled. A revoke of only `message:` items keeps the module on ("it stays on, and the next message asks again"). From an agent: a card first |
| `kind_of(agent_id) -> str` | The subject an agent's grants are saved under: its kind (from `own_agent`; `helper_2` → `helper`), else its id |
| `granted(module_id, agent_id, item) -> bool` | Whether `module_id`'s saved grant for the agent's kind holds `item` (and isn't denied) |
| `async ask(module_id, agent_id, item, reason="") -> bool` | A one-item `message` card (Allow once · Always allow · Deny), awaited; True at once if granted. Allow once saves nothing; Always adds the item to the grant for the agent's kind. Cancelling the call closes the card. Built 2026-11-10 for the Agent Hub's message gate |
| `open_cards() -> int` | How many cards are open |
| `async close()` | Cancel open cards (each settles as denied) |

**Card actions** (built 2026-11-08). A card's action is a `CardAction` (`ACCESS`, `GRANT`, `REVOKE`, `MESSAGE`; a `StrEnum` inside the core whose values are `PermissionRequested.action`'s). An answered card is applied by its action's handler from a table (principle 20): `access` saves the list (and turns the module on); `grant` and `revoke` carry out an agent's call and tell it with an `AgentNotice`; `message` settles the waiting `ask` (`_apply_message`, with `Card.remember` from the answer). Every `PermissionChanged` is built in one place.

Saved grants: `GrantStore` and `Grant` (`store.py`), one section per module and subject in `data/permissions.toml`, written whole and atomically; `fingerprint(items)` hashes a list's keys. Guardrails: `PROTECTED`, `refusals`, `rule_warnings` and `FIXED_RULES` (`rules.py`).

**Defined in:** `src/assistant/core/permissions/handler.py` (`store.py`, `rules.py`) · **Tests:** `tests/test_permissions_handler.py`, `tests/test_permissions.py`

## `PermissionsPort`

`PermissionsPort(module_id: str, handler: PermissionsHandler | None = None)` (a `ModulePermissions`)

Each module's [`ctx.permissions`](modules.md#modulecontextpermissions), bound to its id, so no module asks in another's name. `request_set` forwards to the handler with the module id (and `subject`, default the module id). `has` and `request` aren't checked yet: they return `True`, and the first use of each name logs a warning on `assistant.core.permissions` ("not checked yet: allowing voice_in microphone (You clicked the mic)"), later ones at debug. `granted` and `ask` forward with the module id too. Without a handler (a bare context in a test), `request_set` allows the whole list the same way, and `granted` / `ask` allow and log. `CoreMenu` gets `PermissionsPort("core", handler)`.

**Defined in:** `src/assistant/core/permissions/port.py`

## `PermissionsMenu`

`PermissionsMenu(handler: PermissionsHandler)`

The grant calls as menu items: `permissions.grants`, `permissions.grant(module_id, items, subject="")`, `permissions.request(read, write, commands, python, chrome, reason)` (an agent asking for itself), `permissions.revoke(module_id, subject="", items=None)`, each knowing its caller ([the core's menu](control.md#the-cores-menu)). `App` provides it through a `MenuTools` (`app.permissions_menu_tools`) under the id `core`, and `GetMenu("core")` lists its items after `modules.*`.

**Defined in:** `src/assistant/core/permissions/menu.py`

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
| `remove(contract, impl, owner)` | Take back one provider `owner` gave; nothing if it isn't there |
| `remove_owner(owner)` | Remove everything `owner` provided |
| `get_all(contract) -> list` | All providers, possibly empty |
| `get_one(contract)` | First provider or `None` |

`allows_another(contract, current) -> bool`: the single-provider rule, in one place: whether one more module may provide `contract` given what provides it now (`contract.multiple`, or nothing yet). Used by `Container.provide`, `resolve_modules` and `LifecycleManager` (built 2026-11-08). The lifecycle's startup and runtime activation also share one init path (context, instance, `init`, menu linked; the context closed on failure).

**Defined in:** `src/assistant/core/container.py` · **Tests:** `tests/test_core_tidy.py`

## `is_shared_contract`

`is_shared_contract(t: object) -> bool`

True for `Contract` subclasses defined under `assistant.contracts` (excluding `Contract` itself).

**Defined in:** `src/assistant/core/container.py`

## `MenuTools`

`MenuTools(menu: Menu, module: ModuleProtocol)` (an `IToolProvider`)

The core's adapter from a module's [`Menu`](modules.md#menu) to `IToolProvider`, linked to one running copy. The lifecycle calls `ScopedContext.link_menu(module)` right after a module's `init` (at startup, on activate, on reload); it provides a `MenuTools` in the module's name, so closing the context removes it. `invoke` runs `menu.call`, which checks the arguments first.

**Defined in:** `src/assistant/core/tools.py`

## `dispatch_tool`

`async dispatch_tool(container: Container, command: InvokeTool, start_on_use: Callable[[str], Awaitable[Result | None]] | None = None) -> Result`

The `InvokeTool` handler. Looks up providers at call time; returns `not_available` for an unknown tool, `failed` for a name offered twice, else the provider's result.

**♻ Reusable · Used by:** every `InvokeTool` caller: `talker` (SHOW), `temp_ui` (Open in viewer), `SessionTaskAgent` (SHOW), the agents' door (`use_item`) · start on use built 2026-11-05.

**Start on use:** when nobody offers the tool, `App` passes `start_on_use=App._start_for_tool`. It finds the module that is off, has the tool on its menu, and has `start_on_use = true` in its `[modules.<id>]` config, and turns it on the same way as [`ActivateModule`](control.md#activatemodule) (`LifecycleManager.activate`, with what it requires); then the call goes ahead. A failed start answers `failed` with "The <id> module couldn't start: …" (retryable; the next call tries again). Calls that arrive while it's starting wait on the lifecycle's lock and find it on, so it starts once. A module you turned off is started again too. Today only `html_viewer` sets it.

**Defined in:** `src/assistant/core/tools.py`

## `CoreMenu`

`CoreMenu(send, permissions: ModulePermissions)`

The core's own [menu](../api/control.md#the-cores-menu) (`modules.*`), id `core` (`CORE_ID`; no module may use it). `App` builds one with the router's `send` and `PermissionsPort("core", app.permissions)` (as `app.core_menu`), and provides it through a `MenuTools` (`app.core_menu_tools`) in the name `core` from `start` to `stop`. `App` also handles `GetMenu`. Tests swap `app.core_menu.permissions` for one that refuses.

**Defined in:** `src/assistant/core/directory.py`
