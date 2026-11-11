# Handoff: building agent-talk-and-questions (task 9bc35422)

Building [agent-talk-and-questions](agent-talk-and-questions.md). The user approved all six choices as recommended (option C, one grant per direction, a message waits for the turn to end, context from the module's notes, yes to both settings changes, one build with one restart at the end). Runs in Auto. **Don't restart or reload the app.** At the end, list the hand checks and say it's ready for the restart. The user already agreed to the restart.

## Sessions

One step per session, then hand off: **step 1** (the cv module does the hand-off: code written, **tests not run yet**), **step 2** (the message gate), **step 3** (questions as messages, which takes in two-agent-states). After step 3: the docs, the HTML rebuild (`scripts\build_docs.py`), the change note's status, the Pending table in `docs/next-steps/README.md`, the architecture-check, and the final report with the hand checks.

## Session 7: finished

Docs for all three steps written, HTML rebuilt, 768 passed (9 pt test deselected), ruff clean, final architecture check OK, change note and Pending row updated. Nothing left but the restart and the hand checks in the change note.

## Session 8: verified

Run again in the foreground: ruff clean, 768 passed (3 deselected), docs checked and rebuilt, architecture check OK. The build is finished; it waits only on the restart and the hand checks.

## Session 7's plan (done)

**Step 3 is done and checked (session 6):** the whole suite passed (761, the 3 known deselected), plus the new `tests/test_questions_as_messages.py` (5 tests: NEED leaves the agent idle and it takes new work, the Hub's `busy()` ignores the question and `export_state` hands it over, a late answer gets `set_context`'s notes in a fresh session, an answer during a turn waits (`pending`) and goes in at the turn's end, cancelling a question needs no agent, `job_notes`). In `tests/test_agents.py`, the answer assertion that was stuck inside a comment is fixed. Ruff was clean before the new test file; run ruff again first. Architecture check for step 3: modularity OK (cv takes `default_context` from infra; the Hub never imports cv; nothing module-specific in the core); fit OK (the answer is a plain `SendToTask`). The reuse finding goes in the docs step: add `default_context`, `SessionTaskAgent.set_context`, `Delivery.later` and `TaskBoard.export_questions/restore` to `docs/api/reusable.md` with their Used by lines.

What step 3 built, beyond the list below: `TaskRecord.asked` / `.paused`, `ANSWER` text, `_answer`, `_drop_paused`, `held_records`, `export_questions` / `restore` (`agent_hub/tasks.py`); `open_task_of` prefers a held record over an asked one; `AgentHubModule._send` wraps `SendToTask` (answer → `Delivery.later` when the agent is active or gone; `hub.send` returns `delivered: when its agent is free`); `Waiting.task_id`, `Delivery.later`; cv `JobStartAgent._jobs`, `question_key`, `job_notes(key)` in `job_start.py`, wired with `set_context` in `cv/module.py`; the restart no longer refuses (`RestartFlow.ask()`, the `ASKED` kinds start a separate reset-note task; the note adds `(context: <key>)`).

**To do now:**
1. `.\.venv\Scripts\ruff check`.
2. Docs (the change note's Touches list; steps 1 to 3 are all undocumented so far): `architecture/agents.md`, `agents-code.md`, `permissions.md` (message items, Allow once, a revoke of `message:` keeps the module on), `core.md`, `api/agents.md` (AgentState, TaskState, AgentInfo.state, Task/TaskInfo.question_key, ReportTask.key, `DeliverMessage` with its anchor, the Hub menu's `hub.send`/`hub.agents`), `api/messaging.md` (AccessKind.MESSAGE, `remember`), `api/infra.md` (`set_context`, `default_context`, `has_task`), `modules/agent_hub.md` (`named_only`, delivery, gate, questions handed over), `modules/temp_ui.md`, `agents/runtime.md`, the cv module's `docs/` (hand-off: no coordinator, `DeliverMessage`, `job_notes`), `api/reusable.md`. Grep docs for `busy`, `working`, `waiting_for_input`, `paused`, `RESTART: anyway`, `start_only_by`, `coordinator` to find stale lines. A docs subagent with this list is a good fit.
3. `.\.venv\Scripts\python scripts\build_docs.py` (also fixes the two stale generated-doc tests), then the whole suite with only the cv_tool 9 pt test deselected.
4. The change note: Status → built, waiting on the restart; a Build status section; the Pending table row in `docs/next-steps/README.md` (and two-agent-states' row: built as part of it).
5. The final architecture-check, then the report: the hand checks (the change note's five), and after the restart: revoke cv_agent's three repo write folders (it turns cv off: ask first), plus `named_only = ["cv_agent"]` replacing `start_only_by`. Also mention the cv_tool `MIN_PT` test. App restart needed (contracts, core, infra).

## Step 3 as planned (session 5's list, all built in session 6)

**Design (decided, follow it):** the question record *is* the task record, in state `IDLE` with its question; the agent drops the task and is free. The answer re-assigns the **same task id** (so parents/children and the Talker's `open_tasks` stay valid).
- Agent "holds" a record unless `record.asked` (= state IDLE and question_kind NEED/RISKY). IDLE with no question = paused (`hub.send` pause), agent still holds it.

**Done in session 5:**
- `contracts/agents.py`: `AgentState` (ACTIVE/IDLE, exported in `contracts/__init__.py`); `AgentInfo.state` + `.active` property (busy/working gone); `TaskState` = ACTIVE, IDLE, DONE, FAILED, CANCELLED; `Task.question_key: str | None`; `TaskInfo.question_key: str = ""`; `ReportTask.key: str = ""`; `AgentStateChanged.state` (busy/working gone); docstrings (`SendToTask`, `assign`).
- `infra/session_agent.py`: `_Mode.WAITING` → `ASKING` (dropped task, active until the NEED report is sent; `_send_reports` then sets IDLE + publishes); `_IDLE_MODES = (IDLE, PAUSED)`; `state` / `has_task` properties; `set_context(key(task_id), notes(key))`, default `default_context(key)` (NOTE_HINT, module-level, reusable); `_ask_user(question, live)` reports NEED with `key = question_key(task.id) or _last_note`; too-many handoffs uses `_ask_user(live=False)` (`_handoff_asked`, `_go_ahead` gone; `_continue_fresh(note)` has no `extra`); `assign` accepts IDLE/PAUSED (drops a paused task), `live = question_key is not None and task.id == _asked and session.running` → no fresh session, text as-is; else `_first_text` adds `CONTEXT_AGAIN` with the notes; `message` returns not_available while ASKING for `_asked`.

**Still to do in step 3:**
1. `agent_hub/tasks.py`: `TaskRecord.state` default ACTIVE, `question_key` field (in `info()`), `asked` property. `report`: NEED → state IDLE, `ask`, `question_key = command.key or record.question_key`, `holder = None`, held as before; PERMISSION → stays ACTIVE with its question. `send`: if `record.asked` → `_answer(record, text)`: agent None or `info().active` → `not_available` (question kept); else finish the agent's paused records (DONE "stopped: a new task replaced it"), state ACTIVE, `answered()`, holder = agent, `agent.assign(Task(id=record.id, text=ANSWER.format(id, question_line, text), question_key=record.question_key))`, revert (IDLE + question + key) if refused. Normal send: `ACTIVE if resume else IDLE`. `answer` / `set_mode`: ACTIVE. `cancel` on an asked record: finish CANCELLED without calling the agent. `start`: refuse `info.active`; extras and `_folder_clash` count only ACTIVE records; finish the chosen agent's paused records before assigning. Add `export_questions()` / restore of asked records (for a Hub reload).
2. `agent_hub/module.py`: `ctx.handle(SendToTask, ...)` wrapper: if `tasks.send` is not_available and the record is `asked` → `delivery.later(agent_id, task_id, text)` (ok "pending"). `hub.agents` gives `"state"` instead of busy/working. `busy()` counts only records that aren't `asked`; `export_state` adds `"questions"`, read back in `init`. `agent_hub/delivery.py`: `Waiting.task_id: str = ""`, `later(...)`; `_try` checks `agent.info().active`; an item with task_id sends to that record if it's still open, else a new task.
3. `cv`: `JobStartAgent` keeps `_jobs: dict[task_id, work_dir]` (set in `_set_up`/`assign`/`message`); `question_key(task_id)`; `job_start.job_notes(folder)` = job_start.json summary (company, role, folder, files, replied) + any `*handoff*.md` in the folder, else `default_context(key)` for a non-folder key; `cv/module.py` after `gate.attach`: `self.worker.agent.set_context(gate.question_key, job_notes)`. `job_start.py:200` `busy=True` → `state=AgentState.ACTIVE`; `:207` `.busy` → `.active`.
4. Renames: `profile_agent.py` 113/129/158 → `self.agent.has_task`; `main_assistant/module.py:145` → `self._agent.has_task`; `task_agents/module.py` 210/251 → `AgentStateChanged(agent_id=…, change=…)` (state defaults IDLE); `assistant_view/module.py:64` → `str(event.state)`; `temp_ui/module.py` 545/548/559/739 → `"state"` key ("working" if active else "idle" for the pill); `page.html:669` → `a.state === "active" ? "working" : "idle"`; `temp_ui/agent_tabs.py:98` → `a.active`; `talker/session.py:444` → `agent.get("state") == "active"`; `talker/module.py:291` → `event.question_kind is not QuestionKind.PERMISSION`.
5. `talker/restart.py`: no refusal (delete `RESTART_WAITING`, `ask()` takes no `anyway`; `session.py:383` call updated); a worker task holding a NEED/RISKY question → start a separate reset-note task (`hub.start`), the question stays open; `app_state` "working" from `info.active`, and adds `(context: <key>)` when `task.question_key`. `talker/prompt.py:63-64`: drop the "restart anyway" sentence.
6. Tests: update every `busy=`/`working=`/RUNNING/PAUSED/WAITING_FOR_INPUT use (grep `tests/` and `src/**/tests/`; e.g. `test_delivery.py`, `test_gate.py`, `test_stale_task.py`, `test_reply_delivery.py`, `test_job_start.py`, `tests/test_agents.py`, `test_multi_agent.py`, `test_permission_mode.py`, `test_question_kinds.py`, `test_temp_ui.py`, `test_agent_kit.py`, `test_honest_manifests.py`, `test_worker_parts.py`, `test_agent_hub_parts.py`, `test_task_agents.py`, `test_agent_names.py`, `test_permissions_handler.py`) and add the change note's "Questions as messages" tests (NEED → idle, new task accepted with a question open, answer → "Answer to your question" same task id, fresh-session notes via `set_context`, restart goes ahead, permission card keeps it active, asked record doesn't clash). Hand the fix-up loop to the `debugger` subagent if failures pile up.
7. Then the docs step (below) and the final report.

## Step 2: done and checked (session 4)

Session 4: whole suite 759 passed (the 3 known failures deselected; `test_voice_pieces` socket test is flaky, passes alone), ruff clean. Architecture-check: fits (the gate is in `agent_hub`, reaches the handler only through `ctx.permissions`; the core's handler names no module).

Done in code:
- **Contracts:** `AccessKind.MESSAGE` (label `message <id>`), `PermissionRequested.action` takes `"message"`, `AnswerPermissionRequest.remember` (default True; False = Allow once), `ModulePermissions.granted(item, agent_id)` and `ask(item, agent_id, reason) -> bool` (not abstract; raise NotImplementedError).
- **Core** (`core/permissions/`): `CardAction.MESSAGE`, `Card.remember`, `handler.kind_of / granted / ask` (subject = the agent's kind from `own_agent`, else its id; cancelling `ask` drops the card), `_apply_message` (once: nothing saved; always: the key joins the grant's asked + granted, fingerprint of asked), `messages_only()`: a revoke of only `message:` items says "stays on" and doesn't turn the module off (card text too). Port forwards both; without a handler both allow and log.
- **`agent_hub/gate.py`** `MessageGate(permissions, deliver, note, log)`: `send(sender, receiver, text)`, `held()`, `close()`; one card per (sender, receiver), later messages wait behind it; Allow → each through `Delivery.deliver`; Deny/timeout → `[messages]` note to the sender.
- **`agent_hub/module.py`:** `hub.send` from a non-Talker with no task_id needs `agent_id` (not self, a running or claimed agent); its open task is the caller's child → straight in (interrupts, as before), else the gate. `hub.start` unchanged (it makes a child task, so no card). `busy()` also waits on held messages; `stop()` closes the gate; `_note(agent, line)`.
- **temp_ui:** `page.html` message card has Allow once · Always allow · Deny, head "X wants to message Y"; `/access-answer` passes `remember`. **talker:** `access_card_text` for message cards; ALLOW sends `remember=False` (once; Always only by the button).
- **Tests:** new `agent_hub/tests/test_gate.py` (7); `tests/test_core_tidy.py` card actions include `message`.
- **Revoking cv_agent's three repo write folders** still turns cv off (they're folder items). Do it as the first step after the restart, as planned; list it in the final report.

## Step 1: done and checked (session 3)

Session 3: agent_hub + cv tests pass (161), the whole suite passes (754), ruff clean. Architecture-check: fits (cv reaches the Hub only through the `DeliverMessage` contract; the queue lives in `agent_hub`). `DeliverMessage` / `Delivery` are in `docs/api/reusable.md` (the anchor `agents.md#delivermessage` still needs its entry in `docs/api/agents.md` at the docs step).

Known failures that are **not ours**, deselect them while building:
- `tests/test_module_docs.py::test_the_library_table_is_generated_from_the_manifests_and_menus` and `tests/test_module_layout.py::test_every_modules_tools_page_is_current`: generated docs are stale after the manifest and cv.task changes; `scripts\build_docs.py` at the docs step fixes both.
- `src/assistant/modules/cv/tests/test_cv_tool.py::test_every_style_on_the_page_is_9_pt_or_more`: `src/cv_tool/cvlib.py` now has `MIN_PT = 10.0` but the test asserts `== 9.0`. That change wasn't made in this task (src/cv_tool is untracked). Mention it in the final report; don't fix it unless the user says so.

Done in code:
- **Contract** `DeliverMessage(agent_id, text, sender)` in `contracts/agents.py`, exported in `contracts/__init__.py`. Value: `"message <task>"`, `"task <id>"`, `"pending"`; `failed` Result if refused for good.
- **`agent_hub/delivery.py`**: `Delivery(board, agent, log, waiting)` with `deliver`, `flush`, `export`, `waiting(agent_id)`; `message_text(sender, text)` gives `[Message from <sender>] <text>`. Never into a working agent; open task → `board.send`, else `board.start`; NOT_AVAILABLE → waits; per-agent order kept; asyncio.Lock.
- **`agent_hub/module.py`**: handles `DeliverMessage`; `_on_state` (focus check, then `delivery.flush()`) on `AgentStateChanged` and `ModuleStateChanged`; `export_state` has `"waiting"`, read back in `init`; new config `named_only` (`agent_ids()` checker) joins `restricted`; `start_only_by` kept, empty default.
- **`config/default.toml`**: `start_only_by` for cv_agent replaced with `named_only = ["cv_agent"]` (keeps free picks off cv_agent; tell the user).
- **cv**: `cv.task` finds the caller's newest open task (`GetTaskStatus`), sends `StartTask(agent_id=cv_agent, parent_task_id=…)`; refused → same status with `_on_job()` naming the job and who it's for, "Nothing was queued". `_ask_coordinator`, `_wake`, `AgentNotice` gone; `_tell_asker` uses `DeliverMessage(sender="cv")`, how = value or `failed: …`. Manifest sends `StartTask, GetTaskStatus, DeliverMessage`; publishes `AGENT_PUBLISHES`. `settings()` drops `coordinator` (a stray one is ignored). Docstrings fixed in `module.py`, `handoff.py`, `reply.py`; `module.toml` coordinator line removed.
- **Tests**: `cv/tests/test_worker.py` `app_with(…, extra=())` with `named_only`; `test_callers.py` rewritten (free pick skips cv_agent; cv.task starts cv_agent, a second job while SLOW is refused naming Acme and job_search_agent); `test_handoff.py` takes `task_id` from cv.task and checks CV_RESULT through a separate `hub.start` by the talker; `test_job_start.py` uses cv.task's `task_id`; `test_tool.py` comment; new `agent_hub/tests/test_delivery.py` (7 tests) and `cv/tests/test_reply_delivery.py` (parent set, Submit waits for the turn end, delivered into the parent task, recorded `pending`, told once).

Watch for: `Result(status=…, error=…)` built directly in `cv.task`'s refusal; the SLOW task in `test_callers` must stop cleanly on `app.stop()`; `test_reply_delivery` reaches the fake module through `app._lifecycle._active["job_fake"][0].ctx`.

## Notes for steps 2 and 3

- **Revoking cv_agent's three repo write folders** (`permissions.revoke`) turns the cv module off today. Per the user's standing rule (ask before any module off/reload), don't do it live. Do it after step 2 makes revokes safe, or list it as the first step after the restart. Check `data/permissions.toml` and the revoke signature first.
- **Code facts:**
  - `SessionTaskAgent.info().busy` is `mode is not IDLE` (`session_agent.py:207`), and `assign` refuses when busy (line 229). It publishes `AgentStateChanged` on every (busy, working) change (line 631).
  - `message()` interrupts mid-turn; when waiting or paused it sends straight away.
  - `TaskBoard.may_steer` allows children only.
  - `hub.send` without a task_id is Talker-only (`agent_hub/module.py` `send_item`).
  - The fake claude keywords are `SLOW`, `ASKME` (NEED), `PERMIT` (`tests/fake_claude.py`).
  - Step 2's gate should deliver through `Delivery.deliver` (it never interrupts).
- **Docs to update at the end:** see the change note's Touches list; also the cv module's docs (hand-off section: no coordinator, `DeliverMessage`), `modules/agent_hub.md` (`named_only`, `DeliverMessage`).
