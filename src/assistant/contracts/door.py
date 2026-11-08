"""The module door: how a Claude session reaches the module menus (module system, decision 2)."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from assistant.contracts.module import Contract


class IModuleDoor(Contract):
    """The one MCP door to the module menus for Claude sessions. Provided by `agent_hub`.

    Three fixed tools (list modules, show a menu, use an item) that go through the core, so the
    directory, permissions and hot swap still apply. A task agent asks for `mcp_config(caller)`
    each time it starts a session and passes it as `--mcp-config`.
    """

    @abstractmethod
    def mcp_config(self, caller: str) -> dict[str, Any]:
        """The `--mcp-config` JSON for one claude session of `caller` (its agent or module id),
        or `{}` while the door is down. Its token proves the caller, so every `InvokeTool` the
        session sends carries that name and can't claim another."""
