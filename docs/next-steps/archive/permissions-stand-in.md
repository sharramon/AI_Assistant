# Permissions stand-in (`ctx.permissions`)

> **Status: done (2026-11-02).** Approved as written, with both recommendations: warn once per module and permission, then debug; no startup check yet. Built with `tests/test_permissions.py` (150 tests pass, ruff clean). Next: the voice contracts (step 1 of [voice in](../README.md#next-voice-in-phase-1)), a separate task.

**Asked:** "Build the permissions stand-in, the first step before voice input": `ctx.permissions` with `has` and `request`, which allows every request and logs it until the real handler exists. Step 5 of [Reusable parts](reusable-parts.md#downstream-effects-in-order).

**Why:** `voice_in` (and every later module) can ask for the mic the final way from day one. When the [permissions handler](../permissions-handler.md) is built, it plugs in behind the same calls and no module changes. Behavior follows the decided [no handler running](../../architecture/permissions.md#what-happens-when-one-is-missing) rule.

## Touches

| File | Change |
|------|--------|
| `src/assistant/contracts/module.py` | `Manifest` gains `permissions` and `optional_permissions` (`tuple[str, ...] = ()`). New ABC `ModulePermissions`. `ModuleContext` gains the attribute `permissions: ModulePermissions` |
| `src/assistant/contracts/__init__.py` | Export `ModulePermissions` |
| `src/assistant/core/permissions.py` (new) | `AllowAllPermissions(ModulePermissions)`: the stand-in, bound to one module id |
| `src/assistant/core/context.py` | `ScopedContext.__init__` sets `self.permissions = AllowAllPermissions(manifest.id)` |
| `tests/test_permissions.py` (new) | Tests below |
| Docs | `api/modules.md` (planned → built), `api/core.md` (`AllowAllPermissions`, internal), `api/README.md` + `api/reusable.md` (drop *planned*, Used by), `architecture/permissions.md` (stand-in built), [permissions-handler](../permissions-handler.md) (one line: the stand-in exists), this note, Pending changes; rebuild |

No module, config, or lifecycle changes. Nothing uses `ctx.permissions` yet; `voice_in` is the first.

## Contract shape

```python
# contracts/module.py
@dataclass(frozen=True)
class Manifest:
    ...
    permissions: tuple[str, ...] = ()            # can't run without
    optional_permissions: tuple[str, ...] = ()   # asked in the moment; a feature is off without

class ModulePermissions(ABC):
    """One module's permission checks. The core fills in the caller's id."""
    @abstractmethod
    def has(self, name: str) -> bool: ...
    @abstractmethod
    async def request(self, name: str, reason: str = "") -> bool: ...

class ModuleContext(ABC):
    ...
    permissions: ModulePermissions
```

```python
# core/permissions.py (internal to the core)
class AllowAllPermissions(ModulePermissions):
    def __init__(self, module_id: str): ...
    def has(self, name) -> bool:              # True, logs
    async def request(self, name, reason="") -> bool:  # True, logs (with the reason)
```

- **Log line:** `WARNING assistant.core.permissions: no permissions handler: allowing voice_in microphone (You clicked the mic)`. One core logger, so every stand-in grant is in one place.
- **Later:** the real handler provides an `IPermissions` contract; `ScopedContext` then builds a `ModulePermissions` that forwards to it with the module id, and falls back to `AllowAllPermissions` when no handler runs. Modules see no difference.
- **Reuse checked:** nothing in the [reusable parts index](../../api/reusable.md) does this; no new helper beyond the class itself.

## Tests (`tests/test_permissions.py`)

1. `has` and `request` return `True` for any name.
2. Each logs a warning naming the module and the permission; `request` includes the reason (`caplog`).
3. A real module's context (through `App`, like `test_control.py`) has `ctx.permissions` bound to its own id: two modules' calls log their own ids.
4. `Manifest` defaults: both permission fields are `()`; a manifest can declare them.

Then `pytest` and `ruff check`.

## Open questions

1. **Log every call, or once per module and permission?** The decided rule says each check is logged. A module calling `has` in a loop would flood the log. **Recommend:** warning the first time per (module, permission), debug after that.
2. **Required permissions at start:** the design blocks a module whose required permission is missing. With the stand-in everything is allowed, so **recommend** no lifecycle change now; the handler adds the check.
