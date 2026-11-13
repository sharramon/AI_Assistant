# An agent in Auto gets no permission cards, and a waiting worker is paused by the Hub

**Status:** checked by you 2026-11-13 (answers below). **Rule 1 built.** **Rule 2, corrected, built** (approved by you 2026-11-13): a waiting task **ends** with a note and is resumed from it, never held paused ([rule 2, corrected](#rule-2-corrected-a-waiting-task-ends-with-a-note)). Full suite 841 passed, ruff clean, docs rebuilt. **Left:** the app restart (core, infra and contracts changed); you said you'll restart it yourself (2026-11-13). Not committed. Date: 2026-11-13. Two code rules in one change: the Auto check at the gate (below), and [the Hub pauses a worker that's only waiting](#rule-2-the-hub-pauses-a-worker-thats-only-waiting).

## What you asked

Why do permission cards and asks still reach you when an agent is in Auto, and can one check at the gate stop that: "if the calling agent is in Auto, skip the card"? `git push` stays blocked, and the "very risky" pause (`NEED: Risky: …`) stays as it is.

## Why the cards come

There are **two card paths**, and only one of them knows about Auto:

1. **The agent's own gate** (`PermissionGate`, in `infra/`). It already checks the agent's mode: in Auto it answers tool requests itself, with `git push` refused.
2. **The core's permissions handler** (`core/permissions/handler.py`). It shows the message cards, access-list cards and grant cards. It never looks at anyone's mode.

**The smoke test's cards are Manual cards.** The mode is per agent, every agent starts in Manual, and only your button switches one to Auto. In Manual, every `use_item` call through the module door (turning cv on, passing the job to cv) asks on a card by design: the door's read-only tools are allowed, `use_item` isn't. So those cards came from path 1 working as meant. The proposed check wouldn't have removed them unless the job agent had been switched to Auto. I didn't read the run's logs, so I can't say which card the "card from the CV agent" was.

## Every place a card or an ask is raised

| # | Where | What raises it | Checks the caller's mode? | Can the mode be read there? |
|---|-------|----------------|---------------------------|------------------------------|
| 1 | Tool permission requests: `PermissionGate.on_tool_request` (`infra/permission_gate.py:104`) | `claude` asks for a tool its rules don't allow (`can_use_tool`) | **Yes** (line 113): in Auto it's allowed, except `git push`. An Auto session runs `bypassPermissions`, so most never arrive | Yes, `mode()` |
| 2 | The module door (`use_item` → `InvokeTool`) | No card of its own. In Manual, `use_item` arrives as #1 (`agent_profile.py:180`). The core menu's `modules.off` with dependents and `modules.add` call `ctx.permissions.request(name)` (`core/directory.py:71, 86`), but single names aren't checked yet: always allowed, no card | Not needed today. Once single names are checked, they'll go through the handler, so #5 to #7 cover them | — |
| 3 | Reload or add from a `RELOAD:` / `ADD_MODULE:` line: `SessionTaskAgent` (`infra/session_agent.py:701`) | The agent's last line | **Yes**: in Auto it runs at once | Yes, `self._permission_mode` |
| 4 | `request_approval` (`infra/session_agent.py:451`), used by `agents.launch` on `task_agents` | A helper launch | **No, on purpose**: "a launch always asks, even in Auto" ([agents](../architecture/agents.md#launching-a-helper)) | Yes, `self._permission_mode` |
| 5 | The message card: `MessageGate.send` (`agent_hub/gate.py:44, 68`) → `handler.ask` (`handler.py:226`) | An agent messages one that isn't its child (`hub.send` with `agent_id`) | **No** | In the Hub, yes (`self._agent(sender).info().permission_mode`). In the core handler, only by asking (`ListAgents` through its `send`) |
| 6 | Access-list cards: `handler.request_set` (`handler.py:188`), from a module's start (`request_access` in job_search, cv, task_agents) | A task-agent module turned on with a new or changed list | **No** | **No.** The card has no caller: `modules.on` (`directory.py:64`) sends `ActivateModule` with no caller, so who turned the module on is lost before `start()` |
| 7 | Grant cards: `handler.grant`, `handler.request`, `handler.revoke` (`handler.py:291, 310, 344`) | An agent's `permissions.grant / request / revoke` | **No** (only "you", the temp UI, skips the card) | The caller is on the card (`card.caller`); the mode only by asking (`ListAgents`) |

## The proposal

Two small checks, one on each card path, so every card goes past exactly one mode check.

**A. The core handler: one check in `_open(card)`.** Every handler card goes through `_open`, so this is the single gate for #5 and #7, and later for single names. Before the card shows:

- If `card.caller` is set and that agent is in Auto, the card isn't shown, and the agent gets a note saying it went through in Auto.
- The mode is read with `ListAgents` through the router's `send` (contracts only, so the handler still imports no module and names no agent). If the caller isn't found or the call fails, it's treated as Manual and the card shows.
- **A message card (#5) in Auto is Allow once:** delivered, nothing saved. Switching back to Manual brings the card back.

**B. The agent's gate: the Auto rule moves into `PermissionGate.ask`.** Today #3 checks the mode in `SessionTaskAgent` and #1 checks it in the gate. Moving #3's check into `gate.ask` makes the gate the one place on the agent side. #4 (helper launch) would then follow it too, unless you keep its exception (question 3).

**Unchanged:**

- **`git push`** stays refused in Auto: it's in `--disallowedTools` and in `PermissionGate.auto_answer`. Neither check touches tool requests.
- **The "very risky" pause** stays a prompt rule. A `NEED: Risky: …` is still a question held for you, never a card, so these checks don't see it.
- **Manual** is unchanged: every card shows as today.

## Your answers (2026-11-13)

**The general rule:** in Auto everything is allowed: no cards, no asks, and no extra cards or configs added, unless something very dangerous might happen. The risky-step stop (`NEED: Risky:`) stays, and `git push` stays blocked.

1. **Grant cards (#7):** skipped in Auto; the grant, request or revoke is carried out at once.
2. **Access-list cards (#6):** skipped in Auto. **No contract change was needed:** `modules.on` already knows its caller, so it sets `ACTING_FOR` (a context variable in the core handler) around its `ActivateModule`; the module's start, and its requires', run in tasks copied from that context, so `request_set` reads who turned it on. In Auto the list is allowed for this launch and **not saved** (Allow once, like a message), so a Manual launch asks again. Protected-zone refusals still apply.
3. **Helper launch (#4):** asks in Manual; once you press Auto on that agent, it stops asking. Each pair's own mode governs its own asks.
4. **Where:** the core handler, as the single place that reads each pair's flag: `_in_auto(caller)` sends `ListAgents` and reads that agent's `permission_mode`; a helper tab's Talker `talker:<id>` counts as `<id>`. On the agent side, `PermissionGate.ask` is the one check for approvals. **Limit:** the main tab's Talker calls as plain `talker`, and the core handler can't name the coordinator (shared code names no module), so its cards still show. It rarely makes these calls.
5. **Yes:** a helper's result reaches the Main Assistant as a message. After your correction, it resumes the Main Assistant's ended, waiting task from its note; nothing is held paused.
6. **Yes:** tasks started with `tell_parent=False` don't count as waiting.
7. **The risky-step stop stays in Auto**, and `git push` stays blocked.

## Rule 1: what was built

- `core/permissions/handler.py`: `_in_auto(caller)` and `ACTING_FOR`; the check in `ask` (Allow once), `request_set` (allowed this launch, not saved), `grant`, `request` and `revoke` (carried out at once). You, an unknown caller, plain `talker` or a failed lookup: the card.
- `core/directory.py`: `modules.on` takes its caller and sets `ACTING_FOR`.
- `infra/permission_gate.py`: `ask` runs the approval at once in Auto; `infra/session_agent.py` drops its own check for `RELOAD:` / `ADD_MODULE:` and `request_approval` follows the gate.
- Tests: `tests/test_auto_skips_cards.py` (Auto message, the pair's Talker, Manual / unknown / plain `talker` / you, a failed lookup, an access list turned on in Auto and in Manual, grant / request / revoke in Auto, `modules.on` passing its caller, the gate in Auto and Manual). Full suite: 831 passed.
- Docs: [permissions](../architecture/permissions.md#permission-mode-built), [agents](../architecture/agents.md) (launching a helper), the [Agents API](../api/agents.md), [infra API](../api/infra.md), [reusable](../api/reusable.md).

## Rule 2, corrected: a waiting task ends with a note

**Your correction (2026-11-13):** a task must never sit in an open-ended pause. A task that is only waiting, on a card, a helper's result or you, **ends**. It leaves a short note of what it waits for, so it never holds a working slot or gets in the way. When the answer, the result or a message comes, the work starts again from that note.

**This is the `NEED:` path, used for every kind of waiting.** A `NEED:` already works this way: the agent drops the task and is free, the Hub's record keeps the question and its `question_key`, and the answer gives the same task id back (`TaskBoard._answer`). It goes into the live session if nothing ran since (`_asked`), else into a fresh one with the key's notes (`CONTEXT_AGAIN`). Rule 2 now just adds two more things a task can wait on.

### What the ending note holds

It's the Hub's record of the ended task, the same record a `NEED:` leaves. It outlives a Hub reload (`export_questions`):

- **What it waits on**, as the record's question: "waiting on child task 3fa2 (cv)", or "waiting on your answer to its card: reload cv". Its kind is a new `QuestionKind.WAIT` (typed, so nobody parses the text). A `NEED:` keeps `need` / `risky`.
- **The task's own text and recent reports**, as today.
- **Where to pick up:** the `question_key` (the module's context key, e.g. the job's folder) or else the task's last handoff note, sent with the `turn_end` report exactly as a `NEED:` sends it. A fresh session gets the original task, the "waiting on" line, and those notes.
- **The turn's last text**, cut short, so the resumed turn knows what it had just said.

### What wakes the work

| Waiting on | It ends when | What wakes it | How |
|---|---|---|---|
| **You** (`NEED:`, `NEED: Risky:`) | as today | your answer | as today: `_answer` |
| **A helper's result** (child tasks with `tell_parent`) | its turn ends with no tag while they're open | each child's end | `_to_parent` delivers the result **into that parent task** (`Delivery.later` with the parent's task id, so it can't land in another task of the same agent); `_answer` resumes it. If other children are still open, the resumed turn ends waiting again |
| **Your answer to a card** (a `RELOAD:` / `ADD_MODULE:` approval or a helper launch, in Manual) | its turn ends with the card open | your answer on the card | the gate keeps that one approval past the drop. On Allow the action runs. Its outcome (or "denied") comes to the Hub as a `progress` report on the waiting task, and the Hub gives the task back with it (`_answer`) |
| **Any of these** | | your message to that task | `hub.send` into a waiting record is an answer, as for a `NEED:` |

If the agent is in another task when the wake comes, it waits in `Delivery` until the agent is free (`pending`), as every message does. A tool request held mid-turn (Manual `can_use_tool`) isn't touched: that turn is still running ("shouldn't catch", below). In Auto there are no cards, so only helpers and `NEED:` can leave a task waiting.

**While it waits, the agent is free:** it takes new tasks and messages, the slot is free (only `active` records count), and the Hub can reload (the note is exported). The record isn't behind the **!** for a helper wait (nothing for you to answer); a card shows as it does today.

### What happens to the code already built

| Part | Fate |
|---|---|
| `ReportKind.TURN_END`, `ReportTask.card_open`, `TURN_DONE` | **Kept.** The agent still reports the turn's end and the Hub still decides. `turn_end` also carries `key` now |
| `TURN_PAUSED` | **Renamed `TURN_WAIT`**: "the task ends waiting" |
| Hub `_settle` (card open, or open `tell_parent` children) | **Kept as the decision.** Instead of `idle` + `waiting_on` with the agent holding the task, it records the note (question, `QuestionKind.WAIT`, key) and the agent drops the task |
| `TaskRecord.waiting_on`, `_waiting_task`, the refusals in `start` and `_answer` ("paused waiting on …"), the `progress` case that woke a paused record | **Removed.** A waiting record is now one kind of `asked` record. The `progress` case becomes "a card's outcome resumes its waiting task" |
| `_to_parent`'s coordinator rule (answer 5) | **Kept**, retargeted: it delivers into the waiting parent task by id |
| Agent: mode `SETTLING`, `_settle`, the messages-while-settling hand-off | **Kept** (it still waits for the Hub's answer, so nothing slips in) |
| Agent: `_after_settle`'s "paused" branch, `_send_outcome` waking a paused task | **Replaced**: on `TURN_WAIT` it drops the task like `_ask_user` (live session kept for `_asked`). An outcome for a dropped task goes to the Hub as that task's `progress` report |
| `PermissionGate` | **Changed a little:** `clear()` on a wait drop keeps the open approval, tied to its task id; `answer_permission` takes that id though it's no longer the current task |
| Docs edited for the pause (agents "Paused by the Hub", runtime mode diagram, Agents API `turn_end`) | **Rewritten** to "ends waiting, resumed from its note" |

### What changes for the Main Assistant

Its turn that ends with helpers still open now **ends waiting** too, instead of ending `done` (before rule 2) or sitting paused (the first build). It's free at once: the Talker's next request starts a new task on it, which the pause used to refuse. Each helper's end arrives as a message into the waiting task. It resumes in the live session if nothing ran since, else in a fresh one from the note. It never holds a slot either way (the coordinator doesn't count against `max_extra_agents`). Its feed line for each child's end stays.

### The tests (838 today)

- **`agent_hub/tests/test_pause_waiting.py`** (6 tests): rewritten, and renamed `test_end_waiting.py`. Same cases, new expectations: nothing open → done (unchanged); a parent with an open child ends waiting, its agent is free and **takes a new task**, and the child's end resumes the **same task id**; `tell_parent=False` doesn't count (unchanged); the coordinator ends waiting and is resumed by its helper's end; a card open at the turn's end ends waiting, and the card's answer resumes it with the outcome; a `NEED` untouched. Added: two waiting tasks on one agent, each child's end lands in its own parent; a waiting record outlives a Hub reload.
- **`agent_hub/tests/test_end_report_race.py`** (3 tests): `turn_end` then `done` and the message-while-settling test unchanged; any check for `TURN_PAUSED` reads `TURN_WAIT`.
- **Session-agent tests:** one added: a `TURN_WAIT` answer drops the task with the gate's approval kept, and the answer goes back into the live session.
- Everything else (the rule 1 tests, the `NEED` tests, Delivery, child results) should pass unchanged. If any other test changes, the report will name it.

### Build of the corrected rule 2: handoff (2026-11-13, approved by you)

**Done in code (not yet tested, no test run since):**
- `contracts/agents.py` + `__init__.py`: `TURN_PAUSED` → `TURN_WAIT` ("wait"); `QuestionKind.WAIT`; `ReportTask.key` also with `turn_end`; `TURN_END` comment says a `progress` on a dropped task is new input for it.
- `infra/permission_gate.py`: `parked=` callback; `park(task_id)` (keeps an open approval, or one whose action runs, tied to the dropped task, out of the next task's way), `unpark(task_id)` (the task given back first), `answer_parked`, `parked` property; `_run_approved(run, action, task_id)` and `_outcome(task_id, text)` route an outcome to the current task or to `parked`; the expiry handles a parked approval.
- `infra/session_agent.py`: `_after_settle` on `TURN_WAIT` → `_drop_waiting` (`_asked = task_id`, `gate.park`, idle, what came while settling goes to `_on_parked`); `_on_parked` = a `progress` report on that task id (`_report` takes `task_id`); `_settle` sends `key`; `assign` calls `gate.unpark`; `answer_permission` answers a parked card; the PAUSED wake in `_send_outcome` removed.
- `agent_hub/tasks.py`: `waiting_on`, `_waiting_task` and the "paused waiting" refusals removed; `asked` also covers `WAIT` and a dropped card (`permission` with `holder is None`); `_settle(record, key)` ends the task waiting (holder None, key kept; a child wait sets question "waiting on child task … " with `WAIT`; **a card wait keeps `question_kind = permission`** so the Talker and temp UI cards keep working: a deviation from the design above); `progress` on an asked record → `tell_parent(agent, text, record.id)` (Delivery gives it back through `_answer`); `answer()` on a dropped card → question "waiting on the outcome of: …", `WAIT`; `_answer` keeps a still-open card's question; `_to_parent` targets the parent task id when it's waiting (`WAIT`), the coordinator only then.
- `agent_hub/delivery.py`: `tell(agent_id, text, task_id="", sender=...)`, `deliver(command, task_id="")`. `module.py` and `test_child_result.py` wiring pass `task_id`.

**Finished (2026-11-13, next session):** `test_pause_waiting.py` replaced by `agent_hub/tests/test_end_waiting.py` (9 tests: the 6 cases, two waiting tasks on one agent, a waiting record outliving a Hub reload, and the session-agent test: `TURN_WAIT` drops the task, `gate.parked` set, the answer goes into the live session with no restart). `test_end_report_race.py` passes unchanged. Full suite **841 passed**, ruff clean. Docs rewritten (agents "A waiting task ends with a note", the state diagram, runtime mode diagram and bullet, Agents API `QuestionKind.WAIT` / `ReportTask` / `TURN_WAIT`, API index, infra `PermissionGate.park`, reusable) and rebuilt. Left: the app restart after your yes; `talker/restart.py`'s `ASKED` doesn't list `WAIT` (out of scope). Not committed.

**The plan this session followed:**
1. Rewrite `agent_hub/tests/test_pause_waiting.py` as `test_end_waiting.py` (delete the old file; its rig's `tell_parent` lambda needs the `task_id` arg). Cases as in "The tests" above; the card case: after `end_turn` with `RELOAD: ghost`, `record.asked`, `not agent.has_task`, `agent.info()` idle; `board.answer(AnswerPermission(allow=True))` → the reload runs, the outcome resumes the same task id (`sessions["worker"].sent[-1]` has "Answer to your question in task" and the "[App] Reload the ghost module" outcome text: check the actual `CODE_LOADED` wording). Child case: the parent agent takes a new task while waiting (`board.start` ok), then the child's end resumes the parent task once the agent is free.
2. Add a session-agent test: `TURN_WAIT` answer → task dropped, `gate.parked == task id`, the answer goes into the live session (no fresh session).
3. `test_end_report_race.py`: check it still passes (no `TURN_PAUSED` there).
4. Run `.\.venv\Scripts\python -m pytest` and `.\.venv\Scripts\ruff check`; hand failures to the `debugger` subagent.
5. Docs: rewrite the pause wording in [agents](../architecture/agents.md) ("Paused by the Hub", kinds, the state diagram), [runtime](../agents/runtime.md) (mode diagram), [Agents API](../api/agents.md) (`ReportTask`, `turn_end`, `TURN_WAIT`, `QuestionKind.wait`), [API index](../api/README.md); add `QuestionKind.WAIT` / `PermissionGate.park` wording to [infra API](../api/infra.md) and [reusable](../api/reusable.md); then `.\.venv\Scripts\python scripts\build_docs.py`.
6. Architecture check, then the final report with the real test count and ruff. Not in scope yet: `talker/restart.py`'s `ASKED` doesn't list `WAIT` (the restart note lists only tasks waiting on the user; say so in the report).
7. Ask the user before the app restart (contracts, infra changed). Don't commit. No Chrome tabs open.

## Rule 2: what was built (first version, being replaced as above)

- `contracts/agents.py`: `ReportKind.TURN_END`, `TURN_PAUSED` / `TURN_DONE` (exported), and `ReportTask.card_open` (a tool request that timed out leaves a stale `permission` question in the Hub; `card_open=False` on `turn_end` clears it).
- `infra/session_agent.py`: a new mode `SETTLING`. A turn with no tag, a turn ending with its approval card open, or a last line (`RELOAD:` / `ADD_MODULE:`) that opened a card → `_settle` reports `turn_end`; `_after_settle` reads the Hub's answer: paused → `PAUSED`; done → the Chrome check, then `done`; something that came meanwhile (an approval's outcome, a message) → carries on. If the card was answered meanwhile and its action still runs, it waits as before. The gate's `send` is `_send_outcome` (held while settling; wakes a task paused on its card, with a `progress` report). Dropping a paused task clears the gate. Cancel while settling: idle.
- `agent_hub/tasks.py`: `TaskRecord.waiting_on`; `_settle` (paused if it waits on its card or on open `tell_parent` children); a `progress` report on a waiting record wakes it (active; clears its card question); `start` and `_answer` refuse an agent paused waiting, so it isn't dropped; `_to_parent` tells the coordinator when its parent task is paused waiting (answer 5).
- **Differences from the plan:** the Hub doesn't finish the task on `turn_end`; it answers `done` and the agent sends its own `done` (no double end around the Chrome check). Waiting on a child doesn't set the **!** (nothing for you to answer); a card still does, as before.
- Tests: `agent_hub/tests/test_pause_waiting.py` (new: done with nothing open, paused on a child then woken, `tell_parent=False` doesn't count, the coordinator woken, a card pauses until answered, a `NEED` untouched); `test_end_report_race.py` updated (`turn_end` then `done`) plus a new one (a message while settling carries the task on). Full suite: **838 passed**; ruff clean.
- Docs edited: [agents](../architecture/agents.md) (kinds, state diagram, "Paused by the Hub"), [runtime](../agents/runtime.md) (mode diagram, bullet), [Agents API](../api/agents.md) (`ReportTask`, `turn_end`), [API index](../api/README.md).

**Finished (second session):** docs rebuilt; architecture check: the handler and the Hub import contracts only, nothing module-specific in the core; one fix, `TURN_DONE` / `TURN_PAUSED` now imported from `assistant.contracts` (not `contracts.agents`) in `tasks.py` and `session_agent.py`. Left: the app restart, after you say yes. Not committed.

## Rule 2: build plan (done)

As proposed in [rule 2](#rule-2-the-hub-pauses-a-worker-thats-only-waiting), with answers 5 and 6:

1. `contracts/agents.py`: `ReportKind.TURN_END`.
2. `infra/session_agent.py` `_finish_turn`: a turn with no last-line tag, and a turn ending with `self._gate.waiting`, send `turn_end` instead of `done` / only logging; the report worker reads the Hub's `Result` (`"paused"` → mode `PAUSED`, keep the task and session; `"done"` → `_end_task` as today, after the Chrome tab close). Stays `working` until the answer.
3. `agent_hub/tasks.py`: `TaskBoard._settle(record)` for `turn_end`: an open `permission` question, or open child tasks with `tell_parent` → `idle`, held out of focus, `TaskUpdated` "waiting on …", answer `paused`; else `_finish(DONE, hold=True)`, answer `done`.
4. Answer 5: `_to_parent` also messages the coordinator when its task is paused waiting on that child (into the paused task through `Delivery`).
5. Tests in `agent_hub/tests` and `tests/test_session_agent*` as in the table below; docs: [agents](../architecture/agents.md) task states, [runtime](../agents/runtime.md) mode diagram, [Agents API](../api/agents.md) `ReportKind`; rebuild.
6. Then ask the user before the app restart (rule 1's core change already needs it). Don't commit.

## Your decisions (as asked)

1. **Grant cards (#7) in Auto.** `permissions.grant / request / revoke` save a grant that outlives Auto. An Auto session already has every tool, so it doesn't need these to work. **Recommended: keep the card.** A lasting grant is a settings change, which is on the very-risky list. Or skip it in Auto too.
2. **Access-list cards (#6).** Skipping them needs the caller carried on `ActivateModule` (a contract change), and it would save another agent's whole list for good. **Recommended: leave them as they are.** They show once per list change.
3. **Helper launch (#4).** It was decided that a launch always asks, even in Auto. **Recommended: keep it**, since a launch starts a new agent that spends tokens. Or let Auto launch at once.
4. **Where A lives.** In the core handler (recommended: one place for every handler card, now and later; needs an app restart) or only in the Hub's `MessageGate` (a `RELOAD: agent_hub`, no restart, but it covers messages only). If you keep 1 and 2 as recommended, both cover the same cards today. They differ only for cards added later.

## Rule 2: the Hub pauses a worker that's only waiting

**What you asked:** when a worker's task is only waiting on you or on another agent, the Hub pauses it in code, so nobody has to remember to send a pause (`hub.send` with `pause`).

### What happens today

A task has two states in the Hub, `active` and `idle` ([two states](../architecture/agents.md)). Only `active` tasks count against `max_extra_agents`, only an idle agent takes a message or a new task, and an open task blocks the Hub's reload. Three kinds of waiting, checked in the code:

| Waiting on | Today | Paused? |
|------------|-------|---------|
| **You, with a `NEED:`** (and `NEED: Risky:`) | The agent drops the task and is free; the record is `idle` holding the question (`TaskBoard.report`, `tasks.py:343`) | **Already, in code.** Nothing to add |
| **You, with a held card** (a tool request in Manual, a `RELOAD:` / helper-launch approval), the turn already over | The agent stays in its `working` mode with `PermissionGate.waiting` set (`session_agent.py:584`), so it reads **active**; the record stays `active` (`tasks.py:348`). It holds a slot, messages to it wait in `Delivery`, and the Hub can't reload | **No.** This is the gap |
| **A helper's result** (it started a child task with `hub.start`), the turn over | A turn ending with no last-line tag reports `done` (`session_agent.py:593`): the task ends. The child's end then arrives as a **new** task (`Delivery`), in a fresh session, so the parent's context is lost. The coordinator's children only reach its feed (`_to_parent`, `tasks.py:440`) | **No.** It's ended, not paused |

### The proposal: one report at a turn's end, one check in the Hub

- **The agent reports a fact, the Hub decides.** When a turn ends with no last-line tag, `SessionTaskAgent._finish_turn` sends a new report kind, **`turn_end`** (with the turn's text), instead of `done`. When the turn ends while its gate holds a card, it sends `turn_end` too, instead of only logging "waiting for the user's answer".
- **The check lives in the Hub: `TaskBoard._settle(record)`** (`agent_hub/tasks.py`), called from `report()` for `turn_end`. It answers in the report's `Result`:
  - the record has an open `permission` question, **or** it has open child tasks (records whose `parent_task_id` is this task) → **paused**: `state = idle`, held behind the agent's **!** if it's out of focus, a `TaskUpdated` with "waiting on …" naming what it waits on;
  - otherwise → **done**, exactly as today (`_finish(..., hold=True)`).
- **The agent follows the answer.** `paused`: its mode goes to `PAUSED` (idle, still holding the task, the same session kept). `done`: it ends the task as today. Until the answer comes, it stays in `working`, so nothing slips in between.
- **What wakes it:** the card's answer (`TaskBoard.answer` already sets it active), a child's end (`tell_parent` → `DeliverMessage`, which goes into the agent's open task, now the paused one, with `resume`), or your message. Each child's end wakes it; if others are still open, its next turn ends, `_settle` pauses it again.

**It should catch:**

- A turn that ended with a card still open (Manual tool requests, `RELOAD:` / `ADD_MODULE:` approvals, a helper launch's approval).
- A turn that ended with no tag while a child task it started is still open (active, paused, or holding its own question).

**It shouldn't catch:**

- **An agent still in a turn**: tools running, a long command, its own subagents, a card raised mid-turn that the turn is still running past. Only a turn's end is looked at; code can't pause a turn from outside without interrupting it.
- **The in-between modes**: `interrupting`, `replying` with resume, `compacting`, `closing_tabs`. They end in their own report.
- **A `NEED:`**: it's already dropped and idle. `_settle` leaves it alone.
- **A turn that ended with no tag and no open children**: that's done, as today.
- **Messages it sent that wait elsewhere**: a message on the user's card (`MessageGate`) or one waiting in `Delivery` for a busy agent. They're another agent's mail, not a child task, so the sender ends `done` as today.
- **A child started with `tell_parent=False`** (a module reports its end itself, e.g. cv to job_search): no message would wake the parent. See question 6.

**What doesn't change:** `hub.send` with `pause` still works for you. The two task states stay two: "paused" is `idle` without a question, as today (`TaskRecord.paused`).

### Your decisions for rule 2

5. **The coordinator's helpers.** The Main Assistant's child tasks only reach its feed, never as a message, so a paused coordinator wouldn't be woken by them. **Recommended: wake it too**: when the coordinator's task is paused waiting on a child, the child's end goes to it as a message (into the paused task). Or leave the coordinator out of rule 2 (it ends `done` as today).
6. **Children started with `tell_parent=False`.** **Recommended: they don't count** as "waiting on a helper", so the parent ends `done` and the module's own notice reaches it as today. Or count them, and wake the parent on the module's `AgentNotice` too.

## What the build touches

| File | Change |
|------|--------|
| `src/assistant/core/permissions/handler.py` | The Auto check in `_open`, reading the mode with `ListAgents`; a message card in Auto is Allow once |
| `src/assistant/infra/permission_gate.py`, `infra/session_agent.py` | The reload/add Auto rule moves into `PermissionGate.ask`; `request_approval` according to question 3. Rule 2: `_finish_turn` sends `turn_end` (no tag, or a card still open) and follows the Hub's answer (`PAUSED` or the task's end) |
| `src/assistant/contracts/agents.py` | Rule 2: `ReportKind.TURN_END` |
| `src/assistant/modules/agent_hub/tasks.py` (and `module.py` for question 5) | Rule 2: `TaskBoard._settle` and the `turn_end` case in `report()`; waking a paused coordinator per question 5 |
| Tests | Handler: an Auto caller gets no `PermissionRequested` and nothing is saved; a Manual or unknown caller, or a failed `ListAgents`, still gets the card. Gate: `ask` in Auto runs at once. The `git push` tests stay as they are. Rule 2: a turn end with an open card or an open child → `idle`, held out of focus, the slot free, a message goes in; a child's end wakes it; no children → `done`; a `NEED` and a mid-turn agent untouched |
| Docs | [Permissions](../architecture/permissions.md) (messages between agents, permission mode), [Agents](../architecture/agents.md) (task states, pausing), [agent runtime](../agents/runtime.md) (the mode diagram), the [Agents API](../api/agents.md) (`ReportKind`), then rebuild |

**Loading it:** the handler is core, the gate and `SessionTaskAgent` are infra, and `ReportKind` is a contract, so it needs **an app restart**. No module toggles. The paused smoke test isn't touched.
