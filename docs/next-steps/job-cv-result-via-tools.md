# Job ↔ cv through tools and the Hub's child-result message, not the named event

> **Replaced (2026-11-12) by [job-cv-finish-event](job-cv-finish-event.md).** The result path in this note (the Hub's child-result message with `parent_note` and the parent's brief) is gone. The design is module-to-module named events, with tools only for calls out: the job agent calls `cv.task`, cv publishes `cv.job_finished` and `cv.job_submitted`, and job_search wakes its agent. Kept from this note: `cv.read_result task_id=…`. The rest below is history.
>
> **Old status: built (2026-11-12); the user said yes to the restart, and the app is restarting now.** The user approved option 1 (`StartTask.parent_note`, one app restart). Code, tests and docs done (session 2: every doc spot below updated, docs rebuilt, 814 tests pass, ruff clean). The restart loads the contract field and the new agent_hub, cv and job_search code, so no reloads are needed. **Left after the restart:** wait for the user's go, then the fake-job hand checks in part 5 (the Main Assistant only starts the job agent and stays idle), then the cleanup in part 5.7.
>
> **Build status (handoff, session 1 → 2; session 2 finished the docs):**
> - **Code: done** as written in parts 1 and 2:
>   - `contracts/agents.py`: `StartTask.parent_note`.
>   - `agent_hub/tasks.py`: `PARENT_TEXT = 600`, the new `CHILD_ENDED`, `TaskRecord.parent_note` (also in export / restore), `_to_parent`.
>   - `agent_hub/module.py`: the `parent_note` input on `hub.start`.
>   - `cv/module.py`: `cv.task` sets `parent_note` through `handoff.parent_note` and `JobStart.folder_for` (new, in `job_start.py`); its `next` text names `cv.read_result task_id=…`. `cv.read_result` takes `task_id` or `text`, one of them. `_on_task`, the `TaskUpdated` listen and `publishes_named` are gone.
>   - `cv/handoff.py`: `JOB_FINISHED` and `job_finished` are gone.
>   - `job_search/module.py`: the listener, `cv_finished_note` and `listens_named` are gone.
> - **Tests: updated.** `agent_hub/tests/test_child_result.py` has the new texts plus a test for the note and the brief cut at 600 characters. `cv/tests/test_reply_delivery.py` lost its listener and checks the note and the brief. `cv/tests/test_handoff.py` covers `cv.read_result task_id` and its refusals. The job_search test is out of `tests/test_named_events.py`.
> - **ruff passes.** pytest got to 268 passed and stopped at `tests/test_module_docs.py::test_the_library_table_is_generated…`. That failure is expected: the module library is stale until `build_docs.py` runs. Run the whole suite again after the docs.
> - **Next (session 2):**
>   1. Update the docs in part 4. Spots found:
>      - `docs/api/agents.md:368` (`hub.start`, the message text) and the `StartTask` section (`parent_note`).
>      - `docs/api/modules.md:128-129, 206, 214, 218`: the cv/job_search examples become "no module uses it now; kept".
>      - `docs/api/messaging.md:124, 142`: the `cv.job_finished` row goes.
>      - `docs/api/README.md:49` and `docs/api/reusable.md:20`.
>      - `docs/architecture/modules.md:117`, `communication.md:66`, `agents.md:315` (the new message: note and brief), `decisions.md:24` (add: module-to-module results go through tools and the Hub; named events wait for a real second listener).
>      - `src/assistant/modules/job_search/docs/architecture.md:11`.
>      - `src/assistant/modules/agent_hub/docs/architecture.md:23`, and `tools.md` if it isn't generated.
>      - `src/assistant/modules/cv/docs/architecture.md:26-27, 462` and `cv/docs/tools.md` (`cv.read_result task_id`, `cv.task`'s note).
>      - `named-module-events.md` (status: first use removed, mechanism kept) and `handoff-5eff4e83.md` open point 1 (answered here).
>      - The README row of this note.
>   2. Run `build_docs.py` (`module-library.md` is generated), then pytest and ruff, then the architecture check.
>   3. Ask the user in a NEED for the app restart (contracts changed), with the recommendation. The hand checks come only after the restart and the user's go. Decision you approved: job_search and cv talk through tools (`cv.task`, `cv.read_result`) plus the Hub's child-result message. The named event `cv.job_finished` goes; `ModuleEvent` and `ctx.publish_named / subscribe_named / unsubscribe` stay in the core, built and tested, with nothing more built on them for now.

**Asked (2026-11-12):** the code read showed two tracks for one thing. When cv_agent's task ends, the Hub sends the job agent a child-result message, which wakes it. cv also publishes `cv.job_finished`, which job_search turns into a background note that wakes nobody. You wanted the tools to be the way in, as first intended. So keep one path, the tools and the Hub message, and make the Hub message say which job ended and what the job agent was doing. That also closes open point 1 of [handoff-5eff4e83](handoff-5eff4e83.md): the job agent woke "in a fresh session without the original brief".

## 1. The small fix: the child-result message carries its context

**Today** (`agent_hub/tasks.py:50`, `:431-441`): `"Your child task {id} on {agent} ended {state}: {result}"`, the result cut at 4000 characters. If the job agent's own task has already ended, this message starts a **new task** (`delivery.py:138`) in a fresh session. That session has no brief, no job, and no "what next". The cut can also drop the `CV_RESULT` line, which is the result's last line.

**After:**

```
Your child task 3f2a91c0 on cv_agent ended done.
It was for: the CV for Smoke Test Engineer at NonexistentTestCo, job folder C:\Jobs\CV_Module\work\2026-11-12_NonexistentTestCo_SmokeTestEngineer.
Your task 632c9ff5 started it, with: "Fake job smoke test: call cv.task for … then write the report SMOKE TEST 2 DONE …" (first 600 characters)
Next: read the result with cv.read_result task_id=3f2a91c0.
Result (start): …
```

Where each part comes from:

| Part | Who supplies it | How |
|------|-----------------|-----|
| The job's company, role, folder, and the "Next:" line | `cv.task` | A new optional field on `StartTask`: **`parent_note: str = ""`**, a short text for the parent's agent when this child ends. The Hub keeps it on the `TaskRecord` and puts it in the message. cv builds it from the `CvRequest`. The folder name uses `job_start.job_folder_name(company, role, today)`, the same helper the gate uses (`job_start.py:52`, `:115`). |
| The job agent's original instructions | **the Hub itself** | The parent task's own text, from the parent's `TaskRecord`, which is always still there: `_prune` keeps the parent of an open task (`tasks.py:443-447`), and `_to_parent` runs before `_prune` (`tasks.py:428-429`). This works for every parent-child pair, not only cv. |
| The details | `cv.read_result` | It gets an optional **`task_id`**. cv fetches that task's full result itself (`GetTaskStatus(task_id=…)`, a command cv already sends), so the agent never pastes text or calls a huge `hub.status`, and the 4000-character cut doesn't matter. `text` still works as before. |

**Why a new field rather than the existing `StartTask.context`:** `context` already goes to the *child* agent. `session_agent.py:895-896` adds it to the child's first message. Putting the job agent's brief there would show "write the report SMOKE TEST 2 DONE" to cv_agent, which might act on it. `parent_note` only goes to the parent.

**What it touches:**
- **Contracts** (`contracts/agents.py`, `StartTask`): one optional field. **This needs an app restart.** The field is optional with a default, so every other sender (`task_agents`, `hub.start`, `Delivery`) is unchanged.
- **The core:** nothing.
- **agent_hub** (a module): `TaskRecord.parent_note`, the new `CHILD_ENDED` text, the parent's text in it. `hub.start` gets an optional `parent_note` input as well, so an agent starting a child by hand can say why (one line in the menu item).
- **cv** (a module): `cv.task` sets `parent_note`. `cv.read_result` takes `task_id`. Its `next` text says "read it with cv.read_result task_id=…".

**A reload-only alternative, if you'd rather skip the restart:** the Hub quotes the parent's own text (no contract change), and cv puts the job's line in the child's `context` instead of a new field. The cost: cv_agent sees that line too. It's harmless, since it is cv_agent's own job, but it isn't clean, and job details would ride on a field meant for something else. I recommend the new field. The restart can be batched with others.

## 2. Remove the duplicate path

- **job_search:** remove `CV_FINISHED`, `cv_finished_note`, `_on_cv_finished`, the `ctx.subscribe_named(...)` in `init`, `listens_named` in the manifest, and the `ModuleEvent` import (`job_search/module.py:38`, `:72-87`, `:99`, `:118-124`). `AgentNotice` stays, because `job.search` still uses it (`:171`). The module docstring and the job prompt don't mention the note, so they stay.
- **cv:** remove the `TaskUpdated` subscription and `_on_task` (`cv/module.py:257`, `:288-300`), `publishes_named=(JOB_FINISHED,)` (`:217`), and `TaskUpdated` from its `listens`, if nothing else uses it there (checked at build time). Also remove `JOB_FINISHED` and `job_finished()` from `cv/handoff.py:68-81`, plus imports left unused (`read_record` in module.py, if nothing else uses it).
- **Keep:** `ModuleEvent`, `SubscriptionHandle`, `ctx.publish_named / subscribe_named / unsubscribe`, `Manifest.publishes_named / listens_named`, and their core tests. After this change no module uses them. The docs will say so, and say they're kept as the general mechanism for when a real second listener needs one.

## 3. The risk: the child ends while the parent is busy, or after its task ended

Checked in the code. **The message is never lost and never cut into a turn.** `Delivery.deliver` (`agent_hub/delivery.py:73-87`) calls `_try` (`:120-143`):

| The job agent when cv_agent's task ends | What happens | Code |
|---|---|---|
| **In a turn** (its task still running) | `_try` returns None. The message is queued as **pending**, in order behind any other waiting message for that agent. When the agent's state changes, `flush` delivers it (`agent_hub/module.py:301-304` → `delivery.py:97-111`). | `delivery.py:124-125`, `:81-84` |
| **Idle, its task still open** (stopped, or holding a question) | The message goes into that same task (`SendToTask`), so its session and brief are still there. | `delivery.py:130-134` |
| **Idle, its task already ended** (the usual case: it ends its turn after `cv.task`) | A **new task** on the job agent with the message as its text, in a fresh session. This is why the message must carry the brief and the job (part 1). | `delivery.py:138-140` |
| **Its module is off, or the cap / a folder clash refuses the new task** | Pending again, retried at the next state change. What still waits is passed to the next Hub copy on a reload (`export`). | `delivery.py:123-125`, `:141-142`, `:113-115` |

Tests that already cover the first and third rows: `agent_hub/tests/test_child_result.py` (`test_a_parent_in_a_turn_gets_it_when_the_turn_ends`, `test_an_idle_parent_whose_task_ended_gets_the_result_as_a_new_task`). One gap: if the parent's agent stays off for a long time, the message waits with no time limit. That's the right default (nothing is lost) and doesn't change here.

## 4. Files, tests, docs, loading

**Code:**
- `src/assistant/contracts/agents.py`: `StartTask.parent_note`.
- `src/assistant/modules/agent_hub/tasks.py`: `TaskRecord.parent_note`, `CHILD_ENDED`, `_to_parent` (the note and the parent's text, first 600 characters), the record's export / restore.
- `src/assistant/modules/agent_hub/module.py`: `hub.start`'s optional `parent_note` input.
- `src/assistant/modules/cv/module.py`: `cv.task` sets `parent_note`; `cv.read_result` gets `task_id`; the event publish is removed.
- `src/assistant/modules/cv/handoff.py`: `JOB_FINISHED`, `job_finished` removed.
- `src/assistant/modules/job_search/module.py`: the listener and the note are removed.

**Tests:**
- `agent_hub/tests/test_child_result.py`: the message carries the note and the start of the parent's text, in both the queued case and the new-task case. A child with no note still works (today's text, plus the parent's text). The parent's text is cut at 600 characters.
- `cv/tests/test_callers.py` (or `test_handoff.py`): `cv.task` sends a `StartTask` whose `parent_note` names the company, role and folder. `cv.read_result task_id=…` reads the task's result. A `task_id` it can't find is refused, and the caller check still applies.
- `cv/tests/test_reply_delivery.py`: the `cv.job_finished` listener part (`:71-115`) is removed, with an assert that cv publishes no named event at a task's end.
- `tests/test_named_events.py`: the job_search part (`:170-195`, `cv_finished_note`) is removed. The core tests stay.
- The whole suite and `ruff`.

**Docs** (then rebuild with `build_docs.py`):
- `docs/api/agents.md` (`StartTask.parent_note`, the Hub's menu: `hub.start`), `docs/api/messaging.md` and `docs/api/modules.md` (`ModuleEvent`: kept, no module uses it now), `docs/api/reusable.md` (its Used by line).
- `docs/architecture/agents.md` (the child-result message), `communication.md` and `modules.md` (the cv → job_search example removed), `decisions.md` (a line: module-to-module results go through tools and the Hub, named events only when a real second listener needs one), `module-library.md`.
- Module docs: `agent_hub/docs/architecture.md` and `tools.md`, `cv/docs/architecture.md` (the Publishes and Listens rows) and `tools.md` (`cv.task`, `cv.read_result task_id`), `job_search/docs/architecture.md` (Listens row).
- Next steps: this note's status, [named-module-events](named-module-events.md) (the first use removed, the mechanism kept), and [handoff-5eff4e83](handoff-5eff4e83.md) open point 1 (answered by this note).

**Loading:** the contract field needs **one app restart**. The restart loads agent_hub, cv and job_search with it, so no separate reloads are needed. I'll ask before the restart. With the reload-only alternative, it would be `RELOAD: agent_hub`, `RELOAD: cv`, `RELOAD: job_search`, each asked first.

## 5. Hand checks (after the build and the restart)

The fake job again: no real application, no Submit, no Rezi, no Chrome.

1. **Only the job agent is started.** The Main Assistant does one `hub.start` on `job_search_agent` with the fake-job brief, then ends its turn and stays **idle**. It doesn't watch or call `hub.status` in a loop, so there's no folder clash with cv_agent (open point 2 of handoff-5eff4e83). The brief tells the job agent to call `cv.task` for NonexistentTestCo / Smoke Test Engineer with the test CV (`CV_Test_*.pdf`), with notes telling cv_agent: no Chrome, no Rezi, end at once with `CV_RESULT` status `"stopped"`. Then end its turn, and when the result comes, write the report `SMOKE TEST 3 DONE` with the job and the result's status.
2. **The job agent's task ends** after `cv.task` (its turn over, as before).
3. **cv_agent ends its task** with the `CV_RESULT` line, and touches no Chrome or Rezi.
4. **One message reaches the job agent**, as a new task. It names the job (company, role, folder), quotes the start of its original brief, and says to use `cv.read_result task_id=…`. The log has no `cv.job_finished` and no `[cv.job_finished]` note.
5. **The job agent acts on it with no help:** it calls `cv.read_result task_id=…` and writes the `SMOKE TEST 3 DONE` report. This is what failed in fake job 2.
6. **Busy-parent variant (optional):** you send the job agent a message to keep it in a turn while cv_agent ends. The child-result message waits as pending and arrives right after that turn.
7. **Cleanup:** delete the new work folder under `C:\Jobs\CV_Module\work\` and its CV Tool job, as in session 4 of handoff-5eff4e83.
