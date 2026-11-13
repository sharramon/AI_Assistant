"""Runtime module control: list modules and turn them on and off while the app runs.

Handled by the core. Any module may send these (a control panel, or an agent
acting on "enable the browser module").
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from assistant.contracts.messages import Command, Event


class ModuleState(StrEnum):
    INACTIVE = "inactive"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    RELOADING = "reloading"
    FAILED = "failed"


class ModuleInfo(BaseModel):
    """One available module: its line in the module directory. Contracts are given by class name."""

    model_config = ConfigDict(frozen=True)

    id: str
    state: ModuleState
    description: str = ""
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


class ListModules(Command):
    """The module directory: every available module, one line each. Result value: `list[ModuleInfo]`."""


class GetMenu(Command):
    """A module's menu, read from its class, so it works while the module is off.

    Result value: `list[ToolSpec]` (empty if it has no menu). `module_id="core"` gives the
    core's own menu (`modules.*`). Its items are called with `InvokeTool`, which needs the
    module to be on.
    """

    module_id: str


class ActivateModule(Command):
    """Activate a module, first activating the providers it requires if needed."""

    module_id: str


class StartProvider(Command):
    """Start on use, by contract: turn on the module that is off, declares `contract` (a contract's
    class name, e.g. `"IPageOpener"`) in its `manifest.provides`, and has `start_on_use = true` in
    its config, the same way as `ActivateModule`. So a caller names a contract, never a module.

    Result: the start's result (ok, or `failed` with the reason); `not_available` when no module
    qualifies (none provides it, or it's already on, or its config doesn't allow it)."""

    contract: str


class DeactivateModule(Command):
    """Deactivate a module. Never refused: the modules that need it stay on, and the result's value
    names them ("voice_in is off; voice_notes needs it and stays on"). `with_dependents` turns them off first."""

    module_id: str
    with_dependents: bool = False


class ReloadModule(Command):
    """Reload a module's code while the app runs: stop it, import its package fresh, start it again.

    Its config section is read again too. If the new code fails to import or start, the old code
    is put back and started, and the result reports the error. Modules that require it are
    stopped and started around it. Core, contracts, `infra` and `app_kit` can't be reloaded.

    While the module is busy (its `busy()` gives a reason: replying, working on a task), the
    reload waits, up to `core.reload_idle_timeout`; `now` cuts in instead, and its `stop`
    cancels what it was doing. The old instance's `export_state()` reaches the new one as
    `ctx.handover`.
    """

    module_id: str
    now: bool = False


class AddModule(Command):
    """Load a module that wasn't there at launch, from its package (e.g. `assistant.modules.weather`).

    Result value: the new module's id. Fails if its code needs a contract the running app
    doesn't have: new contracts need a restart. Under `assistant.modules`, its folder must be
    named with its id. The next launch finds it by folder (`modules.enabled` to start it then).
    """

    package: str
    activate: bool = True


class RemoveModule(Command):
    """Remove a module from this run: turn it off if it's on, and take it out of the module list, so
    it isn't offered again until `AddModule` loads it. Refused (`failed`, naming them) while another
    module needs it: an active one that `needs` it or requires something only it provides, or one in
    `modules.enabled` whose `needs` lists it.

    `purge` deletes its settings, `config/<id>.toml` and `config/<id>.local.toml`, and nothing else;
    without it nothing is deleted. Its folder is never deleted (that's yours to do), and
    `config/modules.toml` is never rewritten: the result says to take it out of `enabled` yourself.

    Result value: `{"module_id", "deleted": [paths], "kept": [paths], "folder": path or None,
    "enabled": bool, "message": str}`.
    """

    module_id: str
    purge: bool = False


class ModuleStateChanged(Event):
    """A module moved to a new state."""

    module_id: str
    state: ModuleState
