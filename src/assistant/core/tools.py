"""Routes InvokeTool to whichever provider currently offers the named tool."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from assistant.contracts import InvokeTool, IToolProvider, Menu, ModuleProtocol, Result, ToolSpec
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


async def dispatch_tool(
    container: Container,
    command: InvokeTool,
    start_on_use: Callable[[str], Awaitable[Result | None]] | None = None,
) -> Result:
    """Call the one IToolProvider that offers `command.name`.

    Providers are asked for their tools on every call, nothing is cached, so
    tools can appear or disappear at runtime (e.g. when a remote client connects).

    With `start_on_use`, a tool nobody offers is passed to it first: it turns on the
    module that is off and has the tool on its menu (if that module allows it), and
    returns the start's `Result`, or None when no module qualifies. If the start
    worked, the call goes ahead; if it failed, its error is the answer.
    """
    providers = _providers(container, command.name)
    if not providers and start_on_use is not None:
        started = await start_on_use(command.name)
        if started is not None and not started.is_ok:
            return started
        if started is not None:
            providers = _providers(container, command.name)
    if not providers:
        return Result.not_available(f"No tool named {command.name!r}")
    if len(providers) > 1:
        return Result.failed(f"Tool {command.name!r} is offered by {len(providers)} providers")
    return await providers[0].invoke_as(command.name, command.args, command.caller)


def _providers(container: Container, name: str) -> list[IToolProvider]:
    return [
        provider
        for provider in container.get_all(IToolProvider)
        if any(spec.name == name for spec in provider.tools())
    ]
