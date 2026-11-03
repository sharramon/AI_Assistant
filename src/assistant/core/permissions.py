"""The `ctx.permissions` stand-in: allows everything and logs it, until a permissions handler exists."""

from __future__ import annotations

import logging

from assistant.contracts import ModulePermissions

log = logging.getLogger(__name__)


class AllowAllPermissions(ModulePermissions):
    """One module's permissions while no handler runs: every check is allowed.

    The first use of each permission is logged as a warning naming the module;
    later uses of the same one only at debug, so a module checking in a loop
    doesn't flood the log.
    """

    def __init__(self, module_id: str):
        self.module_id = module_id
        self._warned: set[str] = set()

    def has(self, name: str) -> bool:
        self._allow(name, "")
        return True

    async def request(self, name: str, reason: str = "") -> bool:
        self._allow(name, reason)
        return True

    def _allow(self, name: str, reason: str) -> None:
        level = logging.DEBUG if name in self._warned else logging.WARNING
        self._warned.add(name)
        suffix = f" ({reason})" if reason else ""
        log.log(level, "no permissions handler: allowing %s %s%s", self.module_id, name, suffix)
