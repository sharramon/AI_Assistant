"""The module door, hosted by the core (decision D1: part of the Tools port; was the Agent Hub's).

The core opens the `DoorServer` (`assistant.infra.mcp_door`) before any module starts, so every
agent's first session has the door, and a Hub reload no longer touches it. Its calls go straight
to the router as the core's own (`ListModules`, `GetMenu`, `InvokeTool` with the caller its token
proved).

`IModuleDoor` is provided by the core. A module never gets the core's own door: its context
hands it a `ModuleDoor` bound to its id, whose `mcp_config(caller)` answers only for the module
itself or an agent id it claimed in the Callers port (G11); for anyone else it logs and gives {}.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from assistant.contracts import IModuleDoor
from assistant.infra.mcp_door import DoorServer

log = logging.getLogger(__name__)

#: The directory line for the core's own menu, added to `list_modules` (a test checks it names every `modules.*` item).
CORE_LINE = {"id": "core", "description": "Module control and permissions: list, menu, docs, on, off, reload, add, remove; "
             "permissions.*", "state": "active"}


class CoreDoor(IModuleDoor):
    """The core's door: the `DoorServer` and who may ask for whose config. `claims()`: the
    Callers port's agent id -> owning module."""

    def __init__(self, server: DoorServer, claims: Callable[[], dict[str, str]]) -> None:
        self.server = server
        self._claims = claims

    def mcp_config(self, caller: str) -> dict[str, Any]:
        """The core's own call, unchecked (the core and tests)."""
        return self.server.mcp_config(caller)

    def may_ask(self, module_id: str, caller: str) -> bool:
        """A module asks only for itself or for an agent id it claimed."""
        return bool(caller) and (caller == module_id or self._claims().get(caller) == module_id)

    def for_module(self, module_id: str) -> ModuleDoor:
        return ModuleDoor(self, module_id)


class ModuleDoor(IModuleDoor):
    """The door as one module sees it (`ctx.get_one(IModuleDoor)`)."""

    def __init__(self, door: CoreDoor, module_id: str) -> None:
        self._door = door
        self.module_id = module_id

    def mcp_config(self, caller: str) -> dict[str, Any]:
        if not self._door.may_ask(self.module_id, caller):
            log.warning("%s asked for the module door as %r, which isn't it or an agent it claimed: refused",
                        self.module_id, caller)  # fmt: skip
            return {}
        return self._door.mcp_config(caller)
