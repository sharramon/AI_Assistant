# API Reference

Every public class and function, grouped by area. Check here before writing something new. If it already exists, reuse or extend it.

Each group links to a page with full signatures, parameters, return values, errors and examples. For how the pieces fit together, see the [architecture overview](../architecture/README.md).

Modules may use **Modules**, **Messaging**, **Tools**, **Module control**, **Agents**, and **Infrastructure**. **Core host** is internal to `assistant.core`; it's listed so nothing gets duplicated.

## Groups

### [Modules](modules.md)
Writing a module: lifecycle, manifest, and its context. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`Module`](modules.md#module) | base class | Base for every module: `init`, `start`, `stop` |
| [`Manifest`](modules.md#manifest) | data | Module id and the contracts it provides, requires, and optionally uses |
| [`ModuleContext`](modules.md#modulecontext) | interface | A module's only access to the app: events, commands, contracts, config, logging |
| [`Contract`](modules.md#contract) | base class | Base for capability interfaces resolvable through DI |

### [Messaging](messaging.md)
Commands, events, and results. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`Message`](messaging.md#message) | data | Base with `id`, `correlation_id`, `timestamp` |
| [`Command`](messaging.md#command) | data | Base for requests with exactly one handler |
| [`Event`](messaging.md#event) | data | Base for notifications with any number of subscribers |
| [`Result`](messaging.md#result) | data | Outcome of every command |
| [`Status`](messaging.md#status) | enum | `ok`, `invalid_arguments`, `not_available`, `failed`, `timed_out`, `cancelled` |
| [`InputReceived`](messaging.md#inputreceived) | event | User input from any source |
| [`ResponseReady`](messaging.md#responseready) | event | A reply to present, correlated to its input |
| [`ShutdownRequested`](messaging.md#shutdownrequested) | event | Asks the host to shut down |

### [Tools](tools.md)
Capabilities invocable by name. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`IToolProvider`](tools.md#itoolprovider) | contract | A module that offers tools (any number of providers) |
| [`ToolSpec`](tools.md#toolspec) | data | Tool name, description, and JSON Schema for its arguments |
| [`InvokeTool`](tools.md#invoketool) | command | Run a tool by name; routed to its provider |

### [Module control](control.md)
Turning modules on and off while the app runs. Handled by the core. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`ListModules`](control.md#listmodules) | command | Every available module and its state |
| [`ActivateModule`](control.md#activatemodule) | command | Turn a module on, with the providers it requires |
| [`DeactivateModule`](control.md#deactivatemodule) | command | Turn a module off, respecting dependents |
| [`ModuleInfo`](control.md#moduleinfo) | data | A module's id, state, and contracts |
| [`ModuleState`](control.md#modulestate) | enum | `inactive`, `starting`, `active`, `stopping`, `failed` |
| [`ModuleStateChanged`](control.md#modulestatechanged) | event | A module moved to a new state |

### [Agents](agents.md)
Task agents and the Agent Hub. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`ITaskAgent`](agents.md#itaskagent) | contract | An agent that takes tasks: `info`, `assign`, `message`, `cancel` |
| [`Task`](agents.md#task) | data | A unit of work: id, text, context |
| [`AgentInfo`](agents.md#agentinfo) | data | An agent's id, description, capabilities, `busy` (has a task), `working` (in a turn now) |
| [`TaskInfo`](agents.md#taskinfo) | data | A task as the Hub knows it |
| [`TaskState`](agents.md#taskstate) | enum | `running`, `paused`, `waiting_for_input`, `done`, `failed`, `cancelled` |
| [`ListAgents`](agents.md#listagents) | command | Every agent and whether it's busy or working |
| [`StartTask`](agents.md#starttask) | command | Give work to a free agent |
| [`GetTaskStatus`](agents.md#gettaskstatus) | command | Task status without disturbing the agent |
| [`SendToTask`](agents.md#sendtotask) | command | Question, instruction, or answer; interrupts, then continues unless paused |
| [`CancelTask`](agents.md#canceltask) | command | Stop a task, like Esc |
| [`ReportTask`](agents.md#reporttask) | command | Agent → Hub: `progress`, `reply`, `need`, `done`, `failed` |
| [`TaskUpdated`](agents.md#taskupdated) | event | A task's report or state changed (for the Talker) |
| [`AgentStateChanged`](agents.md#agentstatechanged) | event | An agent's `busy` or `working` changed (for UIs) |
| [`AgentActivity`](agents.md#agentactivity) | event | An agent's raw activity (for terminal 2) |

### [Infrastructure](infra.md)
Shared services. `from assistant.infra import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`load_config`](infra.md#load_config) | function | Load TOML config with local overrides |
| [`setup_logging`](infra.md#setup_logging) | function | Configure logging from the `[logging]` section |
| [`ClaudeSession`](infra.md#claudesession) | class | One `claude -p` stream-json process: start, send, interrupt, events |
| [`claude_command`](infra.md#claude_command) | function | The command line for a stream-json `claude` session |
| [`SessionTaskAgent`](infra.md#sessiontaskagent) | class | An `ITaskAgent` backed by a `ClaudeSession`; reuse it for every task agent |

### [Core host](core.md) (internal)
The stable host. Modules never use these directly. `from assistant.core import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`App`](core.md#app) | class | Wires the core together and runs the enabled modules |
| [`StartupError`](core.md#startuperror) | exception | The configured modules can't start together |
| [`resolve_modules`](core.md#resolve_modules) | function | Select enabled modules, validate dependencies, return start order |
| [`LifecycleManager`](core.md#lifecyclemanager) | class | Init, start, and stop modules in dependency order; activate and deactivate at runtime |
| [`ScopedContext`](core.md#scopedcontext) | class | The `ModuleContext` implementation; undoes registrations on close |
| [`CommandRouter`](core.md#commandrouter) | class | One handler per command; timeouts, cancellation, `Result`s |
| [`EventBus`](core.md#eventbus) | class | Non-blocking publish with isolated, bounded subscribers |
| [`Container`](core.md#container) | class | DI restricted to shared contracts |
| [`is_shared_contract`](core.md#is_shared_contract) | function | Whether a type is a contract from `assistant.contracts` |
| [`dispatch_tool`](core.md#dispatch_tool) | function | The `InvokeTool` handler |
