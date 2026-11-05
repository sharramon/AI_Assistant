# Worker batching reminder

> **Status: done (2026-11-03).** Built as below; both open questions approved (the app logs the second edit; the settings matcher is widened). Loaded at the relaunch of 2026-11-03 12:59. Behavior is documented in [agent runtime](../../agents/runtime.md#fresh-sessions-and-handoffs). Tests: `tests/test_edit_note.py` and one in `tests/test_agents.py`.

**Asked:** remind the worker (Main Assistant) to batch its edits when it edits the same file repeatedly (code, Markdown, config, any type), so it reads each file once and groups all edits to a file into one pass. **It must never interrupt the worker or cost it an extra step**, because interrupts balloon context use.

**Why:** the worker edits the same file in several passes, and every extra step resends its whole context.

**Touches:** `src/assistant/modules/main_assistant/module.py` (prompt line, passes the setting), `src/assistant/infra/claude_session.py` (an `env` argument), `src/assistant/infra/session_agent.py` (writes the current task id), `scripts/hooks/edit_tracker.py`, `.claude/settings.json` (hook matcher), `config/default.toml`, `docs/agents/runtime.md`, `docs/api/infra.md`, tests.

## What's already there

- **A Claude Code hook**, `.claude/settings.json` → `scripts/hooks/edit_tracker.py`, before every `Edit` or `Write`. It counts edits per file per `claude` session and, from the second edit on, adds a note to that tool call's context. This costs no extra step. Gaps: it fires on every repeat, misses `MultiEdit` and `NotebookEdit`, restarts its count after a handoff, and has no off switch.
- **The worker's prompt**, `WORKER_PROMPT`, says "Batch independent reads and edits into one step", but nothing about one pass per file.

## Approach: two cheap parts, no interrupts

**1. An always-present line in `WORKER_PROMPT`**, next to the existing batching line:
> Read each file once, plan all its changes, and make them in one pass (one Write, or one Edit per separate spot in the same step). Edits to a file you've already changed in this task cost a full step each.

It's in the system prompt, so it's cached and costs nothing per step.

**2. The hook's note, made better for the worker only.** It still arrives with the edit itself, so no extra step.
- **Worker only:** the worker's `claude` process gets `ASSISTANT_AGENT=main_assistant` in its environment, through a new `env` argument on `ClaudeSession`. Without that variable, the hook behaves exactly as today, so your own Claude Code sessions don't change.
- **For the worker:**
  - **Once per file per task:** the note comes on the second edit to a file and not again for that file.
  - **All edit tools:** the matcher becomes `Edit|Write|MultiEdit|NotebookEdit` (path from `file_path` or `notebook_path`). For your own sessions the hook exits at once on the two new tools, so nothing changes for you.
  - **Counts across handoffs:** the count is keyed by task, not session. `SessionTaskAgent` writes the current task id to `.claude/state/worker-task.txt` on `assign`; the hook uses `edits-task-<id>.txt` when it's set. A fresh session after a handoff keeps the same task, so it keeps the count.
- **Note text:** *"You've now edited {file} twice in this task. Make the rest of its changes in one pass (batching skill)."*
- **Off switch**, the only config setting:
  ```toml
  [modules.main_assistant]
  edit_note = true  # the worker's once-per-file batching note (false = off; the prompt line stays)
  ```
  Passed as `ASSISTANT_EDIT_NOTE=0` when off; the hook then stays silent for the worker.
- **Logs:** see open question 1.

## Dropped from the earlier design

- **Injecting the reminder through `message()`** (interrupt, then carry on), its holding while the worker waits on you, and the merging of several files into one message.
- **Reusing `ContextWatch`**: not needed, the hook does the counting. Its Used by line stays as it is.
- **The `edit_reminder = 2` setting**: replaced by the on/off `edit_note`; the threshold is fixed at the second edit.
- **The hook skipping the worker**: the hook is now the worker's channel.

## Open questions

1. **Logs.** The hook's note isn't visible to the app, and a pane line must not cost the worker a step. *Recommend: `SessionTaskAgent._on_block` already sees each edit's `tool_use`; it keeps a per-task set of edited files and, on a file's second edit, writes one main-log line and one pane line (`batching note: infra.md`). It's a few lines that mirror the hook's rule; the worker's transcript shows the note itself.*
2. **The `.claude/settings.json` change** (matcher widened to four tools) is a settings edit, so I'll ask before making it during the build. *Recommend: yes, since the hook exits at once for your sessions on the new tools.*

**Restart needed:** `claude_session.py` and `session_agent.py` are in `assistant.infra`, so this needs one app restart. The hook and settings take effect on the worker's next session.
