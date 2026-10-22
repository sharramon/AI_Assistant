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


class ModuleStateChanged(Event):
    """A module moved to a new state."""

    module_id: str
    state: ModuleState
