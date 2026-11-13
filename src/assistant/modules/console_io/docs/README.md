# console_io: terminal 1

## Purpose

Terminal input and output: each line you type becomes an `InputReceived`, and the replies are printed. `exit` or `quit` shuts the app down. On by default.

## Wrapper

| Field | Value |
|-------|-------|
| id | `console_io` |
| provides / requires / optional | nothing |
| permissions | none |
| needs | none ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): a core module, it needs no other module by id |
| packages | none |

## Config

Defaults in `module.toml` in this module's folder; your `config/console_io.toml` (top-level keys, gitignored; `[modules.console_io]` in `config/local.toml` still works, last) only overrides them, key by key ([how a module's config is built](../../../../../docs/api/core.md#app)). `config/default.toml` has no section for it. The key: `prompt` (default `"> "`).

## Code and tests

- `src/assistant/modules/console_io/module.py`, `module.toml` (defaults, `needs`, `packages`)
- In this folder's `tests/` (on the [test kit](../../../../../docs/api/testkit.md)): `test_console_io.py` (its defaults under `module.toml`; off and on again reuses its one input thread)
- Centrally, as a module the core's tests start: `tests/test_find_modules.py`, `tests/test_module_docs.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
