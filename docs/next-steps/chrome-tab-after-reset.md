# Keep a worker's Chrome tab across a reset

> **Status (2026-11-10): steps 1 and 2 (option a, chosen by the user) built, tested and documented (`docs/agents/runtime.md`, `docs/api/infra.md`). Extra tests added: a message during the compact goes in after it, and a failed compact falls back to a fresh session. Waiting on the app restart, which the user wants asked only after all the pending fixes are built.** The second Chrome problem (old tabs never closed) is a separate task.
>
> **Step 2 as built:** `SessionTaskAgent(compact_handoffs=...)` (`ProfileAgent` passes `lambda: profile.chrome`). On `HANDOFF:` a Chrome agent with a live session in the right mode goes to `_Mode.COMPACTING`, sends `COMPACT` (bare `/compact <keep note path and tab ids>`), and on its result sends `HANDED_OFF_COMPACTED` plus any messages held meanwhile (`WHILE_COMPACTING`). A failed compact falls back to `_continue_fresh(note, held)`. Progress reads "Handed off in place, context compacted (n)". New tasks still start fresh. Texts in `infra/handoff_keeper.py`; `BASICS_BLOCK` reworded. Test: `tests/test_agents.py::test_a_chrome_agents_handoff_compacts_the_same_session`.
>
> **Checks:** ruff clean; full suite 786 passed. Known failures not from this change: the cv docs link into next-steps (`test_main_docs_never_link_into_next_steps`), and flaky `test_voice_pieces` closing-socket and `test_html_viewer::test_refuses_what_it_cant_do` (ConnectionAborted; was being re-run).
>
> **Next:** (1) re-run `tests/test_html_viewer.py` to confirm it's flaky; (2) optional extra tests: a message during the compact is held and delivered, and a failed compact falls back to a fresh session; (3) add the Chrome rule to `docs/agents/runtime.md` ("Fresh sessions and handoffs") and `SessionTaskAgent` in `docs/api/infra.md` (`compact_handoffs`), then rebuild the docs; (4) architecture check; (5) ask the user before the one app restart (`src/assistant/infra` changed). `scratch/chrome_clear_spike.py` is the spike script; two example.com spike tabs are left in Chrome for the user to close.

## What happened (job agent, task b7c1a092, 2026-11-10)

From `logs/2026-11-10_17-30-53_open-job-agent/` (`job_search_agent.jsonl`, `assistant.log`):

1. Before the reset the agent worked the Microsoft apply form in Chrome tab **2086284216**, in the tab group of its `claude` session (5a166bfd…). Nothing in the app tracks the tab. Only that session knew its id.
2. At 18:49:45 its context passed 150k. It wrote `C:\Chang\Jobs\CV\docs\next-steps\handoff-b7c1a092.md` and ended with `HANDOFF:`. The note carried the form's **URL** and "Chrome tab (MCP group) is open on the apply form", but no tab id. A tab id wouldn't have helped anyway (see 4).
3. `SessionTaskAgent._continue_fresh` → `_fresh_session` (`src/assistant/infra/session_agent.py`) closed that `claude` process and started a new one (18:50:09, session 741217b8…). That is by design: every task and every handoff gets a new process.
4. The new session's `tabs_context_mcp` answered: *"This session has no tab group of its own. Any tabs opened earlier … may still be open in Chrome, in a group this session cannot see or control."*
5. So the agent did `navigate` to the URL from the note, which made a new group and tab (**2086284219**). The old tab stayed open, unreachable. The form had autosaved on Microsoft's side, so nothing was lost this time.

**Cause:** the Chrome extension ties a tab group to the `claude` **session id**. Every reset starts a new session, so it starts with no tabs: a handoff, a new task, or an answer that arrives after the session is gone. Tasks 4424e909 and 131f8e4f each started a new `claude` too.

## Step 1: say it in the shared texts (built)

- `BASICS_BLOCK` (`infra/agent_profile.py`, every agent's prompt): Chrome tabs belong to your session. Before a `HANDOFF:`, write each open tab's URL and state into the note, and save or finish unsaved form work first. In a fresh session, reopen the note's URLs in your own group and don't look for the old tabs.
- `CHROME_HANDOFF` (`infra/handoff_keeper.py`) is added to the reset request and the 150k reminder. `CHROME_FRESH` is added to the fresh-session start (`HANDED_OFF`) and to the "your question's session is gone" text (`CONTEXT_AGAIN`, `infra/session_agent.py`).
- Test: `tests/test_worker_parts.py::test_handoff_texts_carry_the_chrome_lines`.
- These files are in `src/assistant/infra`, so running agents get them only after an **app restart**.

## Step 2: the spike (done)

`scratch/chrome_clear_spike.py` starts one `claude -p` stream-json session with `--chrome`. The session opens a tab, gets a command, then checks with `tabs_context_mcp` whether the tab is still reachable.

| Command sent | Session id | Context | Tab group |
|---|---|---|---|
| `/clear` | **new** (7a9c… → 0926…) | cleared | **lost**: "This session has no tab group of its own" |
| `/compact` | **same** (6760…) | summarised | **kept**: the same tab 2086284226, reachable |

So the group follows the session id. A clear can't save it, but a compact in the same process can.

### Step 2: options (your choice)

- **(a) Compact instead of a fresh session, for agents with Chrome open.** On a context handoff (`HANDOFF:` after the 150k reminder, or a reset you asked for), an agent started with `--chrome` sends `/compact` to its running session instead of starting a new one, then "continue; your handoff note is <path>". The tab stays. The cost is that the context keeps a summary, so it starts larger than a fresh session reading a note, and a summary can miss details the note has. Only the handoff path changes; a new task still starts fresh. Recommended.
- **(b) The same as (a), and also keep the session across tasks for Chrome agents** (resume with `--resume <id>` plus a compact). Not tested yet: it would need one more spike. Each new job-agent task would then carry the last task's summary.
- **(c) Stop at step 1.** Tabs are reopened from the note's URL. That's enough when sites save on their own (Microsoft did).

Two spike tabs (example.com, 2086284225 and 2086284226) are left in Chrome in their own groups. Close them by hand.

When it's settled, `docs/agents/runtime.md` ("Fresh sessions and handoffs") gets the Chrome rule.
