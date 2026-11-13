# Handoff: cv → job_search through the `cv.job_finished` named event only (task 4dca192a)

> **Status: built (2026-11-12, session 2).** Code, tests and docs done, including the Submit as `cv.job_submitted` (the user confirmed it). The current state is in [job-cv-finish-event](job-cv-finish-event.md). Left: the user's go for the app restart, then the fake-job check. No restart, no smoke test, no agent started. The rest of this note is session 1's plan, kept as history.

## What the user decided (all approved)

- **The design:** modules talk to each other through `ModuleEvent`s (`ctx.publish_named` / `ctx.subscribe_named`). Direct tools are only for calls out. The job agent calls `cv.task` to pass the job. cv publishes `cv.job_finished` when cv_agent's task ends. job_search subscribes and wakes its agent with a `DeliverMessage`. The job agent then updates the job's tracker row as its skill says; the module writes nothing into the job project.
- **One path only.** `StartTask.tell_parent: bool = True` (new, optional). `cv.task` sets it to False, so the Hub sends no "child task ended" message for cv's task.
- **Remove last session's road:** `StartTask.parent_note`, the Hub quoting the parent's brief (`PARENT_TEXT`, the brief part of `CHILD_ENDED`), `hub.start`'s `parent_note` input, `cv/handoff.parent_note`, and the "read it with cv.read_result task_id=…" pointer in the Hub message. Put `CHILD_ENDED` back to `"Your child task {id} on {agent} ended {state}: {result}"`. **Keep `cv.read_result`** (with `task_id`): job_search's message points the agent to it.
- **Kill every other parallel track** between cv and the job agent (user, latest message). See the audit below.
- **Move the Submit message onto a named event** too (for example `cv.job_submitted`), unless there's a reason it's wrong. If there is one, tell the user.
- **The lost-event gap: record it in the note, don't build a fallback.** A named event is lost if job_search is off or reloading, or the app restarts, when cv publishes (the bus keeps nothing: `docs/api/modules.md:222`, `core/context.py:103-109`). With `tell_parent=False`, nothing else wakes the job agent then. The result stays in the Hub's task record (last 20 finished) and the job folder. The fallback I suggested (cv marks the job finished in `job_start.json`, and job_search reports unreported finished jobs when it starts) waits for the user's decision.
- **The notes:** say plainly that the design is module-to-module ModuleEvents and tools only for calls out. No "restore" or "re-add" wording. Keep it short and plain. Mark [job-cv-result-via-tools](job-cv-result-via-tools.md)'s tool-plus-Hub-message result path as **replaced**. Fix [named-module-events](named-module-events.md)'s status lines (lines 3 and 5) and the README rows to match.

## Done so far (unrun)

- `src/assistant/contracts/agents.py`: `StartTask.tell_parent: bool = True` added, with its docstring. `parent_note` is **still there**: remove it, and its docstring sentence.
- `src/assistant/modules/agent_hub/tasks.py`: `TaskRecord.tell_parent`, in `export` / `restore` and in `start`. `_to_parent` returns early when `not record.tell_parent`. Still to do in this file, in one pass: remove `parent_note` (record field `:69`, export, restore, start), `PARENT_TEXT` (`:50`), and the brief and note parts of `CHILD_ENDED` (`:51`) and `_to_parent` (`:435-453`).
- `src/assistant/modules/cv/handoff.py`: the module docstring says the end goes out as `cv.job_finished`. `parent_note()` (`:69-74`) is **still there**: replace it with `JOB_FINISHED` and `job_finished()` (below).

## Next, in order

1. **Audit first (the user's request), then cut.** List every route that carries a cv result, finish or status to the job agent, with file and line. The candidates I know of:
   - `cv/module.py`: `_tell_asker` / `_deliver_submit` (the Submit's `DeliverMessage` to `reply_to`, about `:433-475`), and the `AgentNotice` to cv_agent (`:473`, which goes to cv's own worker, not the job agent).
   - `cv/module.py` `cv.task`'s `next` text (`:407-415`): the Hub message, the Submit message, and `hub.send`.
   - `cv/submit_watch.py` (the Submit watch and its reminder).
   - `cv/reply.py` (`reply_text`, `pending_reply`, `mark_replied`).
   - The Hub's `_to_parent` (`agent_hub/tasks.py`).
   - `agent_hub/module.py`'s `hub.start` text about the end coming back as a message (about `:195-215`).
   - The `job_start.json` `replied` record.
   - The job project: `C:\Jobs\CV\.claude\skills\apply-session\SKILL.md:29-37` and `C:\Jobs\CV\CLAUDE.md` (grep `cv.task`, `cv.read_result`, `CV_RESULT`, `job_start.json`, "wait", "poll").
   - cv's worker prompt (`cv/worker.py`), for anything that tells cv_agent to message the asker.

   Report the list to the user before the restart question, and record what was cut in [job-cv-finish-event](job-cv-finish-event.md).
2. **cv** (`cv/module.py`, `cv/handoff.py`):
   - `JOB_FINISHED = "cv.job_finished"`, plus `job_finished(task_id, state, parent_task_id, folder, record, text) -> dict` returning `{reply_to, task_id, parent_task_id, state, job_dir, company, role, cv_result}`. `cv_result` is `read_result(text).model_dump(mode="json")`, or None on a ValueError. reply_to, company and role come from `record["request"]`.
   - In the manifest: `listens` gets `TaskUpdated`, and `publishes_named=(JOB_FINISHED,)` (plus the Submit event if it moves).
   - In `init`: `ctx.subscribe(TaskUpdated, self._on_task)`.
   - `_on_task` acts only when `agent_id == self._agent_id`, `kind in (ReportKind.DONE, ReportKind.FAILED)` and `self.gate` is set. Folder = `self.gate.question_key(task_id)`, then `read_record` in a thread. If there's no `reply_to`, log it and skip. Otherwise `publish_named` and a log line.
   - `cv.task`: `StartTask(..., tell_parent=False)` with no `parent_note`. The `next` text says: end your turn; cv publishes `cv.job_finished`, your module wakes you with the result; `cv.read_result task_id=…` gives the whole result.
   - Fix the imports: drop `parent_note`, add `ReportKind`, `TaskUpdated`, `read_record`.
   - Update the module docstring (`:10-13`).
3. **job_search** (`job_search/module.py`):
   - `CV_FINISHED = "cv.job_finished"`. In the manifest: `sends=(*AGENT_SENDS, DeliverMessage)` and `listens_named=(CV_FINISHED,)`.
   - In `init`: `ctx.subscribe_named(CV_FINISHED, self._on_cv_finished)`.
   - Act only when `data["reply_to"] == self._agent_id`, then send `DeliverMessage(agent_id=self._agent_id, text=cv_finished_text(data), sender="job_search")`.
   - The text names the role, company, folder, task and state, and the result's status, PDF and last score (or "no valid CV_RESULT line"). It ends with "Next: update the job's tracker row as your apply-session skill says; the whole result: cv.read_result task_id=…".
   - Do **not** quote the parent's brief: the user removed that road. Note in the change note that a fresh session gets no brief.
   - Do the same for the Submit event if it moves.
4. **agent_hub/module.py:** remove `hub.start`'s `parent_note` input (about `:205-215`).
5. **Tests:**
   - `agent_hub/tests/test_child_result.py`: put the old texts back, remove the note/brief test, and add a test that `tell_parent=False` tells no one (the feed line still goes out).
   - `cv/tests/test_reply_delivery.py`: the stand-in job module (`JobModule`) subscribes to `cv.job_finished`. Check one event with reply_to, task_id, parent_task_id, job_dir, company and role (the fake echo gives `cv_result` None), and no Hub message. Change the Submit part if it moves to an event.
   - New `src/assistant/modules/job_search/tests/` with `__init__.py` and `test_cv_finished.py`: a fake ctx records the `DeliverMessage`; another `reply_to` is ignored; check the manifest's `listens_named`.
   - `cv/tests/test_handoff.py:134` stays (`"cv.read_result" in next`).
   - Run the full suite (`.\.venv\Scripts\python -m pytest`) and `.\.venv\Scripts\ruff check`.
6. **Docs:**
   - `docs/api/agents.md` (`StartTask`: drop `parent_note`, add `tell_parent`; the `hub.start` row).
   - `docs/api/messaging.md:124, :138` (`ModuleEvent` Used by: cv, job_search; the named events today).
   - `docs/api/modules.md:214`.
   - `docs/api/reusable.md`, and `docs/api/README.md` if a row changes.
   - `docs/architecture/communication.md:66`, `modules.md`, `decisions.md` (module-to-module = ModuleEvents, tools for calls out), `agents.md` (the child-result message: plain text again, `tell_parent`).
   - `cv/docs/architecture.md:26`, `cv/docs/tools.md`, `job_search/docs/architecture.md:11`, `agent_hub/docs/architecture.md`.
   - Then the notes (above), and run `.\.venv\Scripts\python scripts\build_docs.py`.
7. **Architecture check** (the skill), then a NEED: the audit list, then the restart question (contracts changed: `StartTask`), with the recommendation. No smoke test until the user says so.

## Other facts from this task

- The cancelled SMOKE TEST 3 left nothing behind. There's no NonexistentTestCo folder anywhere under `C:\Jobs`, so nothing was deleted.
- The history question, answered for the user: `cv.job_finished` was built on `publish_named` / `subscribe_named` (never committed). job_search turned it into an `AgentNotice` (wakes nobody), not the approved `DeliverMessage`. It was removed after the user approved the assistant's recommendation (`logs/2026-11-12_05-20-12_running-tests-after-restart/talker.jsonl`, lines 172, 179, 181).
