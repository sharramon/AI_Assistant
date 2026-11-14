# task_agents: helper agents launched by name from kinds in config

## Purpose

Builds the helper agents beside the Main Assistant from *kinds* of helper in config. Each helper is a task agent the Agent Hub can start, focus and hold questions for. A helper is launched by name for one task, only with your yes; a kind with `autostart = true` also starts at launch. Off at launch (turn it on with `modules.on`). Design: [working together](../../../../../docs/architecture/agents.md#working-together), [launching a helper](../../../../../docs/architecture/agents.md#launching-a-helper).

## Wrapper

| Field | Value |
|-------|-------|
| id | `task_agents` |
| provides | [`ITaskAgent`](../../../../../docs/api/agents.md#itaskagent), once per helper (only the Hub calls them) |
| requires / optional | none (uses [`IAgentNames`](../../../../../docs/api/agents.md#iagentnames), the core's Callers: the names, and `is_you` for who is you) |
| needs | none ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): a core module, it needs no other module by id; launching a helper goes through the Hub (`StartTask`) |
| packages | none |
| permissions | `agent.access`: each kind's access list is asked for on one card ([access lists](../../../../../docs/architecture/permissions.md#access-lists-built)) |

## Config

Defaults in `module.toml` in this module's folder, its kinds of helper included: the keys at its top level are defaults for every kind (`permission_mode`, `permission_timeout`, `chrome = true`; never `needs` or `packages`), and `[agents.<kind>]` is one kind. your `config/task_agents.toml` (top-level keys, gitignored; `[modules.task_agents]` in `config/local.toml` still works, last) only overrides them, key by key: `[agents.<kind>]` there (`[modules.task_agents.agents.<kind>]` in `config/local.toml`) changes the keys it names of a shipped kind, or adds a kind. `config/default.toml` has no section for it. A kind takes the keys of main_assistant's config plus `description`, `prompt`, `autostart` (start at launch; default false) and `instances` (how many to autostart). The shipped kinds: `helper` works in `../assistant-helper` (outside the repo, which the Main Assistant writes); `rezi` (the Rezi helper) in `../assistant-rezi`, reading the repo's `docs` (point it at your own folders in `config/task_agents.toml` or `config/local.toml`). Neither is autostarted.

## Code and tests

- `src/assistant/modules/task_agents/module.py`, `module.toml` (defaults and kinds, `needs`, `packages`); `src/assistant/infra/profile_agent.py`
- `tests/test_task_agents.py` in this folder (on the [test kit](../../../../../docs/api/testkit.md)): its defaults and kinds under `module.toml`; two agents at once, `STATUS:` to the coordinator, `NEED:` held until focused, the cap refusing a fourth extra agent, the door under each agent's name, a kind's grant reaching all its helpers, an idle session restarting on a grant and a busy one waiting)
- Centrally: `tests/test_agent_names.py` (launch proposes, allowed, denied, refused from the Talker or with no task)
- `tests/test_agent_tabs.py` (opened by you: idle or with a task, free names, a denied access card, closing)
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
