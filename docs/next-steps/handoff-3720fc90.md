# Handoff: hand checks 1, 2, 4 of agent-talk-and-questions (task 3720fc90)

> **Status: checks run 2026-11-10 against the live app; the write-up for check 2 is next.** Logs: `logs\2026-11-10_01-33-35_it-reached-the-job-agent\` (`assistant.log` has the evidence below).

## Results

| Check | Result | Evidence (assistant.log, 2026-11-10) |
|---|---|---|
| 1. `cv.task` reaches cv_agent while the Main Assistant is busy | **passed** (third run) | 01:52:28.388 job set up in `C:\Jobs\CV_Module\work\2026-11-10_HandCheckCo_HandCheckRole`; 01:52:28.409 `cv.task from job_search_agent: task 226a1dfa on cv_agent` (parent 52513adb, the job agent's task); no Main Assistant task, no notice; `job_start.json` `reply_to: job_search_agent` |
| 2. A Submit reaches the job agent while it waits on a question | **failed** | Submit saved 01:56:39 (`C:\Jobs\CV_Module\cv_tool\jobs\2026-11-10_HandCheckCo\result.json`, `ready.flag`), but no `cv.tool_result` call, no delivery, no `replied` in `job_start.json`; the job agent stayed idle on its question (not busy, no notice) |
| 4. A waiting agent is idle, takes new work, a late answer finds its job | **passed** (second run) | 01:58:20 job A 3b7c46c0 asks; cv_agent idle, task idle `question_kind: need`; 01:58:41–43 job B 898279fb accepted and done; 01:59:02 the late answer goes into 3b7c46c0 (new session), 01:59:05 done: "A4b is for job A, and the colour is blue" |

Earlier runs that didn't count: check 1 run 1 (01:47:24) refused because `base_cv` was a bare file name; run 2 (01:49:31) refused by the folder check, since cv_agent still had its repo write grants. **The user then revoked those three grants** (`write:` `src\cv_tool`, `src\assistant\modules\cv\docs`, `tests`; cv off 01:50:36, on 01:50:40); `permissions.grants` confirms. That closes the to-do on line 92 of [agent-talk-and-questions](agent-talk-and-questions.md). Check 4 run 1 (2fbec13e) didn't count: the user answered at once.

## Why check 2 failed

1. **The hand-off is pull only.** The message to `reply_to` goes out only inside `cv.tool_result` (`src/assistant/modules/cv/module.py:479` → `_tell_asker` → `DeliverMessage`). Nothing watches the CV Tool for the Submit (`cv/tool.py` has no event or stream). With questions as messages, cv_agent is usually idle when the user submits, so nobody calls `cv.tool_result` and the job agent is never told. (In this run cv_agent's task 5c335ad0 had ended at 01:55:58, told not to call it.)
2. **The test PDF would be refused anyway.** `result.json` lists "417 text pieces print under 10.0 pt (e.g. 6.66 pt)"; `cv.tool_result` returns `failed` on small text before telling anyone (`module.py:476`). The CV Tool still accepted the Submit (`src/cv_tool/cvlib.py:1358` `submit`, `server.py:213` `/api/submit`): app and module disagree.
3. **The minimum is inconsistent:** `cvlib.MIN_PT = 10.0` (the user's 10 pt rule, 2026-11-09, `cvlib.py:74`), but `cv/tool.py:29` `NINE_PT` and the menu texts say 9 pt, and `test_cv_tool.py:81` asserts 9.0 (the known stale test).

## Next (the user chose "write it up", no code until they approve)

1. Write the change note `docs/next-steps/cv-submit-delivers.md` (option table, recommendation, touches, tests, hand check), covering:
   - the cv module watches the Submit itself (recommended: `CompanionApp`'s event stream if the CV Tool server can push one, else a watch for new `ready.flag` files under `cv_tool\jobs\`) and calls the same `_tell_asker` path, so delivery doesn't need cv_agent; `cv.tool_result` stays and tells nobody twice (`pending_reply` already dedups by `submitted_at`);
   - the CV Tool refuses a Submit with text under the minimum (in `cvlib.submit` / `/api/submit`), with the reason in the page;
   - **one number: 10 pt** (`cvlib.MIN_PT`), used by the module's check, the messages (`NINE_PT` renamed) and the menu texts; fix the stale 9 pt test to 10.
   - Still to read first: `cvlib.py:1358-1410` (`submit`) and `server.py` (is there an event stream?).
2. Add it to the Pending table in `docs/next-steps/README.md`, and update the agent-talk-and-questions row: checks 1 and 4 passed, 2 failed (link the new note), cv_agent's repo writes revoked.
3. Rebuild: `.\.venv\Scripts\python scripts\build_docs.py` (next-steps-html skill).
4. Report the note's path. Check 4 is already done (passed, above).

## Side findings to mention

- `agent_hub` ERROR "Two agents share the id 'cv_agent'; only the first is used" at 01:41:58 when cv first turned on (also on 2026-11-09); not on the second turn-on at 01:50:40.
- `cv.task` refuses a bare `base_cv` name (`module.py:361` resolves against the app's folder, not `cv_dir`), though its description says "in cv_dir".
- `job_search` and `cv` are on now (turned on for the checks). The job agent's test task 52513adb was closed with "done". Test files: the two HandCheckCo folders above.
