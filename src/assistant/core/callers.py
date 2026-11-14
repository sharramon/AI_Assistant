"""The Callers port (decision D2): who calls, as the core knows them, in one list.

- **Agent names:** one claim per agent id (`IAgentNames`; was the Agent Hub's `names.py`). The
  rules for an id are `check_agent_id` (shared); this part adds who holds which id, and offers a
  free one (`free_agent_id`) when an id is taken. Claims live in the core, so a Hub reload keeps them.
- **Permission modes:** each agent's mode. Only the core's `SetPermissionMode` handler sets one,
  and Auto only for a `you` caller (G12, G17); an agent's own `set_permission_mode` refuses Auto
  unless this list already says Auto. The permissions handler reads modes here (`_in_auto`). A
  released id goes back to Manual (a restarted agent starts in Manual).
- **You:** the callers that are you clicking in a UI (`[core.permissions] you`, today `temp_ui`),
  and the relays that pass your answer to a card (`relays`, today the Talker; never Auto).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from assistant.contracts import IAgentNames, PermissionMode, Result
from assistant.infra.agent_names import check_agent_id, free_agent_id

#: Ids no agent may take: the core's menu, the Hub's own menu prefix, the Talker's sessions.
#: Every module's id is refused too (`check_agent_id`), the coordinator's among them.
RESERVED_AGENT_IDS = frozenset({"core", "hub", "talker"})


class Callers(IAgentNames):
    """The core's list of callers. `module_ids()`: the ids of every known module, on or off."""

    def __init__(self, module_ids: Callable[[], Iterable[str]], you: Iterable[str] = (),
                 relays: Iterable[str] = (), reserved: frozenset[str] = RESERVED_AGENT_IDS) -> None:  # fmt: skip
        self._module_ids = module_ids
        self.you = tuple(you)
        self.relays = tuple(relays)
        self.reserved = frozenset(reserved)
        self.claims: dict[str, str] = {}  # agent id -> owning module
        self.modes: dict[str, PermissionMode] = {}  # only the agents not in Manual

    # --- names (IAgentNames) ---

    def _why_not(self, agent_id: str, owner: str) -> str | None:
        module_ids = list(self._module_ids())
        if reason := check_agent_id(agent_id, owner, module_ids, self.reserved):
            return reason
        holder = self.claims.get(agent_id)
        if holder is None:
            return None
        free = free_agent_id(agent_id, {*self.claims, *module_ids, *self.reserved})
        return f"`{agent_id}` is taken by {holder}; `{free}` is free"

    async def check(self, agent_id: str, owner: str) -> str | None:
        return self._why_not(agent_id, owner)

    async def claim(self, agent_id: str, owner: str) -> Result:
        if self.claims.get(agent_id) == owner:  # a repeat claim by its holder: it already has it
            return Result.ok(agent_id)
        if reason := self._why_not(agent_id, owner):
            return Result.invalid_arguments(reason)
        self.claims[agent_id] = owner
        return Result.ok(agent_id)

    def release(self, agent_id: str, owner: str) -> None:
        if self.claims.get(agent_id) == owner:
            del self.claims[agent_id]
            self.modes.pop(agent_id, None)

    def taken(self) -> dict[str, str]:
        return dict(self.claims)

    # --- modes and you ---

    def mode(self, agent_id: str) -> PermissionMode:
        return self.modes.get(agent_id, PermissionMode.MANUAL)

    def set_mode(self, agent_id: str, mode: PermissionMode) -> None:
        if mode is PermissionMode.MANUAL:
            self.modes.pop(agent_id, None)
        else:
            self.modes[agent_id] = mode

    def is_you(self, caller: str) -> bool:
        return caller in self.you

    def may_set_auto(self, sender: str) -> bool:
        """Auto comes only from you (the UI's button) or the core itself; never from a relay (G17)."""
        return sender == "core" or sender in self.you
