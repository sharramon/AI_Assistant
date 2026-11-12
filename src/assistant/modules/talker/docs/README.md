# talker: the agents' Talkers, one per agent tab

## Purpose

Fast `claude` sessions that talk with you and hand work to the Agent Hub, **one per agent tab** (built 2026-11-05): each tab is a pair, its Talker and its agent (its partner), with its own chat. Tags in its replies become Hub commands and viewer tools. On by default. Design: [agents](../../../../../docs/architecture/agents.md), [the Talker on its own](../../../../../docs/agents/runtime.md#the-talker-on-its-own).

## Wrapper

| Field | Value |
|-------|-------|
| id | `talker` |
| provides / requires / optional | optional `IModuleDoor` (the module door, from the Agent Hub) |
| permissions | none declared |

## Config

`[modules.talker]`: `model` (every tab's), `turn_timeout`, `context_exchanges`, `context_warning`, `transcript` (the main tab's name; a helper's gets `-<agent>`), `restart_note`, `restart_timeout`, `door`.

## Code and tests

- `src/assistant/modules/talker/module.py` (the router), `session.py` (`TalkerSession`), `prompt.py` (`talker_prompt`)
- `tests/test_agents.py`, `test_agent_tags.py`, `test_restart.py`, `test_talker_agents.py`, and the snip tests in `test_html_viewer.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
