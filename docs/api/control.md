# Module control

Turning modules on and off while the app runs. The core handles these commands; any module may send them (a control panel, or an agent asked to "enable the browser module"). All items: `from assistant.contracts import ...`. Back to the [API index](README.md). How it works: [runtime module control](../architecture/core.md#runtime-module-control).

Every module listed in `src/assistant/__main__.py` is **available**; `modules.enabled` in config only sets which are active at startup.

## `ListModules`

`ListModules()` (command)

The module directory: every available module, one line each (its id, one-line description and current state).

**Returns:** `Result.ok(list[ModuleInfo])`, in the order the modules are listed in `__main__.py`.

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

Module control as menu items, under the id `core` (`GetMenu(module_id="core")`), called with `InvokeTool` like any module's items. Each sends the matching command above, so results and errors are the same.

| Item | Arguments | Sends | Asks first |
|------|-----------|-------|------------|
| `modules.list` | none | `ListModules` | no |
| `modules.menu` | `module_id` | `GetMenu` | no |
| `modules.on` | `module_id` | `ActivateModule` | no |
| `modules.off` | `module_id`, `with_dependents` (false) | `DeactivateModule` | with `with_dependents` |
| `modules.reload` | `module_id`, `now` (false) | `ReloadModule` | no |
| `modules.add` | `package`, `activate` (true) | `AddModule` | yes |

"Asks first" goes through the core's permissions (`modules.off_with_dependents`, `modules.add`); today that's the allow-all stand-in, which logs. Refused → `failed` ("Not allowed: …"). Through `InvokeTool` a call is capped by its timeout (30 s by default); a reload or add that takes longer still finishes, and `ModuleStateChanged` reports it.

**Defined in:** `src/assistant/core/directory.py`

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
| `failed` | Several modules could provide a required contract (the error lists them; activate one first), it would be a second provider of a single-provider contract, a required provider failed, or its own `init`/`start` raised. In the last case its state is `failed` and it can be retried |
| `timed_out` | The command timed out; the activation still finishes, and `ModuleStateChanged` reports the outcome |

**Example**

    result = await ctx.send(ActivateModule(module_id="voice_output"))
    if not result.is_ok:
        ctx.log.warning("Couldn't enable voice output: %s", result.error)

**Defined in:** `src/assistant/contracts/control.py`

## `DeactivateModule`

`DeactivateModule(module_id: str, with_dependents: bool = False)` (command)

Turn a module off: `stop`, then everything it registered is removed. Its tools, handlers, and contracts disappear.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `module_id` | `str` | yes | The module's manifest id |
| `with_dependents` | `bool` | no | Also deactivate active modules that require something only this one provides (they go first) |

**Returns**
| Status | When |
|--------|------|
| `ok` | It's inactive (or already was) |
| `invalid_arguments` | No module has that id |
| `failed` | Active modules require it and `with_dependents` is false; the error names them |

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

Load a module that wasn't there at launch, from its package, and activate it unless `activate` is false. Its package must export exactly one `ModuleProtocol` subclass. To keep it on the next launch, add it to `MODULES` in `__main__.py` (and to `modules.enabled`).

**Returns**
| Status | When |
|--------|------|
| `ok` | Value: the new module's id |
| `failed` | Already loaded (use `ReloadModule`), an id that's taken, an import error, or its code needs a contract the running app doesn't have: new contracts and port types need a restart |

**Example**

    result = await ctx.send(AddModule(package="assistant.modules.weather"))

**Defined in:** `src/assistant/contracts/control.py`

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
