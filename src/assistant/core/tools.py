"""Routes InvokeTool to whichever provider currently offers the named tool."""

from __future__ import annotations

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


async def dispatch_tool(container: Container, command: InvokeTool) -> Result:
    """Call the one IToolProvider that offers `command.name`.

    Providers are asked for their tools on every call, nothing is cached, so
    tools can appear or disappear at runtime (e.g. when a remote client connects).
    """
    providers = [
        provider
        for provider in container.get_all(IToolProvider)
        if any(spec.name == command.name for spec in provider.tools())
    ]
    if not providers:
        return Result.not_available(f"No tool named {command.name!r}")
    if len(providers) > 1:
        return Result.failed(f"Tool {command.name!r} is offered by {len(providers)} providers")
    return await providers[0].invoke(command.name, command.args)
