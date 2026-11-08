"""The usage tally: every agent's tokens since the app started, kept in memory only.

Listens to `SessionUsage` (from every agent, sub-agent and wrapped tool) and feeds a
`UsageLedger`. Its menu, on the agents' door like every menu: `usage.total` (all agents
together), `usage.agents` (one row each, sub-agents and tools nested under their parent, the
Talker as its own row) and `usage.mine` (the caller's own tally with its sub-agents; the door
knows the caller, so an agent asks with no arguments). Nothing is written to disk: the tally
ends with the app. A reload hands the ledger to the new copy.

A closed agent (one `ListAgents` listed before and doesn't now: its tab closed, its module
off) keeps its usage in the totals; its row in `usage.agents`, and the rows nested under it
(its tab's Talker, its sub-agents), get `"closed": true`. The agents seen are noted on every
`AgentStateChanged` / `ModuleStateChanged`, and the closed ones worked out on each ask.
"""

from __future__ import annotations

from typing import Any

from assistant.contracts import (
    AgentStateChanged,
    ListAgents,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    ModuleStateChanged,
    Result,
    SessionUsage,
)
from assistant.infra import UsageLedger

menu = Menu()


class UsageModule(ModuleProtocol):
    manifest = Manifest(
        id="usage",
        description="Every agent's tokens since launch, sub-agents under their parent",
        sends=(ListAgents,),
        listens=(SessionUsage, AgentStateChanged, ModuleStateChanged,),
    )  # fmt: skip
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        handed = ctx.handover if isinstance(ctx.handover, dict) else {"ledger": ctx.handover}
        ledger = handed.get("ledger")
        self._ledger = ledger if isinstance(ledger, UsageLedger) else UsageLedger()
        self._seen: set[str] = set(handed.get("seen", ()))  # every agent ListAgents has listed since launch
        ctx.subscribe(SessionUsage, self._on_usage)
        ctx.subscribe(AgentStateChanged, self._on_agents_changed)
        ctx.subscribe(ModuleStateChanged, self._on_agents_changed)

    async def start(self) -> None:
        await self._listed()

    def export_state(self) -> dict[str, Any]:
        """For a reload: the ledger itself (an `assistant.infra` part, never reloaded) and the agents seen."""
        return {"ledger": self._ledger, "seen": sorted(self._seen)}

    async def _on_usage(self, event: SessionUsage) -> None:
        self._ledger.add(event)

    async def _on_agents_changed(self, event: AgentStateChanged | ModuleStateChanged) -> None:
        await self._listed()

    async def _listed(self) -> set[str] | None:
        """The agents listed now (also noted as seen); None if the Hub can't say."""
        result = await self._ctx.send(ListAgents())
        if not result.is_ok or not isinstance(result.value, list):
            return None
        listed = {info.agent_id for info in result.value}
        self._seen |= listed
        return listed

    @menu.item("usage.total", "Every agent's tokens together since the app started (every call counted, "
               "cached context included each time)")  # fmt: skip
    async def total(self) -> Result:
        return Result.ok(self._ledger.total())

    @menu.item("usage.agents", "Each agent's tokens since launch; its sub-agents and tools nested "
               "under it; a closed agent's rows say closed")  # fmt: skip
    async def agents(self) -> Result:
        rows = self._ledger.by_agent()
        listed = await self._listed()
        mark_closed(rows, self._seen - listed if listed is not None else set())
        return Result.ok(rows)

    @menu.item("usage.mine", "Your own tokens since launch, with your sub-agents; or another agent's",
               {"agent_id": {"type": "string", "minLength": 1}})  # fmt: skip
    async def mine(self, agent_id: str | None = None, caller: str = "") -> Result:
        return Result.ok(self._ledger.mine(agent_id or caller))


def mark_closed(rows: list[dict[str, Any]], closed: set[str], inherited: bool = False) -> None:
    """Set `closed` on each row (and its children) whose agent, or an agent above it, is closed."""
    for row in rows:
        row["closed"] = inherited or row["agent_id"] in closed
        mark_closed(row["children"], closed, row["closed"])
