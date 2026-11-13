# Job ↔ cv: module-to-module through named events

> **Status (2026-11-13, 02:51): the smoke test's order is rewritten (step 2 of [Loading and the check](#loading-and-the-check-both-after-your-go)): job_search on alone, the job agent turns cv on. Smoke test 4 ran in that order and was blocked at `cv.task` ([results](#smoke-test-4-results-2026-11-13)): the job agent turned cv on itself (pass), but cv refused the task because the Main Assistant's own task was open. cv and job_search are off again. Rerun with the Main Assistant ending its task right after the `hub.start`.**
>
> Earlier status (2026-11-13): **the fixes for problems A and B, and the `base_` rename (problem C), are verified: 821 tests pass and ruff is clean ([Tests](#tests-2026-11-13)). Decided: no fallback for lost events. Nothing is reloaded, restarted or committed. Next, each on your go: the app restart, then smoke test 4.**
>
> Earlier status (2026-11-12, evening): the fake-job check ran; the event path works. See [The fake-job check: results](#the-fake-job-check-results-2026-11-12).
>
> Earlier status: built (2026-11-12), waiting on you: one app restart (`StartTask.tell_parent` is a contract change), then the fake-job check below, both after your go. **2026-11-12, before the restart:** 818 tests pass, docs rebuilt; the flow page [job-cv-flow](job-cv-flow.md) is drawn (event bus as its own block) and you approved it; you gave the go for the restart ("build it"). **Left after the restart:** the fake-job check (step 2 below) only on your go; then the design-notes skill task, also on your go. No agent is started until you say so. Approved with your three answers: (1) `tell_parent=False`; (2) the job agent updates the tracker row, the module writes nothing into the job project; (3) the Submit goes the same way, as a named event (your later message).

## The design

Modules talk to each other through named events ([`ModuleEvent`](../api/messaging.md#moduleevent): `ctx.publish_named` / `ctx.subscribe_named`). A direct tool is only for a call out.

| # | Step | How |
|---|------|-----|
| 1 | The job agent passes the job to cv | the `cv.task` tool (a call out). cv starts cv_agent as the job agent's child task, with `tell_parent=False` |
| 2 | cv_agent ends the job (`done` or `failed`) | cv hears its own worker's end (`TaskUpdated`) and publishes **`cv.job_finished`** |
| 3 | The user presses Submit in the CV Tool | the app tells cv on its event stream; cv publishes **`cv.job_submitted`**, once per Submit |
| 4 | job_search hears both | `subscribe_named`; it keeps the events whose `reply_to` is its agent and wakes the agent with one `DeliverMessage` each |
| 5 | The job agent acts | updates the job's tracker row as its project's skills say; the whole result with `cv.read_result task_id=…` |

One path only. The Hub sends no child-task message for cv's task (`tell_parent=False`), and cv sends the job agent no message of its own. The parent link stays, so the job agent can still `hub.send` to cv's task without a card.

Event data ([the table](../api/messaging.md#moduleevent)): both carry `reply_to`, the job folder, company, role and a one-line `summary` written by cv. `cv.job_finished` adds the task, its state and the parsed `CV_RESULT`; `cv.job_submitted` adds the PDF, the score and the whole `result.json`.

## What was cut (the audit)

Every other route between cv and the job agent, checked 2026-11-12:

| Route | Where | Now |
|-------|-------|-----|
| The Hub's child-task message, with `parent_note` and the parent's brief quoted | `agent_hub/tasks.py` `_to_parent`, `contracts/agents.py` `StartTask.parent_note`, `hub.start`'s `parent_note` input, `cv/handoff.parent_note` | `parent_note` and the brief quote removed everywhere; the plain message stays for other parents; cv's task sets `tell_parent=False` |
| cv's Submit message to the asker (`DeliverMessage` to `reply_to`) | `cv/module.py` `_tell_asker` | replaced by `_pass_submit`, which publishes `cv.job_submitted` |
| `cv.task`'s `next` text ("comes to you as a message naming your brief") | `cv/module.py` | now says: cv publishes the events, your module wakes you |
| `job_start.json` `replied` record | `cv/reply.py` | kept, to pass each Submit on once; `how` is now `published cv.job_submitted` |
| cv_agent's `AgentNotice` about a Submit | `cv/module.py` | kept: it goes to cv's own worker, not the job agent |
| The Rezi click message | `cv/module.py` `_tell_worker_rezi` | kept: it goes to cv_agent, not the job agent |
| The job project (`C:\Chang\Jobs\CV` CLAUDE.md, skills) | | nothing to cut: it only calls `cv.task`. It has no step for the result either; the message tells the agent to update the tracker row |
| cv's worker prompt (`cv/worker.py`) | | nothing: it never tells cv_agent to message the asker |

## Known gap (not built, your call)

A named event published while job_search is off or reloading, or across an app restart, is lost: the bus keeps nothing. With `tell_parent=False` nothing else wakes the job agent then. The result is still in the Hub's task record (last 20 finished) and the job folder. A fallback (cv marks the job finished in `job_start.json`, job_search reports unreported ones when it starts) was proposed. **Decided 2026-11-13: no fallback.** Losing these events is accepted, as normal at-most-once event behavior.

A job agent woken in a fresh session gets the job, the folder, the summary and what next, but not its own earlier brief.

## Files

- Contract: `contracts/agents.py` (`StartTask.tell_parent`; `parent_note` removed).
- agent_hub: `tasks.py` (`TaskRecord.tell_parent`, `_to_parent`, the plain `CHILD_ENDED`), `module.py` (`hub.start` without `parent_note`).
- cv: `module.py` (`_on_task`, `_pass_submit`, `cv.task`, manifest `publishes_named` and `TaskUpdated`), `handoff.py` (`JOB_FINISHED`, `job_finished`, `finish_summary`), `reply.py` (`JOB_SUBMITTED`, `job_submitted`, `submit_notice`), `submit_watch.py` (docstring).
- job_search: `module.py` (`CV_FINISHED`, `CV_SUBMITTED`, `_on_cv`, `cv_finished_text`, `cv_submitted_text`, manifest `listens_named` and `DeliverMessage`).
- Tests: `agent_hub/tests/test_child_result.py` (plain text; `tell_parent=False` tells no one), `cv/tests/test_reply_delivery.py` (cv → both events, no message), `cv/tests/test_tool.py`, new `job_search/tests/test_cv_events.py`.
- Docs: `docs/api/agents.md`, `messaging.md`, `modules.md`, `reusable.md`, `README.md`; `docs/architecture/decisions.md`, `communication.md`, `modules.md`, `agents.md`; the cv, job_search and agent_hub module pages.

## Loading and the check (both after your go)

1. **One app restart:** the contract changed. It loads agent_hub, cv and job_search with it; no reloads needed. (Done 2026-11-13 02:19, launch `logs/2026-11-13_02-19-03_wtf`.)
2. **The fake job, in this order (updated 2026-11-13 on your request):**
   1. **Start: cv off.** The Main Assistant checks with `modules.list` that cv is off (`modules.off cv` if not) and that no earlier fake-job task is open. Then it turns on **job_search only** (`modules.on job_search`). The job_search module subscribes to `cv.job_finished` and `cv.job_submitted` when it starts.
   2. **The job agent turns on cv itself.** The Main Assistant makes one `hub.start` on `job_search_agent` with the fake-job brief (NonexistentTestCo / Smoke Test Engineer, a `CV_Test_*.pdf` base CV; notes for cv_agent: no Chrome, no Rezi, end at once with `CV_RESULT` status "stopped"). The brief tells the job agent that cv is off and that it turns cv on with `modules.on cv` before its `cv.task` call. Give `base_cv` as the full path (`C:/Chang/Jobs/CV/<name>.pdf`): the bare file name was refused on 2026-11-13. **The Main Assistant then ends its own task at once** (its turn ends right after the `hub.start`): cv refuses `cv.task` while any open task writes the repo, which cv_agent also writes, and the Main Assistant's task counts. The log check (step 4) is a separate, later task.
   3. **cv fires its event:** cv_agent ends the job and cv publishes `cv.job_finished`.
   4. **The check:** the logs show that job_search received the event and the job agent was woken by it.

   **The Main Assistant must NOT turn cv on by hand.** That hides whether the job_search side brings cv up, which is what this order tests. If the job agent can't turn cv on, that's a result to report, not something to work around.

   Permission cards the job agent raises (its `modules.on` and `cv.task` calls) show in **the job agent's tab**, and only you can answer them there. When one waits, the Main Assistant stops, tells you once which card it is, and waits for your "continue". It doesn't ask the Talker to keep relaying it.

   Checks, from `assistant.log` and the agents' logs:
   1. `Activated job_search` with no `Activated cv` before it; then `Activated cv` after the job agent's task started (its own `modules.on` call). `cv.task` from job_search_agent; a work folder with `job_start.json`.
   2. cv_agent ends with `CV_RESULT`, no Chrome, no Rezi.
   3. cv logs "published cv.job_finished"; job_search logs it received it.
   4. Exactly one message reaches the job agent, `[Message from job_search]`; no `[Message from agent_hub] Your child task` message.
   5. The job agent reports `SMOKE TEST 3 DONE` with the job and the status.
   6. Cleanup: delete the new work folder and its CV Tool job only, after looking at them.

### Why the same conversation kept coming back (logs, 2026-11-12 and 2026-11-13)

Five launches ran this test, and each ended the same way: the job agent waited on a card, and the Talker asked you again and again whether to go to its tab.

| Launch | Who turned cv on | What happened |
|--------|------------------|---------------|
| `2026-11-12_04-41-44` | Main Assistant: `Activated job_search` 04:43:42, `Activated cv` 04:43:48 | the job agent's questions waited ("2 question(s) released" at 04:45:00); focus flipped between job_search_agent and cv_agent eleven times in two minutes |
| `2026-11-12_05-20-12` | Main Assistant: cv 05:25:16, job_search 05:25:17 | a card waited; then `cv.task` was refused twice (cv_agent would write the repo, which the Main Assistant's open task wrote) |
| `2026-11-12_05-53-09` | Main Assistant: cv, job_search, then cv off again within 4 s | you had said to launch only job_search; cv was turned on by hand anyway, then off |
| `2026-11-12_17-30-04` | Main Assistant: cv and job_search 28 ms apart (17:49:47) | the job agent's `cv.task` card waited 6.5 minutes (17:49:57 → 17:56:25) |
| `2026-11-13_02-19-03` | Main Assistant: cv and job_search 31 ms apart (02:45:26) | task 8580d066 waited on its `cv.task` card; the Talker relayed the suggestion again; you stopped it, and both were cancelled at 02:46–02:47 |

**The causes:**
1. **cv was turned on by hand every time.** The plan's step 2 didn't say who turns cv on, so the Main Assistant turned on both modules before the `hub.start`. So the run never tested whether the job side brings cv up, which is the order you asked for from the start.
2. **The plan didn't say who answers the cards or what the Main Assistant does meanwhile.** The job agent's cards show only in its own tab. Each time, the Main Assistant and the Talker asked you in the main tab whether to go there, and asked again on the next update.

**So it doesn't come back:** step 2 now names the order and who does each step, says the Main Assistant never turns cv on, and says the Main Assistant tells you about a waiting card once and then waits for your "continue".

## Smoke test 4: results (2026-11-13)

Launch `logs/2026-11-13_02-19-03_wtf`, the new order. Main Assistant task 92bd651e; job agent task 7b19925b. The earlier task 8580d066 was confirmed `cancelled` first, and cv and job_search were both off. There's still no `CV_Test_*.pdf` in `C:\Chang\Jobs`, so the brief named the real `<cv_prefix>SWE.pdf` (copy only).

| Step | Result | Evidence (`assistant.log`, the Hub's task record) |
|------|--------|-----------------------------------------------------|
| (a) Main Assistant turns on job_search only | **pass** | 02:49:32 "Activated job_search"; no `Activated cv` before it |
| (b) the job agent turns cv on | **pass** | task started 02:49:42; its `modules.on cv` card was allowed in its tab; 02:49:59 "Activated cv" |
| (b) the job agent's `cv.task` | **fail** | 1st call, `base_cv: "<cv_prefix>SWE.pdf"`: refused, "base_cv must be one of your CVs in C:/Chang/Jobs/CV" (the file is there). 2nd call with the full path: 02:50:36 "cv.task from job_search_agent refused: cv_agent would write C:\Chang\Git_projects\AI_Assistant, which main_assistant's open task 92bd651e writes" |
| (c) cv fires `cv.job_finished` | **not reached** | cv_agent never started |
| (d) job_search receives it | **not reached** | |
| Job agent's end | done, as told | 02:50:43 "Task 7b19925b done", last line "SMOKE TEST 4 DONE: … status none (cv.task refused …), read_result not called (no task_id), cv turned on by job_search_agent yes" |

**The blocker** is the same as in launch `2026-11-12_05-20-12`: cv's write-folder check refuses a cv_agent task while another open task writes the repo, and the Main Assistant running the test is such a task. The fix for the run is in step 2.2 above: the Main Assistant ends its task right after the `hub.start`. **Open, not looked at:** why the bare `base_cv` name was refused although the file exists.

After the run, cv and job_search were turned off again (`modules.off`), so the next run starts from cv off. Nothing was created on disk: no work folder, since cv_agent never started.

## The fake-job check: results (2026-11-12)

Launch `logs/2026-11-12_17-30-04_yes`. The app was restarted on your go. Main Assistant task 9b894240 turned on cv and job_search and made one `hub.start` on job_search_agent (task e3bdad67). cv_agent's task was cf403d73, and the job agent's wake-up task was 71c0616e. **Evidence:** `assistant.log` only. `cv_agent.jsonl`, `job_search_agent.jsonl` and their Talkers' logs are 0 bytes in this launch, so the agents' own turns are known only from the Hub's task records.

There was no `CV_Test_*.pdf` anywhere, so the base CV was the real `C:\Chang\Jobs\CV\<cv_prefix>SWE.pdf`. It was only copied, never changed.

| Check | Result | Evidence (`assistant.log`) |
|-------|--------|----------------------------|
| 2.1 `cv.task` from job_search_agent; work folder with `job_start.json` | **pass** | 17:56:26 "cv job set up in …\work\2026-11-12_NonexistentTestCo_SmokeTestEngineer (copy <cv_prefix>SWE.pdf, 15 rule file(s))"; "cv.task from job_search_agent: task cf403d73 on cv_agent". The job agent saw `job_start.json` and `jd.txt` in the folder |
| 2.2 cv_agent ends with `CV_RESULT`, no Chrome, no Rezi | **pass, with a defect** | 17:56:33 "Task cf403d73 done". Its last line was `CV_RESULT: {"status": "stopped", …}`, and it reported no CV Tool, Chrome or Rezi. No Chrome or Rezi activity is logged. Defect: `section_order` was capitalized, so the line failed validation (problem B) |
| 2.3 cv publishes `cv.job_finished`; job_search receives it | **pass** | 17:56:33.687 "cv: task cf403d73 ended done; published cv.job_finished for job_search_agent"; same ms "job_search: cv.job_finished for job_search_agent -> pending" |
| 2.4 Exactly one message reaches the job agent, `[Message from job_search]`; no `[Message from agent_hub] Your child task` | **pass** | 17:56:40 "Task 71c0616e started on job_search_agent" / "A waiting message from job_search for job_search_agent: task 71c0616e". The task text starts `[Message from job_search]`, and there's no child-task message in the log. It came in as a new task because of the Hub race (problem A) |
| 2.5 Job agent reports `SMOKE TEST 3 DONE` | **fail** | 17:56:40 "Task e3bdad67 failed"; "Hub refused done report: Task 'e3bdad67' is already failed" (problem A). The wake-up task 71c0616e ended done without the `SMOKE TEST 3 DONE` line, because a fresh session doesn't get its earlier brief (the known gap above). It reported the job and folder, and said `cv.read_result` fails |
| 2.6 Cleanup | **pass, per the earlier session** | Task 9b894240 reported that the work folder is deleted and the base CV is still in place. Not re-checked by hand in this session |

### Problem A: the Hub race (fixed; verified 2026-11-13)

**What happened:** cv_agent finished while job_search_agent was still in its turn, so job_search's message waited (`pending`). The job agent's turn ended, and its `idle` state was published before its DONE report reached the Hub. The Hub flushed the waiting message into the old task. The agent answered "not my current task" (`invalid_arguments`), and the board took that as "the agent was reloaded" (`tasks.py`, "no longer holds this task (reloaded)"). It marked e3bdad67 **failed** and then refused the late DONE report.

**The fix (in `infra/session_agent.py`):** a `_ended` set holds tasks whose DONE or FAILED report is queued but not yet taken by the Hub. While a task is in it, `message()` returns `not_available` ("has just ended … try again"), so the Delivery keeps the message waiting instead of failing the task. The message then goes in as a new task once the report is in. `agent_hub/delivery.py` and `module.py` also changed (`Delivery.tell` / `drain` for the parent message).

**Tests:** new `agent_hub/tests/test_end_report_race.py` (the turn ends before its DONE report: the task ends DONE and the message becomes a new task; the agent says `not_available` for a task it just ended).

**Not verified:** the debugger subagent (started 18:00 by task 9b894240) never reported back. Its session was killed at 18:02:39 when the next task started, so it's unknown whether it finished or ran the tests. **Verified 2026-11-13:** the full suite passes, with `test_end_report_race.py` in it. The fix needs an **app restart**, not a reload, because `infra/` changed.

### Problem B: `section_order` case (fixed; verified 2026-11-13)

cv_agent wrote `["Summary", "Skills", …]`, but `check_sections` accepted only lowercase ids. So the `CV_RESULT` line was "not valid" in the event, and `cv.read_result task_id=cf403d73` failed. **Fix:** `cv/content.py` `check_sections` now trims and lowercases each name. Duplicates are still refused ("Summary" and "summary" count as one name twice). `cv/worker.py`'s prompt now says "section ids in lowercase". **Test:** `cv/tests/test_cv.py::test_a_results_section_order_ignores_case_as_the_worker_may_write_it`. Verified 2026-11-13 in the full run. It loads with a cv reload, or with the restart that problem A needs.

### Problem C: the stray PDF (fixed 2026-11-13: the copy is named `base_`)

**Fixed 2026-11-13** ([cv-base-copy-name](cv-base-copy-name.md)): the copy is now `base_<name>.pdf`. What was found on 2026-11-12:

The job agent saw `<cv_prefix>SWE.pdf` (148 KB) in the work folder and took it for a CV that cv_agent made. It's the **base CV's copy**: `JobStart.prepare` always copies the base CV into the job folder under its own name. The log says so at 17:56:26 ("copy <cv_prefix>SWE.pdf"), before cv_agent started. cv_agent said it didn't read or change "the base CV or its copy". Nothing was fixed. The open question for you is whether the copy should get a clearer name (`base_…pdf`) so it isn't mistaken for a tailored CV. Also unexplained: a `folder_for(company, role)` helper was added to `cv/job_start.py` (used by `prepare` only). It changes nothing, but it has no test of its own.

### Tests (2026-11-13)

Full suite, run in the foreground: **821 passed, 2 deselected, 0 failed** (177.9 s). It covers problems A and B and the `base_` rename. 4 warnings: `PytestUnraisableExceptionWarning` ("I/O operation on closed pipe" from an unclosed asyncio subprocess transport) in `test_talker_agents.py::test_a_helper_tabs_talker_starts_on_use_has_its_own_usage_row_and_closes_with_its_agent` and `test_voice_in.py::test_send_as_input_off_keeps_the_text_from_the_talker`. These are Windows clean-up noise in tests this work didn't touch. `ruff check`: "All checks passed!" (run 2026-11-13 after the rename; no file changed since).

The earlier run on 2026-11-12 was stopped before it finished, and the 818 passing before that came before these fixes.

### What's next (each waits for your go)

1. ~~Run the full suite and `ruff check`.~~ Done 2026-11-13, all pass.
2. **App restart** (problem A touches `infra/`). It also loads problem B's fix.
3. **Hand checks:** a fresh fake job (smoke test 4), to see 2.5 pass (the job agent's own task ends DONE and the result is read by `cv.read_result`). Re-check by hand that the 2026-11-12 work folder is gone and the CV Tool has no NonexistentTestCo job.
4. ~~Rename the base CV's copy (problem C).~~ Done 2026-11-13.
5. ~~The known gap.~~ Decided 2026-11-13: no fallback.
6. **The design-notes skill task.**
