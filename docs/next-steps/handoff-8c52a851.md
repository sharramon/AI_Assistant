# Handoff: prepare the helpers for the batched restart (task 9, after the code-review cleanup)

## Done

- The whole code-review cleanup is built: chunks 1 to 14, with A, B and C. 696 tests pass and ruff is clean. The record is in [code-review.md](code-review.md), under "Done (session 9, task 9)".
- All of it waits on one full app restart. The hand checks for after the restart are in code-review.md.
- The user said **YES to the restart**, but **the user will restart the app themselves**. Do NOT restart, reload, or ask about a restart again.
- Helpers checked (2026-11-08): only `job_search_agent` (task `26423c52`) is running; `cv_agent` is gone. Its task has no parent, so `hub.send` was refused; the user tells it in its own tab to stop and write its handoff note. Recorded in code-review.md, "The helpers before the restart".

## Next

- Once the user gives the job agent's note path, add it to that section of code-review.md and rebuild with `build_docs.py`.
- After the restart: restart its task with `hub.start` (`agent_id="job_search_agent"`, text pointing at its note), and do the hand checks.
