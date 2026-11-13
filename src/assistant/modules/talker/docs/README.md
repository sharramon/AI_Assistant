# talker: the agents' Talkers, one per agent tab

## Purpose

Fast `claude` sessions that talk with you and hand work to the Agent Hub, **one per agent tab** (built 2026-11-05): each tab is a pair, its Talker and its agent (its partner), with its own chat. Tags in its replies become Hub commands and viewer tools. On by default. Design: [agents](../../../../../docs/architecture/agents.md), [the Talker on its own](../../../../../docs/agents/runtime.md#the-talker-on-its-own).

## Wrapper

| Field | Value |
|-------|-------|
| id | `talker` |
| provides / requires / optional | optional `IModuleDoor` (the module door, from the Agent Hub) |
| permissions | none declared |
| needs | none ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): a core module, it needs no other module by id |
| packages | none |

## Config

Defaults in `module.toml` in this module's folder, with their comments; `[modules.talker]` in the app's config (your `config/local.toml`) only overrides them, key by key ([how a module's config is built](../../../../../docs/api/core.md#app)). `config/default.toml` has no section for it. The keys: `model` (every tab's), `turn_timeout`, `context_exchanges`, `context_warning`, `transcript` (the main tab's name; a helper's gets `-<agent>`), `restart_note`, `restart_timeout`, `door`.

## Code and tests

- `src/assistant/modules/talker/module.py` (the router), `session.py` (`TalkerSession`), `prompt.py` (`talker_prompt`), `restart.py` (`RestartFlow`), `module.toml` (defaults, `needs`, `packages`)
- In this folder's `tests/` (on the [test kit](../../../../../docs/api/testkit.md)): `test_talker.py` (tags, the session theme, the context warnings, a reset, spoken input, its defaults under `module.toml`), `test_talker_snips.py` (snips, a pasted image, the viewer's open tabs), `test_talker_parts.py`, `test_talker_prompt.py`
- Centrally, with the Hub and a worker or temp_ui: `tests/test_agents.py`, `test_agent_tags.py`, `test_restart.py`, `test_talker_agents.py`, `test_mcp_door.py`, `test_permission_mode.py`, `test_usage.py` (its `[Usage]` line)
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
