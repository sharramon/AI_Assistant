# assistant_view: terminal 2

## Purpose

A view-only console window showing what the agents are doing. Off by default (the temp UI's left pane shows the same); turn it on with `ActivateModule`. Windows only for now.

## Wrapper

| Field | Value |
|-------|-------|
| id | `assistant_view` |
| provides / requires / optional | nothing |
| permissions | none |
| needs | none ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): a core module, it needs no other module by id |
| packages | none |

## Config

None: its `module.toml` holds only `needs = []` and `packages = []`.

## Code and tests

- `src/assistant/modules/assistant_view/` (`module.py`, `module.toml`, `viewer.py`)
- No tests of its own (it opens a console window); `tests/test_swap_every_module.py` swaps it with the others
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
