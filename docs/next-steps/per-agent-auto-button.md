# The Auto button sets the agent of the tab you're in

> **Status: built, waiting on the restart (2026-11-06).** Built as below, steps 1–5; not reloaded (you were working with sub-agents), so it takes effect at your next app restart (a reload of `temp_ui` and `talker` would also do). Tests: `test_permission_mode.py` (the button sends its tab's agent, none means the Main Assistant, an unknown agent is refused, a helper's mode is kept and noted in its own tab; `[Mode] main_assistant: auto`). One test-only fix: the replay check reads the Main Assistant's chat only.

**Asked:** "The auto button has to be fixed now as well. Put that onto the pile." After the job agent kept asking for permissions with Auto pressed in its tab.

**Related:** the idea [Each agent's own Auto/Manual toggle](per-agent-mode-toggle.md). This note is the bug fix under that idea: each tab's button sets and shows its own agent. An "all agents" switch stays with the idea, for the UI handler.

## What's wrong today

Found in the logs: `job_search_agent` never left Manual (every session started in `acceptEdits`). Every Auto press switched the **Main Assistant** instead, which has been in Auto since.

- `temp_ui/module.py:631`: `POST /permission-mode` always sends `SetPermissionMode` to the Main Assistant (`self._agents["worker"]`), whichever tab you're in.
- `temp_ui/page.html:371`: the page posts only `{mode}`, not the tab's agent.
- `temp_ui/module.py:368` (`_on_mode`): ignores mode changes of any agent but the Main Assistant, and always names it "Main Assistant". So a helper's tab can never show its real mode.
- `talker/module.py:365-369` (`_on_mode`): the `[Mode]` note says "worker". In a helper's tab that reads like its own partner.

Past the UI it already works per agent: `SetPermissionMode` takes an `agent_id`, the Hub routes it, and `SessionTaskAgent` applies it.

## The fix

1. **`page.html`:** post `{mode, agent: <the current tab's agent id>}`; each tab's button shows the mode kept for its agent.
2. **`temp_ui` `/permission-mode`:** send `SetPermissionMode` to that agent; the Main Assistant when none is given.
3. **`temp_ui` `_on_mode`:** keep the mode per agent and push it with the agent's id; the note names the real agent.
4. **`talker` `_on_mode`:** the `[Mode]` note names the real agent id, not "worker".
5. **Tests** for the route (agent given, none given) and the per-agent push; `pytest`, `ruff`; docs (temp UI page, [runtime](../agents/runtime.md#temp-ui)) and rebuild.

Then `RELOAD: temp_ui` and `RELOAD: talker`.

## After the fix (by design, unchanged)

- Auto pressed while the agent is mid-task applies from its next task or handoff session (Auto's prompt is fixed at session start). Pressed while idle, at once. Manual applies to the running process at once.
- A Reset or new task keeps the chosen mode.

## Your check

In the job agent's tab, press Auto: its button shows Auto, the Main Assistant's tab is unchanged, and the job agent's next session stops asking. Separately: the Main Assistant is in Auto now; switch it back to Manual if you want.
