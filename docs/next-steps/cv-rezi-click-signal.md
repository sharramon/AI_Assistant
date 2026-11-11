# The "Send JD and CV to Rezi" click reaches cv_agent

> **Status: built (waiting on you), 2026-11-10.** Built as below (the user asked for it 2026-11-10: the pick stays saved with no event; the click is an event to cv_agent; Submit unchanged). Touches: `cv_tool/server.py` (`/api/draft/rezi` publishes `rezi_request`), `cv_tool/cvlib.py` (`rezi_request` gives `job_id`, `at`), `cv_tool/static/index.html` and `app.js` (the hint), `cv/submit_watch.py` (`on_rezi`, once per request id), `cv/module.py` (`_tell_worker_rezi`), `cv/reply.py` (`rezi_click_text`), `cv/worker.py` (step 3: the click is the yes), `cv/docs/architecture.md`. Tests: `test_the_send_to_rezi_click_is_an_event_and_the_pick_is_not` (test_cv_tool.py), `test_the_send_to_rezi_click_tells_cv_agent_once_and_submit_stays_the_same` (test_tool.py); 159 passed. Also run on a copy (`C:\Chang\Jobs\CV_Module\work\2026-11-10_rezi_click_check`). Next: one CV Tool restart and a reload of the cv module only (asked first), together with the page layout settings. Came from the log investigation of the Contoso click at 11:48:00.

## What's wrong

The CV Tool's **Send JD and CV to Rezi** button only writes a request file and sets `rezi_pending` on the job. No event, notice or Hub message goes out, so cv_agent is never told. The signal is lost at the source: nothing was delivered, held or refused, because nothing was sent.

- `src/cv_tool/static/app.js:234-246` (`draftRezi`) posts `/api/draft/rezi`, copies the text to the clipboard and shows "Next: cv_agent picks it up (cv.tool_status)".
- `src/cv_tool/server.py:227-228` calls `cvlib.rezi_request(...)` and publishes nothing. `/api/submit` (`server.py:241`) does publish `{"kind": "submitted", ...}`.
- `src/cv_tool/cvlib.py:974-998` writes the file and `rezi_pending`, nothing else.
- `src/assistant/modules/cv/submit_watch.py:101`, the cv module's only watcher on the CV Tool's event stream, acts only on `kind == "submitted"`. An event from the click would be dropped too.
- `src/assistant/modules/cv/worker.py:52-57` only says to pass `request_id` "when cv.tool_status shows a pending rezi_request". It doesn't say the click is your yes, so cv_agent would ask again.
- `src/cv_tool/static/index.html:72`, the panel's hint: "You tell the Main Assistant to run it." The flow predates cv_agent and assumes someone polls.

## Evidence (Contoso job, cv_agent task 0c8a6a33, 2026-11-10)

| Time | What happened |
|---|---|
| 11:47:54 | cv_agent's turn ends: it will ask you before any Rezi write if Rezi is picked. |
| 11:47:57 | The cv tab's Talker tells cv_agent to check the pick and ask you before the first Rezi write. |
| 11:47:58 | cv_agent calls `cv.tool_status`: Rezi picked, no pending request yet. A long turn starts (Rezi sign-in, reading CVs, ~40 s thinking). |
| **11:48:00** | **The click.** `C:\Chang\Jobs\CV_Module\cv_tool\rezi_requests\2026-11-10_Contoso_20261110-114800.json` written, `rezi_pending` set. Nothing in assistant.log; no event, notice, `DeliverMessage` or Hub call. |
| 11:48:39 | You type in cv_agent's tab that you picked Rezi and clicked the button. |
| 11:48:42 | The Talker interrupts cv_agent with it; cv_agent takes the click as your yes and carries on (`cv.tool_round` ×2, then `rezi.write_resume`, done 11:50:37). |

Sources: `cv_agent.jsonl` (262, 276, 281–348), `talker-cv_agent.jsonl`, `assistant.log`, the request file's time, all in `logs\2026-11-10_01-33-35_it-reached-the-job-agent\`.

## The fix: treat the click like Submit

The button stays (you want to keep working through the UI too).

1. **`src/cv_tool/server.py`, `/api/draft/rezi`:** after `cvlib.rezi_request(...)`, also `tool.publish({"kind": "rezi_request", "job_id": ..., "request_id": ...})`, as `/api/submit` does.
2. **`src/assistant/modules/cv/submit_watch.py`** (line 101 acts only on `"submitted"`): handle `"rezi_request"` too. The cv module sends cv_agent a `DeliverMessage` (sender `cv`): the user pressed Send JD and CV to Rezi for job `<job_id>` at `<time>`, request `<request_id>`; that click is their yes for the Rezi write. `DeliverMessage` never cuts into a turn: it answers an open `NEED:`, or waits until the turn ends. (Whether to rename the watcher to a general CV Tool event watcher is decided at build time.)
3. **`src/assistant/modules/cv/worker.py`, step 3:** one line: a pending `rezi_request` in `cv.tool_status` means the user has already approved; don't ask again.
4. **`src/cv_tool/static/index.html:72`:** the hint says the click tells cv_agent and counts as your yes for the Rezi write (and `app.js`'s "Next:" text to match).

**At build time:** tests for the new event kind and the message (as the Submit watch's tests do), the cv module's docs pages and tools page, `RELOAD: cv` (asked first); the CV Tool restarts with its new code on the reload.

## Rejected: drop the button

cv_agent now drives Rezi itself through `rezi.write_resume`, so picking Rezi in tab 2 could be the only signal. Turned down: you want to be able to act through the UI as well, not only by telling the agent.
