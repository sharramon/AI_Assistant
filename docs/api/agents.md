# Agents

Task agents and the Agent Hub's commands and events. All items: `from assistant.contracts import ...`. Back to the [API index](README.md). How it works: [task agents](../architecture/agents.md#task-agents).

## `ITaskAgent`

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

**Example**

    class MainAssistantModule(Module):
        manifest = Manifest(id="main_assistant", provides=(ITaskAgent,))

        async def init(self, ctx):
            self._session = ClaudeSession(claude_command(...), cwd=..., log=ctx.log)
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

`AgentInfo(agent_id: str, description: str, capabilities: tuple[str, ...] = (), busy: bool = False, working: bool = False)`

Frozen. What [`ITaskAgent.info`](#itaskagentinfo) returns.

| Name | Type | Description |
|------|------|-------------|
| `agent_id` | `str` | Unique id |
| `description` | `str` | What it does |
| `capabilities` | `tuple[str, ...]` | What kinds of tasks it takes |
| `busy` | `bool` | It has an unfinished task: running, paused, or waiting for input |
| `working` | `bool` | Its session is in a turn right now (generating or running tools). True from sending a message until the turn's `result` arrives. Always false when `busy` is false |

## `TaskState`

`class TaskState(StrEnum)`: `RUNNING`, `PAUSED`, `WAITING_FOR_INPUT`, `DONE`, `FAILED`, `CANCELLED`. Values are the lowercase names. `PAUSED` means you stopped it on purpose; `WAITING_FOR_INPUT` means it asked you something. The last three are final: `state.is_final`. Transitions: [task state](../architecture/agents.md#task-state).

## `TaskInfo`

`TaskInfo(id: str, agent_id: str, text: str, state: TaskState, recent: tuple[str, ...] = (), question: str | None = None, result: str | None = None)`

Frozen. A task as the Hub knows it.

| Name | Type | Description |
|------|------|-------------|
| `id` | `str` | Task id |
| `agent_id` | `str` | Who's doing it |
| `text` | `str` | What was asked |
| `state` | `TaskState` | Authoritative state |
| `recent` | `tuple[str, ...]` | Latest reports, newest last |
| `question` | `str \| None` | The open question while `WAITING_FOR_INPUT` |
| `result` | `str \| None` | Final text when `DONE` or `FAILED` |

## `ListAgents`

`ListAgents()` (command)

Every registered agent and whether it's busy or working. Handled by the Agent Hub, which reads [`ITaskAgent.info`](#itaskagentinfo) from each provider. For UIs and the Talker.

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

## `ReportTask`

`ReportTask(task_id: str, kind: ReportKind, text: str)` (command)

Sent by an agent to the Hub. A command rather than an event so the Hub's state never misses it.

| `kind` | Means | State becomes |
|--------|-------|---------------|
| `progress` | What it's doing | unchanged |
| `reply` | Answer to a `message` | unchanged |
| `need` | A question for you; the turn has ended | `WAITING_FOR_INPUT` |
| `done` | Finished; `text` is the result | `DONE` |
| `failed` | Gave up; `text` says why | `FAILED` |

`ReportKind` is a `StrEnum` with these values.

**Returns:** `ok`, or `invalid_arguments` for an unknown or finished task.

## `TaskUpdated`

`TaskUpdated(task_id: str, state: TaskState, kind: ReportKind | None, text: str)` (event)

Published by the Hub on every report and state change; the Talker listens. `kind` is `None` for changes the Hub made itself (start, with `text` "started"; `SendToTask`; cancel). May be dropped; `GetTaskStatus` is authoritative.

## `AgentStateChanged`

`AgentStateChanged(agent_id: str, busy: bool, working: bool)` (event)

Published by the agent module whenever `busy` or `working` changes, so a UI can show it live without polling. May be dropped; [`ListAgents`](#listagents) is authoritative.

## `AgentActivity`

`AgentActivity(agent_id: str, task_id: str | None, text: str)` (event)

An agent's raw activity (its text and tool calls), published by the agent module itself for viewers such as terminal 2. High-volume and view-only.
