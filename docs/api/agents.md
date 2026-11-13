# Agents

Task agents and the Agent Hub's commands and events. All items: `from assistant.contracts import ...`. Back to the [API index](README.md). How it works: [task agents](../architecture/agents.md#task-agents).

## `ITaskAgent`

**Reusable** · Used by: `main_assistant`, `task_agents`, `job_search` provide (through `SessionTaskAgent`); `agent_hub` calls; `task_agents` calls `request_approval` on the caller of `agents.launch`

`class ITaskAgent(Contract)`

A contract for agents that take tasks: the Main Assistant, the helpers and module agents such as `job_search_agent`. Any number of modules may provide it (`multiple = True`). Declare it in `manifest.provides` and provide a composed object in `init`: `ctx.provide(ITaskAgent, self._agent)`. Only the Agent Hub calls these methods.

In v1 an agent runs one task at a time.

### `ITaskAgent.info`

`info(self) -> AgentInfo`

Abstract. Who this agent is and whether it's active. Called on every lookup, never cached.

### `ITaskAgent.assign`

`async assign(self, task: Task) -> Result`

Abstract. Accept or refuse a task. **Returns at once and never waits for the work**; the agent reports back with [`ReportTask`](#reporttask). Starts the agent's process first if it isn't running. An idle agent takes it whatever questions it has open; a task it was stopped on (paused) is dropped for it. A task with `question_key` set is the answer to a question the agent asked in that task id: it carries on in its live session if that still has the question, else in a fresh one with its module's notes for the key ([`SessionTaskAgent.set_context`](infra.md#sessiontaskagent)).

**Returns**
| Status | When |
|--------|------|
| `ok` | Accepted; the work has started |
| `not_available` | Active (in a turn) |
| `failed` | The agent couldn't start (e.g. its process didn't launch) |

### `ITaskAgent.message`

`async message(self, task_id: str, text: str, resume: bool = True) -> Result`

Abstract. Like typing into Claude Code while it works. If the task is active, interrupt the current turn and send `text`; the answer comes back as `ReportTask(kind="reply")`. Then, if `resume` is true, continue the task; if false, stay stopped (the task is `idle`, still held). If the task is stopped, `text` is simply the next message ("carry on"). An answer to a question doesn't come here: the agent dropped that task, and the Hub assigns it again ([`assign`](#itaskagentassign)). Returns once the message is delivered, not when it's answered.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `task_id` | `str` | yes | The task |
| `text` | `str` | yes | A question, extra instruction, or your answer |
| `resume` | `bool` | no | Continue the task after replying. False means stop or pause |

**Returns**
| Status | When |
|--------|------|
| `ok` | Delivered |
| `invalid_arguments` | Not this agent's current task |
| `not_available` | It has just asked a question in this task (the report is on its way to the Hub) |
| `failed` | The session couldn't be interrupted or written to |

### `ITaskAgent.cancel`

`async cancel(self, task_id: str) -> Result`

Abstract. Like pressing Esc: interrupt the turn and drop the task. The session and its memory stay for the next task. If the interrupt doesn't stop it, the agent kills its process instead.

**Returns:** `ok` once stopped, `invalid_arguments` if it's not this agent's current task.

### `ITaskAgent.answer_permission`

`async answer_permission(self, task_id: str, allow: bool) -> Result`

Abstract. Answer the task's open permission request (the one its last `permission` report announced), once. Returns as soon as the answer is written; the tool then runs (or doesn't) in the same turn.

**Returns:** `ok`; `invalid_arguments` if it's not this agent's current task or no request is open (already answered, timed out, or ended by an interrupt); `failed` if the session couldn't be written to.

### `ITaskAgent.set_permission_mode`

`async set_permission_mode(self, mode: PermissionMode) -> Result`

Not abstract. Switch what the agent may do ([`PermissionMode`](#permissionmode)) and publish [`PermissionModeChanged`](#permissionmodechanged). The default refuses with `not_available`, for agents without modes. [`SessionTaskAgent`](infra.md#sessiontaskagent) implements it: every switch applies at once (`now`), to the running task too; mid-task to Auto, it answers permission requests itself (all but `git push`) and interrupts a running turn to give it the Auto rules ([live switch](../agents/runtime.md#permission-mode)). Its `Result.value` is `True` when it answered an open permission request, so the Hub closes that card. Called by the Hub for [`SetPermissionMode`](#setpermissionmode).

**Returns:** `ok`, or `not_available` (the default).

### `ITaskAgent.note`

`note(self, text: str) -> None`

Not abstract. A background line for the agent's next turn: another agent's `STATUS:` milestone, the end of another agent's task, a focus move, or a module's callback ([`AgentNotice`](#agentnotice)). Never interrupts and never starts work. The default drops it. Called by the Hub, only on the coordinator for the feed lines and on the named agent for a notice. [`SessionTaskAgent`](infra.md#sessiontaskagent) keeps the lines in a [`MilestoneFeed`](infra.md#milestonefeed) and adds them at the end of the next message it writes to its session. Built 2026-11-05.

### `ITaskAgent.request_approval`

`async request_approval(self, action: str, run: Callable[[], Awaitable[Result]]) -> Result`

Not abstract. Ask you to allow `action` on this agent's open task. It puts a `permission` report on the task, so you get the same card (the temp UI's Allow / Deny, the Talker's ALLOW / DENY) and answer it with [`AnswerPermission`](#answerpermission). In Manual it asks; in Auto (the agent's own mode) there's no card and `run()` runs at once. On Allow, `run()` is called and its outcome reaches the agent as its next message (`[App] <action>: <outcome> Continue the task...`). On Deny or no answer, nothing runs. Returns once the question is open. The default refuses with `not_available`, for agents without tasks.

[`SessionTaskAgent`](infra.md#sessiontaskagent) implements it. Called by `task_agents`' `agents.launch` on its caller; `SessionTaskAgent`'s own `RELOAD:` / `ADD_MODULE:` request uses the same path. Built 2026-11-05.

**Returns:** `ok` once the question is open; `not_available` if there is no open task, a question is already open, or the agent keeps the default.

**Example**

    class MainAssistantModule(ModuleProtocol):
        manifest = Manifest(id="main_assistant", provides=(ITaskAgent,))

        async def init(self, ctx):
            # A callable command: read on every start, so each session gets the mode of that moment.
            self._session = ClaudeSession(lambda: build_command(..., self._agent.permission_mode), cwd=..., log=ctx.log)
            self._agent = SessionTaskAgent(self._session, ctx, agent_id="main_assistant", description="...")
            ctx.provide(ITaskAgent, self._agent)

        async def start(self):
            await self._session.start()

        async def stop(self):
            await self._agent.close()
            await self._session.close()

**Defined in:** `src/assistant/contracts/agents.py`. Implemented by [`SessionTaskAgent`](infra.md#sessiontaskagent).

## `IAgentNames`

**Reusable** · Used by: `agent_hub` provides; [`ProfileAgent`](infra.md#profileagent) claims and releases (`main_assistant`, `task_agents`, `job_search`); `task_agents` checks a name at `agents.launch` · built 2026-11-05

`class IAgentNames(Contract)`

The agent ids in use, so no two agents share one. One provider: the Agent Hub. `owner` is the id of the module that runs the agent. The rules are [`check_agent_id`](infra.md#agent_names): the form, the reserved ids, and every module's id, except that a module's own agent may carry its module's id (`main_assistant`). Get it with `ctx.get_one(IAgentNames)`.

| Method | Does |
|--------|------|
| `async check(agent_id, owner) -> str \| None` | Why `owner` can't have `agent_id` now, with a free id to use; None if it can |
| `async claim(agent_id, owner) -> Result` | Take `agent_id` for `owner`. Checked and taken with no `await` between, so two claims can't both win. A repeat claim by the owner that holds it is `ok`; a different owner is still refused, and `check` still calls the name taken (so a module can't name a second agent with it) |
| `release(agent_id, owner) -> None` | Free `agent_id` if `owner` holds it |
| `taken() -> dict[str, str]` | Every claimed id and the module that holds it |

**Returns** (`claim`)
| Status | When |
|--------|------|
| `ok` | The id is now `owner`'s |
| `invalid_arguments` | `check`'s reason: a bad form, a reserved or module id, or taken. A taken id names a free one: "`flight_search` is taken by task_agents; `flight_search_2` is free" |

The claims survive a Hub reload (handed over as `claims`, and shown in its `export_state`). As a safety net, an agent that skipped the claim and shares an id with another is seen once: the Hub uses the first one everywhere (`hub.agents`, [`ListAgents`](#listagents), routing) and logs the clash once.

**Defined in:** `src/assistant/contracts/agents.py`. Provided by `agent_hub` (`AgentNames` in `src/assistant/modules/agent_hub/names.py`). Design: [agent names](../architecture/agents.md#agent-names).

## `Task`

`Task(id: str, text: str, context: str = "", question_key: str | None = None)`

A unit of work the Hub assigns. Frozen. The other data types and all commands and events below are defined in `src/assistant/contracts/agents.py` too.

| Name | Type | Description |
|------|------|-------------|
| `id` | `str` | Set by the Hub |
| `text` | `str` | What to do |
| `context` | `str` | Relevant conversation context from the Talker |
| `question_key` | `str \| None` | Set when the task answers a question the agent asked in it (the same id, active again): the question's context key (`""` for none). None for a new task |

## `AgentState`

**Reusable** · Used by: `SessionTaskAgent` sets it; `agent_hub`, `talker`, `temp_ui`, `assistant_view`, `usage`, `cv` read it · built 2026-11-10

`class AgentState(StrEnum)`: `ACTIVE` (`"active"`), `IDLE` (`"idle"`).

An agent is `active` while it's in a turn, or held in one by a permission card, and `idle` otherwise. An idle agent takes new work, whatever questions it has open: a question never keeps it busy. It replaced the old `busy` and `working` flags.

## `AgentInfo`

`AgentInfo(agent_id: str, description: str, capabilities: tuple[str, ...] = (), state: AgentState = AgentState.IDLE, permission_mode: PermissionMode = PermissionMode.MANUAL, write_folders: tuple[str, ...] = ())`

Frozen. What [`ITaskAgent.info`](#itaskagentinfo) returns.

| Name | Type | Description |
|------|------|-------------|
| `agent_id` | `str` | Unique id |
| `description` | `str` | What it does |
| `capabilities` | `tuple[str, ...]` | What kinds of tasks it takes |
| `state` | [`AgentState`](#agentstate) | `active` (in a turn) or `idle`. `info.active` (property) is `state is AgentState.ACTIVE` |
| `permission_mode` | `PermissionMode` | The mode its next session starts in; Manual at every launch |
| `write_folders` | `tuple[str, ...]` | Every folder it may write, resolved (its workspace and `write_dirs`, from [`AgentProfile.write_folders`](infra.md#agentprofile)). The Hub refuses to start a task whose agent writes a folder another active task's agent writes, or one inside it |

## `PermissionMode`

**Reusable** · Used by: `SessionTaskAgent`, `main_assistant`, `talker`, `temp_ui`

`class PermissionMode(StrEnum)`: `MANUAL` (`"manual"`), `AUTO` (`"auto"`).

What a task agent may do without asking. **Every launch starts in Manual**; the mode isn't saved.

| Mode | The Main Assistant's `claude` |
|------|-------------------------------|
| `manual` | `--permission-mode acceptEdits`, its standing rules, and an Allow / Deny card for anything else |
| `auto` | `--permission-mode bypassPermissions`: every tool, no prompts, except `git push` (`--disallowedTools`, refused even under bypass). Its prompt tells it to stop and ask (`NEED: Risky: …`) before very risky steps. That pause is its own judgment, not a guarantee |

Design: [permission mode](../agents/runtime.md#permission-mode).

## `TaskState`

`class TaskState(StrEnum)`: `ACTIVE`, `IDLE`, `DONE`, `FAILED`, `CANCELLED`. Values are the lowercase names. `ACTIVE`: its agent is in a turn on it (a permission card mid-turn keeps it active). `IDLE`: stopped after a reply (`hub.send` with pause; its agent still holds it), or holding the question its agent asked (a `need`; the agent dropped it and is free, and the answer makes it active again). The last three are final: `state.is_final`. Transitions: [task state](../architecture/agents.md#task-state). Changed 2026-11-10: `running`, `paused` and `waiting_for_input` are gone.

## `TaskInfo`

`TaskInfo(id: str, agent_id: str, text: str, state: TaskState, recent: tuple[str, ...] = (), activity: tuple[str, ...] = (), question: str | None = None, result: str | None = None, parent_task_id: str | None = None, held: bool = False, reply: str | None = None, question_kind: QuestionKind = QuestionKind.NONE, question_key: str = "")`

Frozen. A task as the Hub knows it.

| Name | Type | Description |
|------|------|-------------|
| `id` | `str` | Task id |
| `agent_id` | `str` | Who's doing it |
| `text` | `str` | What was asked |
| `state` | `TaskState` | Authoritative state |
| `recent` | `tuple[str, ...]` | Latest reports, newest last |
| `activity` | `tuple[str, ...]` | The agent's last 15 [`AgentActivity`](#agentactivity) lines for this task (its text, and tool calls with their file or command), newest last. What lets the Talker answer "what is it doing?" without interrupting it |
| `question` | `str \| None` | The open question or permission request: the agent's own text, with no prefix added |
| `question_kind` | [`QuestionKind`](#questionkind) | What `question` is: `permission`, `risky`, `need`, or `none` (`""`, the default). Set by the Hub; readers check it instead of parsing the text |
| `question_key` | `str` | The question's context key, from its agent's report ([`ReportTask.key`](#reporttask); cv: the job's folder), so a late answer finds its context again. `""` for none |
| `result` | `str \| None` | Final text when `DONE` or `FAILED` |
| `parent_task_id` | `str \| None` | The task that started this one (an agent's child task, through `hub.start`) |
| `held` | `bool` | Its `question`, its `reply` or its end (`result`) waits behind its agent's **!** until you focus that agent ([`SetFocus`](#setfocus)). Each is stored once, here; held is only a flag |
| `reply` | `str \| None` | The agent's latest reply, kept only while held (a `reply` from an agent out of focus) |

`task.question_line`: the question for a person or an agent to read, `Permission: <text>` for a permission request, else the text (`""` with none). The Talker's task lines and the restart note use it.

## `QuestionKind`

**Reusable** · Used by: `agent_hub` sets it (`QuestionKind.of`); `talker`, `temp_ui` read it

`class QuestionKind(StrEnum)`: `NONE = ""`, `NEED = "need"`, `RISKY = "risky"`, `PERMISSION = "permission"`, `WAIT = "wait"`. `WAIT` (2026-11-13): the task ended waiting, on child tasks or on an approval's outcome; the question is what it waits on ("waiting on child task 3fa2 (cv)"), set by the Hub (`TaskBoard._settle`), never by `of`. A task that ended waiting on its card keeps `PERMISSION`, so the card shows as before. What a task's open question is, on [`TaskInfo`](#taskinfo) and [`TaskUpdated`](#taskupdated), so no reader parses a text prefix ([principle 19](../architecture/principles.md)). `QuestionKind.of(kind, text)` is the one place the text is read: a `permission` report is `PERMISSION`; a `need` starting with `RISKY_PREFIX` (`"Risky:"`, also in the contracts) is `RISKY`; any other `need` is `NEED`; anything else `NONE`.

## `ListAgents`

`ListAgents()` (command)

Every registered agent, whether it's active or idle, and its permission mode. Handled by the Agent Hub, which reads [`ITaskAgent.info`](#itaskagentinfo) from each provider. For UIs and the Talker.

**Returns:** `Result.ok(list[AgentInfo])`.

**Example**

    result = await ctx.send(ListAgents())
    active = [a.agent_id for a in result.value if a.active]

## `StartTask`

`StartTask(text: str, context: str = "", agent_id: str | None = None, parent_task_id: str | None = None, tell_parent: bool = True)` (command)

Give work to a free (idle) agent, or to `agent_id` only. Handled by the Agent Hub. `parent_task_id` is set by the Hub's `hub.start` item for an agent's child task, or by a module that starts an agent for a caller (`cv.task`). `context` goes to the agent doing the task. `tell_parent=False` (2026-11-12): the Hub sends the parent's agent no message when this task ends, because the module that started it reports the end itself as a named event (`cv.task`: `cv.job_finished`). The parent link stays, so the parent's agent may still `hub.send` to the task. Several agents may run at once, one task each: the coordinator plus at most `[modules.agent_hub] max_extra_agents` (3) other agents with an active task; past that, `not_available`. Only active tasks count for the cap and the folder check: a task holding a question ties up no agent. A free pick (no `agent_id`) skips the agents in `[modules.agent_hub] named_only` (and `start_only_by`).

**Returns:** `Result.ok(task_id)`; `not_available` if no agent is free, the cap is reached, or the agent would write a folder another active task's agent writes ([`AgentInfo.write_folders`](#agentinfo)); `invalid_arguments` for an unknown `agent_id`.

## `DeliverMessage`

**Reusable** · Used by: `cv` sends (the result at Submit); `agent_hub` handles (`Delivery`, `delivery.py`) and its message gate delivers through it · built 2026-11-10

`DeliverMessage(agent_id: str, text: str, sender: str)` (command)

A message for an agent from a module (or the Hub's own message gate), delivered **without ever interrupting a turn**. Handled by the Agent Hub. The text reaches the agent as `[Message from <sender>] <text>`: into its open task if it has one (which also answers a question it waits on), else as a new task. An agent in a turn gets it when the turn ends; one that isn't running gets it when it starts. Messages to one agent keep their order. What waits is handed over on a Hub reload and lost on an app restart. Unlike an [`AgentNotice`](#agentnotice), it wakes the agent.

**Returns:** `Result.ok(how)`, `how` one of `"message <task id>"` (into its open task), `"task <task id>"` (a new task) or `"pending"` (delivered later); `failed` if the agent refused the task for good.

## `GetTaskStatus`

`GetTaskStatus(task_id: str | None = None)` (command)

Task status from the Hub, without disturbing the agent.

**Returns:** `Result.ok(list[TaskInfo])`: that task, or with no `task_id`, the last five finished ones followed by the unfinished ones. `invalid_arguments` for an unknown id.

## `SendToTask`

`SendToTask(task_id: str, text: str, resume: bool = True)` (command)

A question, extra instruction, or your answer for a task. The Hub calls [`ITaskAgent.message`](#itaskagentmessage) and updates the state: `resume=False` makes it `IDLE`, otherwise `ACTIVE`.

Into a task that holds its agent's question, the text is the answer: the Hub assigns the same task id to the agent again ([`ITaskAgent.assign`](#itaskagentassign) with `question_key`), with the text `Answer to your question in task <id> ("<question>"): <text>`, and the task is `ACTIVE` again. If the agent is in a turn on other work (or not running), the answer waits and goes in when it's free: `ok("pending")` (the Hub's `Delivery.later`).

**Returns:** the agent's `Result`, `ok("pending")` for an answer that waits, or `invalid_arguments` for an unknown or finished task.

## `CancelTask`

`CancelTask(task_id: str)` (command)

Stop a task, like Esc. The Hub calls [`ITaskAgent.cancel`](#itaskagentcancel) and marks it `CANCELLED`. A task holding a question is cancelled without calling the agent (it dropped the task already).

**Returns:** the agent's `Result`, or `invalid_arguments` for an unknown or finished task.

## `AnswerPermission`

`AnswerPermission(task_id: str, allow: bool)` (command)

Allow or deny the task's open permission request, once. Sent by a UI (the temp UI's buttons); the Talker (`<<ALLOW>>` / `<<DENY>>`) uses the Hub's `hub.answer` item, which does the same. The Hub calls [`ITaskAgent.answer_permission`](#itaskagentanswer_permission), keeps the task `ACTIVE`, and publishes `TaskUpdated` with `kind=None` and `text` "permission allowed" or "permission denied".

**Returns:** the agent's `Result`, or `invalid_arguments` for an unknown or finished task.

## `SetPermissionMode`

**Reusable** · Used by: `temp_ui` (the Manual | Auto button) sends; `agent_hub` handles (and its `hub.mode` item, for the Talker's `<<MODE: manual>>`, Manual only)

`SetPermissionMode(agent_id: str, mode: PermissionMode)` (command)

Switch a task agent between Manual and Auto. Handled by the Agent Hub, which calls [`ITaskAgent.set_permission_mode`](#itaskagentset_permission_mode); later the permissions handler takes it over, with no change for the senders. **Only you switch to Auto**, with the button; the Talker only ever asks for Manual (`hub.mode` refuses Auto), and the Main Assistant has no route to it.

**Returns:** the agent's `Result`; `invalid_arguments` for an unknown agent.

## `ReportTask`

`ReportTask(task_id: str, kind: ReportKind, text: str, key: str = "", card_open: bool = False)` (command)

Sent by an agent to the Hub. A command rather than an event so the Hub's state never misses it. `key`: with a `need` or a `turn_end`, the task's context key (the agent's module decides it, through [`SessionTaskAgent.set_context`](infra.md#sessiontaskagent); `""` for none). The Hub keeps it as [`TaskInfo.question_key`](#taskinfo). `card_open`: with a `turn_end`, the agent's card is still open; without it, a `permission` question the Hub still lists is closed (a tool request that timed out).

| `kind` | Means | State becomes |
|--------|-------|---------------|
| `progress` | What it's doing. For a task that ended waiting, new input for it (an approval's outcome): the Hub gives the task back with it | unchanged (`ACTIVE` once given back) |
| `reply` | Answer to a `message` | unchanged |
| `need` | A question for you; the turn has ended, and the agent dropped the task and is free. In Auto, a `need` starting with `Risky:` is a pause before a risky step (`question_kind` `risky`, else `need`). The answer gives the same task back ([`SendToTask`](#sendtotask)) | `IDLE` (with its question) |
| `permission` | Wants to use a tool its rules don't allow, e.g. `Write C:\…\SKILL.md`; the turn waits for [`AnswerPermission`](#answerpermission) | `ACTIVE` (`question_kind` `permission`) |
| `milestone` | A `STATUS: <one line>` line in its text ([`status_lines`](infra.md#agent_tags)). From an agent that isn't the coordinator, the Hub passes `[<agent>] <line>` to the coordinator's [`note`](#itaskagentnote) | unchanged |
| `turn_end` | A turn ended with no last-line tag, or with its card open. The Hub decides: waiting on its card or on open child tasks (`tell_parent`) → the task **ends waiting**: the agent drops it and is free, and the record keeps the note (what it waits on, `key`) until the card's outcome, a child's end or a message gives it back; else nothing changes and the agent sends its own `done` | `IDLE` (with its note: `question_kind` `wait`, or `permission` for its card) or unchanged |
| `done` | Finished; `text` is the result | `DONE` |
| `failed` | Gave up; `text` says why | `FAILED` |

`ReportKind` is a `StrEnum` with these values.

**Returns:** `ok`, or `invalid_arguments` for an unknown or finished task. For a `turn_end`, the value is `TURN_WAIT` (`"wait"`: the agent drops the task like a `need`, its live session and any open approval kept for it) or `TURN_DONE` (`"done"`: it ends the task as usual); both are in `assistant.contracts`.

## `TaskUpdated`

`TaskUpdated(task_id: str, state: TaskState, kind: ReportKind | None = None, text: str = "", agent_id: str = "", parent_task_id: str | None = None, held: bool = False, question_kind: QuestionKind = QuestionKind.NONE)` (event)

Published by the Hub on every report and state change; the Talker listens. `question_kind`: what the task's open question is now ([`QuestionKind`](#questionkind)), so the Talker and the temp UI tell a permission request or a risky step from its kind, not its text. `kind` is `None` for changes the Hub made itself (start, with `text` "started"; `SendToTask`; `AnswerPermission`, with "permission allowed" / "permission denied"; cancel). `held`: the task's question, reply or end waits behind its agent's **!** (a `need`, `permission`, `reply`, `done` or `failed` while another agent has the focus). May be dropped; `GetTaskStatus` is authoritative.

## The focus

The **focus** is the agent you're talking to. The Hub keeps it: the coordinator (`[modules.agent_hub] coordinator`, `main_assistant` by default) at launch, kept across a Hub reload, and back to the coordinator when the focused agent stops running. A `need`, `permission`, `reply`, `done` or `failed` from an agent out of focus is held ([`TaskInfo.held`](#taskinfo)) until you focus that agent, so nothing lands in another tab's chat. Design: [Working together](../architecture/agents.md#working-together). Built 2026-11-05.

### `SetFocus`

`SetFocus(agent_id: str = "")` (command)

Move the focus to `agent_id`; empty means the coordinator. Handled by the Agent Hub; sent by a UI (a tab click, later) or by the Hub's own `hub.focus` item (the Talker, after you said so). Releases that agent's held questions and publishes [`FocusChanged`](#focuschanged) when the focus moved or something was released; a move also feeds `[focus] the user is now talking to <agent>` to the coordinator.

**Returns:** `Result.ok(agent_id)` (the focused agent), `invalid_arguments` for an unknown agent.

### `FocusChanged`

`FocusChanged(agent_id: str, previous: str = "", released: tuple[TaskInfo, ...] = ())` (event)

The focus moved to `agent_id`. `released`: that agent's tasks whose question, permission request, reply or end was held until now (finished tasks too), so the Talker says it in that tab and the UI shows its card.

Also published when the focused agent goes away (closed with ×, its module turned off or failed): the Hub moves the focus to the coordinator, with `previous` the gone agent, so no UI stays on a dead tab.

### `FocusSuggested`

`FocusSuggested(agent_id: str, reason: str = "", by: str = "")` (event)

The coordinator (`by`) suggests you talk to `agent_id` directly. Published by the Hub's `hub.suggest_focus`. The Talker asks you; the focus moves only if you say yes (then `hub.focus`).

### `AgentNotice`

`AgentNotice(agent_id: str, text: str, source: str = "")` (event)

A module's callback for an agent, e.g. a slow menu item's result: the item returns at once and, when the work ends, publishes this with `agent_id` = the item's caller. The Hub passes `[<source>] <text>` to that agent's [`note`](#itaskagentnote), for its next turn. Dropped (and logged) if the agent isn't running.

## The Hub's menu

**Reusable** · Used by: `talker` and `main_assistant` through the [module door](tools.md#imoduledoor) · built 2026-11-05

The `agent_hub` module's [`Menu`](modules.md#menu), id prefix `hub.`. Every item knows its caller ([`InvokeTool.caller`](tools.md#invoketool)), which a session can't fake.

| Item | Who may use it | Does |
|------|----------------|------|
| `hub.agents` | anyone | The task agents: `agent_id`, `description`, `state` (`active` or `idle`; an idle one takes work, whatever it asked), `permission_mode`, `focused`, `held` (a question, reply or finished task waiting behind its **!**), `task_id` (its open task, else its newest task holding a question) |
| `hub.status(task_id?)` | anyone | [`GetTaskStatus`](#gettaskstatus), without disturbing the agent |
| `hub.start(text, agent_id?, context?)` | anyone | [`StartTask`](#starttask); the caller's open task becomes the new task's parent. Its end (`done` or `failed`) comes back to the parent's agent as a message: `[Message from agent_hub] Your child task <id> on <agent> ended <state>: <result>` (cut at 4000 characters; the coordinator: only its feed line) |
| `hub.send(text, task_id?, agent_id?, pause?)` | the Talker any task; others: `task_id` only for their child tasks, `agent_id` for any agent | [`SendToTask`](#sendtotask). The Talker with no `task_id`: to `agent_id`'s open task (its tab's agent; default the focused agent), or a new task on it. Another agent with `agent_id` (not itself): into that agent's open task straight away if it's the caller's child (interrupts, as before); otherwise through the message gate: a card the first time ("X wants to message Y": Allow once · Always allow · Deny), then [`DeliverMessage`](#delivermessage) (never into a turn). `ok({"agent_id", "task_id"})`; plus `"delivered": "when its agent is free"` for an answer that waits; `ok({"agent_id", "how"})` through the gate, `how` being `"waiting on the user's card"` or the delivery's value. Design: [permissions](../architecture/permissions.md#messages-between-agents) |
| `hub.cancel(task_id)` | the Talker any task; others only their child tasks | [`CancelTask`](#canceltask) |
| `hub.focus(agent_id)` | the Talker only (`callers=("talker",)`) | [`SetFocus`](#setfocus), after you said so; empty is back to the coordinator |
| `hub.suggest_focus(agent_id, reason?)` | the coordinator only | Publishes [`FocusSuggested`](#focussuggested) |
| `hub.answer(task_id, allow)` | the Talker only | [`AnswerPermission`](#answerpermission), after you said yes or no to a task's permission card |
| `hub.mode(agent_id, mode)` | the Talker only | [`SetPermissionMode`](#setpermissionmode) to Manual; `auto` is refused (`not_available`): only you switch to Auto, with the button |

Refused callers get `not_available`. The UI's own buttons still send `AnswerPermission` and `SetPermissionMode` as commands. Code: `AgentHubModule` (`module.py`) wires a `TaskBoard` (`tasks.py`), a `Focus` (`focus.py`), `AgentNames` (`names.py`), a `Delivery` (`delivery.py`) and a `MessageGate` (`gate.py`); tests in `tests/test_agent_hub_parts.py` and `agent_hub/tests/`.

## `AgentStateChanged`

`AgentStateChanged(agent_id: str, state: AgentState = AgentState.IDLE, change: Literal["state", "opened", "closed"] = "state")` (event)

Published by the agent module whenever its [`state`](#agentstate) changes (active or idle), so a UI can show it live without polling. `change` says what happened: `"state"` (the default), or `"opened"` / `"closed"` for an agent that isn't a module of its own (a helper inside `task_agents`), so UIs add or drop its tab (built 2026-11-08; it used to be a plain state event with both flags off). May be dropped; [`ListAgents`](#listagents) is authoritative.

## `PermissionModeChanged`

**Reusable** · Used by: `SessionTaskAgent` publishes; `talker`, `temp_ui` subscribe

`PermissionModeChanged(agent_id: str, mode: PermissionMode, applies: Literal["now", "next_task"] = "now")` (event)

A task agent's mode was set. `applies` is `now`, even mid-task (built 2026-11-08); `next_task` only when a live switch to Manual failed. The temp UI shows it (amber header in Auto) and logs it in both panes; the Talker hears it once, as a `[Mode] worker: …` line before your next message. May be dropped; [`ListAgents`](#listagents) is authoritative.

## `AgentActivity`

**Reusable** · Used by: `SessionTaskAgent` publishes; `agent_hub`, `assistant_view`, `temp_ui`, `html_viewer` subscribe

`AgentActivity(agent_id: str, task_id: str | None, text: str)` (event)

An agent's raw activity (its text and tool calls), published by the agent module itself for viewers such as terminal 2. High-volume and view-only. The Hub keeps each task's latest lines in [`TaskInfo.activity`](#taskinfo).

## `SessionUsage`

**Reusable** · Used by: `SessionTaskAgent`, `talker` publish; `usage`, `temp_ui` subscribe

`SessionUsage(agent_id: str, context_tokens: int, input_tokens: int = 0, cache_write_tokens: int = 0, cache_read_tokens: int = 0, output_tokens: int = 0, session: str = "", parent: str = "", kind: "claude" | "subagent" | "tool" = "claude")` (event)

One agent's usage, in tokens only (no money figure): "talker" (the Main Assistant's Talker), `talker:<agent>` (a helper tab's Talker), a task agent's id, a sub-agent's (`<parent>/<type> #<agentId>`) or a wrapped tool's. `parent`: who started it ("" for none); `kind`: `claude` (an agent's own session), `subagent` or `tool`. The [`usage`](../../src/assistant/modules/usage/docs/README.md) module adds them up into one tally since launch, sub-agents nested under their parent. Built with [`session_usage`](infra.md#session_usage). Published by [`SessionTaskAgent`](infra.md#sessiontaskagent) on every call that changes it (live while the worker works), and by the Talker after each turn. View-only.

| Name | Description |
|------|-------------|
| `context_tokens` | What each call sends now: the latest call's input, cached or not. Every further call resends that much, so it shows when a reset is worth it. 0 when no session runs; a fresh session starts small |
| `input_tokens`, `cache_write_tokens`, `cache_read_tokens`, `output_tokens` | Every call since the app started, across fresh sessions and resets |
| `used_tokens` | (property) Their sum |
| `session` | The sender's session id, new for each fresh session (`ClaudeSession.id`); when it changes, the ledger keeps the old totals and adds the new ones. "" if unknown |

The Talker hears the worker's, adds its own, and puts both before each of your messages as a `[Usage]` line; it also warns you once when either context passes `context_warning`. The temp UI keeps every agent's by id and shows the selected tab's worker and Talker in its header.

## `ResetRequested`

`ResetRequested(agent_id: str)` (event)

Asks the session behind `agent_id` ("talker" or a task agent's id) to start fresh. Sent by the temp UI's Reset buttons and the Talker's `<<RESET: talker | worker>>` tag. The Talker restarts its session and tells the new one its last few exchanges. A task agent ([`SessionTaskAgent.reset`](infra.md#sessiontaskagent)) closes its session at once when idle; with a task, it asks the agent to write a handoff note, and the task carries on in a fresh session.
