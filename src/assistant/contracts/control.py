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
    """One available module and its current state. Contracts are given by class name."""

    model_config = ConfigDict(frozen=True)

    id: str
    state: ModuleState
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


class ListModules(Command):
    """Every available module and its state. Result value: `list[ModuleInfo]`."""


class ActivateModule(Command):
    """Activate a module, first activating the providers it requires if needed."""

    module_id: str


class DeactivateModule(Command):
    """Deactivate a module. Refused while an active module requires it, unless `with_dependents`."""

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
    doesn't have: new contracts need a restart. To keep it on the next launch, it must also be
    listed in `MODULES` (and in `modules.enabled` to start then).
    """

    package: str
    activate: bool = True


class ModuleStateChanged(Event):
    """A module moved to a new state."""

    module_id: str
    state: ModuleState
