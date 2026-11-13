# temp_ui: the temporary two-pane page

## Purpose

A local web page with the worker's activity on the left and the Talker conversation on the right, with the mic button, usage meters, permission cards and the Manual | Auto toggle. A throwaway stand-in until the UI handler is designed. On by default. Design: [temp UI](../../../../../docs/agents/runtime.md#temp-ui).

## Wrapper

| Field | Value |
|-------|-------|
| id | `temp_ui` |
| provides / requires | nothing |
| optional | [`IAgentNames`](../../../../../docs/api/agents.md#iagentnames) (which module an agent belongs to, for the tabs' ×) |
| permissions | none declared |
| needs | none ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): a core module, it needs no other module by id. Its Open in viewer button opens pages through the page-opener slot ([`IPageOpener`](../../../../../docs/api/modules.md#ipageopener)), which an add-on fills, so it names no add-on |
| packages | none |

## Config

Defaults in `module.toml` in this module's folder; your `config/temp_ui.toml` (top-level keys, gitignored; `[modules.temp_ui]` in `config/local.toml` still works, last) only overrides them, key by key ([how a module's config is built](../../../../../docs/api/core.md#app)). `config/default.toml` has no section for it. The keys: `port` (8765), `window` (`"app"`); `host`, `window_profile` and `worker` have their defaults in code.

## Code and tests

- `src/assistant/modules/temp_ui/` (`module.py`, `module.toml`, `agent_tabs.py`, `page.html`, `static/grants.js`, `static/agent_tabs.js`)
- In this folder's `tests/` (on the [test kit](../../../../../docs/api/testkit.md)): `test_temp_ui.py` (its defaults, the page, the mic button, the agent tabs, the reset buttons), `test_temp_ui_snips.py` (snips heard by name, a pasted image, the Open in viewer button), `test_taskbar_flash.py`
- Centrally, with other modules: `tests/test_agent_tabs.py`, `tests/test_access_cards.py`, `tests/test_permission_mode.py`, `tests/test_usage.py` (the usage tally on the page)
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
