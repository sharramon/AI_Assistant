# Module control

Turning modules on and off while the app runs. The core handles these commands. A module sends one only if its manifest lists it in `sends`, and its sender is stamped ([`Command.sent_by`](messaging.md#command)).

**Control commands** ([D3](../architecture/decisions.md#decided)): `DeactivateModule`, `ReloadModule`, `AddModule` and `RemoveModule` here, plus the card answers `AnswerPermission` and `AnswerPermissionRequest`. Who may send them:

- the core, and a caller that is you (`[core.permissions] you`, `temp_ui`), may send any of them;
- a relay (`[core.permissions] relays`, the Talker) may send the two card answers;
- a module that provides `ITaskAgent` may send `ReloadModule` / `AddModule`, which it does after your Allow on its agent's own card ([the table](modules.md#modulecontextsend));
- anyone else gets `failed`.

`ListModules`, `GetMenu`, `ActivateModule` and `StartProvider` aren't control commands. Agents reach all of them through [the core's menu](#the-cores-menu), whose risky items ask you first. The menu sends its command as the core, so through the menu the control-command check is not what guards a step: the item's card is. `modules.off` without dependents has no card, so any agent can turn a module off. All items: `from assistant.contracts import ...`. Back to the [API index](README.md). How it works: [runtime module control](../architecture/core.md#runtime-module-control).

Every module found at startup is **available**; `modules.enabled` in config only sets which are active at startup.

## `ListModules`

`ListModules()` (command)

The module directory: every available module, one line each (its id, one-line description and current state).

**Returns:** `Result.ok(list[ModuleInfo])`, in the order the modules were found (by folder name, `find_modules`).

**Example**

    result = await ctx.send(ListModules())
    active = [m.id for m in result.value if m.state is ModuleState.ACTIVE]

**Defined in:** `src/assistant/contracts/control.py`

## `GetMenu`

`GetMenu(module_id: str)` (command)

One module's menu: the second step of the directory. Read from the module's class, so it works while the module is off; its items are called with [`InvokeTool`](tools.md#invoketool), which needs the module on. `module_id="core"` gives the core's own menu (below).

**Returns**
| Status | When |
|--------|------|
| `ok` | Value: `list[ToolSpec]`, in the order declared; empty if the module has no menu |
| `invalid_arguments` | No module has that id |

**Example**

    specs = (await ctx.send(GetMenu(module_id="html_viewer"))).value
    result = await ctx.send(InvokeTool(name=specs[0].name, args={"path": "docs/html/index.html"}))

**Defined in:** `src/assistant/contracts/control.py`

## The core's menu

Module control as menu items, under the id `core` (`GetMenu(module_id="core")`), called with `InvokeTool` like any module's items. Each `modules.*` item sends the matching command above, so results and errors are the same.

| Item | Arguments | Sends | Asks first |
|------|-----------|-------|------------|
| `modules.list` | none | `ListModules` | no |
| `modules.menu` | `module_id` | `GetMenu` | no |
| `modules.docs` | `module_id` | (the core reads the module's own `docs/` folder) | no |
| `modules.on` | `module_id` | `ActivateModule` | no |
| `modules.off` | `module_id`, `with_dependents` (false) | `DeactivateModule` | with `with_dependents` (`ask="always", ask_when="with_dependents"`) |
| `modules.reload` | `module_id`, `now` (false) | `ReloadModule` | yes (`ask="always"`) |
| `modules.add` | `package`, `activate` (true) | `AddModule` | yes (`ask="always"`) |
| `modules.remove` | `module_id`, `settings` (`"keep"` or `"purge"`, required) | `RemoveModule` (`purge` when `"purge"`) | yes (`ask="always"`) |
| `permissions.grants` | none | (the handler) | no |
| `permissions.grant` | `module_id`, `items` (keys), `subject` | (the handler) | from an agent in Manual: your card |
| `permissions.request` | `read`, `write`, `commands` (lists), `python`, `chrome`, `reason` | (the handler) | from an agent in Manual: your card |
| `permissions.revoke` | `module_id`, `subject`, `items` (keys; none: all) | (the handler) | from an agent in Manual: your card |

`modules.docs` returns the module's own docs, on or off: a list of `{"title", "path"}`, one per page in its folder's `docs/` (order and titles from [`module_docs`](app_kit.md#module_docs)), `[]` if it ships none, `invalid_arguments` for an unknown id. An agent learns what a module does from the module itself: its menu, then these pages.

"Asks first" for `modules.*` is the core's [ask-first gate](tools.md#the-ask-first-gate). The items are marked `ask="always"`, so every agent caller, in Manual **or Auto**, gets a `confirm` card ([`PermissionRequested`](messaging.md#permissionrequested), `action="confirm"`) naming the call and its arguments (`modules.remove (module_id: weather, settings: purge)`). A caller that is you (`temp_ui`) runs at once. The call answers at once: "Asked the user on a card (<id>) to confirm …; the answer reaches you as a note". On Allow the core runs it and the outcome reaches the caller as a note ([`AgentNotice`](agents.md#agentnotice)); on Deny nothing runs. The items' own code asks nothing. Through `InvokeTool` a call is capped by its timeout (30 s by default); a reload or add that takes longer still finishes, and `ModuleStateChanged` reports it.

The `permissions.*` items are the [permissions handler](../architecture/permissions.md#managing-grants)'s grant calls ([`PermissionsMenu`](core.md#permissionsmenu)):

- `permissions.grants` lists the saved grants per module and subject (the kind of agent): what was granted, the date, and whether the current list still matches.
- `permissions.grant` widens a grant with asked-for items. A module that's off is turned on; one that's on takes it live (from its agents' next session, at once when idle).
- `permissions.request` is an agent asking for more access for itself. Its module and subject come from its id, and folders are resolved. On Allow the items join its grant as added items, and a running agent takes them live. An agent with no access list (the Main Assistant) gets `not_available`.
- `permissions.revoke` takes back all or some items. The module turns off right away and its running tasks are stopped, except for a revoke of only `message:` items, which leaves it on.

From you (a UI you click in, `temp_ui` by default), or from an agent in Auto, they apply at once. From an agent in Manual they show you a card, and the answer reaches the agent as a note.

**Defined in:** `src/assistant/core/directory.py`, `src/assistant/core/permissions/menu.py` · **Tests:** `tests/test_directory.py`, `tests/test_risky_steps_ask.py`, `tests/test_auto_skips_cards.py`

## `ActivateModule`

`ActivateModule(module_id: str)` (command)

Turn a module on: a fresh instance, then `init` and `start`.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `module_id` | `str` | yes | The module's manifest id |

**Returns**
| Status | When |
|--------|------|
| `ok` | It's active (or already was). Any sole provider of a contract it `requires` was activated first |
| `invalid_arguments` | No module has that id |
| `not_available` | It requires a contract that no available module provides |
| `failed` | Several modules could provide a required contract (the error lists them; activate one first), it would be a second provider of a single-provider contract, a required provider failed, a circle of `needs`, or its own `init`/`start` raised. In the last case its state is `failed` and it can be retried. A module it `needs` that fails doesn't fail it: that's logged, and it turns on anyway |
| `timed_out` | The command timed out; the activation still finishes, and `ModuleStateChanged` reports the outcome |

**Example**

    result = await ctx.send(ActivateModule(module_id="voice_output"))
    if not result.is_ok:
        ctx.log.warning("Couldn't enable voice output: %s", result.error)

**Defined in:** `src/assistant/contracts/control.py`

## `StartProvider`

`StartProvider(contract: str)` (command)

Start on use, by contract: turn on the module that is off, declares `contract` (a contract's class name, e.g. `"IPageOpener"`) in its `manifest.provides`, and has `start_on_use = true` in its config, the same way as `ActivateModule`. A caller names a contract, never a module, so no core module names an add-on. Sent by [`open_page`](infra.md#show_page) when no [`IPageOpener`](modules.md#ipageopener) is on.

**Returns**
| Status | When |
|--------|------|
| `ok` | The module started; look the contract up again |
| `not_available` | No module qualifies: none provides it, it's already on, or its config doesn't allow start on use |
| `failed` | The module couldn't start (`The <id> module couldn't start: …`, retryable) |

**Defined in:** `src/assistant/contracts/control.py` (command), `src/assistant/core/app.py` (`App._start_provider`) · **Tests:** `tests/test_start_on_use.py`

## `DeactivateModule`

`DeactivateModule(module_id: str, with_dependents: bool = False)` (command)

Turn a module off: `stop`, then everything it registered is removed. Its tools, handlers, and contracts disappear. **Never refused:** the modules that need it (`needs`, or a contract only it provides) stay on, and the result's value names them. A later call to one of its menu items answers `not_available` with "The <id> module isn't on … use modules.on" (see [`InvokeTool`](tools.md#invoketool)).

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `module_id` | `str` | yes | The module's manifest id |
| `with_dependents` | `bool` | no | Also deactivate the active modules that need it or require something only this one provides (they go first). `modules.off` asks you first |

**Returns**
| Status | When |
|--------|------|
| `ok` | It's inactive (or already was). With modules left on that need it, the value says so: `"voice_in is off; voice_notes needs it and stays on"`; otherwise `None` |
| `invalid_arguments` | No module has that id |

**Defined in:** `src/assistant/contracts/control.py`

## `ReloadModule`

`ReloadModule(module_id: str, now: bool = False)` (command)

Swap a module's code while the app runs: stop it, import its package fresh (with every submodule), re-read its config section, start the new code. Active modules that require something only it provides are stopped and started around it. If the module says it's [`busy`](modules.md#moduleprotocolbusy), the reload waits until it isn't (up to `core.reload_idle_timeout`, 300 s), unless `now`, which cuts in. The old instance's [`export_state`](modules.md#moduleprotocolexport_state) reaches the new one as `ctx.handover`. How it works: [reloading](../architecture/core.md#reloading-a-modules-code).

**Returns**
| Status | When |
|--------|------|
| `ok` | The new code runs (or is loaded, if the module was inactive) |
| `invalid_arguments` | No module has that id |
| `failed` | Its code is shared (core, contracts, `infra`, `app_kit`) or not in its own package; it stayed busy past `core.reload_idle_timeout` (the error says why, and to use `now`); or the new code failed to import, `init`, or `start`. Then the old code is put back and started, and the error says so |

**Example**

    result = await ctx.send(ReloadModule(module_id="voice_in"))

**Defined in:** `src/assistant/contracts/control.py`

## `AddModule`

`AddModule(package: str, activate: bool = True)` (command)

Load a module that wasn't there at launch, from its package, and activate it unless `activate` is false. Its package must export exactly one `ModuleProtocol` subclass; under `assistant.modules`, its folder must be named with its id, else it fails. The next launch finds it by folder; add it to `modules.enabled` to start it then.

**Returns**
| Status | When |
|--------|------|
| `ok` | Value: the new module's id |
| `failed` | Already loaded (use `ReloadModule`), an id that's taken, an import error, or its code needs a contract the running app doesn't have: new contracts and port types need a restart |

**Example**

    result = await ctx.send(AddModule(package="assistant.modules.weather"))

**Defined in:** `src/assistant/contracts/control.py`

## `RemoveModule`

`RemoveModule(module_id: str, purge: bool = False)` (command)

Remove a module from this run: turn it off if it's on, and take it out of the module list, so `ListModules` and `GetMenu` don't offer it until [`AddModule`](#addmodule) loads it again. Sent by the core's `modules.remove`, which asks first. How it works: [runtime module control](../architecture/core.md#runtime-module-control).

- **Never refused while needed:** the active modules that `need` it or require something only it provides stay on; the result lists them (`still_on`) and its message says "Still on, and needing it: …".
- **`purge`:** deletes `config/<id>.toml` and `config/<id>.local.toml` (in the app's config directory: `App(config_dir=...)`, else `ASSISTANT_CONFIG_DIR`, else `config/`), and nothing else. An id that names a shared file (`default`, `local`, `modules`, `permissions`, `voice_service`) has none to purge. Without `purge`, nothing is deleted.
- **Never:** deletes the module's folder, or rewrites `config/modules.toml`. If it's in `enabled`, the result tells you to take it out, or it starts again at the next launch.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `module_id` | `str` | yes | The module's manifest id |
| `purge` | `bool` | no | Delete its two settings files (`modules.remove`'s `settings="purge"`) |

**Returns**
| Status | When |
|--------|------|
| `ok` | Value: `{"module_id", "still_on": [ids], "deleted": [paths], "kept": [paths], "folder": path or None, "enabled": bool, "message": str}`; `message` says what was deleted or kept, whether to edit `enabled`, and that the folder is yours to delete |
| `invalid_arguments` | No module has that id |
| `failed` | It couldn't be turned off. Nothing is deleted |

**Example**

    result = await ctx.send(RemoveModule(module_id="weather", purge=True))

**Defined in:** `src/assistant/contracts/control.py` (command), `src/assistant/core/app.py` (`App._remove`), `src/assistant/core/lifecycle.py` (`LifecycleManager.remove`) · **Tests:** `tests/test_remove_module.py`, `tests/test_directory.py`

## `ModuleInfo`

`class ModuleInfo(BaseModel)` (frozen)

| Name | Type | Description |
|------|------|-------------|
| `id` | `str` | Manifest id |
| `state` | `ModuleState` | Current state |
| `description` | `str` | The manifest's one line on what it does |
| `provides` | `tuple[str, ...]` | Contract class names it provides |
| `requires` | `tuple[str, ...]` | Contract class names it requires |

**Defined in:** `src/assistant/contracts/control.py`

## `ModuleState`

`class ModuleState(StrEnum)`: `INACTIVE`, `STARTING`, `ACTIVE`, `STOPPING`, `RELOADING` (its code is being swapped), `FAILED`. Values are the lowercase names. `FAILED` modules can be activated again.

**Defined in:** `src/assistant/contracts/control.py`

## `ModuleStateChanged`

`ModuleStateChanged(module_id: str, state: ModuleState)` (event)

Published by the core on every transition, including at startup and shutdown. Like any event it may be dropped; `ListModules` is the authoritative state.

**Defined in:** `src/assistant/contracts/control.py`
