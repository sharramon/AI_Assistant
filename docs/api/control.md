# Module control

Turning modules on and off while the app runs. The core handles these commands; any module may send them (a control panel, or an agent asked to "enable the browser module"). All items: `from assistant.contracts import ...`. Back to the [API index](README.md). How it works: [runtime module control](../architecture/core.md#runtime-module-control).

Every module listed in `src/assistant/__main__.py` is **available**; `modules.enabled` in config only sets which are active at startup.

## `ListModules`

`ListModules()` (command)

Every available module and its current state.

**Returns:** `Result.ok(list[ModuleInfo])`, in the order the modules are listed in `__main__.py`.

**Example**

    result = await ctx.send(ListModules())
    active = [m.id for m in result.value if m.state is ModuleState.ACTIVE]

**Defined in:** `src/assistant/contracts/control.py`

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

## `ModuleInfo`

`class ModuleInfo(BaseModel)` (frozen)

| Name | Type | Description |
|------|------|-------------|
| `id` | `str` | Manifest id |
| `state` | `ModuleState` | Current state |
| `provides` | `tuple[str, ...]` | Contract class names it provides |
| `requires` | `tuple[str, ...]` | Contract class names it requires |

**Defined in:** `src/assistant/contracts/control.py`

## `ModuleState`

`class ModuleState(StrEnum)`: `INACTIVE`, `STARTING`, `ACTIVE`, `STOPPING`, `FAILED`. Values are the lowercase names. `FAILED` modules can be activated again.

**Defined in:** `src/assistant/contracts/control.py`

## `ModuleStateChanged`

`ModuleStateChanged(module_id: str, state: ModuleState)` (event)

Published by the core on every transition, including at startup and shutdown. Like any event it may be dropped; `ListModules` is the authoritative state.

**Defined in:** `src/assistant/contracts/control.py`
