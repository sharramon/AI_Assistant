# Closing the tab you're in moves you to the Main Assistant's tab

> **Status: built (waiting on you), 2026-11-06.** Approved as written. Built: the Hub's `_focused()` publishes `FocusChanged` when it falls back, and the Hub calls it on `AgentStateChanged` / `ModuleStateChanged`; `_set_focus` counts a gone agent as `previous`; the temp UI's own `SetFocus` after a close is gone. Test: `test_agent_tabs.py::test_when_the_tab_youre_on_goes_you_land_on_the_main_assistants` (× close, module off, an unfocused agent going moves nothing). **2026-11-06: the app is being restarted, which loads both, so no reload is needed after it; only the hand check is left.** (Without a restart: reload `agent_hub` and `temp_ui` **once no task is open** (`modules.reload agent_hub`, then `modules.reload temp_ui`, from the Talker), then the hand check below.) **Don't reload `agent_hub` from inside a task:** a `RELOAD: agent_hub` at the end of the Main Assistant's task waits for the Hub to go idle, the Hub counts that same task as open, so it waits the full `reload_idle_timeout` (300 s) and fails with nothing changed (seen 2026-11-06). `now` would cut in but drops the Hub's task records (no handover of tasks yet). Worth its own fix later: the Hub handing its open tasks over on reload.

**Asked:** found while redoing hand check 6 ([close-tab-ends-talker](close-tab-ends-talker.md), [agent-talkers](agent-talkers.md)). "When I close the window, I don't get kicked off it while I'm in it. I need to get kicked off into the Main Assistant's window, because that one never dies." Check the same for every other way a tab can go away.

**Why:** you stay on a dead tab. What you type goes to an agent that no longer exists, and the page shows nothing selected you can use.

## Cause

The Agent Hub owns the focus. Its `_focused()` helper checks whether the focused agent still exists and, if not, **quietly** sets the focus back to the Main Assistant, without telling anyone (no `FocusChanged`).

- **Closing with ×:** the temp UI does send `SetFocus(main_assistant)` after `agents.close`. But the Hub's `_set_focus` reads "previous" through `_focused()`, which has already reset it to `main_assistant`. So target equals previous, the Hub sees "no change" and publishes no `FocusChanged`. The temp UI (and the page) keep showing the closed helper's tab as focused.
- **Every other way** (the job agent turned off, `task_agents` turned off, a helper's module failing): the temp UI only re-reads the tab list. Nobody sends `SetFocus` and nobody publishes `FocusChanged`, so you stay on the dead tab there too.

## Fix

Put it in one place, the Hub, since it owns the focus:

1. **`_focused()` says so when it falls back.** When the focused agent is gone, it sets the focus to the coordinator *and* publishes `FocusChanged(agent_id=main_assistant, previous=<gone agent>)`, logs "Focus: main_assistant (<agent> is gone)", and feeds the usual `[focus]` line.
2. **The Hub checks at once when an agent may have gone.** It listens to `AgentStateChanged` and `ModuleStateChanged` (the events every removal path already sends: `agents.close` since the last fix, `modules.off`, a module failing) and calls `_focused()`. That covers all three paths without each sender having to remember.
3. **The temp UI's own `SetFocus` after a close is dropped**: the Hub now does it, so there's one rule, not two.

The temp UI already moves the page when `FocusChanged` arrives, so no page change is needed. No new part, no new event.

**Tests** (in `test_agent_hub*.py` / the temp UI's tests): focused on a helper, then `agents.close` → `FocusChanged` to `main_assistant`; the same for `DeactivateModule` of the helper's module; and no `FocusChanged` when an agent you're *not* on goes away.

**Touches:** `agent_hub` (fixes 1 and 2), `temp_ui` (fix 3). Docs: [agent_hub](../../src/assistant/modules/agent_hub/docs/README.md) and the `FocusChanged` / `SetFocus` entries in [API: agents](../api/agents.md) ("the focus falls back to the coordinator when its agent goes, with a `FocusChanged`").

**Open questions:** none. (A helper whose `claude` process crashes but stays listed keeps its tab, so it isn't a dead tab; that's unchanged.)

## Restart?

**No restart.** Both are modules: `RELOAD: agent_hub`, then `RELOAD: temp_ui`. Then check: open a helper with **+**, stay on its tab, close it with × → you land on the Main Assistant's tab. Optional: the same with `modules.off job_search` while on the job agent's tab.
