# The restart note says everything the next launch needs

> **Status: built, waiting on the batched restart (2026-11-08).** Tests pass. Changes the `talker` module only, so a `RELOAD: talker` would also load it; it waits for the restart with the others.

**Asked:** update the restart note (the reset instructions the app writes when it restarts, the `[Restart]` message the Talker sees first after a relaunch) so it's accurate and complete, for example which helpers were running and which hand checks are due.

## What was missing

The note was only the Main Assistant's reply: what it was working on, what's done, what's left, which notes to read. Since then the app gained helper tabs, agent names, per-tab Auto/Manual, usage tallies and batched restarts, and none of that reached the next launch:

| Missing | What the next session got wrong |
|---------|--------------------------------|
| Which helpers were open, and their tasks | It didn't know `cv_agent` and the others had been there. Launched helpers don't come back after a restart, and every task ends with it |
| Questions waiting behind a tab's **!** | Lost without a word |
| Each agent's mode | Every agent starts in Manual again; the note didn't say who had been in Auto |
| The tab you were in | Not said; the next launch opens on the Main Assistant's tab |
| Changes built and waiting on this restart | Not asked for, so the hand checks now due weren't listed |
| Usage | The counts start again from zero after a restart, which wasn't said |
| The fallback note (no answer from the worker) | Only the Talker's last exchanges, with none of the above |

## What changed

1. **The app writes a state section itself** (`TalkerModule._app_state`) under the worker's instructions, or under the fallback note. It's facts, not the worker's memory: the tab you were in, then every agent (`ListAgents`) with its description (a helper's kind), its mode and whether it was working, then each open task (`hub.status`) with its state, its text, and any question waiting on you (and whether it waited behind the **!**). Then a fixed paragraph says what a restart does: every agent back in Manual, no task carried over, launched helpers gone (reopen by name) while autostart ones are back idle, usage from zero, and the waiting changes now loaded with their hand checks due.
2. **The worker is asked for the waiting changes** (`WRITE_RESET_NOTE`): every row of the Pending changes table in [README](README.md) that is built and waiting on a restart, each with its note's path and the hand checks now due, plus which helpers it started and what for.
3. **The Talker's prompt** (`_RESTART_NOTE`) says what the note holds and what to tell you: where the work stands, the hand checks now due, which helpers were open and that launched ones can be reopened by name, that everyone is back in Manual, and any lost question. It still waits for your go before starting anything.

`_restart` is now async (it reads the agents and tasks before writing). The state section can never stop a restart: if reading fails, the note says so and the restart goes on.

[Restarts that keep the agents running](restart-keep-agents.md) (proposed) would change the "no task carries over" paragraph once it's built.

## Your checks (after the restart)

1. With a helper tab open (and ideally one in Auto, one with a question behind its **!**), ask for a restart.
2. After the relaunch, the Talker's first message should say where the work stands, list the hand checks now due from the batched changes, name the helpers that were open (and offer to reopen the launched ones), say everyone is back in Manual, and mention the waiting question.
3. Before the next launch reads it, the note is at `.claude/state/reset-instructions.md` if you want to see it whole. It's deleted once the Talker has it.
