# Restart with reset instructions

> **Status: done (2026-11-03).** Loaded at the next relaunch (2026-11-03 12:59). Approved 2026-11-03 with all four recommended answers. Needs one manual relaunch (core, contracts and `__main__.py` changed); after that, restarts work by voice or text.

**Asked:** "When I ask for a 'restart' I want something that triggers this app being closed and opened. But also for the worker to create a 'reset instructions' that is given as the first input."

**Why:** core, contract and `__main__.py` changes still need a full relaunch, and until now that was done by hand or from a Claude Code session ([`app-update`](../../../.claude/skills/app-update/SKILL.md) step 4). After a relaunch both sessions start blank, so you had to explain again where things stood.

**Touched:** `contracts/messages.py` (`ShutdownRequested.restart`), `core/app.py` (`restart_requested`), `__main__.py` (the launcher), the `talker` module (the `<<RESTART>>` tag, the reset-instructions request, the first input), `config/default.toml` (`[modules.talker] restart_note`, `restart_timeout`), `tests/fake_claude.py`, new `tests/test_restart.py`. Docs: [agents runtime](../../agents/runtime.md#the-talker-on-its-own), [core](../../architecture/core.md#lifecycle), [messaging API](../../api/messaging.md#shutdownrequested), the `agent_tags` Used by lines. Not voice, not hot-loading.

## Before this change

- `ShutdownRequested(reason)` → `App` sets `_stopping` → modules stop in reverse order → `main()` returns 0. Only `console_io` publishes it (`exit`).
- The app is launched by hand: `python -m assistant` in a PowerShell window titled "Assistant: talk here". Nothing relaunches it.
- **`HANDOFF:` lines:** a worker turn ending `HANDOFF: <note>` makes `SessionTaskAgent` start a fresh session on the same task, reading that note. **`<<RESET: worker>>`** sends `RESET_NOW`: "write what's done and next into the change note, end with `HANDOFF:`". Both stay inside one launch.

## As built

```
you: "restart" → Talker <<RESTART>> → worker replies with reset instructions, last line RESTART_READY
  → Talker saves them, publishes ShutdownRequested(restart=True) → app stops, exits with code 75
  → launcher sees 75, starts the app again → Talker's first input = the note → note deleted
```

1. **Trigger:** the Talker's `<<RESTART>>` tag, used only when you ask for a restart. It says in the same reply that it's restarting.
2. **Reset instructions:** the Talker sends the worker `WRITE_RESET_NOTE`, as `SendToTask(resume=false)` if a task runs or as a small `StartTask` if none does. The worker first updates the task's change note. It then replies with what was being worked on, what is done, what is left, and which notes to read, and ends with `RESTART_READY` (read with `agent_tags.last_line`). **Change from the proposal:** the worker writes the instructions in its reply and the Talker module saves the file. Writing under `.claude/` would ask for permission in Manual and hold up the restart.
3. **Waiting on you:** if the task waits on a `need` or a permission, a `[Status]` makes the Talker ask first, and only `<<RESTART: anyway>>` goes ahead (open question 2).
4. **Fallback:** if the worker can't be reached, its task fails, or it doesn't answer within `restart_timeout` (120 s), the Talker saves its own last few exchanges as the note and restarts anyway.
5. **Closing:** `ShutdownRequested(restart=True)` sets `App.restart_requested`, and the app exits with `core.restart_exit_code` (75). This is the normal clean stop.
6. **Reopening:** `python -m assistant` is now a launcher (`__main__.launch`). It runs the app (`run_app`) as a child process with `ASSISTANT_APP_CHILD=1`, in the same console. It waits through Ctrl+C, which the child handles, and starts the child again while it exits with 75. The `app-update` relaunch command still works, because it stops both processes.
7. **Saved at:** `restart_note` = `.claude/state/reset-instructions.md` (gitignored). If it isn't set, restarts carry no note, which keeps tests away from a real note.
8. **Next launch:** if the note is there, the Talker's first turn is `[Restart] The app was just restarted. Reset instructions from the last session: …`. Its prompt says to tell you where things stand and wait for your go (open question 1).
9. **Used once:** the note is deleted once that turn is sent. Any stop that isn't a restart deletes a leftover note too.

**Reused:** `ShutdownRequested`, `agent_tags.last_line`, `StartTask` / `SendToTask` / `GetTaskStatus`, the Talker's inbox and `[Status]` items. No new reusable part; `talker` was added to `agent_tags`' Used by.

**Tests:** `tests/test_restart.py`: restart with an idle worker; asking first when the task waits on you, then going ahead with `anyway`; the fallback note with no worker; the note given first at the next launch and then deleted; a stop that isn't a restart deleting a leftover note; the launcher looping on 75. 256 tests pass, ruff clean.

## Decided (2026-11-03)

1. After a restart the Talker doesn't carry on by itself; it waits for your go.
2. If the worker waits on a permission prompt or a `NEED:`, the Talker asks before restarting.
3. No temp UI button for now.
4. Exit code 75 (`core.restart_exit_code`) and `.claude/state/reset-instructions.md` (`[modules.talker] restart_note`) as defaults.

## Left

- One manual relaunch to load this code, then a live try: say "restart" mid-task and check the first message after the restart.
