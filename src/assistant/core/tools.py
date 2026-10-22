"""Routes InvokeTool to whichever provider currently offers the named tool."""

from __future__ import annotations

from assistant.contracts import InvokeTool, IToolProvider, Result
from assistant.core.container import Container


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
