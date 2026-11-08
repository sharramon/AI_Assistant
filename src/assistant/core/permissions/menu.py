"""The grant calls as the core's own menu items (`permissions.*`), offered under the id "core"
beside `modules.*`, so agents reach them through the module door and UIs through `InvokeTool`.
Each item knows its caller: you (a UI you click in) apply at once; an agent's grant or revoke
shows you a card first."""

from __future__ import annotations

from pathlib import Path

from assistant.contracts import AccessItem, AccessKind, Menu, Result
from assistant.core.permissions.handler import PermissionsHandler

ITEMS = {"type": "array", "items": {"type": "string"}}


def _folder(path: str) -> str:
    return str(Path(path).resolve())

menu = Menu()


class PermissionsMenu:
    menu = menu

    def __init__(self, handler: PermissionsHandler) -> None:
        self._handler = handler

    @menu.item("permissions.grants", "The saved access grants per module and kind of agent: what was granted, "
               "the date, and whether its current list still matches")  # fmt: skip
    async def grants_item(self) -> Result:
        return Result.ok(self._handler.grants())

    @menu.item("permissions.grant", "Grant asked-for items to a module, then it turns on with them; from an agent "
               "it shows the user a card and only their Allow applies it",
               {"module_id": {"type": "string", "minLength": 1}, "items": ITEMS, "subject": {"type": "string"}},
               required=["module_id", "items"])  # fmt: skip
    async def grant_item(self, module_id: str, items: list[str], subject: str = "", caller: str = "") -> Result:
        return await self._handler.grant(module_id, items, subject, caller)

    @menu.item("permissions.request", "Ask for more access for yourself (a task agent with an access list): folders to "
               "read or write, shell commands, a Python, Chrome, with a short reason. The user answers on a card; "
               "the answer reaches you as a note, and what they allow applies from your next session",
               {"read": ITEMS, "write": ITEMS, "commands": ITEMS, "python": {"type": "string"},
                "chrome": {"type": "boolean"}, "reason": {"type": "string"}})  # fmt: skip
    async def request_item(self, read: list[str] | None = None, write: list[str] | None = None,
                           commands: list[str] | None = None, python: str = "", chrome: bool = False,
                           reason: str = "", caller: str = "") -> Result:  # fmt: skip
        items = [AccessItem(kind=AccessKind.READ, target=_folder(d)) for d in read or ()]
        items += [AccessItem(kind=AccessKind.WRITE, target=_folder(d)) for d in write or ()]
        items += [AccessItem(kind=AccessKind.COMMAND, target=c.strip()) for c in commands or () if c.strip()]
        if python.strip():
            items.append(AccessItem(kind=AccessKind.PYTHON, target=python.strip()))
        if chrome:
            items.append(AccessItem(kind=AccessKind.CHROME))
        if not items:
            return Result.invalid_arguments("Name what you need: read, write, commands, python or chrome")
        return await self._handler.request(caller, items, reason)

    @menu.item("permissions.revoke", "Take back a module's grant (all, or some items): it turns off right away and its "
               "running task is stopped; from an agent it shows the user a card first",
               {"module_id": {"type": "string", "minLength": 1}, "subject": {"type": "string"}, "items": ITEMS},
               required=["module_id"])  # fmt: skip
    async def revoke_item(self, module_id: str, subject: str = "", items: list[str] | None = None,
                          caller: str = "") -> Result:  # fmt: skip
        return await self._handler.revoke(module_id, subject, items, caller)
