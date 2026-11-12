# agent_hub: tools

<!-- tools:start (generated from the module's menu by scripts/build_docs.py; don't edit) -->

Its menu, as the main AI sees it (`modules.menu`). Every item is called with `modules.use_item`.

## `hub.agents`

The big agents: state (active or idle; an idle one takes work, whatever it asked), focused (the one the user talks to), holding a question (!), and their open task

No arguments.

## `hub.status`

Task status without disturbing the agent: one task, or the open and recent ones

| Argument | Type | Required | What it is |
|---|---|---|---|
| `task_id` | string | no |  |

## `hub.start`

Start a task on a free agent (or the one named); your open task becomes its parent

| Argument | Type | Required | What it is |
|---|---|---|---|
| `text` | string | yes |  |
| `agent_id` | string | no |  |
| `context` | string | no |  |

## `hub.send`

Pass words to a task or an agent. task_id: your own child task (the Talker: any), straight in. agent_id: message that agent; its open task if it's your child, else it arrives when its turn ends (into its open task or as a new task), and the first message to it asks the user once on a card (Allow once / Always / Deny; the reply says 'waiting on the user's card'). The Talker with neither: the focused agent

| Argument | Type | Required | What it is |
|---|---|---|---|
| `text` | string | yes |  |
| `task_id` | string | no |  |
| `agent_id` | string | no |  |
| `pause` | boolean | no |  |

## `hub.cancel`

Stop a task, like Esc (the Talker: any task; others: their child tasks)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `task_id` | string | yes |  |

## `hub.answer`

Allow or deny a task's open permission request, once (the Talker, after the user answered)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `task_id` | string | yes |  |
| `allow` | boolean | yes |  |

## `hub.mode`

Switch an agent to Manual (only the user switches to Auto, with the app's button)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `agent_id` | string | yes |  |
| `mode` | string | yes |  |

## `hub.focus`

Move the focus to an agent, after the user said so (empty: back to the main one)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `agent_id` | string | yes |  |

## `hub.suggest_focus`

Suggest the user talks to an agent directly (the coordinator only); the Talker asks them

| Argument | Type | Required | What it is |
|---|---|---|---|
| `agent_id` | string | yes |  |
| `reason` | string | no |  |


<!-- tools:end -->
