# Agents and tasks: only two states, active and idle

> **Status: proposed (2026-11-09), taken into [agent-talk-and-questions](agent-talk-and-questions.md) step 3.** That note changes one thing: a question becomes its own record and stays answerable, instead of a new task ending it as "left unanswered".

**Asked:** "I only want two states: active and idle. Waiting is screwing a lot of stuff up."

**Why:** when an agent asks you something (`NEED:`), its turn has ended, but the task is marked `waiting_for_input` and the agent stays `busy`. So it refuses new work ("busy"), the restart refuses to go ahead, questions sit behind a tab's **!** after you've moved on, and the Talker, the temp UI and the restart note each read "waiting" their own way.

## What "waiting" touches today

| Where | What it does with "waiting" |
|-------|-----------------------------|
| `TaskState` (`contracts/agents.py`) | `running`, `paused`, `waiting_for_input`, plus the ends `done` / `failed` / `cancelled` |
| `AgentInfo` | two flags: `busy` (has an open task, which includes waiting) and `working` (in a turn) |
| Hub `tasks.py` `report` | a `need` or `permission` report sets `waiting_for_input`, and `held` if the agent isn't the focus |
| Hub `answer`, `send`, `set_mode` | move the task back to `running` (or to `paused`) |
| Held questions (`tasks.holds`, `focus.py`) | the **!** on a tab; `SetFocus` releases them as `FocusChanged.released` |
| `QuestionKind` | `need`, `risky`, `permission`: what the open question is. This stays; it's data, not a state |
| `SessionTaskAgent` (`infra/session_agent.py`) | its own `_Mode`: `idle`, `working`, `interrupting`, `replying`, `waiting`, `paused`, `cancelling`. `waiting` and `paused` keep `busy` true; the handoff go-ahead checks `waiting` |
| Talker (`talker/module.py`) | drops a permission card when the state isn't `waiting_for_input`; skips `held` updates |
| Restart note (`talker/restart.py`) | refuses to restart while the worker's task is `waiting_for_input` (`RESTART_WAITING`) |
| Temp UI (`temp_ui/module.py`, `page.html`) | counts held task ids per agent for the **!**; holds back cards until focus |
| Docs | `docs/api/agents.md`, `docs/architecture/agents.md`, `agents-code.md`, `core.md`, `docs/modules/agent_hub.md`, `temp_ui.md`, `docs/api/infra.md`, `docs/agents/runtime.md` |

## Proposal

**Active** = in a turn (doing something). **Idle** = not in a turn. That's all an agent or a live task can be. Whether a question is open is a field on the task (`question`, `question_kind`), never a state.

- **A `NEED:` question:** the turn ends, so the task goes **idle**, with its question attached. Your answer is the next message to the same task (`hub.send`), and the task goes **active** again. The session keeps its memory, as it does today for a paused task.
- **A permission request:** the `claude` process is still mid-turn, blocked on the tool call, so the task stays **active** with a permission card open. Allow or Deny lets the turn carry on.
- **Paused** (a reply that stays stopped) is just **idle** too.
- **A new task for an idle agent:** accepted. If the agent's old task is still open (an unanswered question, say), it ends as `done` with "left unanswered: <question>", so nothing hangs. No more "busy" refusals for an agent that's doing nothing.
- **The ends** (`done`, `failed`, `cancelled`) stay as how a finished task ended; they aren't live states.
- **The restart** goes ahead when the worker is idle, question or not: the open question goes into the restart note, and the next launch asks it again.

The other way, the task stays **active** while a question is open, would keep the agent "busy" doing nothing, which is the problem you have now. So the recommendation is idle.

## What changes

**Code:**
- `contracts/agents.py`: `TaskState` becomes `active`, `idle`, `done`, `failed`, `cancelled` (no `running`, `paused`, `waiting_for_input`). `AgentInfo` gets `state: active | idle` in place of `busy` and `working`; `AgentStateChanged` the same. A contract change, so it needs an **app restart**.
- `agent_hub/tasks.py`: `need` → idle with its question; `permission` → active with its question; `answer` / `send` / `set_mode` set active or idle from the agent's report; `start` on an idle agent ends its old open task first.
- `infra/session_agent.py`: `_Mode` keeps its in-between steps (`interrupting`, `cancelling`) inside, but outside it reports only active or idle; `waiting` and `paused` merge into idle with a task; the handoff go-ahead checks `_handoff_asked` alone.
- `talker/module.py`, `talker/restart.py`, `talker/session.py`: read `question_kind` instead of the state; restart doesn't refuse.
- `temp_ui`: shows active or idle per agent; the **!** comes from "has an open question and you're not on its tab".
- `task_agents`, `job_search`, `cv` workers and the agent tests (`tests/test_agents.py`, `tests/test_worker_parts.py`, the Hub's tests): updated to the new names.

**Docs:** the pages in the table above, the API's `TaskState` / `AgentInfo` / `AgentStateChanged` entries, and the reusable index line for `QuestionKind` (unchanged in meaning). Rebuilt with `build_docs.py`.

## Open questions

1. **Does the !** on a tab stay? It's a UI marker ("this agent asked you something while you were elsewhere"), not a state. **Recommended: keep it**, computed from the open question, so you still see which tab wants you.
2. **A new task for an agent with an unanswered question:** end the old one (as above), or refuse until you answer or cancel it? **Recommended: end it**, with the question in its result, so an agent is never stuck.
3. **Relaunching:** a contract change needs an app restart, which stops the open tasks (the job agent's 6 pt draft question would need asking again). **Recommended:** build now, restart when the job agent's question is settled.
