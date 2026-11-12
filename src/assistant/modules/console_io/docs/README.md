# console_io: terminal 1

## Purpose

Terminal input and output: each line you type becomes an `InputReceived`, and the replies are printed. `exit` or `quit` shuts the app down. On by default.

## Wrapper

| Field | Value |
|-------|-------|
| id | `console_io` |
| provides / requires / optional | nothing |
| permissions | none |

## Config

`[modules.console_io]`: `prompt`.

## Code and tests

- `src/assistant/modules/console_io/module.py`
- `tests/test_app.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
