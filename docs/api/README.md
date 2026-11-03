# API Reference

Every public class and function, grouped by area. Check here before writing something new. If it already exists, reuse or extend it.

Each group links to a page with full signatures, parameters, return values, errors and examples. For how the pieces fit together, see the [architecture overview](../architecture/README.md).

Modules may use **Modules**, **Messaging**, **Tools**, **Module control**, **Agents**, **Infrastructure**, and **App kit**. **Core host** is internal to `assistant.core`; it's listed so nothing gets duplicated.

**♻ Reusable** marks a part built once and shared ([principle 13](../architecture/principles.md)). Its entry starts with **Reusable · Used by: …**.

## ♻ Reusable parts

**Check the [reusable parts index](reusable.md) before writing a helper.** One line per part (name, kind, purpose, where, used by), sorted by where it lives:

- **Contracts** (`assistant.contracts`): `ModuleContext`, `ctx.permissions`, `Manifest`, the Event Bus, `InputReceived`, `ResponseReady`, `IToolProvider`, `ITaskAgent`, `AgentActivity`, `SessionUsage`, `PermissionMode`, `SetPermissionMode`, `PermissionModeChanged`, `StartListening`, `StopListening`, `ListeningState`, `VoiceState`, `VoiceTranscript`
- **Voice service** (`voice_service`): the `/ws/listen` messages (`protocol`); inside the service, `SttEngine` / `SttStream` and `AudioSource` / `FakeSource`
- **Main-app helpers** (`assistant.infra`): `load_config`, `setup_logging`, `LogSession`, `LogSink`, `theme_slug`, `ClaudeSession`, `claude_command`, `path_rule`, `SessionTaskAgent`, `session_usage`, `agent_tags`
- **Shared with the independent apps** ([`app_kit`](app_kit.md)): `window`, `load_layered`, `CompanionApp`

## Groups

### [Modules](modules.md)
Writing a module: lifecycle, manifest, and its context. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`Module`](modules.md#module) | base class | Base for every module: `init`, `start`, `stop` |
| [`Manifest`](modules.md#manifest) | data | ♻ Module id, the contracts it provides, requires, and optionally uses, and its permissions |
| [`ModuleContext`](modules.md#modulecontext) | interface | ♻ A module's only access to the app: events, commands, contracts, config, logging |
| [`ctx.permissions`](modules.md#modulecontextpermissions) | interface | ♻ `has` / `request` a permission (`ModulePermissions`); a stand-in allows and logs until the handler runs |
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
| [`InputReceived`](messaging.md#inputreceived) | event | ♻ User input from any source |
| [`ResponseReady`](messaging.md#responseready) | event | ♻ A reply to present, correlated to its input |
| [`ShutdownRequested`](messaging.md#shutdownrequested) | event | Asks the host to shut down |
| [`SessionTheme`](messaging.md#sessiontheme) | event | A few words about the session, for its log folder name |
| [`ViewerTabsChanged`](messaging.md#viewertabschanged) | event | The HTML viewer's open tabs or highlights changed |
| [`ViewerClip`](messaging.md#viewerclip) | event | You snipped part of a page in the HTML viewer: an image for the Talker |
| [`ViewerClipDropped`](messaging.md#viewerclipdropped) | event | You dropped a snip before sending it |
| [`StartListening`](messaging.md#startlistening) | command | ♻ Turn the mic on; `send_as_input` decides whether the Talker gets the text |
| [`StopListening`](messaging.md#stoplistening) | command | ♻ Turn the mic off; the result has the final text |
| [`ListeningState`](messaging.md#listeningstate) | enum | ♻ `idle`, `starting`, `listening`, `failed` |
| [`VoiceState`](messaging.md#voicestate) | event | ♻ The mic's state changed, for the button |
| [`VoiceTranscript`](messaging.md#voicetranscript) | event | ♻ Live and final voice text, for any subscriber |
| [Voice service protocol](messaging.md#the-voice-service-protocol) | models | ♻ `/ws/listen` messages shared by `voice_service` and `voice_in` (`from voice_service.protocol import ...`) |
| [Voice service parts](messaging.md#the-voice-services-parts) | classes | ♻ Inside the service app: `SttEngine` / `SttStream`, `AudioSource` (`MicSource`, `FakeSource`), `create_app`, `load_engine`, `load_service_config`, `download_model` |

### [Tools](tools.md)
Capabilities invocable by name. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`IToolProvider`](tools.md#itoolprovider) | contract | ♻ A module that offers tools (any number of providers) |
| [`ToolSpec`](tools.md#toolspec) | data | Tool name, description, and JSON Schema for its arguments |
| [`InvokeTool`](tools.md#invoketool) | command | Run a tool by name; routed to its provider |
| [Tools offered today](tools.md#tools-offered-today) | list | `viewer.open`, `viewer.highlight`, `viewer.tabs` |

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
| [`ITaskAgent`](agents.md#itaskagent) | contract | ♻ An agent that takes tasks: `info`, `assign`, `message`, `cancel`, `answer_permission`, `set_permission_mode` |
| [`Task`](agents.md#task) | data | A unit of work: id, text, context |
| [`AgentInfo`](agents.md#agentinfo) | data | An agent's id, description, capabilities, `busy` (has a task), `working` (in a turn now), `permission_mode` |
| [`TaskInfo`](agents.md#taskinfo) | data | A task as the Hub knows it, with its recent activity |
| [`TaskState`](agents.md#taskstate) | enum | `running`, `paused`, `waiting_for_input`, `done`, `failed`, `cancelled` |
| [`PermissionMode`](agents.md#permissionmode) | enum | ♻ `manual` (asks outside its rules; every launch) or `auto` (no prompts, `git push` blocked) |
| [`ListAgents`](agents.md#listagents) | command | Every agent and whether it's busy or working |
| [`StartTask`](agents.md#starttask) | command | Give work to a free agent |
| [`GetTaskStatus`](agents.md#gettaskstatus) | command | Task status without disturbing the agent |
| [`SendToTask`](agents.md#sendtotask) | command | Question, instruction, or answer; interrupts, then continues unless paused |
| [`CancelTask`](agents.md#canceltask) | command | Stop a task, like Esc |
| [`AnswerPermission`](agents.md#answerpermission) | command | Allow or deny a task's open permission request, once |
| [`SetPermissionMode`](agents.md#setpermissionmode) | command | ♻ Switch a task agent between Manual and Auto (only you switch to Auto) |
| [`ReportTask`](agents.md#reporttask) | command | Agent → Hub: `progress`, `reply`, `need`, `permission`, `done`, `failed` |
| [`TaskUpdated`](agents.md#taskupdated) | event | A task's report or state changed (for the Talker) |
| [`AgentStateChanged`](agents.md#agentstatechanged) | event | An agent's `busy` or `working` changed (for UIs) |
| [`PermissionModeChanged`](agents.md#permissionmodechanged) | event | ♻ A task agent's mode was set: `now` or `next_task` (for UIs and the Talker) |
| [`AgentActivity`](agents.md#agentactivity) | event | ♻ An agent's raw activity (for terminal 2, the temp UI, the viewer) |
| [`SessionUsage`](agents.md#sessionusage) | event | ♻ One agent's usage, worker or Talker apart: context now, tokens and ~$ since launch |
| [`ResetRequested`](agents.md#resetrequested) | event | Start a session fresh: the Talker's, or a task agent's (handoff mid-task) |

### [Infrastructure](infra.md)
Shared services for the main app's modules. `from assistant.infra import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`load_config`](infra.md#load_config) | function | ♻ Load TOML config with local overrides |
| [`setup_logging`](infra.md#setup_logging) | function | ♻ Configure logging from the `[logging]` section |
| [`LogSession`](infra.md#logsession) | class | ♻ The log handler: one folder per app launch, created with its theme at the first message; no chat, no folder |
| [`LogSink`](infra.md#logsink) | class | ♻ One log file of a `LogSession`: held in memory until the folder exists |
| [`theme_slug`](infra.md#theme_slug) | function | ♻ Make a theme folder-safe: lowercase, hyphens, at most five words |
| [`ClaudeSession`](infra.md#claudesession) | class | ♻ One `claude -p` stream-json process: start (command read each time), send, interrupt, set_permission_mode, events |
| [`claude_command`](infra.md#claude_command) | function | ♻ The command line for a stream-json `claude` session, with allowed and disallowed rules |
| [`path_rule`](infra.md#path_rule) | function | ♻ A permission rule (`Read(//c/x/**)`) for a folder |
| [`SessionTaskAgent`](infra.md#sessiontaskagent) | class | ♻ An `ITaskAgent` backed by a `ClaudeSession`, a fresh one per task, with handoffs and the permission mode; reuse it for every task agent |
| [`session_usage`](infra.md#session_usage) | function | ♻ A `ClaudeSession`'s usage so far as a `SessionUsage` event |
| [`agent_tags`](infra.md#agent_tags) | functions | ♻ Read SHOW tags, `NEED:` and `HANDOFF:` lines the same way everywhere |

### [App kit](app_kit.md)
Shared by the main app and the independent apps; standard library only. `from app_kit import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`window`](app_kit.md#window) | functions | ♻ Edge app window: `open_app_window`, `close_app_windows`, `raise_window`, `devtools_port` |
| [`load_layered`](app_kit.md#load_layered) | function | ♻ A TOML file plus its `.local` override, deep-merged |
| [`CompanionApp`](app_kit.md#companionapp) | class | ♻ Launch a companion app if needed, call its API, read its event stream, quit it if we launched it |

### [Core host](core.md) (internal)
The stable host. Modules never use these directly. `from assistant.core import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`App`](core.md#app) | class | Wires the core together and runs the enabled modules |
| [`StartupError`](core.md#startuperror) | exception | The configured modules can't start together |
| [`resolve_modules`](core.md#resolve_modules) | function | Select enabled modules, validate dependencies, return start order |
| [`LifecycleManager`](core.md#lifecyclemanager) | class | Init, start, and stop modules in dependency order; activate and deactivate at runtime |
| [`ScopedContext`](core.md#scopedcontext) | class | The `ModuleContext` implementation; undoes registrations on close |
| [`AllowAllPermissions`](core.md#allowallpermissions) | class | The `ctx.permissions` stand-in: allows, warns once per module and permission |
| [`CommandRouter`](core.md#commandrouter) | class | One handler per command; timeouts, cancellation, `Result`s |
| [`EventBus`](core.md#eventbus) | class | Non-blocking publish with isolated, bounded subscribers |
| [`Container`](core.md#container) | class | DI restricted to shared contracts |
| [`is_shared_contract`](core.md#is_shared_contract) | function | Whether a type is a contract from `assistant.contracts` |
| [`dispatch_tool`](core.md#dispatch_tool) | function | The `InvokeTool` handler |
