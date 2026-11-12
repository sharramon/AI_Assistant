# task_agents: helper agents launched by name from kinds in config

## Purpose

Builds the helper agents beside the Main Assistant from *kinds* of helper in config. Each helper is a task agent the Agent Hub can start, focus and hold questions for. A helper is launched by name for one task, only with your yes; a kind with `autostart = true` also starts at launch. Off at launch (turn it on with `modules.on`). Design: [working together](../../../../../docs/architecture/agents.md#working-together), [launching a helper](../../../../../docs/architecture/agents.md#launching-a-helper).

## Wrapper

| Field | Value |
|-------|-------|
| id | `task_agents` |
| provides | [`ITaskAgent`](../../../../../docs/api/agents.md#itaskagent), once per helper (only the Hub calls them) |
| requires / optional | none (uses [`IAgentNames`](../../../../../docs/api/agents.md#iagentnames) when the Hub runs) |
| permissions | `agent.access`: each kind's access list is asked for on one card ([access lists](../../../../../docs/architecture/permissions.md#access-lists-built)) |

## Config

`[modules.task_agents]`: defaults for every kind. `[modules.task_agents.agents.<kind>]`: one kind, with the keys of `[modules.main_assistant]` plus `description`, `prompt`, `autostart` (start at launch; default false) and `instances` (how many to autostart). The shipped `helper` kind works in `../assistant-helper` (outside the repo, which the Main Assistant writes) and isn't autostarted.

## Code and tests

- `src/assistant/modules/task_agents/module.py`; `src/assistant/infra/profile_agent.py`
- `tests/test_task_agents.py` (two agents at once, `STATUS:` to the coordinator, `NEED:` held until focused, the cap refusing a fourth extra agent, the door under each agent's name, a kind's grant reaching all its helpers, an idle session restarting on a grant and a busy one waiting)
- `tests/test_agent_names.py` (launch proposes, allowed, denied, refused from the Talker or with no task)
- `tests/test_agent_tabs.py` (opened by you: idle or with a task, free names, a denied access card, closing)
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
