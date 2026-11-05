# Worker context reminder

> **Status: done (2026-11-03).** Approved with all three recommendations: the worker hands off by itself (`HANDOFF:`); the Talker keeps its 150k warning about the worker, reworded to say the worker has been reminded; the reminder interrupts the current step and the task carries on. Built as described; loaded at the relaunch of 2026-11-03 12:59. Tests: `test_context_watch_fires_once_per_crossing`, `test_context_reminder_hands_off_once_per_session`, `test_context_reminder_waits_for_an_open_permission_request` in `tests/test_agents.py`.

**Asked:** "a code snippet … that waits for the context to pass 150k and then injects a 'reminder to find a reset point' prompt into the worker."

**Why:** nothing tells the worker its context is big. The Talker's `context_warning` (150k) only goes to the Talker, as a `[Status]` for you, so the worker keeps working while every step resends 150k+ tokens.

**Touches:** `src/assistant/infra/session_agent.py` (`SessionTaskAgent`), `src/assistant/modules/main_assistant/module.py` (passes the config value), `src/assistant/modules/talker/module.py` (uses the shared check), `config/default.toml`, `docs/api/infra.md`, `docs/api/reusable.md`, `docs/agents/runtime.md`, tests in `tests/test_agents.py`.

## Approach

- **Where it watches:** in `SessionTaskAgent._publish_usage`, which already runs after every call with the worker's `session_usage`. No new subscriber, no new event: the agent that owns the session watches its own context. Every task agent built on `SessionTaskAgent` gets it.
- **Reuse, not a copy:** the Talker's `_check_size` logic (warn once, re-arm when back under) moves into a small shared helper, **`ContextWatch`** in `assistant.infra` (`crossed(agent_id, tokens) -> bool`). The Talker's warning and the worker's reminder both use it. Added to `docs/api/reusable.md` with *Used by: talker, SessionTaskAgent (main_assistant)*.
- **Config, same style as the Talker's:**
  ```toml
  [modules.main_assistant]
  context_reminder = 150000  # tokens: once past this, the worker is reminded to find a reset point (0 = off)
  ```
- **How it's injected:** through the existing `message(task_id, text)` path, the one `SendToTask` and `<<RESET: worker>>` use. Mid-turn it interrupts, sends the reminder, then continues the task (`resume=True`). The task is not cancelled.
  - Only fired while a task is **working**. If the worker is waiting on you (a question or a permission request), the reminder is held and sent the next time it works, so an open permission request isn't dropped.
  - No task (idle): nothing is sent; the next task starts a fresh session anyway.
- **Once per crossing:** fires the first time context passes the threshold, then stays quiet. A handoff or reset starts a fresh session, its context drops under the threshold, and that re-arms it.
- **Reminder text** (a constant next to `RESET_NOW`):
  > [Context check] Your context is at {tokens}, past {limit}: every step now resends that much. Find a good reset point: finish the step you're on or pause at a safe boundary (tests passing, no half-done edits). Then write what's done and what's next into this task's change note in docs/next-steps/ (or docs/next-steps/handoff-{task_id}.md), say in one line that you're at a reset point, and end with `HANDOFF: <that note's path>`.
- **In the logs:**
  - main log: `INFO main_assistant: context 152k past 150k: reminded task 1a2b3c4d to find a reset point`
  - activity line (terminal 2 and the temp UI's worker pane): `context reminder sent (152k)`
  - the worker's transcript holds the reminder as a user message, like any `SendToTask`.

## Open questions

1. **After the reminder: hand off by itself, or stop and ask you?** A `HANDOFF:` line already continues the task in a fresh session automatically, and the Talker tells you. The alternative is ending with `NEED:` so you choose when to reset. *Recommend: `HANDOFF:` (as in the text above); the reset happens without waiting on you, and you still hear about it.*
2. **The Talker's own worker warning at 150k:** keep it alongside? *Recommend: keep it, reworded to "the worker has been reminded to find a reset point", so you're told once, not asked to reset by hand.*
3. **Interrupting mid-turn** cuts the current step short (the worker continues right after). *Recommend: accept it; that's how every `SendToTask` works today.*

**Restart needed:** `session_agent.py` and the shared helper are in `assistant.infra`, so this takes one app restart, not a module reload.
