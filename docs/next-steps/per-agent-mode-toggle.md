# Each agent's own Auto/Manual toggle, shown in the UI

> **Status: idea, for later (2026-11-06).** No action now; to be designed with the UI handler.

**Asked:** "Each agent should have its own Auto/Manual toggle, tracked and shown by the UI, so the real mode of every agent is visible." (relayed by the job agent's Talker)

**Why:** pressing Auto in one tab (the Main Assistant's, say) looks like it sets every agent, but it only sets that one agent. The job agent then still asks for permissions, so you end up pressing Manual, then Auto, in every agent's tab.

**The bug fix under it** (each tab's button sets and shows its own agent) is its own note: [The Auto button sets the agent of the tab you're in](per-agent-auto-button.md), proposed.

**Notes for when it's picked up:**
- The mode is already per agent (`SetPermissionMode` takes an `agent_id`; `PermissionModeChanged` says which agent and whether it applies `now` or at `next_task`). So the gap is mostly in the UI: show each tab's real mode from those events, rather than one toggle that seems to apply to all.
- Possibly an "all agents" switch as well, sending `SetPermissionMode` to each agent.
- The temp UI is a stand-in, so this belongs to the UI handler's design ([decisions](../architecture/decisions.md#open-decisions)).
