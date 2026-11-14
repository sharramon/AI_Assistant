# agent_hub: who is doing what

## Purpose

Holds the authoritative task state and routes work between the Talker and the task agents, and keeps the **focus** (the agent you're talking to). It does agent coordination only: the module door, the agent names and the permission mode are the core's (2026-11-13). Not an AI; launches nothing. On by default. Design: [agents](../../../../../docs/architecture/agents.md), [working together](../../../../../docs/architecture/agents.md#working-together).

## Wrapper

| Field | Value |
|-------|-------|
| id | `agent_hub` |
| provides / requires | provides nothing; requires nothing. The module door ([`IModuleDoor`](../../../../../docs/api/tools.md#imoduledoor)) and the agent names ([`IAgentNames`](../../../../../docs/api/agents.md#iagentnames)) are the core's |
| optional / uses | optional [`ITaskAgent`](../../../../../docs/api/agents.md#itaskagent) (every task agent; it never imports one); uses [`IAgentNames`](../../../../../docs/api/agents.md#iagentnames) (the core's Callers) |
| permissions | none |
| needs | none ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): a core module, it needs no other module by id |
| packages | none |

## Config

Defaults in `module.toml` in this module's folder, with their comments; your `config/agent_hub.toml` (top-level keys, gitignored; `[modules.agent_hub]` in `config/local.toml` still works, last) only overrides them, key by key ([how a module's config is built](../../../../../docs/api/core.md#app)). `config/default.toml` has no section for it. The keys: `coordinator` (default `main_assistant`), `max_extra_agents` (default 3: big agents besides the coordinator with an active task at once), `named_only` (an optional fallback list of agent ids a free-agent pick, `hub.start` with no `agent_id`, never lands on; empty by default. The usual place is the agent's own config: `named_only = true` in its section, read from [`AgentInfo.named_only`](../../../../../docs/api/agents.md#agentinfo); cv_agent sets it in cv's `[agent]`, since its jobs come from `cv.task`. Anyone may still name such an agent), `start_only_by` (agent id → the only callers whose `hub.start` may start it; the Talker always may, and a free-agent pick skips these agents too; empty by default). The door's settings moved to `[core.door]` in `config/default.toml`; an old `door` key here is ignored.

## Code and tests

- `src/assistant/modules/agent_hub/module.toml`: its defaults, `needs`, `packages`
- `src/assistant/modules/agent_hub/module.py`: `AgentHubModule`, the small coordinator (commands, events, the menu, the running-agent lookup and the coordinator's feed)
- `tasks.py`: `TaskBoard` and `TaskRecord` (the task records and their state machine, the cap, the folder check; a record keeps the agent object that took it, and when a reload provides a new agent under that id the board closes the old record as failed, "reloaded", so it never counts as open, never blocks the Hub's reload, and never catches the tab's messages; an agent's tab messages go to its newest open task; a send or cancel the agent refuses as "not my task" closes the record too. Built 2026-11-09 after task 20c1d08e stayed open across two `cv` reloads; tests in `agent_hub/tests/test_stale_task.py`, live after the next app restart); `focus.py`: `Focus` (the focus and releasing what was held); `delivery.py`: `Delivery` and `Waiting`; `gate.py`: `MessageGate` (2026-11-10); `review.py`: `Reviewer`, `REVIEW_PROMPT` and `review_lines` (the access-list review, 2026-11-13). `names.py` is gone: the agent names moved to the core (`core/callers.py`)
- In this folder's `tests/` (on the [test kit](../../../../../docs/api/testkit.md)): `test_agent_hub_parts.py` (the board, the focus, the Talker's menu items, its defaults under `module.toml`), `test_delivery.py`, `test_gate.py`, `test_stale_task.py`, `test_end_waiting.py`, `test_end_report_race.py`, `test_child_result.py`, `test_review.py`
- Centrally, with other modules: `tests/test_agents.py`, `tests/test_multi_agent.py`, `tests/test_mcp_door.py`, `tests/test_agent_names.py`, `tests/test_questions_as_messages.py`, `tests/test_events_never_control.py`, `tests/test_review_listener.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
