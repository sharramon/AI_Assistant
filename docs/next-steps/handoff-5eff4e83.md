# Handoff: smoke test of the job and CV agents, the Hub child-result fix, named module events (task 5eff4e83)

> **Status: in progress (2026-11-12), stopped for the app restart the user approved ("yes, restart").** Main Assistant task 5eff4e83, Auto mode. Reset point: full suite **814 passed**, ruff clean, docs rebuilt; nothing half-edited. No Chrome tabs open. The Hub fix and ModuleEvent go live with this restart. **After the restart, carry on at Next step 6.**

## The user's standing rules for this task
- No real job applications, no Submit anywhere, no Rezi writes.
- **Ask with a NEED before any module reload (agent_hub, cv, job_search) or app restart.** ModuleEvent needs an app restart (contracts + core changed).
- Nothing in the named-events note gets built beyond what the note says (approved).
- Order (user, 2026-11-12): (3) CV Tool check + cleanup → Hub fix → ModuleEvent → ask, restart → rerun fake job 2 → final report.

## Done (sessions 1–2)
- Fake job 1 (task 18411c44) passed: STATUS milestones, ended `done`, no HANDOFF.
- Fake job 2 (task f274970d): job agent → `cv.task` → cv_agent task c880fae8 "CV SMOKE OK"; the answer never reached the job agent (the bug the Hub fix closes).
- Change note [named-module-events.md](named-module-events.md): approved, status set to approved in the note and the README row.
- **Hub fix built (not live yet):**
  - `agent_hub/tasks.py`: `TaskBoard(tell_parent=...)`, `_finish(..., hold=True)` → `_to_parent`: parent task's agent (not the coordinator, not the same agent) gets `Your child task <id> on <agent> ended <state>: <result>` (cut at 4000 chars). Cancels tell no one.
  - `agent_hub/delivery.py`: `Delivery.tell(agent_id, text, sender="agent_hub")` (background `deliver`, logs failures) and `drain()`.
  - `agent_hub/module.py`: wiring (`tell_parent=lambda a, t: self._delivery.tell(a, t)`); `hub.start` menu text says the end comes back as a message.
  - `cv/module.py` `cv.task` "next": don't wait, end your turn; the end comes as a message, the Submit as a second one.
  - Tests: new `agent_hub/tests/test_child_result.py` (idle parent → new task; busy parent → after its turn; coordinator → feed only; cancel → nothing); `cv/tests/test_reply_delivery.py` now expects the Hub's child-end message before the Submit message.
  - Docs: agent_hub architecture ("A child's end to its parent"), `docs/architecture/agents.md`, `docs/api/agents.md` (hub.start row), cv architecture diagram line. Docs rebuilt.
- **ModuleEvent core built (needs the restart):**
  - `contracts/messages.py`: `ModuleEvent(name, source, data)`.
  - `contracts/module.py`: `event_name_ok(name, pattern=False)`, `SubscriptionHandle`, `Manifest.publishes_named` / `listens_named` (validated: own-id prefix for publishes; `x.*` allowed for listens), `ModuleContext.publish_named` / `subscribe_named` / `unsubscribe` (non-abstract, NotImplementedError defaults; `subscribe` now returns a handle).
  - `contracts/__init__.py` exports `ModuleEvent`, `SubscriptionHandle`, `event_name_ok`.
  - `core/context.py` `ScopedContext`: `_subscriptions` is now a dict handle→Subscription; `publish_named` (own-id check, JSON round-trip copy, undeclared logged once), `subscribe_named` (filter wrapper over a `ModuleEvent` bus subscription, `.*` prefix), `unsubscribe`, `_keep`.
  - `scripts/build_docs.py`: module library Publishes/Listens columns include named events.

## Done (session 3)
- Next steps 1–4 below are **built**: `tests/test_named_events.py` (incl. job_search's handler), cv publishes `cv.job_finished` (`handoff.job_finished`, `CvModule._on_task`, listens `TaskUpdated`), job_search listens (`cv_finished_note` → `AgentNotice`, subscribed in `init`), `test_reply_delivery.py` checks the event. Docs updated (api modules/messaging/reusable/README, architecture modules/communication/decisions, cv + job_search docs, the change note step 5 and status). Docs rebuilt; ruff clean; full suite 814 passed.
- **CV Tool check: passed.** The user saved "main_assistant may message cv_agent" (no more message cards). cv_agent's task ended done: the CV Tool opened the fake job, the draft applied, the Internal round scored 56. No Rezi, no Submit.
- Step 5 done: the user approved the restart (2026-11-12).
- Remaining: step 6 (rerun fake job 2), the cleanup below, step 7 (final report).

## Session 4 (after the restart, Main Assistant task 67960000)
- Stage 1 passed: `modules.on cv`, `modules.on job_search` both ok.
- Stage 2 passed: `hub.start` → job_search_agent task **632c9ff5** (parent 67960000); it sent `STATUS: smoke test 2 taken` and called `cv.task` (base CV `<cv_prefix>SWE.pdf`, tool Internal).
- Stage 3 first try **refused**: `cv.task` → `not_available`: "cv_agent would write C:\Projects\AI_Assistant, which main_assistant's open task 67960000 writes". Cause: cv_agent's saved grant has an added item `write:…\AI_Assistant\src\cv_tool\cvlib.py` (2026-11-10, inside the repo), and the Main Assistant writes the whole repo; the Hub's folder-clash check counts **active** tasks only, so it refuses while the Main Assistant is mid-turn. Not a code bug; a test-setup clash. Fix options for later: revoke that write item (`permissions.revoke cv items=[…cvlib.py]`), or run such smoke tests with the Main Assistant idle.
- **User decision (2026-11-12): keep cv_agent's write grant on `src\cv_tool\cvlib.py`; do not revoke it.** For such tests the Main Assistant stays idle while cv_agent starts.
- Workaround: told the job agent (answering its NEED) to wait ~90 s and retry, and the Main Assistant ended its turn idle (NEED to the user) so the clash clears. **Next:** read task 632c9ff5 with `hub.status task_id=632c9ff5` (and cv_agent's child task) for stages 3–4, then the cleanup and the final report.

- **Result (after the retry): all four stages passed.** `assistant.log` 05:29:15 "cv.task from job_search_agent: task e1bd249f on cv_agent"; 05:29:22 "Task e1bd249f ended done; telling its parent 632c9ff5's agent job_search_agent". The job agent's transcript (line 54) got `New task: [Message from agent_hub] Your child task e1bd249f on cv_agent ended done: CV SMOKE OK: …`, with the background line `[cv.job_finished] cv_agent's task e1bd249f … ended done: no valid CV_RESULT line …` (expected: a smoke test makes no CV).
- **Cleanup done:** deleted the work folder and the CV Tool job `cv_tool\jobs\2026-11-12_Nonexistent_Test_Co`; the base CV in `C:\Jobs\CV` untouched. (The CV Tool's headless print profile `.chrome_print` still names the fake job in its browser history; left alone.)
- **Open points (for the user):**
  1. The job agent had ended its task (632c9ff5 done) when it ended its turn, so the child-end message came as a **new task in a fresh session without the original brief**. It understood the result but didn't write the asked-for "SMOKE TEST 2 DONE" report. Possible fix: the Hub's message names the parent task and quotes the start of its text, or the asker ends with a NEED-free "waiting" state that keeps the task open. **Answered by [job-cv-result-via-tools](job-cv-result-via-tools.md) (2026-11-12):** the Hub's message now carries the child's `parent_note` (the job, its folder, `cv.read_result task_id=…`) and quotes the parent's brief (first 600 characters). Built; live after the next app restart.
  2. A watching Main Assistant (active) blocks cv_agent through the folder clash while cv_agent has write grants inside the repo. The user keeps the grant; run such tests with the Main Assistant idle.

## Cleanup (done in session 4)
- Delete `C:\Jobs\CV_Module\work\2026-11-12_NonexistentTestCo_SmokeTestEngineer` and its CV Tool job under `C:\Jobs\CV_Module\cv_tool\jobs\` (the job_id is in cv_agent's smoke-test report; look it up with `hub.status task_id=…` on cv_agent's last task, or find the job whose files name NonexistentTestCo). Avoid plain `hub.status` (huge output). Do it after the fake job 2 rerun, which makes a new work folder too.

## Next
1. **Tests for the ModuleEvent core** (e.g. `tests/test_named_events.py`): publish/subscribe by name; `cv.*` wildcard; another module's name refused; non-JSON data refused; data is a copy; unsubscribe of one named and one typed sub; undeclared logged once; Manifest validation of `publishes_named` / `listens_named`.
2. **cv publishes `cv.job_finished`:** manifest `listens += TaskUpdated`, `publishes_named=("cv.job_finished",)`; in `init` `ctx.subscribe(TaskUpdated, self._on_task)`; on `agent_id == cv_agent`, `kind in (ReportKind.DONE, ReportKind.FAILED)`: folder = `self.gate.question_key(task_id)` (JobStartAgent maps task→folder), `read_record(folder)` (job_start.py, in a thread) → `request.reply_to/company/role`; `cv_result` = `read_result(text).model_dump(mode="json")` or None on ValueError (handoff.py); publish `{reply_to, task_id, state, cv_result, job_dir, company, role}`.
3. **job_search listens:** `listens_named=("cv.job_finished",)`, `subscribe_named` in start. **Decision made (avoid a double wake, since the Hub fix already messages the parent):** job_search turns a matching event (`reply_to` == its agent id) into an `AgentNotice` (background line for its agent's next turn: status, pdf_path, score, "read with cv.read_result"), not a second `DeliverMessage`. Mention this in the final report; it differs from the note's sketch (DeliverMessage), so update the note's step 5 to say so.
4. Tests for cv and job_search; docs: `docs/api/modules.md` (ctx methods, Manifest fields, SubscriptionHandle), `docs/api/messaging.md` (ModuleEvent), `docs/api/reusable.md` (ModuleEvent, publish_named/subscribe_named/unsubscribe, event_name_ok, with Used by: cv, job_search), `docs/architecture/modules.md`, `communication.md`, `decisions.md` ("How general event types are" → decided (iii)), cv and job_search module docs. Rebuild docs, ruff, full suite, architecture-check.
5. **NEED before restart:** ask the user for an app restart (it makes the Hub fix and ModuleEvent live together).
6. After the restart: turn on `job_search` and `cv` if off; **rerun fake job 2** (brief as task f274970d, but: "after cv.task, end your turn; cv_agent's end comes to you as a message; then end with 'SMOKE TEST 2 DONE' quoting it"). Confirm the job agent got `[Message from agent_hub] Your child task … ended done: CV SMOKE OK…`. Clean up the work folder again.
7. Final report: passed/failed with output, skipped items, Architecture check section.
