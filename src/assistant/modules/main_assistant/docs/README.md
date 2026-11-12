# main_assistant: the worker agent

## Purpose

A `claude` session with file tools that does the work handed to it by the Agent Hub. On by default. It is the **coordinator** (`[modules.agent_hub] coordinator`): other agents' milestones and ends, and each focus move, reach it at the end of its next message ([working together](../../../../../docs/architecture/agents.md#working-together)). Design: [agents](../../../../../docs/architecture/agents.md), [the Main Assistant on its own](../../../../../docs/agents/runtime.md#the-main-assistant-on-its-own).

## Wrapper

| Field | Value |
|-------|-------|
| id | `main_assistant` |
| provides | [`ITaskAgent`](../../../../../docs/api/agents.md#itaskagent) (only the Hub calls it) |
| requires / optional | none |
| permissions | none declared; its file and shell access are its `claude` rules (config below) |

## Config

`[modules.main_assistant]`: `workspace`, `tools`, `permission_mode`, `read_dirs`, `write_dirs`, `allowed_commands`, `fresh_sessions`, `max_handoffs`, `context_reminder`, `edit_note`, `permission_prompts`, `permission_timeout`, `transcript`, `model`.

## Code and tests

- `src/assistant/modules/main_assistant/module.py`; the agent itself is `src/assistant/infra/session_agent.py`, its setup `infra/agent_profile.py`
- `tests/test_agents.py`, `test_permission_mode.py`, `test_edit_note.py`, `test_multi_agent.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
