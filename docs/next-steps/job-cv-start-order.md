# job_search turns cv on only when its agent needs a CV

> **Status: built (waiting on you) (2026-11-13).** You chose: the job module sends the CV job to cv itself (Q1), and the modules.md rule is rewritten (below). Code, tests and docs are done. `job_search` and `cv` were reloaded on 2026-11-13 (both ok; `job.tailor_cv` is on job_search's menu); both are off, ready for the [smoke test](smoke-test-job-cv.md). Known problem (b), `modules.off` on a failed module, is a separate core change, not built.
>
> **App restart asked (2026-11-13), before the smoke test.** The restart clears job_search's stale `failed` state and loads the comment-only contracts edits. **Done:** code, tests (929 passed; the 1 failure is the old overview link test from the Restructuring section of `docs/architecture/README.md`, not this fix), docs, the reload. **Left:** after the restart, run the [smoke test](smoke-test-job-cv.md) from "Before you start" (clear the two saved grants, turn on job_search alone, check that cv stays off, Deny cv's card once for the fallback). Then the separate note for (b).

**Asked:** "Fix the job and cv start order, then update the docs to reflect the reality." The Main Assistant turns on only job_search. cv stays off until the job agent needs a CV. Then the job module turns cv on, hands it the PDF and the JD, and hears cv's event.

**Why:** cv came on as soon as job_search was turned on. That failed the smoke test's first check every time ([smoke test](smoke-test-job-cv.md)).

## Where the wrong rule came from

- **Chaining is older than the overnight build:** decisions.md "Module shape" (2026-11-04), principle 16 "Chain, don't glue", and the 2026-11-12 decision "Modules talk to each other through named events" (job-cv-finish-event). None of them says who turns the next module on.
- **modules.md:150** ("No module starts another itself … the core does it") is not from the overnight build. It came in commit `6c32d8f` (2026-11-05), written for voice notes → voice_in. Principle 17 said the same thing.
- **modules.md:146** (job_search `needs = ["cv"]`) is from the overnight build: its text came in commit `b787049` (module folders item 2), and job_search's `needs = ["cv"]` in commit `330a380` (item 7), following module-folders-checklist decision 4 and its item 7 hand check. That applied the 11-05 rule to job → cv, which was never decided for that flow.
- **The docs are written by hand.** Agent sessions write the Markdown and commit it under your git name. Only the HTML, each module's tools page and the module library's tables are generated.

## Before the fix, step by step (checked in the code)

| # | Your step | What the code did | Same as wanted? |
|---|-----------|-------------------|-----------------|
| 1 | The Main Assistant turns on only job_search | `modules.on job_search` → `LifecycleManager._activate` turns on every module in job_search's `needs` **first**. `job_search/module.toml` said `needs = ["cv"]`. So cv came up (and showed cv_agent's card) before job_search. | **No: the bug.** |
| 2 | The job module starts the job agent | `JobSearchModule.start` asks for job_search_agent's access (one card), then builds the agent. | Yes |
| 3 | The agent realizes it needs a CV | The `apply-session` skill (step 3) picks the base PDF, saves the JD, and called `cv.task`. | Yes |
| 4 | The job module turns cv on, hands it the PDF and JD, subscribes to cv's event | The **agent** called `cv.task` itself. If cv was off, the door answered "cv isn't on" and the agent asked you, then ran `modules.on cv`. The job module subscribed to cv's events once, at its start. | **No** |
| 5 | cv runs and pings its event | `cv.job_finished` with `reply_to` at its worker's end, `cv.job_submitted` at your Submit. | Yes |
| 6 | The job module gets the event and the tailored PDF | `JobSearchModule._on_cv` wakes the agent with one `DeliverMessage`; the summary gives the PDF path, `cv.read_result` the full result. | Yes |

## The rule, rewritten

- **`needs`** means only "can't run without" (voice_notes → voice_in). job_search's is `[]`.
- **On-demand chaining** (replaces "No module starts another itself"): a module may turn on the add-on it chains to at the moment it needs it, with `ActivateModule`. The core still asks that module's access card (in Manual), and the reply comes back as the other module's named events. Nothing else changes: the module still reaches the other only through its menu and its named events, and the core still turns on what a module `requires` or `needs`.

Written into modules.md (Dependencies, Chaining modules), principle 17, core.md, decisions.md (2026-11-13), the API pages and both modules' pages.

## The fix (built)

1. **job_search/module.toml:** `needs = []`, plus `cv_wait = 600.0` (seconds to wait for cv to come on, your card's Allow included).
2. **New menu item `job.tailor_cv`** on job_search's menu, with `cv.task`'s inputs. Only the job agent may call it (anyone else: `not_available`). It answers at once, then in the background:
   - turns cv on (`ActivateModule("cv")`). In Manual you get cv_agent's access card now, not before.
   - if the card is open, waits for cv to be active (`ModuleStateChanged`), or for your Deny (`PermissionChanged` with nothing granted), up to `cv_wait`.
   - sends `cv.task` as the job module, with `for_agent` = the job agent, so cv's events still reach the agent.
   - tells the agent the outcome with one `DeliverMessage`: the job was taken, or "cv couldn't come on (why). Ask the user whether to use the chosen base PDF untailored."
3. **Subscription:** unchanged. The job module subscribes to cv's two named events from its start; a named event is matched by name, so this works while cv is off, and nothing is missed between turning cv on and the event.
4. **cv/module.toml `[hand_off] modules = ["job_search"]`:** the modules that may send `cv.task` and `cv.read_result` for one of their agents. For such a caller `for_agent` is required and becomes the asker (`reply_to`, the parent task). Anyone else passing `for_agent` gets `invalid_arguments`.
5. **Job project skill** (`job_search/workspace/.claude/skills/apply-session/SKILL.md`, step 3): calls `job.tailor_cv`. Never `modules.on cv`, and it asks you about the untailored PDF only on the module's message.
6. **Tests:** `job_search/tests/test_job_search.py` (needs `[]`; turning job_search on leaves cv off; tailor turns cv on and sends; only for the agent; a failed start gives the untailored question; a card Deny, then Allow; the `cv_wait` timeout), `cv/tests/test_callers.py` (`for_agent`), and the `stand_in("cv")` setups removed from `tests/test_access_cards.py`, `test_agent_names.py`, `test_agent_tabs.py`, `test_module_folders.py`.
7. **Docs:** as listed under the rule, plus the smoke test page, the module-folders checklist (decision 4 and item 7's hand check marked replaced) and the Pending table.

**Touches:** `job_search/module.py`, `job_search/module.toml`, `cv/module.py`, `cv/module.toml`, the apply-session skill, the tests, the docs. Comment-only changes in `contracts/module.py` (`Manifest.needs`) and `contracts/control.py` (`DeactivateModule`): the example is now voice_notes → voice_in; they load at the next app restart, and nothing depends on them. No other core change. A reload of `job_search` and `cv` loads the code (asked first).

## Separate change, not built

**(b) `modules.off` on a failed module leaves it `failed`.** The cause is in the core: `LifecycleManager._deactivate` (`core/lifecycle.py`) returns ok for a module that isn't active and leaves its FAILED state as it was. It should set it to inactive. It's core code, so it needs its own note and an app restart.
