# Agents talk to each other freely, and a question never makes an agent busy

> **Status: built (2026-11-10), waiting on the app restart and the hand checks.** The user approved all six choices as recommended. Takes in [two-agent-states](two-agent-states.md) and replaces [hub-folder-check-parent](hub-folder-check-parent.md) (cancelled, never built).

**Asked:** "the cv module can't give the job module the resulting cv and the info about it either. Which makes the process a mess." "They can just ask for permission to send things to each other if we need a gate." The cv and job modules were meant to talk to each other freely when needed; restore that, with the permission card as the only gate. And: an agent that asks a question must not sit in a holding pattern. The question is just a message; the agent ends its turn and is free; the user answers whenever they like, as a normal message, and the module finds the right context again from its notes.

**Why:** on 2026-11-09 the Globex Robotics hand-off failed both ways, and only manual relays by the Talker got it through.

## What went wrong, exactly

**Job agent → cv agent** (the job: `cv.task`). Three blocks, one after the other:

1. **Who may start cv_agent** (cv-path-hardening): `cv.task` doesn't start cv_agent. It hands the text to the coordinator (`[hand_off] coordinator = "main_assistant"`), and `start_only_by = { cv_agent = ["main_assistant"] }` in `[modules.agent_hub]` refuses `hub.start` for cv_agent from anyone else, the job agent included.
2. **The queue that never runs:** the hand-off to the Main Assistant is a `StartTask`. The Main Assistant had an open task waiting on a `NEED:` (4df48918), so it counted as **busy** and refused. `cv.task` fell back to an `AgentNotice`, which only joins the agent's next turn and never wakes it. That turn didn't come, so the job agent sent `cv.task` three times into the same hole.
3. **The folder check counts the requester's own task:** when the Main Assistant did run it, `hub.start` refused: "cv_agent would write C:\Projects\AI_Assistant, which main_assistant's open task writes". `_folder_clash` (`agent_hub/tasks.py`) counts every open task, including the one calling `hub.start`. The clash is real on paper: **cv_agent's saved grant holds three write folders inside the repo** (`src\cv_tool`, `src\assistant\modules\cv\docs`, `tests`, added in `data/permissions.toml` when cv_agent built the CV Tool), and the Main Assistant writes the whole repo. So any open Main Assistant task blocks cv_agent, and the reverse.

**Cv agent → job agent** (the finished CV):

1. **Child-only `hub.send`:** an agent may message only tasks it started (`may_steer`). cv_agent didn't start the job agent's task 0590f5bc, so: "Task 0590f5bc isn't one of cv_agent child tasks".
2. **The automatic return did fire, as a notice nobody saw.** The job's `job_start.json` says `replied: {submitted_at 23:41:12, to job_search_agent, how: notice}`. At the Submit, `_tell_asker` → `_wake` tried a `StartTask` on job_search_agent. The job agent was waiting on its question ("tell me CV ready"), so it counted as busy and refused, and the module fell back to an `AgentNotice`. A notice never wakes an agent, so the job agent only saw it when the Talker messaged its task by hand. cv_agent didn't know the return had gone (the `told` field of `cv.tool_result` wasn't in its view by then) and tried `hub.send` itself.

**The shared root:** "busy" includes "waiting on a question" (`session_agent.py:207`: busy unless the mode is idle; `assign` refuses a busy agent at line 230). Every fallback that hit a waiting agent turned into a silent notice.

## Options

| | What | Good | Bad |
|---|---|---|---|
| **A** | Gated agent messages only: any agent may `hub.send` / `hub.start` any other, after a permission card | One general mechanism | The hand-off depends on agents remembering to send; a relaunch between job and Submit loses who to tell |
| **B** | Module hand-off only: the cv module starts cv_agent on `cv.task` and delivers the result at Submit, in code | Reliable, survives relaunches, no AI in the middle | No free talk: the job agent can't ask cv_agent for a change, cv_agent can't ask the job agent about the JD |
| **C (recommended)** | **B for the fixed hand-off, A for everything else, and questions as messages** so neither ever hits a "busy" agent | Both ways work, one gate, nothing waits silently | The biggest change; contract changes, so an app restart |

## The approach (option C)

### 1. The cv module does the hand-off itself (no Main Assistant)

- **`cv.task` starts cv_agent** with a `StartTask` of its own, `parent_task_id` = the caller's open task (so the job agent may `hub.send` to it as its child, as today). `[hand_off] coordinator` goes; `start_only_by` for cv_agent goes from `config/default.toml`. A module's `StartTask` isn't an agent's `hub.start`, so the parent-task rules don't apply to it.
- **If cv_agent is working on another job**, `cv.task` says so and who it's for. No silent queue.
- **At Submit**, the module delivers the result to `reply_to` with one shared helper, *deliver* (in the Hub, below): to the asker's open task as a message, or a new task if it has none, or held and delivered when it next starts if it isn't running. `job_start.json` records how (`message <task>`, `task <id>`, `pending`). No `AgentNotice` fallback.
- **No card for these two:** `cv.task` is already limited to `[hand_off] callers`, and the Submit is your own click.

### 2. Agents message each other, with the permission card as the gate

- **`hub.send` with `agent_id`** (and `hub.start` on a named agent) works for every agent, not only the Talker. Your child tasks stay free as now; the Talker (you) is never asked.
- **The first message from A to B** opens a permission card: "job_search_agent wants to message cv_agent", with the start of the text. Buttons: **Allow once** · **Always allow** · **Deny**.
- **How it fits the existing grants:** "Always" saves a grant in `data/permissions.toml`, module `agent_hub`, subject = the sender's kind (as [grants per kind of agent](../architecture/permissions.md#grants-per-kind-of-agent): `helper_2` shares `helper`'s), item `message:<receiver>`. One grant per direction, so job → cv and cv → job are each asked once. It shows in `permissions.grants` and the Grants panel; `permissions.revoke` takes it back and the next message asks again. "Allow once" sends this message and saves nothing. Deny sends nothing; the sender gets a note saying so.
- **New in the handler:** an `AccessKind.MESSAGE`, `AnswerPermissionRequest.remember` (false = once), and a revoke of a `message:` item doesn't turn `agent_hub` off (today any revoke turns the module off).
- **While the card is open,** `hub.send` answers "waiting on the user's card"; the Hub holds the message and delivers it on Allow.
- **Delivery never interrupts:** an agent in a turn gets the message when the turn ends, as its next message (unlike a notice, it wakes the agent). An idle agent gets it at once: into its open task if it has one, else as a new task. The text starts `[Message from <sender>]`.

### 3. A question is a message; the agent is never busy waiting (takes in two-agent-states)

- **Two states only:** an agent or task is **active** (in a turn) or **idle**, as in [two-agent-states](two-agent-states.md); its table of what "waiting" touches is the work list. `TaskState` loses `running`, `paused` and `waiting_for_input`; `AgentInfo` gets `state` in place of `busy` and `working`.
- **A `NEED:` ends the turn and the task.** The agent is free at once. The question becomes its own record in the Hub (id, agent, text, a **context key**, asked at), shown behind the tab's **!** as today. This replaces two-agent-states' "a new task ends the old one as left unanswered": the question stays answerable however much happens in between.
- **Your answer is a normal message**, whenever you like: the Hub sends it to the agent as "Answer to your question <id> (<question>): <answer>", into its open task or as a new task.
- **The module finds the context again.** The question carries a context key (cv: the job's work folder; job_search: the application doc). If the agent's session still has the question, nothing more is needed. If not (a relaunch, a reset, other work in between), the module adds its notes for that key to the message: cv adds the job's `job_start.json` summary and its handoff note; others their handoff note. Each module says how, through one small hook on its agent (`context_for(key)`), default: none.
- **A permission card** (a tool call mid-turn) stays as it is: the turn is still active, and Allow or Deny lets it carry on.
- **The restart** goes ahead with questions open; they're in the restart note and asked again after the launch.

### The Hub's folder check

- **Keep the check, don't skip the requester.** The cancelled note's idea (skip the parent task) is not needed: in step 1 the Main Assistant is out of the loop, and the job agent's folders (`C:\Jobs\CV`) don't overlap cv_agent's (`C:\Jobs\CV_Module`).
- **Revoke cv_agent's three repo write folders** (with your yes; they were for building the CV Tool, and CV jobs never write the repo). cv_agent can ask for them again with `permissions.request` when it builds again; live grants reach it without a restart.
- **With step 3,** an agent waiting on a question has no open task, so it holds no folder. Only agents really in a turn can clash.

## Touches

- **Contracts** (`contracts/agents.py`, `contracts/permissions` types): `TaskState`, `AgentInfo.state`, `AgentStateChanged`, the question record, `AccessKind.MESSAGE`, `AnswerPermissionRequest.remember`. App restart.
- **Core:** `core/permissions/` (message items, once, revoke without turning off). App restart.
- **Infra:** `session_agent.py` (no `waiting`/`paused` outside, `context_for`), `profile_agent.py`, `agent_tags.py` if the NEED parse changes.
- **Modules:** `agent_hub` (`tasks.py`: states, question records, *deliver*, the message gate; `module.py`: `hub.send` / `hub.start` for all, `hub.answer` for questions), `cv` (`module.py`, `reply.py`, `module.toml`: no coordinator; its `context_for`), `job_search` (its `context_for`), `main_assistant`, `talker` (`module.py`, `restart.py`, `session.py`), `temp_ui` (active/idle, the three card buttons, the **!** from question records), `task_agents`.
- **Config** (with your yes): `start_only_by` removed for cv_agent. **Grants** (with your yes): `permissions.revoke` of cv_agent's three repo write folders.
- **Docs:** `architecture/agents.md`, `agents-code.md`, `permissions.md`, `core.md`, `api/agents.md`, `api/messaging.md`, `api/infra.md`, `modules/agent_hub.md`, `modules/temp_ui.md`, `agents/runtime.md`, the cv module's `docs/` (hand-off section), `api/reusable.md` (*deliver*, `context_for`); rebuilt.

## Tests

- **cv hand-off** (`cv/tests/test_handoff.py`, through the real Hub with fake `claude`): `cv.task` from job_search_agent starts cv_agent with the job agent's task as parent, no Main Assistant task; cv_agent active on another job → refused with the reason, nothing queued; Submit with the asker idle and a question open → a message to it; asker with no task → a new task; asker in a turn → delivered at its turn end; asker not running → `pending`, delivered when it starts; a second look at the same Submit tells nobody.
- **Message gate** (`agent_hub/tests/`): non-child send with no grant → a card, the message held; Allow once → delivered, nothing saved, the next asks again; Always → saved under `agent_hub` / the sender's kind, the next goes through with no card; Deny → not delivered, the sender noted; revoke → asks again and `agent_hub` stays on; a `helper_2` uses `helper`'s grant; the Talker and child tasks never asked; a message never interrupts a turn.
- **Questions as messages** (`tests/test_agents.py`, `tests/test_worker_parts.py`, the Hub's tests): a `NEED:` ends the task and the agent is idle (`state` idle); a new task is accepted with a question open; the answer arrives as "Answer to your question …" in a new task; with the session reset, `context_for` adds the notes for the key (cv: the job folder's); the restart goes ahead and its note lists the open questions; a permission card still keeps the turn active.
- **Folder check:** unchanged rules; an idle agent with an open question doesn't clash.
- Then the whole suite and `ruff check src tests scripts`.

## Build status

Built 2026-11-10 in one build, tested step by step. Final run: 768 passed (the cv_tool 9 pt test deselected, below; 2 `claude`-marked tests skipped by default), ruff clean. The docs for all three steps are updated (architecture, API, reusable index, module pages, the cv module's docs) and the HTML is rebuilt. Final architecture check: the Hub imports no other module, cv reaches the Hub only through contracts (`StartTask`, `GetTaskStatus`, `DeliverMessage`), the core's permissions handler names no module. Needs one app restart (contracts, core, infra changed).

**Verified again 2026-11-10 (final session):** ruff clean; the whole suite 768 passed, 3 deselected (the 9 pt test and the 2 `claude` tests), run in the foreground; the generated-docs tests pass after the rebuild; no stale `busy` / `working` / `waiting_for_input` lines left in the permanent docs; `agent_hub` and `cv` import no other module and nothing from the core.

- **Step 1, the cv hand-off:** `cv.task` starts cv_agent itself (`StartTask` with the caller's open task as parent) and refuses with the job and its asker when cv_agent is busy on another job. At Submit the result goes out through the new `DeliverMessage` contract, handled by the Hub's `Delivery` (`agent_hub/delivery.py`): never into a turn, into the open task or a new one, `pending` until the agent runs. The coordinator and the `AgentNotice` fallback are gone. Tests: `agent_hub/tests/test_delivery.py`, `cv/tests/test_reply_delivery.py`, `test_callers.py`, `test_handoff.py`.
- **Step 2, the message gate:** `agent_hub/gate.py` `MessageGate`; `hub.send` with `agent_id` for every agent; the card with Allow once · Always allow · Deny; `AccessKind.MESSAGE`, `AnswerPermissionRequest.remember`, `ModulePermissions.granted / ask`; a revoke of only `message:` items keeps the module on. Tests: `agent_hub/tests/test_gate.py`.
- **Step 3, questions as messages:** `AgentState` (active, idle) replaces busy and working; `TaskState` is active, idle, done, failed, cancelled. A `NEED:` ends the turn and the agent is free; the Hub keeps the task idle with its question (`TaskRecord.asked`), and the answer re-assigns the same task id. An answer during a turn waits for the turn's end (`Delivery.later`). The module's notes come back through `SessionTaskAgent.set_context(key, notes)` (cv: `job_notes`, the job folder's `job_start.json` and handoff note). Open questions survive a Hub reload (`export_questions / restore`); the restart no longer refuses with questions open. Tests: `tests/test_questions_as_messages.py`, plus the updated agent tests.
- **Differences from the plan:** the hook is named `set_context` (not `context_for`); the question is kept on its task record, not a separate record, so parents, children and the Talker's open tasks stay valid. `start_only_by` for cv_agent became `named_only = ["cv_agent"]` in `config/default.toml`, which keeps free picks off cv_agent while anyone may name it.
- **After the restart, still to do (asks first):** revoke cv_agent's three repo write folders (`write:` `src\cv_tool`, `src\assistant\modules\cv\docs`, `tests`; still in `data/permissions.toml` under `cv.cv_agent`). It's a folder revoke, so it turns the cv module off (`handler.py` `_turn_off`); not done before the restart because you're asked before any module goes off. `named_only = ["cv_agent"]` replacing `start_only_by` is confirmed in `config/default.toml`.
- **Not from this change:** `cv/tests/test_cv_tool.py::test_every_style_on_the_page_is_9_pt_or_more` fails because `src/cv_tool/cvlib.py` now sets `MIN_PT = 10.0`; left as is.

## Hand checks (after the restart)

1. With the Main Assistant busy on something else, the job agent sends a job with `cv.task`: cv_agent's tab has it within seconds, and the Main Assistant's tab shows nothing.
2. In the CV Tool, Submit while the job agent is waiting on a question: its tab gets the cv message and it carries on with the upload.
3. The job agent messages cv_agent for the first time: a card with Allow once · Always allow · Deny. Pick Always; the second message has no card; the Grants panel shows it; revoke it; the next message asks again.
4. cv_agent asks you something; `hub.agents` shows it idle. Give it another job: accepted. Answer the first question later: it picks up the right job.
5. Relaunch between a question and your answer: the answer still finds its job.
6. Revoke cv_agent's three repo write folders (`permissions.revoke`, asked first: cv turns off, then back on). `permissions.grants` no longer lists them, and a CV job still runs.
7. The temp UI's tabs show active or idle (no "busy"), and a message card has the three buttons.

## Open questions

1. **Which option?** Recommended: **C**.
2. **One grant per direction, or one per pair both ways?** Recommended: **per direction**.
3. **Should a message interrupt an agent in a turn, as `hub.send` does for a parent today?** Recommended: **no**, delivered at its turn end; a parent's own `hub.send` to its child keeps interrupting.
4. **Where the answer finds its context:** the module's notes by the question's key, with the live session when it still has it (recommended), or keep every asking session open until answered.
5. **Revoke cv_agent's three repo write folders and drop `start_only_by` for cv_agent?** Recommended: **yes, both**.
6. **Build order:** recommended in one build (you chose one change), checked per part with the tests: step 1, then 2, then 3. One app restart at the end.
