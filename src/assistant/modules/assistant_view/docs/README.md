# assistant_view: terminal 2

## Purpose

A view-only console window showing what the agents are doing. Off by default (the temp UI's left pane shows the same); turn it on with `ActivateModule`. Windows only for now.

## Wrapper

| Field | Value |
|-------|-------|
| id | `assistant_view` |
| provides / requires / optional | nothing |
| permissions | none |

## Config

None.

## Code and tests

- `src/assistant/modules/assistant_view/` (`module.py`, `viewer.py`)
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
