"""Routes InvokeTool to whichever provider currently offers the named tool."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from assistant.contracts import InvokeTool, IToolProvider, Menu, ModuleProtocol, Result, ToolSpec
from assistant.contracts.menu import MenuItem
from assistant.core.container import Container


class MenuTools(IToolProvider):
    """The core's adapter from a module's `Menu` to `IToolProvider`, linked to one running copy.

    The core provides it in the module's name after `init`, so closing the module's context
    removes it; the module itself never provides `IToolProvider` for its menu.
    """

    def __init__(self, menu: Menu, module: ModuleProtocol) -> None:
        self._menu = menu
        self._module = module

    def tools(self) -> list[ToolSpec]:
        return self._menu.specs()

    async def invoke(self, name: str, args: dict[str, Any]) -> Result:
        return await self._menu.call(self._module, name, args)

    async def invoke_as(self, name: str, args: dict[str, Any], caller: str) -> Result:
        return await self._menu.call(self._module, name, args, caller)

    def item(self, name: str) -> MenuItem | None:
        return self._menu.get(name)


class MenuTable:
    """The core-private table of linked menus (G16): `InvokeTool` reaches them, nothing else
    does. Menus are never in the container, so no module can call one as a plain
    `IToolProvider` with a caller of its choosing. Each context removes exactly what it added,
    so a reload's old copy never takes the new copy's menu with it."""

    def __init__(self) -> None:
        self._tools: list[MenuTools] = []

    def add(self, tools: MenuTools) -> None:
        self._tools.append(tools)

    def remove(self, tools: MenuTools) -> None:
        if tools in self._tools:
            self._tools.remove(tools)

    def all(self) -> list[MenuTools]:
        return list(self._tools)


# The ask-first gate: (caller, what, the call, risky) -> the Result (the handler's `confirm`).
Confirm = Callable[[str, str, Callable[[], Awaitable[Result]], bool], Awaitable[Result]]


async def dispatch_tool(
    container: Container,
    menus: MenuTable,
    command: InvokeTool,
    start_on_use: Callable[[str], Awaitable[Result | None]] | None = None,
    off_owner: Callable[[str], str | None] | None = None,
    confirm: Confirm | None = None,
) -> Result:
    """Call the one provider that offers `command.name`: a linked menu (`menus`) or a module
    that provides `IToolProvider` itself (`container`).

    Providers are asked for their tools on every call, nothing is cached, so
    tools can appear or disappear at runtime (e.g. when a remote client connects).

    With `start_on_use`, a tool nobody offers is passed to it first: it turns on the
    module that is off and has the tool on its menu (if that module allows it), and
    returns the start's `Result`, or None when no module qualifies. If the start
    worked, the call goes ahead; if it failed, its error is the answer.

    With `off_owner` (the id of a module that is off and has the tool on its menu), a tool
    nobody offers is answered "<id> isn't on", so the caller can ask the user to turn it on.

    With `confirm`, an item marked `ask` (and its `ask_when` argument true) is the one ask-first
    gate: its arguments are checked, then `confirm` asks you on a card and runs the call on Allow.
    """
    providers = _providers(container, menus, command.name)
    if not providers and start_on_use is not None:
        started = await start_on_use(command.name)
        if started is not None and not started.is_ok:
            return started
        if started is not None:
            providers = _providers(container, menus, command.name)
    if not providers and off_owner is not None and (owner := off_owner(command.name)):
        return Result.not_available(module_off_text(owner, command.name))
    if not providers:
        return Result.not_available(f"No tool named {command.name!r}")
    if len(providers) > 1:
        return Result.failed(f"Tool {command.name!r} is offered by {len(providers)} providers")
    provider = providers[0]
    item = provider.item(command.name) if isinstance(provider, MenuTools) else None
    if confirm is None or item is None or not item.asks(command.args):
        return await provider.invoke_as(command.name, command.args, command.caller)
    if problem := provider._menu.check(command.name, command.args):  # a bad call never reaches a card
        return Result.invalid_arguments(problem)
    if item.callers and command.caller not in item.callers:
        return Result.not_available(f"{command.name} is only for: {', '.join(item.callers)}")
    shown = ", ".join(f"{k}: {v}" for k, v in command.args.items())
    what = f"{command.name}" + (f" ({shown})" if shown else "")
    return await confirm(command.caller, what, lambda: provider.invoke_as(command.name, command.args, command.caller),
                         item.ask == "risky")  # fmt: skip


def module_off_text(module_id: str, tool: str) -> str:
    """The answer to a call that reaches a module that is off: which one, and how to turn it on."""
    return (
        f"The {module_id} module isn't on, so {tool!r} can't run. Ask the user whether to turn "
        f"{module_id} on; on their yes, use modules.on with module_id {module_id!r}, then call {tool!r} again."
    )


def _providers(container: Container, menus: MenuTable, name: str) -> list[IToolProvider]:
    return [
        provider
        for provider in [*menus.all(), *container.get_all(IToolProvider)]
        if any(spec.name == name for spec in provider.tools())
    ]
