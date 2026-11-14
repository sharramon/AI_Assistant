# The Main Assistant's session starts without the module door

> **Status: built (waiting on you) (2026-11-05).** Approved with the recommended approach. Needs an app restart (infra code), then the helper launch test is rerun.

**Cause, confirmed:** `agent_hub` provides `IModuleDoor` at its init, but the door gets its address only at the Hub's `start` (`DoorServer.start`); until then `mcp_config` returns `{}`. `main_assistant` starts before `agent_hub` (the Hub lists `ITaskAgent` as optional), so its session, started with the module, had no door. The "later" empty starts in the log were the same process: claude repeats its init line every turn.

**Built:** `ProfileAgent.start` (with `start_session`) sees there's no door, logs a warning, and listens for `ModuleStateChanged`. The first `active` with the door up restarts an idle session once with the new `SessionTaskAgent.restart_session()`; a busy agent is left alone. That method holds a session lock which every session start now takes, because a first try (`reset()`, then `start()`) raced with a task arriving during the close and broke it. Tests: 485 pass, plus the known flaky voice test; ruff clean. Test: `test_the_worker_restarts_once_to_pick_up_the_door` in `tests/test_mcp_door.py`. Docs: `ProfileAgent` in `docs/api/infra.md`.

**Asked:** the live helper launch test (handoff-73fc479c item 3) couldn't run, because the Main Assistant had no module door tools. Write a change note for the fix; don't change code yet.

**Why:** with no door, the Main Assistant can't use `modules.*`, `hub.*` or `agents.*`, so none of the live checks after the restart can run. What the launch `2026-11-05_16-09-39` shows:
- The door runs: `assistant.log` has "The agents' module door is at http://127.0.0.1:49628", with no errors.
- The Main Assistant's session never gets it: every session start in `main_assistant.jsonl` shows `"mcp_servers": []`. In the 13:16 launch it showed `modules` as `connected`. So the config was never handed over; this isn't a connection that failed.
- Likely cause: `ProfileAgent.door()` (`src/assistant/infra/profile_agent.py:70`) returns `{}` when `ctx.get_one(IModuleDoor)` finds nothing. `start_session=True` starts the first session before `agent_hub` has registered the door. Not confirmed yet: later session starts in this launch were empty too, so `get_one` may also come back empty after the Hub is up (for example the agent can't see the contract, or `door` is false in the config).

**Left, after the restart:** (1) Check that the Main Assistant's session has the `modules` door: its tools load, and the log says "main_assistant restarted its session with the module door". (2) Open hand check, not yet rerun: with `task_agents` on, `agents.launch` two job search helpers under different names and Allow each; each starts, shows its access card and gets its own tab, `hub.agents` lists both, and a taken name is refused with a free one offered. (3) Report, and leave task_agents on until the user says otherwise. Nothing is committed or pushed.

**Touches:** `src/assistant/infra/profile_agent.py` (infra: needs an app restart), its tests, and possibly `agent_hub`'s start order. Docs: `docs/api/infra.md` (`ProfileAgent`).

**Approach:**
1. Confirm the cause first: log one line at each session start saying what `door()` found (door missing, or turned off in config), and run it in a test that starts `main_assistant` before `agent_hub`. If later starts still find nothing, the bug is in how the agent looks up the contract, and the note gets updated before any fix.
2. Fix, if the cause is confirmed: when there's no door at session start, a warning is logged. When the door appears (the Hub provides `IModuleDoor`), an idle agent restarts its session once so it picks the door up. A busy agent picks it up at its next session start, as it does now.
3. Add a test: start the agent before the Hub, then provide the door. The next session's command must have `--mcp-config`.
4. After the restart, rerun the helper launch test (the open hand check under "Left" above).

**Open questions:**
- Restart the idle session when the door arrives, or hold the first session start until the Hub is up? **Recommended:** restart it when the door arrives. Holding the start would tie `main_assistant` to `agent_hub`, and the two can't depend on each other (that dependency would be circular).
