# Core host (internal)

The stable host in `assistant.core`. Modules never use these directly; they go through [`ModuleContext`](modules.md#modulecontext). Listed here so nothing gets rebuilt elsewhere. Back to the [API index](README.md). Design and behavior: [core architecture](../architecture/core.md).

## `App`

`App(available: Sequence[type[ModuleProtocol]], config: dict[str, Any], config_loader: Callable[[], dict] | None = None, logs: LogSession | None = None, config_dir: str | Path | None = None)`

Wires the core together and runs the enabled modules. Construction validates the module selection. Handles `InvokeTool` (through [the ask-first gate](tools.md#the-ask-first-gate)), `ListModules`, `GetMenu`, `StartProvider`, the [module control](control.md) commands (including `ReloadModule`, `AddModule` and `RemoveModule`), `AnswerPermissionRequest` and `AddCardNotes` (the permissions handler's), `SetPermissionMode` (`_set_mode`) and `ShutdownRequested` (`_on_shutdown_requested`). A module's `ctx.config` is its own `module.toml` defaults with its `[modules.<id>]` section merged over them ([`loader.module_defaults`](#loader), [`merge`](app_kit.md#merge)); `modules.docs` reads its own `docs/` folder.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `available` | `Sequence[type[ModuleProtocol]]` | yes | Every module the app can run: `__main__` passes [`find_modules()`](#loader) |
| `config` | `dict` | yes | From [`load_config`](infra.md#load_config) |
| `config_loader` | callable | no | Re-reads the config before a reload, add or remove (`__main__` passes `load_config`) |
| `config_dir` | `str`, `Path` | no | Where your choices files are, for `RemoveModule`'s purge ([`config_folder`](infra.md#load_config): else `ASSISTANT_CONFIG_DIR`, else `config/`); the permissions handler protects it like `config/` (writes refused, reads allowed); tests pass a tmp folder |
| `logs` | `LogSession` | no | The launch's log handler; every module reaches it as `ctx.logs` through a [`SessionLogs`](#sessionlogs) (`app.logs`). Without it, `ctx.logs` gives paths under `logging.dir` |

**Raises:** [`StartupError`](#startuperror) if the enabled modules can't run together.

**Class attribute:** `PUBLISHES` (the events the core publishes: `ModuleStateChanged` and [`PermissionsHandler.PUBLISHES`](#permissionshandler), the card events `PermissionRequested`, `PermissionChanged`; `tests/test_module_docs.py` checks every `publish(X(...))` in the core is named).

**Attributes:** `router: CommandRouter`, `bus: EventBus`, `container: Container`, `menus: MenuTable` (the linked menus, core-private: [`MenuTable`](#menutable)), `callers: Callers` (the [Callers port](#callers), provided as `IAgentNames`), `door: CoreDoor` (the [module door](#coredoor-moduledoor), provided as `IModuleDoor`), `permissions: PermissionsHandler`, `generated: GeneratedFiles` (writes [`generated/`](#generatedfiles) after `start()` and on every module state change), `restart_requested: bool` (a `ShutdownRequested` asked for a restart).

| Method | Description |
|--------|-------------|
| `async run()` | `start()`, wait for shutdown (or task cancellation), then `stop()` |
| `async start()` | Register the core's handlers, add the core's menus to `menus`, provide `IAgentNames` (`callers`) and `IModuleDoor` (`door`) as `core`, open the door's server (`[core.door]`, **before any module**, so every agent's first session has it; a taken port is logged and the agents go without), then init and start modules. May raise `StartupError` |
| `async stop()` | Cancel in-flight commands, close the permissions handler, stop modules in reverse order, stop the door's server, unregister the handlers, close the bus |
| `request_shutdown()` | Make `run()` proceed to `stop()` |
| `core_specs() -> list[ToolSpec]` | Static: the core's own menu (`modules.*`, then `permissions.*`), what `GetMenu` answers for `core` and `generated/directory.json` lists |
| `offers() -> dict[str, list[str]]` | What the core offers, by name, from the tables `start` registers: `handles`, `provides`, `menu`, `publishes`. `scripts/build_docs.py` generates the [module library](../architecture/module-library.md)'s core row from it (`core_offers`, `core_line`) |

**Inside** (the handlers, listed so nothing duplicates them):

| Handler | Description |
|---------|-------------|
| `_set_mode(command: SetPermissionMode) -> Result` | Auto only when `command.sent_by` may set it (`Callers.may_set_auto`: the core or a `you` caller), else `not_available`; Manual from anyone. Finds the agent among the `ITaskAgent` providers (`invalid_arguments` if none), records the mode in `callers` first, calls `set_permission_mode`, and puts the old mode back if the agent refuses. Decision D2 |
| `_on_shutdown_requested(command: ShutdownRequested) -> Result` | Logs `sent_by` and the reason, sets `restart_requested` with `restart`, calls `request_shutdown()`; `ok`. Decision D5: a command, so it has one handler and a known sender |

**Config:** `[core.door]` `enabled` (true), `host` (`127.0.0.1`), `port` (0: any free); `[core.permissions]` `you` (`["temp_ui"]`), `relays` (`["talker"]`), and the handler's keys ([`PermissionsHandler`](#permissionshandler)).

**Defined in:** `src/assistant/core/app.py`

## `Callers`

**♻ Reusable · Used by:** `App` (provided as [`IAgentNames`](agents.md#iagentnames), owner `core`); every module through `IAgentNames` (`ProfileAgent`, `task_agents`, `talker`, `agent_hub`, `SessionTaskAgent`); `ScopedContext` (`you`, `relays`); `PermissionsHandler` (`mode_of=callers.mode`); `CoreDoor` (`claims`) · decision D2

`Callers(module_ids: Callable[[], Iterable[str]], you: Iterable[str] = (), relays: Iterable[str] = (), reserved: frozenset[str] = RESERVED_AGENT_IDS)` (an `IAgentNames`)

The Callers port: who calls, as the core knows them, in one list. `module_ids()`: the ids of every known module, on or off (refused as agent ids). `RESERVED_AGENT_IDS = {"core", "hub", "talker"}`.

| Member | Description |
|--------|-------------|
| `claims: dict[str, str]` | Agent id → owning module. In the core, so a Hub reload keeps them |
| `async check(agent_id, owner)`, `async claim(agent_id, owner)`, `release(agent_id, owner)`, `taken()` | `IAgentNames`' names: [`check_agent_id`](infra.md#agent_names), then who holds the id; a taken id names a free one ([`free_agent_id`](infra.md#agent_names)). `release` also resets the agent's mode to Manual |
| `mode(agent_id) -> PermissionMode` | The agent's mode, Manual unless set |
| `set_mode(agent_id, mode)` | Core only (`App._set_mode`): only non-Manual modes are kept |
| `you`, `relays` | `[core.permissions] you` (you clicking in a UI) and `relays` (modules that pass your answer to a card; never Auto, G17) |
| `is_you(caller) -> bool` | `caller in you`. Trusted by module id, not by the folder the code came from |
| `may_set_auto(sender) -> bool` | Auto comes only from `"core"` or a `you` caller; never from a relay |

**Defined in:** `src/assistant/core/callers.py` · **Tests:** `tests/test_callers.py`, `tests/test_agent_names.py`

## `CoreDoor`, `ModuleDoor`

**♻ Reusable · Used by:** `App` (`app.door`, provided as [`IModuleDoor`](tools.md#imoduledoor)); every module that asks for a door config (`ProfileAgent`, `talker`), each through its own `ModuleDoor` · decision D1

`CoreDoor(server: DoorServer, claims: Callable[[], dict[str, str]])` · `ModuleDoor(door: CoreDoor, module_id: str)` · `CORE_LINE`

The module door, hosted by the core as part of the Tools port. `CoreDoor` holds the [`DoorServer`](infra.md#mcp_door) (its calls go to the router as the core's own sends: `ListModules`, `GetMenu`, `InvokeTool` with the caller its token proved, so a door call goes router → gate like a module's own) and who may ask for whose config.

| Member | Description |
|--------|-------------|
| `CoreDoor.mcp_config(caller)` | The core's own call, unchecked (the core and tests: `app.container.get_one(IModuleDoor)`) |
| `CoreDoor.may_ask(module_id, caller) -> bool` | Whether `module_id` may get a config for `caller`: the module itself, or an agent id it claimed in the Callers port (G11) |
| `CoreDoor.for_module(module_id) -> ModuleDoor` | The door as one module sees it. `ScopedContext.get_one` / `get_all` hand it out instead of the core's door |
| `ModuleDoor.mcp_config(caller)` | `may_ask`, then the core's config; for anyone else a warning ("… isn't it or an agent it claimed: refused") and `{}` |
| `CORE_LINE` | The directory line for the core's own menu (`{"id": "core", ...}`: "Module control and permissions: list, menu, docs, on, off, reload, add, remove; permissions.*"), added to `list_modules`; a test checks it names every core menu item |

**Defined in:** `src/assistant/core/door.py` · **Tests:** `tests/test_mcp_door.py`

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
| `async deactivate(module_id, with_dependents=False) -> Result` | Runtime deactivation, never refused (the value names the modules left on that need it); see [`DeactivateModule`](control.md#deactivatemodule) |
| `async reload(module_id) -> Result` | Swap a module's code, with rollback; see [`ReloadModule`](control.md#reloadmodule) |
| `async add(package, activate=True) -> Result` | Load a new module; see [`AddModule`](control.md#addmodule). It doesn't check for the same id in another module folder (that check runs only at startup) |
| `async remove(module_id) -> Result` | Off, then out of the module list for this run; never refused: the value lists the active modules that need it and stay on. `App` adds the settings purge; see [`RemoveModule`](control.md#removemodule) |
| `module_class(module_id) -> type` | The module's current class, on or off (the new one after a reload). `KeyError` if unknown. `App` uses it to find the module's folder (its `module.toml` and `docs/`) |

**Defined in:** `src/assistant/core/lifecycle.py`

## `loader`

Functions for finding the modules by folder and loading a module's code fresh. Generic: they know no module by name.

| Function | Description |
|----------|-------------|
| `find_modules(root="assistant.modules", folders=()) -> list[type[ModuleProtocol]]` | Every module under `root`, sorted by folder: one per sub-package whose one `ModuleProtocol` class has the folder's name as its id. A bad folder is skipped with a warning; `_` folders are ignored. `folders` (the outside module folders, `configured_module_folders`) go on `root`'s path first (`add_module_folders`); then the modules' `app/` folders on the import path (`add_app_folders`). Also exported as `assistant.core.find_modules`; `__main__` passes the configured folders |
| `configured_module_folders(config) -> list[Path]` | `[core] module_folders` (`MODULE_FOLDERS_KEY`): the folders holding module folders outside the repo, `~` expanded and resolved; `[]` when unset. `LoadError` unless it's a list of absolute paths. Also exported as `assistant.core.configured_module_folders` |
| `add_module_folders(folders, root="assistant.modules") -> list[Path]` | ♻ **Reusable** · Used by: `find_modules` (startup), the root `conftest.py`, `scripts/build_docs.py` (`module_dirs`). Appends each folder to `root`'s package path once, after the repo's, so its modules import as `<root>.<id>` and every lookup by folder (`app_folders`, `module_folder`, reload, `AddModule`, `infra.module_roots`) sees them; returns the folders added now. `LoadError` for a folder that doesn't exist, or one holding a module id another folder of `root` already has (refused, never shadowed). Runs at startup only |
| `app_folders(root="assistant.modules") -> list[Path]` | Every module's `app/` folder (`APP_FOLDER`), found by folder with no names, resolved and sorted: where the modules' companion apps' packages live (`cv/app/cv_tool`) |
| `add_app_folders(root="assistant.modules") -> list[Path]` | ♻ **Reusable** · Used by: `find_modules` (startup), `import_fresh` (a reload or `AddModule`), the root `conftest.py` (the test setup). Appends each `app/` folder to `sys.path` once, so an app's package imports by its own name; returns the folders added now. Also exported as `assistant.core.add_app_folders`. A launch passes the folder on with [`launch_env`](app_kit.md#companionapp) |
| `check_folder(cls, package, root="assistant.modules")` | Raises `LoadError` if a package directly under `root` holds a module with another id. `AddModule` uses it too |
| `package_of(cls) -> str` | The package a module class lives in |
| `module_folder(cls) -> Path \| None` | The folder of that package, where the module keeps its own config defaults and docs; `None` if it can't be found |
| `module_defaults(cls) -> dict` | The module's own config defaults, `module.toml` in its folder, read fresh each time (a reload picks up new defaults). `{}` if none; an unreadable file is logged and counts as none. `App` merges the `[modules.<id>]` section over it for `ctx.config` |
| `apply_module_toml(cls) -> type` | Puts the manifest keys of the module's `module.toml` (`MANIFEST_KEYS`: `needs`, `packages`, each a list of strings) on its manifest; a key the file doesn't have leaves that field as it is. `LoadError` for a value that isn't a list of strings, or one the manifest refuses. Used by `find_module_class` and `resolve_modules` |
| `check_reloadable(package)` | Raises `LoadError` for shared code (`assistant.core`, `.contracts`, `.infra`, `.testkit`, `app_kit`), `assistant` / `assistant.modules` themselves, or a top-level name |
| `drop(package) -> dict` | Remove the package and its submodules from `sys.modules` (and their `__pycache__`); returns them |
| `restore(package, removed)` | Put back what `drop` removed |
| `import_fresh(package)` | Import from source (a new module's `app/` folder on the path first); a missing contract becomes `LoadError` ("needs a restart") |
| `find_module_class(package, module_id=None)` | The one `ModuleProtocol` subclass the package exports, with its `module.toml` keys applied (`apply_module_toml`) |

**Defined in:** `src/assistant/core/loader.py`

## `ScopedContext`

`ScopedContext(manifest, router, bus, container, config, log, handover=None, logs=None, permissions=None, you=(), relays=(), menus=None)`

The [`ModuleContext`](modules.md#modulecontext) implementation. Records every subscription, handler, provided contract and linked menu made through it. Sets the module's [`ctx.permissions`](modules.md#modulecontextpermissions) to `permissions`: `App` passes a [`PermissionsPort`](#permissionsport) bound to the module's id and the app's handler (without one, a bare `PermissionsPort(module_id)`). Sets its [`ctx.logs`](modules.md#modulecontextlogs) to the app's `SessionLogs` (a default one if none is given). `you` and `relays`: the Callers port's (`App` passes `callers.you` / `callers.relays`), for the control-command check. `menus`: the app's [`MenuTable`](#menutable) (a fresh one if none).

| Method | Description |
|--------|-------------|
| `send(command, timeout=None)` | Strict and stamped (decision D3): a type not in `manifest.sends` → `invalid_arguments` and an error log; a control command (`CONTROL`) from a caller it doesn't allow → `failed`; then `sent_by` (and an `InvokeTool`'s `caller`) set to the module's id. These checks run here, before the router. The table: [`ModuleContext.send`](modules.md#modulecontextsend) |
| `publish(event)` | Strict: a type not in `manifest.publishes` is dropped with an error log; a `ModuleEvent` raises `ValueError` (only `publish_named`, G15) |
| `link_menu(module)` | Core only: add the module's menu to the `MenuTable` (never the container, G16), until close |
| `get_one(contract)`, `get_all(contract)` | The container's providers; the core's `CoreDoor` comes back as this module's `ModuleDoor` (`_scoped`) |
| `withdraw(contract, impl)` | Take back one provider this module gave ([`Container.remove`](#container)); nothing once closed |
| `close()` | Remove everything this module registered, its own menus from the table among them (safe across a reload) |

**`CONTROL`** (module constant): control command type → who else may send it besides `you` (`RELAY`: a `relays` module; `AGENT`: a module that provides `ITaskAgent`). `DeactivateModule`, `RemoveModule`: nobody else; `AnswerPermission`, `AnswerPermissionRequest`: relays; `ReloadModule`, `AddModule`: a task agent's module. `ActivateModule`, `CancelTask`, `SetPermissionMode` and `ShutdownRequested` are left out on purpose (the reasons are in the module's comment and [`ModuleContext.send`](modules.md#modulecontextsend)).

**Undeclared uses are logged** (principle 17). A `subscribe`, `subscribe_named` or `publish_named` not in the manifest's `listens`, `listens_named` or `publishes_named`, or a `get_one` / `get_all` of a contract not in `provides`, `requires`, `optional` or `uses`, still works but logs one warning per type (`<id> uses <Type> without declaring it in its manifest (...)`), so the manifest gets fixed. `handle` and `provide` are strict (they raise), and so are `send` and the typed `publish` (above).

**Defined in:** `src/assistant/core/context.py` · **Tests:** `tests/test_honest_manifests.py`, `tests/test_sender_checks.py`

## `SessionLogs`

`SessionLogs(session: LogSession | None = None, root: str | Path = "logs")` (a `ModuleLogs`)

The `ctx.logs` port. With a `LogSession`, `folder()` and `sink(name)` are the session's; without one (tests), `folder()` is `root` and `sink(name)` is `root / name`. `App` builds one for every module from its `logs` argument and `logging.dir`.

**Defined in:** `src/assistant/core/logs.py`

## `GeneratedFiles`

`GeneratedFiles(folder: Path | None, lifecycle: LifecycleManager, core_specs: Callable[[], list[ToolSpec]])`

Writes the core's [generated files](../architecture/core.md#generated-files): `modules.json`, `directory.json` and `dependencies.json`, each with a `_generated` note key. `App` builds one from `[core] generated_dir` (`app.generated`) and calls `write()` after startup and on every module state change.

| Method | Description |
|--------|-------------|
| `from_config(generated_dir, lifecycle, core_specs)` | Class method: the folder relative to the repo unless absolute; empty or `None` for no folder (`folder` is `None`, nothing written) |
| `write()` | Rewrite the three files, each atomically (temp file, then replace); creates the folder if it was deleted. A failure is logged, never raised |
| `contents() -> dict[str, dict]` | Each file's name and JSON content, from `lifecycle.modules()`, `menu(id)`, `module_class(id).manifest` and the core's menu |

**Defined in:** `src/assistant/core/generated.py` · **Tests:** `tests/test_generated.py`

## `PermissionsHandler`

`PermissionsHandler(send, publish, find, grants_file=GRANTS_FILE, reviewer=REVIEWER, review_timeout=90.0, answer_timeout=600.0, you=YOU, log=None, mode_of=None)` (`REVIEWER = ""`, `YOU = ()`: the core names no module, principle 21; `config/default.toml` sets `reviewer = "main_assistant"` and `you = ["temp_ui"]` under `[core.permissions]`) · `PermissionsHandler.from_config(config, send, publish, find, mode_of=None)`

The [permissions handler](../architecture/permissions.md#part-of-the-core), part of the core and always on. `send`, `publish`, `find`: the router's `send`, the bus's `publish` and the container's `get_one`; it uses nothing else of the app and imports no module. `mode_of`: each agent's mode, from the [Callers port](#callers) (`App` passes `callers.mode`; none given: everyone is in Manual). `_in_auto(caller)` reads it, never `ListAgents`, so it works with the Hub off. `App` builds it from `[core.permissions]` (every key optional: `grants_file`, `reviewer`, `review_timeout`, `answer_timeout`, `you`) as `app.permissions`, handles `AnswerPermissionRequest` with `answer` and `AddCardNotes` with `add_notes`, passes `confirm` to `dispatch_tool`, and calls `close()` in `stop()`.

| Method | Description |
|--------|-------------|
| `async request_set(module_id, subject, items, reason="", wait=False) -> tuple[AccessItem, ...]` | What `ctx.permissions.request_set` forwards. The saved grant when the fingerprint matches; otherwise a card (refusals, rule warnings, the review, then `PermissionRequested`). `wait=False` raises `AccessPending` and turns the module on after Allow; `wait=True` awaits your answer. Raises `AccessDenied` on Deny or no answer |
| `async answer(cmd: AnswerPermissionRequest) -> Result` | Your answer to an open card. `invalid_arguments` for no such card, or a `keep` key not on it |
| `async confirm(module_id, caller, what, step, reason="", wait=False, risky=False) -> Result` | A `confirm` card before a risky step (`step`: a `Command` it sends itself, so its sender is the core, or an async callable returning a `Result`). A `you` caller runs at once; `risky` also for a caller in Auto; otherwise a card, which **Auto never skips**. `wait=False`: `ok("Asked the user on a card (<id>) to confirm <what>; the answer reaches you as a note")` at once, and the outcome goes to `caller` as an `AgentNotice`. `wait=True`: the step's `Result`, or `failed` on Deny / no answer; cancelling closes the card |
| `async add_notes(cmd: AddCardNotes) -> Result` | A review's outcome for a card waiting on it; `invalid_arguments` when none waits. Decision D6 |
| `grants() -> list[dict]` | Every saved grant and every list waiting on a card: `module_id`, `subject`, `granted`, `labels`, `asked`, `denied`, `date`, `matches`, `waiting` |
| `async grant(module_id, keys, subject="", caller="") -> Result` | Widen a grant with asked-for keys. From `you`: applied (a module that's off is turned on). From an agent: a card, and the answer reaches it as an `AgentNotice` |
| `async revoke(module_id, subject="", keys=None, caller="") -> Result` | Take back all or some items; the module turns off and its running tasks are cancelled. A revoke of only `message:` items keeps the module on ("it stays on, and the next message asks again"). From an agent: a card first |
| `kind_of(agent_id) -> str` | The subject an agent's grants are saved under: its kind (from `own_agent`; `helper_2` → `helper`), else its id |
| `granted(module_id, agent_id, item) -> bool` | Whether `module_id`'s saved grant for the agent's kind holds `item` (and isn't denied) |
| `async ask(module_id, agent_id, item, reason="") -> bool` | A one-item `message` card (Allow once · Always allow · Deny), awaited; True at once if granted. Allow once saves nothing; Always adds the item to the grant for the agent's kind. Cancelling the call closes the card. Used by the Agent Hub's message gate |
| `open_cards() -> int` | How many cards are open |
| `async close()` | Cancel open cards (each settles as denied) |

**Card actions.** A card's action is a `CardAction` (`ACCESS`, `GRANT`, `REVOKE`, `MESSAGE`, `CONFIRM`; a `StrEnum` inside the core whose values are `PermissionRequested.action`'s). An answered card is applied by its action's handler from a table (principle 20): `access` saves the list (and turns the module on); `grant` and `revoke` carry out an agent's call and tell it with an `AgentNotice`; `message` settles the waiting `ask` (`_apply_message`, with `Card.remember` from the answer); `confirm` runs the step on Allow, nothing on Deny, and tells you and the caller (`_apply_confirm`, `_run_step`). Every `PermissionChanged` is built in one place. Notices go through `_notify`: an `AgentNotice` command (`source="permissions"`); with no Hub it only logs.

**The review is a listener's job** (decision D6). `_review` sends [`ReviewAccessList`](messaging.md#reviewaccesslist) (sender: the core) with the card's labels and warnings, and waits up to `review_timeout` + `REVIEW_GRACE` (5 s) for [`AddCardNotes`](messaging.md#addcardnotes); it keeps at most `MAX_REVIEW_LINES` (8) notes, `source="review"`. `not_available` (no Hub, or the reviewer is busy) shows the card "not reviewed" at once. **The core never starts a task.** It does cancel one: `_stop_tasks` sends `GetTaskStatus` / `CancelTask` when a revoke turns a module off.

Saved grants: `GrantStore` and `Grant` (`store.py`), one section per module and subject in `config/permissions.toml` (`GRANTS_FILE`; gitignored), written whole and atomically; `copy_old_grants(new, old)` copies the old `data/permissions.toml` (`OLD_GRANTS`) across once at startup when the new file is missing, leaving the old one in place; `fingerprint(items)` hashes a list's keys. Guardrails: `PROTECTED`, `refusals`, `rule_warnings` and `FIXED_RULES` (`rules.py`).

**Defined in:** `src/assistant/core/permissions/handler.py` (`store.py`, `rules.py`) · **Tests:** `tests/test_permissions_handler.py`, `tests/test_permissions.py`, `tests/test_risky_steps_ask.py`, `tests/test_review_listener.py`, `tests/test_auto_skips_cards.py`

## `PermissionsPort`

`PermissionsPort(module_id: str, handler: PermissionsHandler | None = None)` (a `ModulePermissions`)

Each module's [`ctx.permissions`](modules.md#modulecontextpermissions), bound to its id, so no module asks in another's name. `request_set` forwards to the handler with the module id (and `subject`, default the module id). `has` and `request` aren't checked: they return `True`, and the first use of each name logs a warning on `assistant.core.permissions` ("not checked yet: allowing voice_in microphone (You clicked the mic)"), later ones at debug. `granted`, `ask` and `confirm(what, action, caller="", reason="", wait=False, risky=False)` forward with the module id too (`confirm`'s `caller` defaults to the module). Without a handler (a bare context in a test), `request_set` allows the whole list the same way, `granted` / `ask` allow and log, and `confirm` logs and runs the step (a callable; a `Command` gives `not_available`, there's no router). `CoreMenu` gets `PermissionsPort("core", handler)`.

**Defined in:** `src/assistant/core/permissions/port.py`

## `PermissionsMenu`

`PermissionsMenu(handler: PermissionsHandler)`

The grant calls as menu items: `permissions.grants`, `permissions.grant(module_id, items, subject="")`, `permissions.request(read, write, commands, python, chrome, reason)` (an agent asking for itself), `permissions.revoke(module_id, subject="", items=None)`, each knowing its caller ([the core's menu](control.md#the-cores-menu)). Their cards are their own code's (not `ask` marks). `App` adds it to the `MenuTable` through a `MenuTools` (`app.permissions_menu_tools`) under the id `core`, and `GetMenu("core")` lists its items after `modules.*`.

**Defined in:** `src/assistant/core/permissions/menu.py`

## `CommandRouter`

`CommandRouter(default_timeout: float = 30.0, timeouts: dict[str, float] | None = None)`

`timeouts` maps command class names to per-type timeouts.

| Method | Description |
|--------|-------------|
| `register(command_type, handler)` | Set the single handler. Raises `ValueError` if one exists |
| `unregister(command_type, handler)` | Remove it, only if it's still the registered handler |
| `async send(command, timeout=None) -> Result` | Run the handler as a task; map every outcome to a `Result` (see [commands](../architecture/communication.md#commands)). A command whose `sent_by` is empty is stamped `"core"` (the core's own sends, the door's, tests' `app.router.send`). The `sends` and control checks are the module's context's, not the router's |
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

`allows_another(contract, current) -> bool`: the single-provider rule, in one place: whether one more module may provide `contract` given what provides it now (`contract.multiple`, or nothing yet). Used by `Container.provide`, `resolve_modules` and `LifecycleManager`. The lifecycle's startup and runtime activation also share one init path (context, instance, `init`, menu linked; the context closed on failure). Menus are not in the container: they are in the [`MenuTable`](#menutable).

**Defined in:** `src/assistant/core/container.py` · **Tests:** `tests/test_core_tidy.py`

## `is_shared_contract`

`is_shared_contract(t: object) -> bool`

True for `Contract` subclasses defined under `assistant.contracts` (excluding `Contract` itself).

**Defined in:** `src/assistant/core/container.py`

## `MenuTools`

`MenuTools(menu: Menu, module: ModuleProtocol)` (an `IToolProvider`)

The core's adapter from a module's [`Menu`](modules.md#menu) to `IToolProvider`, linked to one running copy. The lifecycle calls `ScopedContext.link_menu(module)` right after a module's `init` (at startup, on activate, on reload); it adds a `MenuTools` to the app's [`MenuTable`](#menutable), and closing the context removes exactly that one. `invoke` / `invoke_as` run `menu.call`, which checks the caller and the arguments first. `item(name) -> MenuItem | None`: one item, for the gate's `ask`.

**Defined in:** `src/assistant/core/tools.py`

## `MenuTable`

**♻ Reusable · Used by:** `App` (`app.menus`, with the core's two menus), `ScopedContext` (`link_menu`, `close`), `dispatch_tool` · G16

`MenuTable()`

The core-private table of linked menus: `InvokeTool` reaches them, nothing else does. Menus are never in the container, so no module can call one as a plain `IToolProvider` with a caller of its choosing. Each context removes exactly what it added, so a reload's old copy never takes the new copy's menu with it.

| Method | Description |
|--------|-------------|
| `add(tools: MenuTools)` | Link one menu |
| `remove(tools: MenuTools)` | Unlink it; nothing if it isn't there |
| `all() -> list[MenuTools]` | Every linked menu, in the order added |

**Defined in:** `src/assistant/core/tools.py` · **Tests:** `tests/test_menu.py`, `tests/test_mcp_door.py`

## `dispatch_tool`

`async dispatch_tool(container: Container, menus: MenuTable, command: InvokeTool, start_on_use: Callable[[str], Awaitable[Result | None]] | None = None, off_owner: Callable[[str], str | None] | None = None, confirm: Confirm | None = None) -> Result`

The `InvokeTool` handler. Looks up providers at call time, in `menus` and among the container's `IToolProvider`s (modules that provide it themselves still count); returns `not_available` for an unknown tool, `failed` for a name offered twice, else the provider's result. `off_owner`: the id of a module that is off and has the tool on its menu, so the answer is "The <id> module isn't on …" (`module_off_text`).

**`confirm`** (decision D4): the one [ask-first gate](tools.md#the-ask-first-gate). `Confirm = Callable[[caller, what, run, risky], Awaitable[Result]]`. For an item whose `MenuItem.asks(args)` is true, the arguments and `callers` are checked first (a bad call never reaches a card), then `confirm(caller, "<name> (<k>: <v>, …)", run, item.ask == "risky")`. For any other menu item, `Menu.call` makes the same checks. Start on use (below) runs before these checks, so a caller the item's `callers` refuses can still switch an off `start_on_use` module on. `App` passes `lambda caller, what, run, risky: app.permissions.confirm("core", caller, what, run, risky=risky)`.

**♻ Reusable · Used by:** every `InvokeTool` caller: `talker` (the Hub's menu), `temp_ui` (its menu calls), the agents' door (`use_item`). Pages (SHOW, Open in viewer) go through [`IPageOpener`](modules.md#ipageopener) instead, and their start on use is [`StartProvider`](control.md#startprovider) (by contract, the same `App._start_on_use`).

**Start on use:** when nobody offers the tool, `App` passes `start_on_use=App._start_for_tool`. It finds the module that is off, has the tool on its menu, and has `start_on_use = true` in its `[modules.<id>]` config, and turns it on the same way as [`ActivateModule`](control.md#activatemodule) (`LifecycleManager.activate`, with what it requires); then the call goes ahead. A failed start answers `failed` with "The <id> module couldn't start: …" (retryable; the next call tries again). Calls that arrive while it's starting wait on the lifecycle's lock and find it on, so it starts once. A module you turned off is started again too. Only `html_viewer` sets it. `StartProvider` uses the same search (`App._start_on_use`), matching a contract in `manifest.provides` instead of a tool on the menu.

**Defined in:** `src/assistant/core/tools.py` · **Tests:** `tests/test_risky_steps_ask.py`, `tests/test_start_on_use.py`

## `CoreMenu`

`CoreMenu(send, permissions: ModulePermissions, docs=None)`

The core's own [menu](../api/control.md#the-cores-menu) (`modules.*`), id `core` (`CORE_ID`; no module may use it). `App` builds one with the router's `send`, `PermissionsPort("core", app.permissions)` and its module-docs reader (as `app.core_menu`), and adds it to the `MenuTable` through a `MenuTools` (`app.core_menu_tools`) in the name `core` from `start` to `stop`. `App` also handles `GetMenu`. `modules.add`, `modules.remove`, `modules.reload` are marked `ask="always"` and `modules.off` `ask="always", ask_when="with_dependents"`: the gate asks, and the items' own code asks nothing. Each item sends its control command as `core`, so the gate's card, not the control-command check, is what stands between an agent and the command; `modules.off` without dependents shows no card.

**Defined in:** `src/assistant/core/directory.py`
