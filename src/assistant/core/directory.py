"""The core's own menu: module control as menu items, under the id "core".

With `ListModules` (one line per module) and `GetMenu` (a module's menu) it makes the
module directory: list, then open a menu, then call an item with `InvokeTool`. Each item
sends the matching control command, so it goes through the same handlers as a control panel.
The risky ones (turning off with dependents, adding new code) ask through `permissions` first.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from assistant.contracts import (
    ActivateModule,
    AddModule,
    Command,
    DeactivateModule,
    GetMenu,
    ListModules,
    Menu,
    ModulePermissions,
    ReloadModule,
    Result,
)

CORE_ID = "core"
_ID = {"module_id": {"type": "string", "minLength": 1}}

menu = Menu()


class CoreMenu:
    """Module control as menu items. `send` is the router's; `permissions` answers the risky ones."""

    menu = menu

    def __init__(
        self,
        send: Callable[[Command], Awaitable[Result]],
        permissions: ModulePermissions,
        docs: Callable[[str], Awaitable[Result]] | None = None,
    ) -> None:
        """`docs` answers `modules.docs` (the App reads the module's own docs folder)."""
        self._send = send
        self.permissions = permissions
        self._docs = docs

    @menu.item("modules.list", "Every module: its id, one line on what it does, and whether it's on")
    async def list_modules(self) -> Result:
        return await self._send(ListModules())

    @menu.item("modules.menu", "A module's menu: what you can call on it ('core' for this one)", _ID,
               required=["module_id"])
    async def get_menu(self, module_id: str) -> Result:
        return await self._send(GetMenu(module_id=module_id))

    @menu.item("modules.docs", "A module's own docs, to learn what it does and how to use it: each page's "
               "title and path (empty if it ships none)", _ID, required=["module_id"])
    async def docs(self, module_id: str) -> Result:
        if self._docs is None:
            return Result.not_available("Module docs aren't available here")
        return await self._docs(module_id)

    @menu.item("modules.on", "Turn a module on, with the modules it requires", _ID, required=["module_id"])
    async def on(self, module_id: str) -> Result:
        return await self._send(ActivateModule(module_id=module_id))

    @menu.item("modules.off", "Turn a module off; with_dependents also turns off the modules that need it",
               {**_ID, "with_dependents": {"type": "boolean"}}, required=["module_id"])
    async def off(self, module_id: str, with_dependents: bool = False) -> Result:
        if with_dependents and not await self.permissions.request(
            "modules.off_with_dependents", f"turn off {module_id} and the modules that need it"
        ):
            return Result.failed(f"Not allowed: turning off {module_id!r} with its dependents")
        return await self._send(DeactivateModule(module_id=module_id, with_dependents=with_dependents))

    @menu.item("modules.reload", "Swap a module's code while the app runs; now cuts in if it's busy",
               {**_ID, "now": {"type": "boolean"}}, required=["module_id"])
    async def reload(self, module_id: str, now: bool = False) -> Result:
        return await self._send(ReloadModule(module_id=module_id, now=now))

    @menu.item("modules.add", "Load a new module from its package and turn it on",
               {"package": {"type": "string", "minLength": 1}, "activate": {"type": "boolean"}},
               required=["package"])
    async def add(self, package: str, activate: bool = True) -> Result:
        if not await self.permissions.request("modules.add", f"load new code from {package}"):
            return Result.failed(f"Not allowed: adding {package!r}")
        return await self._send(AddModule(package=package, activate=activate))
