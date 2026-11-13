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
| needs | none ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): a core module, it needs no other module by id |
| packages | none |

## Config

Defaults in `module.toml` in this module's folder, with their comments; `[modules.main_assistant]` in the app's config (your `config/local.toml`) only overrides them, key by key (a list such as `write_dirs` is replaced whole; [how a module's config is built](../../../../../docs/api/core.md#app)). `config/default.toml` has no section for it. The keys: `workspace`, `tools`, `permission_mode`, `read_dirs`, `write_dirs`, `allowed_commands`, `fresh_sessions`, `max_handoffs`, `context_reminder`, `edit_note`, `permission_prompts`, `permission_timeout`, `transcript`, `model`.

## Code and tests

- `src/assistant/modules/main_assistant/module.py`, `module.toml` (defaults, `needs`, `packages`); the agent itself is `src/assistant/infra/session_agent.py`, its setup `infra/agent_profile.py`
- In this folder's `tests/`: `test_main_assistant.py` (its defaults under `module.toml`, the same as the old section)
- Centrally, since each runs it with the Hub or tests shared parts: `tests/test_agents.py`, `test_permission_mode.py`, `test_edit_note.py`, `test_multi_agent.py`, `test_mcp_door.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
