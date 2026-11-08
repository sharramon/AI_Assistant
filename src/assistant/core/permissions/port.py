"""`ctx.permissions`: one module's port to the core's permissions handler.

Access lists (`request_set`) go to the handler with this module's id. Single names (`has`,
`request`) aren't checked yet (the handler's next piece): they are allowed, and the first use of
each is logged as a warning naming the module (later ones at debug, so a loop doesn't flood the
log). A port built without a handler (a bare context in a test) allows access lists the same way.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from assistant.contracts import AccessItem, ModulePermissions

if TYPE_CHECKING:
    from assistant.core.permissions.handler import PermissionsHandler

log = logging.getLogger("assistant.core.permissions")


class PermissionsPort(ModulePermissions):
    def __init__(self, module_id: str, handler: PermissionsHandler | None = None):
        self.module_id = module_id
        self._handler = handler
        self._warned: set[str] = set()

    def has(self, name: str) -> bool:
        self._allow(name, "")
        return True

    async def request(self, name: str, reason: str = "") -> bool:
        self._allow(name, reason)
        return True

    async def request_set(
        self, items: Sequence[AccessItem], reason: str = "", subject: str = "", wait: bool = False
    ) -> tuple[AccessItem, ...]:
        if self._handler is None:
            self._allow(f"access list of {subject or self.module_id} ({len(items)} items)", reason)
            return tuple(items)
        return await self._handler.request_set(self.module_id, subject or self.module_id, tuple(items), reason, wait)

    def own_agent(self, agent_id: str, subject: str) -> None:
        if self._handler is not None:
            self._handler.own_agent(self.module_id, agent_id, subject or self.module_id)

    def _allow(self, name: str, reason: str) -> None:
        level = logging.DEBUG if name in self._warned else logging.WARNING
        self._warned.add(name)
        suffix = f" ({reason})" if reason else ""
        log.log(level, "not checked yet: allowing %s %s%s", self.module_id, name, suffix)
