# task_agents: tools

<!-- tools:start (generated from the module's menu by scripts/build_docs.py; don't edit) -->

Its menu, as the main AI sees it (`modules.menu`). Every item is called with `modules.use_item`.

## `agents.kinds`

The kinds of helper you can launch (each with a free name), and the helpers running

No arguments.

## `agents.launch`

Propose a new helper for one task: the user gets a card, and it starts as your child task only if they allow it. End your turn after; the outcome is your next message

| Argument | Type | Required | What it is |
|---|---|---|---|
| `name` | string | yes |  |
| `task` | string | no |  |
| `kind` | string | no |  |

## `agents.close`

Close a launched helper that has no task, and free its name

| Argument | Type | Required | What it is |
|---|---|---|---|
| `agent_id` | string | yes |  |


<!-- tools:end -->
