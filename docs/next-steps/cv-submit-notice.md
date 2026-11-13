# cv_agent hears about the Submit, without being woken; the font floor back to 9 pt

> **Status: built (waiting on you), 2026-11-10.** Approved 2026-11-10 with follow-ups 1 and 3, not 2, plus the font floor back to 9 pt as a warning only. Built: the notice, the 9 pt floor, and follow-up 1 as **design A** (your pick, 2026-11-10: "No wait. I like A"). Next: `RELOAD: cv` (asked first), one reload for all of it; you'll test it on your next real job. Came from hand check 2 of [cv-submit-delivers](cv-submit-delivers.md): your Submit reached the job agent, but cv_agent registered nothing.

## What's wrong

When you press Submit in the CV Tool, the cv module delivers the result to the job agent by itself (`SubmitWatch` → `_tell_asker` → `DeliverMessage`). cv_agent is not told, so as far as it knows the job is still waiting on your Submit.

## The change (the lightest way)

Reuse the notice mechanism that's already there. Nothing new is built: `AgentNotice` is a contract, the Hub passes it to the agent's `note`, and `MilestoneFeed` merges the line into that agent's **next** turn. It never wakes the agent or starts a turn (the same path `job.search` and the permissions handler use; [reusable parts](../api/reusable.md)).

1. **`cv/module.py`:** the Submit watch delivers through `_deliver_submit`, which is `_tell_asker` with `notice=True`: after the delivery, the module publishes one `AgentNotice(agent_id=cv_agent, source="cv", text=...)`. `AgentNotice` is in the manifest's `publishes`.
2. **The line** (`reply.submit_notice`), plain, one sentence (the Hub puts `[cv]` in front of it):
   > The user pressed Submit in the CV Tool on the CV for Robotics Engineer at SubmitCheckCo (job 2026-11-10_SubmitCheckCo) at 2026-11-10T02:51:20; the cv module delivered it to job_search_agent (task 2894c9ca). Note: 2 text pieces print under 9 pt (a warning only; the user submitted it as it is).

   The note is only there when `small_text` isn't empty (`small_text_note`, shared with the job agent's message). A failed delivery says "…; delivering it to job_search_agent failed: <error>".
3. **Only the watch's deliveries.** When cv_agent calls `cv.tool_result` itself, it already gets "told: …" in that call's result, so no notice. A missed Submit (pressed while cv was off) is only a reminder to you and sends nothing, so no notice either.
4. **If cv_agent isn't running**, the Hub drops the notice and logs it (`Dropped a notice for cv_agent (not running)`), as it does today. The delivery is in `job_start.json` (`replied`) either way.

## The font floor: 9 pt, a warning only (your word, 2026-11-10)

"I'll check with 9 as a suggested floor." Everywhere the Submit fix put 10 pt is now 9 pt, and it's still only a warning (a Submit is never refused):
- `cv_tool/cvlib.py`: `MIN_PT = 9.0` (what `font_sizes`, `small_text`, `min_pt` and the on-screen warning use). The page itself still prints its small lines (contact, titles, degrees, awards) at `BODY`, 10 pt, as it did, so the CV looks the same; only the warning moved.
- `cv/tool.py`: `MIN_PT = 9` (`MIN_PT_ADVICE` follows). `cv/reply.py` defaults to it.
- The menu texts (`cv.tool_round`, `cv.check_fonts`, `cv.tool_result`), the worker's prompt, the cv module's docs pages, the Parts row in the architecture overview, and the tests.
- **Conflict left for you:** the CV Module rule file `C:\Jobs\CV_Module\.claude\skills\cv-writing\rules\cv-min-font-9pt-measured.md` says "at least 10 pt … (User rule, 2026-11-09, raised from 9 pt …) measure 10 yourself". cv_agent reads that folder, so it will see 10 there and 9 in its prompt. The Main Assistant can't write there, and you said not to rename the file; its text needs your word (or cv_agent's edit).

## Follow-ups from the hand check

1. **cv_agent's prompt, step 5: built as design A (2026-11-10).** What was built: cv_agent tells you the CV is ready for your Submit and ends its task, with no NEED and no `cv.tool_result` check, and `CV_RESULT` status `"ready"`. `CvResult` takes `"ready"`: it needs `one_page` and `pdf_path` (the last `cv.tool_round`'s PDF) and refuses `approved_by_user` (that's the Submit); `"approved"` stays for older results. `cv.read_result` and `cv.report` ("**Ready** for your Submit") take it. Your Submit goes to the job agent from the cv module, in the same second, with no wait and no fallback timer; cv_agent hears of it from the `[cv]` line at its next task. The job agent's message now ends "this Submit is the user's yes. cv_agent's own CV_RESULT line has status "ready" (everything but this Submit); nothing more comes from it", and `cv.task`'s `next` says the worker's task ends before the Submit. Also fixed in the prompt: it told cv_agent to check its line with `cv.read_result`, which only the hand-off callers may call; it now says the asking agent checks it. Designs B (keep the NEED) and C (cv_agent sends the result, with a fallback timer) were turned down. The problem it fixed, as found: without a NEED, cv_agent's turn ends and its task is done before you press Submit. But `CvResult` can only be `approved` with your yes (`approved_by_user`, the Submit), and the job agent's message says cv_agent's `CV_RESULT` follows when its task ends. The `[cv]` notice can't fix that: it only arrives when a next turn starts. Two ways:
   - **A (recommended):** cv_agent ends its task when the CV is ready, telling you it's ready for your Submit, with `CV_RESULT` status `"ready"` (a new status: everything but your Submit) and its current PDF. The module's delivery is what the job agent acts on; the `[cv]` line tells cv_agent at its next task. Touches `data.py` (`CvResult`), `cv.read_result`, the prompt, `reply_text`'s last sentence.
   - **B:** keep the NEED as it is (your "submitted" ends the task as approved); only the wording drops the `cv.tool_result` check, since the `[cv]` line arrives with your answer.
2. **Rename the rule file:** dropped (your call).
3. **Test jobs keep the job agent's task open:** a note for future hand checks (no code). In hand check 2 the job agent's test task had already ended, so your Submit arrived as a new task with no context.

## Touches (built)

- `src/assistant/modules/cv/module.py`: `_deliver_submit`, `_tell_asker(notice=)`, `AgentNotice` in `publishes`, the menu texts at 9 pt.
- `src/assistant/modules/cv/reply.py`: `small_text_note`, `submit_notice`; the default floor from `tool.MIN_PT`.
- `src/assistant/modules/cv/tool.py`, `src/cv_tool/cvlib.py`: `MIN_PT` 9; cvlib's CSS small lines at `BODY`.
- `src/assistant/modules/cv/worker.py`: 9 pt, a warning.
- Tests: `test_the_submit_watch_delivers_live_submits_and_only_reminds_missed_ones` now checks cv_agent's one notice (job, time, who, the 9 pt note) and none after `cv.tool_result`; the 9 pt asserts in `test_cv_tool.py` and `test_tool.py`.
- Docs: `cv/docs/architecture.md` (the Submit sequence, the return address, Tested), `cv/docs/README.md`, `docs/architecture/README.md` (CV Tool row), `docs/api/reusable.md` (`AgentNotice` Used by `cv`).
- Design A: `cv/data.py` (`CvResult.status` `"ready"`, its check), `cv/report.py` (the Ready line), `cv/worker.py` (step 5 and the Never list), `cv/reply.py` (`reply_text`'s last sentence), `cv/module.py` (`cv.task`'s `next`); tests `test_cv.py` (`test_a_ready_result_is_everything_but_the_submit_and_the_job_agent_is_told_so`) and `test_worker.py` (the prompt: no `cv.tool_result`, no Submit NEED); docs `cv/docs/tools.md` (the hand-off, `CvResult`, and the stale "10 pt … refuses" line fixed to 9 pt, a warning), `cv/docs/architecture.md`, `cv/docs/README.md`. No reusable part was new or changed: the index already lists `AgentNotice` and `DeliverMessage` with cv as a user.

A module change plus the CV Tool app: `RELOAD: cv` (the CV Tool restarts on it, its code changed). No app restart.
