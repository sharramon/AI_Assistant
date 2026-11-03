---
name: batching
description: Use before any multi-step task (several reads, edits, builds, or questions). The single source of the batching rules that keep the step count and per-step cost down.
---

# Batching

Every step resends the whole conversation, so each extra step costs the full context again. These rules are mechanical: follow them as written, not as advice.

**The slip to avoid.** In this project the same file kept getting edited again and again: eight separate edits to one API page, and runs of two edits on the same README and the same architecture page. Each was "a small fix far from the last one". That reason doesn't count.

## Rules

1. **Plan first.** Before the first edit of a task, write one message that lists every file you will change and every change in each. Read everything that plan needs in one batch, each file once.
2. **One edit per file per task.** Each file gets exactly one Edit or one Write in the task. If a file has three or more separate changes, or it's any docs page (`docs/**/*.md`), use a single Write of the whole file.
3. **Check before every edit.** Ask: "Have I already edited this file in this task?" If yes, don't edit it again: fold the change into the pending changes for a file you haven't touched yet, or, if none is left, note it for the end-of-task check.
4. **Tests once.** Write test code and assertions carefully the first time. Run the tests once, at the end. Rerun only after a real failure, and only after fixing it.
5. **One docs build, at the end.**
6. **Group edits across files** into one tool batch, and **ask one consolidated question**, not several.
7. **End-of-task check.** In the report, list every file you edited more than once and why. If none, say "no file edited twice".
8. **Reset the session between tasks**, so the next task doesn't resend this one's context.
