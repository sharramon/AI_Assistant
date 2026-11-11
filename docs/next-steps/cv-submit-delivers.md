# The Submit reaches the job agent by itself, and is never refused

> **Status: done, hand check passed (2026-11-10).** Evidence in [Hand check](#hand-check) below. The small-text warning wasn't exercised by hand (the draft had none); the automated test covers it. Follow-up: [cv-submit-notice](cv-submit-notice.md) (cv_agent hears about the Submit). Code, tests and docs done; `cv` reloaded with your OK and active. You approved it as recommended: (1) the event stream plus a look on start (changed 2026-11-10: that look only reminds you, see "Missed Submits"); (2) keep the "no PDF yet" and "no score yet" refusals. See Build status at the end. Came from hand check 2 of [agent-talk-and-questions](agent-talk-and-questions.md) ([handoff](handoff-3720fc90.md)).

## What went wrong

In hand check 2 you pressed Submit in the CV Tool at 01:56:39. The CV Tool saved the result (`result.json`, `ready.flag`), but the job agent never heard about it:

1. **Delivery only happens when someone asks.** The cv module tells the job's `reply_to` agent only inside `cv.tool_result` (`cv/module.py` `tool_result` → `_tell_asker` → `DeliverMessage`). Nothing watches the CV Tool for your Submit. Now that questions are messages, cv_agent is usually idle when you submit, so nobody calls `cv.tool_result`.
2. **`cv.tool_result` would have refused anyway.** The PDF had text under 10 pt, and `cv.tool_result` returns `failed` on small text before telling anyone. The CV Tool had accepted the same Submit, so the app and the module disagreed.
3. **Two numbers for the minimum.** `cvlib.MIN_PT = 10.0` (your 10 pt rule, 2026-11-09), but the module's `NINE_PT` message, the menu texts, the worker's prompt and `test_cv_tool.py` still say 9 pt.

## Your rule (decided 2026-11-10)

**A Submit is never refused, for any reason.** When you press Submit, that is what gets submitted and delivered. A size check, or any other check, can warn you on screen at most. It never blocks the Submit, and `cv.tool_result` never refuses the delivery because of it.

## The change

1. **The cv module watches for your Submit and delivers it itself.** On each new Submit it runs the same path as today (`_tell_asker`: `pending_reply` → `DeliverMessage` to the job's `reply_to` → `mark_replied`). That path doesn't need cv_agent. `cv.tool_result` stays for cv_agent and still never tells anyone twice: `pending_reply` already skips a Submit whose `submitted_at` was told.
2. **No refusal anywhere.**
   - `cv.tool_result` drops its small-text `failed`. It returns the result with `small_text` as information.
   - The CV Tool (`cvlib.submit`, `/api/submit`) keeps accepting every Submit. Its existing refusals for "no PDF yet" and "no score yet" are not checks on your CV: without a PDF there is nothing to submit. I'd keep those two, but tell me if you want them gone too.
3. **A warning only.** If the PDF has text under the minimum, the CV Tool shows a warning next to Submit and in the submitted view, and `result.json` gets `small_text`. The message to the job agent says it too ("Note: N text pieces print under 10 pt"), so the job agent knows the facts, but nothing waits on it.
4. **One number: 10 pt** (`cvlib.MIN_PT`). `NINE_PT` becomes `MIN_PT_ADVICE` with "10 pt" in it. The menu texts (`cv.check_fonts`, `cv.tool_result`, `cv.tool_round`), the worker's prompt, the module's docs pages and the stale tests (`test_cv_tool.py:81`, `test_tool.py:188`) all change to 10 pt. The worker still shortens wording instead of shrinking the font while it drafts; that advice is unchanged.

## How the module notices a Submit

| Option | How | For | Against |
|---|---|---|---|
| **A. Event stream (recommended)** | The CV Tool's server gets `GET /api/events` (Server-Sent Events) that sends `submitted {job_id}`. The cv module reads it through `CompanionApp.events`, like `html_viewer` does. On start, it also scans `cv_tool\jobs\*\ready.flag` once for Submits made while it was off or reloading. | Instant; reuses `CompanionApp.events`; one pattern with the viewer | New endpoint in the CV Tool |
| B. Poll the folder | Every few seconds the module looks for new `ready.flag` files under `cv_tool\jobs\` | No CV Tool change | A delay; disk polling forever; a second way of doing what A does |

With either option the start-up scan is harmless, because `pending_reply` dedups by `submitted_at`.

## Missed Submits: a reminder, never a delivery (your change, 2026-11-10)

- **Live Submits** (pressed while cv runs) are delivered to the job agent by themselves, as above.
- **A Submit pressed while cv was down** is never sent by itself. On start, the look sends you one plain notice in the chat of the tab in focus (`ResponseReady`), naming the job and the time: "While the cv module was off, you pressed Submit in the CV Tool on the CV for <role> at <company> at <time>. Nothing was sent to the job agent. To send it, ask for cv.tool_result on CV Tool job <id>; otherwise nothing happens." The decision is yours. Each one is reminded once.
- **What's been seen** is kept in `<CV Tool data_dir>\submits_seen.json`, one `job_id@submitted_at` key per Submit (`SeenSubmits` in `submit_watch.py`). Live Submits and reminded ones are added.
- **The first reload:** that file doesn't exist yet, so every Submit already there is marked seen. Nothing old is reminded or sent, including the HandCheckCo test from 01:56:39.

## Touches

- `src/cv_tool/server.py`: `/api/events` (SSE), and a push from `/api/submit` after `cvlib.submit` returns.
- `src/cv_tool/cvlib.py`: `submit` puts `small_text` (from `font_sizes`) into `result.json` and `ready.flag`; no refusal for it.
- `src/cv_tool/static/app.js`: the warning next to Submit and in the submitted view.
- `src/assistant/modules/cv/module.py`: start a watch task on `start` (stopped on `stop`/reload), with the start-up scan; `tool_result` without the refusal; menu texts at 10 pt.
- `src/assistant/modules/cv/tool.py`: `CvTool.events()` over `CompanionApp.events`; `NINE_PT` → `MIN_PT_ADVICE`.
- `src/assistant/modules/cv/reply.py`: `reply_text` adds the small-text note.
- `src/assistant/modules/cv/worker.py`: prompt at 10 pt; no "refused" wording; the module delivers, so cv_agent doesn't need to call `cv.tool_result` for that.
- `src/assistant/modules/cv/docs/` (README, architecture, tools): the Submit flow and 10 pt.

This is a module change plus the CV Tool app, so `RELOAD: cv` is enough. The CV Tool restarts on the reload because its code changed. No app restart.

## Tests

- A Submit with text under 10 pt: accepted, `result.json` has `small_text`, and the job agent gets one `DeliverMessage` with the note, without any `cv.tool_result` call.
- `cv.tool_result` after that: `ok`, `small_text` in the value, nobody told twice.
- The start-up look (changed): on the first start, old Submits are only marked seen; a Submit made while the module was off is reminded once, never delivered; `cv.tool_result` then sends it.
- A job with no `reply_to`: nothing sent, no error.
- 10 pt everywhere: the fixed `test_cv_tool.py` and `test_tool.py`.

## Build status (2026-11-10, handoff)

**Code done** (all in the files under Touches):
- `cvlib.submit` adds `small_text` and `min_pt` to `result.json` and `job["submitted"]`; there's a new `cvlib.submitted_jobs()`.
- `server.py`: `/api/events` (SSE, `Tool.listen` / `unlisten` / `publish`), `/api/submitted`, and a `submitted` push after `/api/submit`.
- `app.js`: the warning box and the status line.
- `tool.py`: `MIN_PT = 10`, `MIN_PT_ADVICE` (replaces `NINE_PT`), `CvTool.running` / `events` / `submitted`, and the `on_running` hook in `call`.
- New `cv/submit_watch.py` (`SubmitWatch`: catch-up look, then the stream).
- `module.py`:
  - `init` wires the watch and an `asyncio.Lock` around `_tell_asker`.
  - `start` follows a running CV Tool; `stop` stops the watch.
  - `tool_result` doesn't refuse any more; the menu texts say 10 pt.
- `reply.py`: `reply_text` carries the small-text note.
- `worker.py`: prompt at 10 pt, "never refused", "the module tells the asker".

**Tests:** the cv tests pass (155), including the new ones:
- `test_a_submit_with_small_text_goes_through_with_a_warning`
- `test_the_server_pushes_each_submit_on_its_event_stream`
- `test_the_submit_watch_delivers_with_no_agent_and_catches_up`
- `test_the_message_carries_the_small_text_as_a_warning`

The 9 pt tests became 10 pt. Full suite: 772 passed, 1 failed (`test_every_modules_tools_page_is_current`): the generated `cv/docs/tools.md` is stale until the docs are rebuilt. Ruff: one import-order error in `test_tool.py`, fixed but not re-run.

**Session 2 (2026-11-10):** steps 1–3 below done (docs updated, rebuilt, full suite and ruff run, architecture check). Then your change to missed Submits (the section above): `SubmitWatch` takes `remind` and `seen_path`, the module publishes `ResponseReady` (`_remind`), and the test is now `test_the_submit_watch_delivers_live_submits_and_only_reminds_missed_ones`. Step 4's warning no longer applies: the first reload marks the HandCheckCo Submit seen and sends nothing. Left: the reload (your OK first) and the hand check.

**Next (as planned in session 1):**
1. Docs, still saying 9 pt and "refused":
   - `src/assistant/modules/cv/docs/architecture.md`: the flowchart node at line 139 (`cv.tool_result at Submit` becomes "Submit watch / cv.tool_result"), the sequence at 456–461 (T pushes `submitted` → M's watch → DeliverMessage; no "refused under 10 pt"), the return-address bullet at 464, the Tested line at 473, the server/cvlib rows at 481–482, and the Routes at 486 (`/api/events`, `/api/submitted`).
   - `src/assistant/modules/cv/docs/README.md`: lines 105, 221, 258, 343, 344.
2. Rebuild with `.\.venv\Scripts\python scripts\build_docs.py` (it regenerates `tools.md`), then rerun the full pytest and `ruff check src tests scripts`.
3. Architecture check (`architecture-check` skill). `SubmitWatch` is module-internal, so it doesn't go in reusable.md.
4. Update this note's status and the README Pending row to built (waiting on you), then ask the user (NEED) before `RELOAD: cv`. The CV Tool restarts on the reload because its code changed. Warn them that the catch-up look will deliver today's HandCheckCo test Submit (01:56:39) to job_search_agent once, since its `job_start.json` has no `replied`. Then the hand check below.

## Hand check

Redo check 2 of agent-talk-and-questions: the job agent asks a question and waits; you press Submit on a CV with small text. You see the warning, the Submit goes through, and the job agent gets the message right away with the PDF, the score and the small-text note. `job_start.json` gets `replied`.

**Passed (2026-11-10, test job SubmitCheckCo,** `logs\2026-11-10_01-33-35_it-reached-the-job-agent\assistant.log`**):**
- **Delivered by itself:** at 02:51:20.852, the same second as the Submit, `cv: the Submit of 2026-11-10_SubmitCheckCo for job_search_agent: task 2894c9ca` and `Task 2894c9ca started on job_search_agent`. It came from the cv module: cv_agent's `cv.tool_result` calls were at 02:51:18 (`ready: false`) and 02:51:42.
- **The message** had the PDF (`…\2026-11-10_SubmitCheckCo\CV_Test_SubmitCheckCo_final.pdf`) and the score (100, target 90).
- **No small-text note, correctly:** `result.json` has `"small_text": []`, `"min_pt": 10.0`. The warning path is covered only by `test_a_submit_with_small_text_goes_through_with_a_warning`.
- **`job_start.json`:** `"replied": {"submitted_at": "2026-11-10T02:51:20", "to": "job_search_agent", "how": "task 2894c9ca"}`.
- **`submits_seen.json`** written at 02:51:20: the three old Submits (ExampleCorp, Globex, HandCheckCo) only marked seen, plus `2026-11-10_SubmitCheckCo@2026-11-10T02:51:20`.
- **Once:** one delivery line, one new task; the 02:51:42 `cv.tool_result` told nobody again; no errors after 02:30.
- **Seen by hand:** cv_agent registered nothing about the Submit, hence [cv-submit-notice](cv-submit-notice.md). The job agent's test task had already ended, so the Submit arrived as a new task without context (follow-up 3 there).
