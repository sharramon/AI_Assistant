# echo_orchestrator: stand-in orchestrator

## Purpose

Replies with the input text; `/tools` lists the available tools. It exists to prove the plumbing without an AI. Off by default; enable it instead of the Talker in `modules.enabled`.

## Wrapper

| Field | Value |
|-------|-------|
| id | `echo_orchestrator` |
| provides / requires | nothing |
| optional | [`IToolProvider`](../../../../../docs/api/tools.md#itoolprovider) (to list tools) |
| menu | a [`Menu`](../../../../../docs/api/modules.md#menu) with one item, `echo.say` ([Tools](tools.md)) |
| permissions | none |

## Config

None (no `module.toml`).

## Code and tests

Everything is in this module's folder, `src/assistant/modules/echo_orchestrator/`:

- `module.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab)
- `tests/test_echo.py`: the echo, `/tools`, the `echo.say` item. Its use as a stand-in orchestrator in the core's tests stays in `tests/test_app.py` and `tests/test_mcp_door.py`.
