# Agents

Task agents and the Agent Hub's commands and events. All items: `from assistant.contracts import ...`. Back to the [API index](README.md). How it works: [task agents](../architecture/agents.md#task-agents).

## `ITaskAgent`

**Reusable** · Used by: `main_assistant` provides (through `SessionTaskAgent`); `agent_hub` calls

`class ITaskAgent(Contract)`

A contract for agents that take tasks: the Main Assistant now, subagents later. Any number of modules may provide it (`multiple = True`). Declare it in `manifest.provides` and provide a composed object in `init`: `ctx.provide(ITaskAgent, self._agent)`. Only the Agent Hub calls these methods.

In v1 an agent runs one task at a time.

### `ITaskAgent.info`

`info(self) -> AgentInfo`

Abstract. Who this agent is and whether it's busy. Called on every lookup, never cached.

### `ITaskAgent.assign`

`async assign(self, task: Task) -> Result`

Abstract. Accept or refuse a task. **Returns at once and never waits for the work**; the agent reports back with [`ReportTask`](#reporttask). Starts the agent's process first if it isn't running.

**Returns**
| Status | When |
|--------|------|
| `ok` | Accepted; the work has started |
| `not_available` | Busy with another task |
| `failed` | The agent couldn't start (e.g. its process didn't launch) |

### `ITaskAgent.message`

`async message(self, task_id: str, text: str, resume: bool = True) -> Result`

Abstract. Like typing into Claude Code while it works. If the task is running, interrupt the current turn and send `text`; the answer comes back as `ReportTask(kind="reply")`. Then, if `resume` is true, continue the task; if false, stay paused. If the task is waiting for input or paused, `text` is simply the next message (your answer, or "carry on"). Returns once the message is delivered, not when it's answered.

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

Not abstract. Switch what the agent may do ([`PermissionMode`](#permissionmode)) and publish [`PermissionModeChanged`](#permissionmodechanged). The default refuses with `not_available`, for agents without modes. [`SessionTaskAgent`](infra.md#sessiontaskagent) implements it: with no task the mode applies to the next one (`now`); mid-task, Manual switches the running session at once, and Auto applies from the next task or handoff session (`next_task`). Called by the Hub for [`SetPermissionMode`](#setpermissionmode).

**Returns:** `ok`, or `not_available` (the default).

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

## `Task`

`Task(id: str, text: str, context: str = "")`

A unit of work the Hub assigns. Frozen. The other data types and all commands and events below are defined in `src/assistant/contracts/agents.py` too.

| Name | Type | Description |
|------|------|-------------|
| `id` | `str` | Set by the Hub |
| `text` | `str` | What to do |
| `context` | `str` | Relevant conversation context from the Talker |

## `AgentInfo`

`AgentInfo(agent_id: str, description: str, capabilities: tuple[str, ...] = (), busy: bool = False, working: bool = False, permission_mode: PermissionMode = PermissionMode.MANUAL)`

Frozen. What [`ITaskAgent.info`](#itaskagentinfo) returns.

| Name | Type | Description |
|------|------|-------------|
| `agent_id` | `str` | Unique id |
| `description` | `str` | What it does |
| `capabilities` | `tuple[str, ...]` | What kinds of tasks it takes |
| `busy` | `bool` | It has an unfinished task: running, paused, or waiting for input |
| `working` | `bool` | Its session is in a turn right now (generating or running tools). True from sending a message until the turn's `result` arrives. Always false when `busy` is false |
| `permission_mode` | `PermissionMode` | The mode its next session starts in; Manual at every launch |

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

`class TaskState(StrEnum)`: `RUNNING`, `PAUSED`, `WAITING_FOR_INPUT`, `DONE`, `FAILED`, `CANCELLED`. Values are the lowercase names. `PAUSED` means you stopped it on purpose; `WAITING_FOR_INPUT` means it asked you something. The last three are final: `state.is_final`. Transitions: [task state](../architecture/agents.md#task-state).

## `TaskInfo`

`TaskInfo(id: str, agent_id: str, text: str, state: TaskState, recent: tuple[str, ...] = (), activity: tuple[str, ...] = (), question: str | None = None, result: str | None = None)`

Frozen. A task as the Hub knows it.

| Name | Type | Description |
|------|------|-------------|
| `id` | `str` | Task id |
| `agent_id` | `str` | Who's doing it |
| `text` | `str` | What was asked |
| `state` | `TaskState` | Authoritative state |
| `recent` | `tuple[str, ...]` | Latest reports, newest last |
| `activity` | `tuple[str, ...]` | The agent's last 15 [`AgentActivity`](#agentactivity) lines for this task (its text, and tool calls with their file or command), newest last. What lets the Talker answer "what is it doing?" without interrupting it |
| `question` | `str \| None` | The open question while `WAITING_FOR_INPUT` |
| `result` | `str \| None` | Final text when `DONE` or `FAILED` |

## `ListAgents`

`ListAgents()` (command)

Every registered agent, whether it's busy or working, and its permission mode. Handled by the Agent Hub, which reads [`ITaskAgent.info`](#itaskagentinfo) from each provider. For UIs and the Talker.

**Returns:** `Result.ok(list[AgentInfo])`.

**Example**

    result = await ctx.send(ListAgents())
    working = [a.agent_id for a in result.value if a.working]

## `StartTask`

`StartTask(text: str, context: str = "")` (command)

Give work to a free agent. Handled by the Agent Hub.

**Returns:** `Result.ok(task_id)`, or `not_available` if no agent is free.

## `GetTaskStatus`

`GetTaskStatus(task_id: str | None = None)` (command)

Task status from the Hub, without disturbing the agent.

**Returns:** `Result.ok(list[TaskInfo])`: that task, or with no `task_id`, the last five finished ones followed by the unfinished ones. `invalid_arguments` for an unknown id.

## `SendToTask`

`SendToTask(task_id: str, text: str, resume: bool = True)` (command)

A question, extra instruction, or your answer for a task. The Hub calls [`ITaskAgent.message`](#itaskagentmessage) and updates the state: `resume=False` makes it `PAUSED`, otherwise `RUNNING`.

**Returns:** the agent's `Result`, or `invalid_arguments` for an unknown or finished task.

## `CancelTask`

`CancelTask(task_id: str)` (command)

Stop a task, like Esc. The Hub calls [`ITaskAgent.cancel`](#itaskagentcancel) and marks it `CANCELLED`.

**Returns:** the agent's `Result`, or `invalid_arguments` for an unknown or finished task.

## `AnswerPermission`

`AnswerPermission(task_id: str, allow: bool)` (command)

Allow or deny the task's open permission request, once. Sent by the Talker (`<<ALLOW>>` / `<<DENY>>`) or a UI (the temp UI's buttons). The Hub calls [`ITaskAgent.answer_permission`](#itaskagentanswer_permission), sets the task back to `RUNNING`, and publishes `TaskUpdated` with `kind=None` and `text` "permission allowed" or "permission denied".

**Returns:** the agent's `Result`, or `invalid_arguments` for an unknown or finished task.

## `SetPermissionMode`

**Reusable** · Used by: `temp_ui` (the Manual | Auto button), `talker` (`<<MODE: manual>>`, Manual only) send; `agent_hub` handles

`SetPermissionMode(agent_id: str, mode: PermissionMode)` (command)

Switch a task agent between Manual and Auto. Handled by the Agent Hub, which calls [`ITaskAgent.set_permission_mode`](#itaskagentset_permission_mode); later the permissions handler takes it over, with no change for the senders. **Only you switch to Auto**, with the button; the Talker only ever sends Manual, and the Main Assistant has no route to it.

**Returns:** the agent's `Result`; `invalid_arguments` for an unknown agent.

## `ReportTask`

`ReportTask(task_id: str, kind: ReportKind, text: str)` (command)

Sent by an agent to the Hub. A command rather than an event so the Hub's state never misses it.

| `kind` | Means | State becomes |
|--------|-------|---------------|
| `progress` | What it's doing | unchanged |
| `reply` | Answer to a `message` | unchanged |
| `need` | A question for you; the turn has ended. In Auto, a `need` starting with `Risky:` is a pause before a risky step | `WAITING_FOR_INPUT` |
| `permission` | Wants to use a tool its rules don't allow, e.g. `Write C:\…\SKILL.md`; the turn waits for [`AnswerPermission`](#answerpermission) | `WAITING_FOR_INPUT` (question `Permission: …`) |
| `done` | Finished; `text` is the result | `DONE` |
| `failed` | Gave up; `text` says why | `FAILED` |

`ReportKind` is a `StrEnum` with these values.

**Returns:** `ok`, or `invalid_arguments` for an unknown or finished task.

## `TaskUpdated`

`TaskUpdated(task_id: str, state: TaskState, kind: ReportKind | None, text: str)` (event)

Published by the Hub on every report and state change; the Talker listens. `kind` is `None` for changes the Hub made itself (start, with `text` "started"; `SendToTask`; `AnswerPermission`, with "permission allowed" / "permission denied"; cancel). May be dropped; `GetTaskStatus` is authoritative.

## `AgentStateChanged`

`AgentStateChanged(agent_id: str, busy: bool, working: bool)` (event)

Published by the agent module whenever `busy` or `working` changes, so a UI can show it live without polling. May be dropped; [`ListAgents`](#listagents) is authoritative.

## `PermissionModeChanged`

**Reusable** · Used by: `SessionTaskAgent` publishes; `talker`, `temp_ui` subscribe

`PermissionModeChanged(agent_id: str, mode: PermissionMode, applies: Literal["now", "next_task"] = "now")` (event)

A task agent's mode was set. `applies` is `next_task` when the running session can't switch: to Auto mid-task (its prompt is fixed when a session starts), or a live switch to Manual that failed. The temp UI shows it (amber header in Auto) and logs it in both panes; the Talker hears it once, as a `[Mode] worker: …` line before your next message. May be dropped; [`ListAgents`](#listagents) is authoritative.

## `AgentActivity`

**Reusable** · Used by: `SessionTaskAgent` publishes; `agent_hub`, `assistant_view`, `temp_ui`, `html_viewer` subscribe

`AgentActivity(agent_id: str, task_id: str | None, text: str)` (event)

An agent's raw activity (its text and tool calls), published by the agent module itself for viewers such as terminal 2. High-volume and view-only. The Hub keeps each task's latest lines in [`TaskInfo.activity`](#taskinfo).

## `SessionUsage`

**Reusable** · Used by: `SessionTaskAgent`, `talker` publish; `temp_ui` subscribes

`SessionUsage(agent_id: str, context_tokens: int, input_tokens: int = 0, cache_write_tokens: int = 0, cache_read_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0)` (event)

One agent's `claude` usage: "talker" or a task agent's id. Agents are never added together. Built with [`session_usage`](infra.md#session_usage). Published by [`SessionTaskAgent`](infra.md#sessiontaskagent) on every call that changes it (live while the worker works), and by the Talker after each turn. View-only.

| Name | Description |
|------|-------------|
| `context_tokens` | What each call sends now: the latest call's input, cached or not. Every further call resends that much, so it shows when a reset is worth it. 0 when no session runs; a fresh session starts small |
| `input_tokens`, `cache_write_tokens`, `cache_read_tokens`, `output_tokens` | Every call since the app started, across fresh sessions and resets |
| `used_tokens` | (property) Their sum |
| `cost_usd` | `claude`'s own estimate for the same span, at API prices (on a subscription you don't pay per token) |

The Talker hears the worker's, adds its own, and puts both before each of your messages as a `[Usage]` line; it also warns you once when either context passes `context_warning`. The temp UI shows both in its header.

## `ResetRequested`

`ResetRequested(agent_id: str)` (event)

Asks the session behind `agent_id` ("talker" or a task agent's id) to start fresh. Sent by the temp UI's Reset buttons and the Talker's `<<RESET: talker | worker>>` tag. The Talker restarts its session and tells the new one its last few exchanges. A task agent ([`SessionTaskAgent.reset`](infra.md#sessiontaskagent)) closes its session at once when idle; with a task, it asks the agent to write a handoff note, and the task carries on in a fresh session.
