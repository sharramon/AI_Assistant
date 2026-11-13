# Handoff: the overnight module-folders run (task 0873d2c8)

**The work:** [module-folders-checklist.md](module-folders-checklist.md). Carry on from it, item by item, in its order.

## The overnight rules (from the user, 2026-11-13; still in force)

- The user is asleep and pre-approved everything here, including doc and structure changes. **Never raise a NEED and never wait.** If a decision is needed, pick the option closest to the approved picture (`docs/html-next-steps/module-folders.html`, section 3; snip `logs\2026-11-13_02-19-03_wtf\snips\snip_ede23309.png`), and add it to the checklist's "Decisions made overnight". If an item is truly blocked, mark it blocked with the reason and go on to the next independent item.
- **No app restart or reload, and no modules on or off**, unless the restart script check passes. The check: find the shell script the user wrote for restarting (look in `scripts/`, `docs/`, the next-steps notes and the app's restart handling), and read what it does. Use it only if it restarts the app and the new session picks this work up on its own from the catch-up message. Before using it, write the handoff and catch-up text so the work continues from the checklist, and log each restart in the morning report. If it doesn't resume the work by itself, or you can't tell, don't restart: put the restart on the morning list. Only check this when a restart or reload is actually needed.
- Never delete folders or files outside the repo (`C:\Chang\Jobs`, the Resume project, `C:\Chang\Jobs\CV_Module`). Copy only, and list what's left for the user to delete. Never `git push`.
- Privacy (see [handoff-privacy-cleanup.md](handoff-privacy-cleanup.md)): real names, the real CV prefix and personal data stay in gitignored local config. Never put them in committed files, commit messages or tests (use `CV_Test_` and made-up names). Check the diff before each commit.
- Don't touch any helper's task (job_search_agent, cv_agent). Runs in Auto.
- **Per item:** do the work, run the full `.\.venv\Scripts\python -m pytest -q -p no:cacheprovider` (about 3 min) and `.\.venv\Scripts\ruff check`, run the item's **Done when** check against the code yourself, then mark it done in the checklist with the evidence, update the count at the top ("N of 20 done") and the overview's "Currently fixing" count (`docs/architecture/README.md`) and the next-steps README row, rebuild the docs (`scripts\build_docs.py`), and commit that item on its own.
- Use the batching, architecture-first and architecture-check skills. Update the module docs, the API and reusable indexes and the overview as each item changes them.
- **At the end:** write a morning report at the top of the checklist: items done and verified; items partly done or blocked, with reasons; the decisions made overnight; what needs an app restart; the hand checks due; old folders left for the user to delete; the real test numbers.
- What worked well this session: handing each item to a `general-purpose` subagent (foreground) with a full brief (read the checklist and the skills, these hard rules, no commit and no checklist edits, report files, tests and restart needs), then verifying and committing it yourself. That keeps your context small.

## Done so far

- **Part 1, commits:** before them the full suite gave 841 passed, 2 deselected, with ruff clean. The real CV prefix was found in two untracked notes and replaced with `<cv_prefix>`. Commits: `2e283b2` (rules 1 and 2, with the Hub's child-result and race fixes), `010ecb6` (named events, the job-to-cv events and the cv fixes including the base_ rename; one commit because the files mix them, which is a decision to note in the report), `2660c25` (the audit note), `111250e` (docs rebuilt). `pytest_run.txt` is a stray old output, left untracked on purpose.
- **Part 2, the checklist:** commit `2e81950`. 20 items, with nine overnight decisions, and the safeguards built: the architecture-check skill's "Plans and checklists" section, the count in "Currently fixing", `cv-agent-folders.md` marked replaced, and the audit's status updated.
- **Part 3, item 1 (every module edits itself): built by a subagent, NOT yet verified or committed.** Its report:
  - The default grant is in `infra/agent_access.py` (`access_items(config, module_id)`, plus the new `module_folder` and `module_folder_of`). task_agents helpers are left out (`own_folder=False`).
  - The Hub's `folders_clash` in `agent_hub/tasks.py` allows a module folder inside a parent grant, and the refusal names the folder and whose grant holds it.
  - The new `tests/test_module_folders.py` has 4 tests. The `config/default.toml` comment is fixed. Docs: agent_hub, permissions, api infra/agents/README/reusable, rebuilt.
  - The subagent reported 845 passed, 2 deselected, ruff clean, but it edited `tests/support.py` after its last full run.
  - It needs an app restart, and cv_agent's and job_search_agent's access cards will show once more (the fingerprint changes).

## Next

1. Verify item 1: the full pytest and ruff; `git grep -n "can't run while the Main Assistant has a task"` finds nothing; `test_module_agent_edits_its_own_folder` and the overlap tests pass. Check `git diff` for personal data. Then mark item 1 done in the checklist (count 2 of 20, with the overview and README counts), add "the task_agents helpers don't get their module folder" to the decisions, add the restart and the two access cards to the morning list, rebuild the docs, and commit.
2. Then items 2 to 19 in order, the same way.
3. Then the morning report.

No Chrome tabs are open.
