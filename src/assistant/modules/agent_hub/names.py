"""The Agent Hub's agent names: `IAgentNames`, one claim per agent id.

The rules for an id are `check_agent_id` (shared); this part adds who holds which id, and
offers a free one (`free_agent_id`) when an id is taken.
"""

from __future__ import annotations

from assistant.contracts import IAgentNames, ListModules, ModuleContext, Result
from assistant.infra.agent_names import check_agent_id, free_agent_id

#: Ids no agent may take: the core's menu, the Hub's own menu prefix, the Talker's sessions;
#: the coordinator is added from config. Every module's id is refused too (`check_agent_id`).
RESERVED_AGENT_IDS = frozenset({"core", "hub", "talker"})


class AgentNames(IAgentNames):
    """The claimed agent ids, checked with `check_agent_id`."""

    def __init__(self, ctx: ModuleContext, claims: dict[str, str], reserved: frozenset[str]) -> None:
        self._ctx = ctx
        self.claims = claims  # agent id -> owning module
        self.reserved = reserved

    async def _module_ids(self) -> list[str]:
        result = await self._ctx.send(ListModules())
        return [m.id for m in result.value] if result.is_ok and result.value else []

    def _why_not(self, agent_id: str, owner: str, module_ids: list[str]) -> str | None:
        if reason := check_agent_id(agent_id, owner, module_ids, self.reserved):
            return reason
        holder = self.claims.get(agent_id)
        if holder is None:
            return None
        free = free_agent_id(agent_id, {*self.claims, *module_ids, *self.reserved})
        return f"`{agent_id}` is taken by {holder}; `{free}` is free"

    async def check(self, agent_id: str, owner: str) -> str | None:
        return self._why_not(agent_id, owner, await self._module_ids())

    async def claim(self, agent_id: str, owner: str) -> Result:
        module_ids = await self._module_ids()
        # Checked and taken with no await between, so two claims can't both win.
        if self.claims.get(agent_id) == owner:  # a repeat claim by its holder: it already has it
            return Result.ok(agent_id)
        if reason := self._why_not(agent_id, owner, module_ids):
            self._ctx.log.warning("Agent id refused for %s: %s", owner, reason)
            return Result.invalid_arguments(reason)
        self.claims[agent_id] = owner
        return Result.ok(agent_id)

    def release(self, agent_id: str, owner: str) -> None:
        if self.claims.get(agent_id) == owner:
            del self.claims[agent_id]

    def taken(self) -> dict[str, str]:
        return dict(self.claims)
