"""The rules for agent ids, in one place: their form, the reserved ones, and a free variant.

The core's Callers port applies them for `IAgentNames`, with the ids it reserves
(`RESERVED_AGENT_IDS`); anything naming an agent (a helper launch) can check a name's form early
with the same rules.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable

_FORM = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def check_agent_id(
    agent_id: str, owner: str = "", module_ids: Iterable[str] = (), reserved: Collection[str] = ()
) -> str | None:
    """Why `agent_id` can't be used by an agent of module `owner`, or None.

    Short, lowercase, letters, digits and `_`, starting with a letter, at most 32 characters.
    `reserved` ids and module ids are refused, except a module's own id for its own agent.
    """
    if not isinstance(agent_id, str) or not _FORM.match(agent_id):
        return (
            f"`{agent_id}` isn't a valid agent id: lowercase letters, digits and `_`, "
            "starting with a letter, at most 32 characters"
        )
    if agent_id == owner:
        return None
    if agent_id in reserved:
        return f"`{agent_id}` is reserved for the app"
    if agent_id in set(module_ids):
        return f"`{agent_id}` is a module's id"
    return None


def free_agent_id(base: str, taken: Collection[str]) -> str:
    """`base` if it's free, else `base_2`, `base_3`, ... (the first one not in `taken`)."""
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"
