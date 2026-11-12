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

## Config

`[modules.temp_ui]`: `port` (8765), `window`.

## Code and tests

- `src/assistant/modules/temp_ui/` (`module.py`, `agent_tabs.py`, `page.html`, `static/grants.js`, `static/agent_tabs.js`)
- `tests/test_temp_ui.py`, `tests/test_agent_tabs.py`, `tests/test_access_cards.py`, `tests/test_taskbar_flash.py`, and the snip tests in `tests/test_html_viewer.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
