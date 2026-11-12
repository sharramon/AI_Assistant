# usage: tools

<!-- tools:start (generated from the module's menu by scripts/build_docs.py; don't edit) -->

Its menu, as the main AI sees it (`modules.menu`). Every item is called with `modules.use_item`.

## `usage.total`

Every agent's tokens together since the app started (every call counted, cached context included each time)

No arguments.

## `usage.agents`

Each agent's tokens since launch; its sub-agents and tools nested under it; a closed agent's rows say closed

No arguments.

## `usage.mine`

Your own tokens since launch, with your sub-agents; or another agent's

| Argument | Type | Required | What it is |
|---|---|---|---|
| `agent_id` | string | no |  |


<!-- tools:end -->
