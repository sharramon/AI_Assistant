"""Every agent's token usage since the app started, from their running totals (`SessionUsage`).

Plain Python, no app imports: anything with `SessionUsage`'s fields can be added.
"""

from __future__ import annotations

from typing import Any

from assistant.infra.usage_meter import EVENT_FIELDS

TOKEN_FIELDS = EVENT_FIELDS  # the `SessionUsage` token fields, named once in `usage_meter`


class UsageLedger:
    """Keeps, per agent id, its latest running totals; adds them up on request.

    Each `add` replaces that agent's numbers (they are totals, not amounts per call), so a
    lost event costs nothing: the next one carries it. When an agent starts a new session
    (its `session` id changes: a reload, its module off and on, a fresh session per task),
    what it had is kept and the new numbers add to it, so the tally stays "since launch". A
    sender with no `session` id is judged by its numbers instead: any going down means a
    new session.

    A usage with a `parent` (a sub-agent, or a tool an agent called) is listed under that
    parent and rolled up into its totals; the parent gets a row of zeros if it hasn't reported
    yet. Rows come in the order the agents first reported.
    """

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def add(self, usage: Any) -> None:
        """Take one `SessionUsage` (or anything with its fields)."""
        row = self._row(usage.agent_id)
        row["kind"] = getattr(usage, "kind", "claude") or "claude"
        row["parent"] = getattr(usage, "parent", "") or ""
        if row["parent"] == row["agent_id"]:
            row["parent"] = ""
        new = {name: int(getattr(usage, name, 0) or 0) for name in TOKEN_FIELDS}
        session = str(getattr(usage, "session", "") or "")
        last = row["last"]
        if session and row["session"]:
            fresh = session != row["session"]
        else:
            fresh = any(new[name] < last[name] for name in TOKEN_FIELDS)
        if fresh:
            row["banked"] = {name: row["banked"][name] + last[name] for name in TOKEN_FIELDS}
        row["last"], row["session"] = new, session
        row["context_tokens"] = int(getattr(usage, "context_tokens", 0) or 0)
        if row["parent"]:
            self._row(row["parent"])

    def total(self) -> dict[str, Any]:
        """Every agent together: tokens by kind, `used_tokens`, and `agents` (how many
        top-level rows: agents and parentless tools; sub-agents aren't counted)."""
        numbers = dict.fromkeys(TOKEN_FIELDS, 0)
        for row in self._rows.values():
            for name, value in self._own(row).items():
                numbers[name] += value
        return self._shape(numbers) | {"agents": len(self._roots())}

    def by_agent(self) -> list[dict[str, Any]]:
        """One row per top-level agent, its sub-agents and tools nested in `children`."""
        return [self._tree(agent_id) for agent_id in self._roots()]

    def mine(self, agent_id: str) -> dict[str, Any]:
        """`agent_id`'s row with its children; a row of zeros if it hasn't reported."""
        if agent_id not in self._rows:
            return self._tree_of({**self._blank(agent_id)})
        return self._tree(agent_id)

    # --- inside ---

    def _row(self, agent_id: str) -> dict[str, Any]:
        if agent_id not in self._rows:
            self._rows[agent_id] = self._blank(agent_id)
        return self._rows[agent_id]

    @staticmethod
    def _blank(agent_id: str) -> dict[str, Any]:
        zero = dict.fromkeys(TOKEN_FIELDS, 0)
        return {"agent_id": agent_id, "kind": "claude", "parent": "", "context_tokens": 0, "session": "",
                "last": dict(zero), "banked": dict(zero)}  # fmt: skip

    @staticmethod
    def _own(row: dict[str, Any]) -> dict[str, int]:
        return {name: row["banked"][name] + row["last"][name] for name in TOKEN_FIELDS}

    @staticmethod
    def _shape(numbers: dict[str, Any]) -> dict[str, Any]:
        shaped = {name: int(numbers[name]) for name in TOKEN_FIELDS}
        return shaped | {"used_tokens": sum(shaped.values())}

    def _roots(self) -> list[str]:
        return [agent_id for agent_id, row in self._rows.items() if not self._parent_of(row)]

    def _parent_of(self, row: dict[str, Any]) -> str:
        """The row's parent, unless following parents would loop back to it."""
        parent, seen = row["parent"], {row["agent_id"]}
        while parent and parent in self._rows:
            if parent in seen:
                return ""
            seen.add(parent)
            parent = self._rows[parent]["parent"]
        return row["parent"]

    def _tree(self, agent_id: str) -> dict[str, Any]:
        return self._tree_of(self._rows[agent_id])

    def _tree_of(self, row: dict[str, Any]) -> dict[str, Any]:
        agent_id = row["agent_id"]
        children = [self._tree(child) for child, r in self._rows.items() if child != agent_id and self._parent_of(r) == agent_id]
        own = self._own(row)
        total = dict(own)
        for child in children:
            for name in TOKEN_FIELDS:
                total[name] += child["total"][name]
        name = agent_id.removeprefix(row["parent"] + "/") if row["parent"] else agent_id
        return {
            "agent_id": agent_id, "name": name, "kind": row["kind"], "parent": row["parent"],
            "context_tokens": row["context_tokens"], **self._shape(own),
            "total": self._shape(total), "children": children,
        }  # fmt: skip
