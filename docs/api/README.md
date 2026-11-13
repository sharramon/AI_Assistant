# API Reference

Every public class and function, grouped by area. Check here before writing something new. If it already exists, reuse or extend it.

Each group links to a page with full signatures, parameters, return values, errors and examples. For how the pieces fit together, see the [architecture overview](../architecture/README.md). For which module handles, sends, and listens to each type, see the [module library](../architecture/module-library.md).

Modules may use **Modules**, **Messaging**, **Tools**, **Module control**, **Agents**, **Infrastructure**, and **App kit**; their tests also use the **Test kit**. **Core host** is internal to `assistant.core`; it's listed so nothing gets duplicated.

**♻ Reusable** marks a part built once and shared ([principle 13](../architecture/principles.md)). Its entry starts with **Reusable · Used by: …**.

## ♻ Reusable parts

**Check the [reusable parts index](reusable.md) before writing a helper.** One line per part (name, kind, purpose, where, used by), sorted by where it lives:

- **Contracts** (`assistant.contracts`): `ModuleProtocol`, `Menu`, `ModuleContext`, `ctx.logs`, `ctx.permissions` (with `request_set`), `Manifest`, the Event Bus, `AccessItem` and the access cards (`PermissionRequested`, `AnswerPermissionRequest`, `PermissionChanged`), `InputReceived`, `ResponseReady`, `IToolProvider`, `ITaskAgent` (with `request_approval`), `AgentState`, `DeliverMessage`, `IAgentNames`, `ModuleContext.withdraw`, `AgentActivity`, `SessionUsage`, `PermissionMode`, `SetPermissionMode`, `PermissionModeChanged`, `SetFocus`, `FocusChanged`, `FocusSuggested`, `AgentNotice`, `QuestionKind` (with `RISKY_PREFIX`), `MAX_SNIPS`, `PASTED_FILE`, the Hub's menu, `IPageOpener`, `IVoice`, `StartListening`, `StopListening`, `ListeningState`, `VoiceState`, `VoiceTranscript`
- **Voice service** (`voice_service`): the `/ws/listen` messages (`protocol`); inside the service, `SttEngine` / `SttStream`, `AudioSource` / `FakeSource` / `FileSource`, and `transcribe` / `transcribe_file`
- **Main-app helpers** (`assistant.infra`): `load_config`, `setup_logging`, `LogSession`, `LogSink`, `theme_slug`, `ClaudeSession`, `claude_command`, `path_rule`, `SessionTaskAgent` (with `set_context`), `default_context`, `PermissionGate`, `HandoffKeeper`, `LastLineTags`, `UsageMeter`, `AgentKit` (with `AGENT_USES` / `SENDS` / `PUBLISHES` / `LISTENS`), `AgentProfile`, `manual_claude_mode`, `access_items`, `granted_config`, `request_access`, `MilestoneFeed`, `session_usage`, `ContextWatch`, `agent_tags`, `show_page` (with `open_page`), `mcp_door`, `check_agent_id`, `free_agent_id`
- **Shared with the independent apps** ([`app_kit`](app_kit.md)): `window` (with `window_profile`), `load_layered`, `local_path`, `merge`, `module_docs`, `CompanionApp`, `CompanionHandover`, `launch_env`, `local_guard`
- **For tests only** ([`assistant.testkit`](testkit.md)): `make_config`, `wait_until`, `pre_grant`, `pre_grant_kinds`, `module_config`, `stand_in`, `free_port`, `sample_card`, `ui_port`, `read_events`, `Speaker`, `Calculator`, the fake `claude` (`FAKE`), `FAKE_JOB_UI`, `start_hub`, `next_matching`, `report`, `StubSession`, `StubContext`, `FakeAgent`, `agent_module`, `status`, `request`, `post`, `next_item`, `FakeVoiceIn`, `clip_event`, `dropped_event`
- **Core host** (`assistant.core`, internal): `add_app_folders` (every module's `app/` folder on the import path)

## Groups

### [Modules](modules.md)
Writing a module: lifecycle, manifest, and its context. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`ModuleProtocol`](modules.md#moduleprotocol) | protocol | ♻ The one interface every module implements: `manifest`, `menu`, `init`, `start`, `stop`, `busy`, `export_state` |
| [`Menu`](modules.md#menu) | part | ♻ A module's actions: `@menu.item(...)` on its methods; checked arguments; the core offers it through `InvokeTool` |
| [`Manifest`](modules.md#manifest) | data | ♻ Module id, one-line description, its contracts (`uses`: looked up at each call, no start order), the modules it `needs` (by id) and its pip `packages` (both from its `module.toml`), the commands it handles and sends, the events it publishes and listens to, its permissions |
| [`ModuleContext`](modules.md#modulecontext) | interface | ♻ A module's only access to the app: events, commands, contracts (`provide`, `withdraw` one back), config, logging |
| [`ctx.logs`](modules.md#modulecontextlogs) | interface | ♻ This launch's log `folder()` and files (`sink(name)`), owned by the core (`ModuleLogs`) |
| [`IPageOpener`](modules.md#ipageopener) | contract | ♻ The page-opener slot: `open(path, quote, heading, front)`; `html_viewer` provides it, the Talker, temp_ui and the workers' SHOW tags use it, so no core module names the viewer |
| [`ctx.permissions`](modules.md#modulecontextpermissions) | interface | ♻ `has` / `request` a permission, `request_set` a whole access list, `granted` / `ask` one item for an agent (`ModulePermissions`); forwards to the core's permissions handler |
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
| [`ModuleEvent`](messaging.md#moduleevent) | event | ♻ A module-owned event matched by name (cv → job_search: `cv.job_finished`, `cv.job_submitted`): `ctx.publish_named` / `subscribe_named` / `unsubscribe`, no restart for a new one |
| [`MAX_SNIPS`, `PASTED_FILE`](messaging.md#snip-constants) | constants | ♻ The snips sent with one message (3); a pasted image's `file`. The viewer's tabs and snips are html_viewer's named events now (`html_viewer.tabs_changed`, `html_viewer.clip`), on [its module page](../../src/assistant/modules/html_viewer/docs/architecture.md#events) |
| [`AccessKind`](messaging.md#accesskind), [`AccessItem`](messaging.md#accessitem), [`AccessNote`](messaging.md#accessnote) | data | ♻ One line of an access list (`workspace`, `read`, `write`, `python`, `command`, `chrome`, `message`) and a card's notes |
| [`AccessDenied`, `AccessPending`](messaging.md#accessdenied-accesspending) | exceptions | ♻ From `request_set`: you denied the list; the list waits on a card |
| [`PermissionRequested`](messaging.md#permissionrequested) | event | ♻ A card for you: an access list, or an agent's grant or revoke |
| [`AnswerPermissionRequest`](messaging.md#answerpermissionrequest) | command | ♻ Your answer to a card; `keep` is the ticked items, `remember=False` a message card's Allow once |
| [`PermissionChanged`](messaging.md#permissionchanged) | event | ♻ A grant was saved, denied or revoked; closes the card |
| [`IVoice`](messaging.md#ivoice) | contract | ♻ The voice contract: `listen(session_id, destination)`, `finish(session_id)`; `voice_notes` requires it |
| [`StartListening`](messaging.md#startlistening) | command | ♻ Turn the mic on; `send_as_input` decides whether the Talker gets the text |
| [`StopListening`](messaging.md#stoplistening) | command | ♻ Turn the mic off; the result has the final text. `discard=True` throws it away (the clear button) |
| [`ListeningState`](messaging.md#listeningstate) | enum | ♻ `idle`, `starting`, `listening`, `dropped`, `finishing`, `failed` |
| [`VoiceState`](messaging.md#voicestate) | event | ♻ The mic's state changed, for the button |
| [`VoiceTranscript`](messaging.md#voicetranscript) | event | ♻ Live and final voice text, for any subscriber |
| [Voice service protocol](messaging.md#the-voice-service-protocol) | models | ♻ `/ws/listen` messages shared by `voice_service` and `voice_in` (`from voice_service.protocol import ...`) |
| [Voice service parts](messaging.md#the-voice-services-parts) | classes | ♻ Inside the service app: `SttEngine` / `SttStream` (`live_partials`, `set_prompt`, `cancel`; `ZipformerEngine`, `WhisperEngine`), `PieceCutter` (two passes), `AudioSource` (`MicSource`, `FileSource`, `FakeSource`), `transcribe` / `transcribe_file`, `create_app`, `load_engine`, `load_service_config`, `download_model` |

### [Tools](tools.md)
Capabilities invocable by name. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`IToolProvider`](tools.md#itoolprovider) | contract | ♻ A module that offers tools (any number of providers) |
| [`ToolSpec`](tools.md#toolspec) | data | Tool name, description, and JSON Schema for its arguments |
| [`InvokeTool`](tools.md#invoketool) | command | Run a tool by name; routed to its provider |
| [`IModuleDoor`](tools.md#imoduledoor) | contract | ♻ The agents' one MCP door: `mcp_config(caller)` for a `claude` session, the caller proved by its token (list modules · show a menu · use an item); `agent_hub` provides it |
| [Tools offered today](tools.md#tools-offered-today) | list | `viewer.open`, `viewer.highlight`, `viewer.tabs`, `echo.say` |

### [Module control](control.md)
Turning modules on and off while the app runs. Handled by the core. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`ListModules`](control.md#listmodules) | command | The directory: every module, one line each (id, description, state) |
| [`GetMenu`](control.md#getmenu) | command | One module's menu (`ToolSpec`s), on or off; `core` for module control |
| [The core's menu](control.md#the-cores-menu) | menu | `modules.list / menu / docs / on / off / reload / add`, the risky ones asking first; `permissions.grants / grant / request / revoke` |
| [`ActivateModule`](control.md#activatemodule) | command | Turn a module on, with the providers it requires |
| [`StartProvider`](control.md#startprovider) | command | Start on use by contract: turn on the module that provides a contract and has `start_on_use` (no module named) |
| [`DeactivateModule`](control.md#deactivatemodule) | command | Turn a module off, respecting dependents |
| [`ReloadModule`](control.md#reloadmodule) | command | Swap a module's code while the app runs; old code back if the new fails |
| [`AddModule`](control.md#addmodule) | command | Load a brand-new module while the app runs (a new contract still needs a restart) |
| [`ModuleInfo`](control.md#moduleinfo) | data | A module's id, state, and contracts |
| [`ModuleState`](control.md#modulestate) | enum | `inactive`, `starting`, `active`, `stopping`, `reloading`, `failed` |
| [`ModuleStateChanged`](control.md#modulestatechanged) | event | A module moved to a new state |

### [Agents](agents.md)
Task agents and the Agent Hub. `from assistant.contracts import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`ITaskAgent`](agents.md#itaskagent) | contract | ♻ An agent that takes tasks: `info`, `assign`, `message`, `cancel`, `answer_permission`, `set_permission_mode`, `note`, `request_approval` (ask you with the permission card) |
| [`IAgentNames`](agents.md#iagentnames) | contract | ♻ The agent ids in use (`check`, `claim`, `release`, `taken`), so no two agents share one; `agent_hub` provides |
| [`Task`](agents.md#task) | data | A unit of work: id, text, context, `question_key` (an answer to its question) |
| [`AgentState`](agents.md#agentstate) | enum | ♻ `active` (in a turn) or `idle` (takes work, whatever questions it has open) |
| [`AgentInfo`](agents.md#agentinfo) | data | An agent's id, description, capabilities, `state` (`AgentState`; `.active`), `permission_mode`, `write_folders`, `named_only` (a free pick skips it) |
| [`TaskInfo`](agents.md#taskinfo) | data | A task as the Hub knows it, with its recent activity and its question's kind |
| [`QuestionKind`](agents.md#questionkind) | enum | ♻ What a task's open question is: `permission`, `risky`, `need`, `wait` (it ended waiting) or none; set by the Hub, so nobody parses the text |
| [`TaskState`](agents.md#taskstate) | enum | `active`, `idle` (stopped, or holding its agent's question), `done`, `failed`, `cancelled` |
| [`PermissionMode`](agents.md#permissionmode) | enum | ♻ `manual` (asks outside its rules; every launch) or `auto` (no prompts, `git push` blocked) |
| [`ListAgents`](agents.md#listagents) | command | Every agent and whether it's active or idle |
| [`StartTask`](agents.md#starttask) | command | Give work to a free agent |
| [`DeliverMessage`](agents.md#delivermessage) | command | ♻ A message for an agent, never into a turn: its open task, a new task, or `pending` until it's free |
| [`GetTaskStatus`](agents.md#gettaskstatus) | command | Task status without disturbing the agent |
| [`SendToTask`](agents.md#sendtotask) | command | Question, instruction, or answer; interrupts, then continues unless paused. Into a task holding a question: the answer, the same task given back |
| [`CancelTask`](agents.md#canceltask) | command | Stop a task, like Esc |
| [`AnswerPermission`](agents.md#answerpermission) | command | Allow or deny a task's open permission request, once |
| [`SetPermissionMode`](agents.md#setpermissionmode) | command | ♻ Switch a task agent between Manual and Auto (only you switch to Auto) |
| [`ReportTask`](agents.md#reporttask) | command | Agent → Hub: `progress`, `milestone`, `reply`, `need`, `permission`, `turn_end` (the Hub answers wait or done), `done`, `failed` |
| [`TaskUpdated`](agents.md#taskupdated) | event | A task's report or state changed (for the Talker); `held` when its question waits behind the **!** |
| [`SetFocus`](agents.md#setfocus) | command | ♻ Move the focus (the agent you talk to); releases its held questions |
| [`FocusChanged`](agents.md#focuschanged) | event | ♻ The focus moved, with the questions it released |
| [`FocusSuggested`](agents.md#focussuggested) | event | ♻ The coordinator suggests you talk to an agent directly |
| [`AgentNotice`](agents.md#agentnotice) | event | ♻ A module's callback for an agent, passed to its `note` |
| [The Hub's menu](agents.md#the-hubs-menu) | menu | ♻ `hub.agents / status / start / send / cancel / focus / suggest_focus / answer / mode`, each knowing its caller |
| [`AgentStateChanged`](agents.md#agentstatechanged) | event | An agent's `state` (active or idle) changed (for UIs) |
| [`PermissionModeChanged`](agents.md#permissionmodechanged) | event | ♻ A task agent's mode was set: `now` or `next_task` (for UIs and the Talker) |
| [`AgentActivity`](agents.md#agentactivity) | event | ♻ An agent's raw activity (for terminal 2, the temp UI, the viewer) |
| [`SessionUsage`](agents.md#sessionusage) | event | ♻ One agent's usage, worker or Talker apart: context now, tokens since launch |
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
| [`AgentProfile`](infra.md#agentprofile) | class | ♻ One task agent's setup: folders, rules, command, prompt with the shared `STATUS:` / `NEED:` block |
| [`ProfileAgent`](infra.md#profileagent) | class | ♻ One big agent from its config: profile, session and `SessionTaskAgent`, the door under its own name |
| [`agent_access`](infra.md#agent_access) | functions | ♻ A task agent's access list from its config (`access_items`, with a write on its module's own folder by default), the config cut to the grant (`granted_config`), both in one call (`request_access`); `module_folder` / `module_folder_of` |
| [`MilestoneFeed`](infra.md#milestonefeed) | class | ♻ Other agents' milestones, ends, focus moves and notices, merged for an agent's next turn |
| [`session_usage`](infra.md#session_usage) | function | ♻ A `ClaudeSession`'s usage so far as a `SessionUsage` event |
| [`UsageLedger`](infra.md#usageledger) | class | ♻ Every agent's usage since launch, sub-agents nested under their parent (the `usage` module's tally) |
| [`ContextWatch`](infra.md#contextwatch) | class | ♻ Says once when a context passes a size (the Talker's warning, the worker's reminder) |
| [`agent_tags`](infra.md#agent_tags) | functions | ♻ Read SHOW tags, `NEED:`, `HANDOFF:` and `STATUS:` lines the same way everywhere |
| [`show_page`](infra.md#show_page) | function | ♻ Open a page through `IPageOpener` (`open_page`; started on use, or "No page viewer is on"); `show_page` for a SHOW tag, for the worker, the Talker and temp_ui |
| [`agent_names`](infra.md#agent_names) | functions | ♻ The agent id rules: `check_agent_id` (the caller passes the ids it reserves), `free_agent_id` |
| [`PermissionGate`](infra.md#permissiongate) | class | ♻ A task agent's one open question: tool requests, approvals, the Auto policy, the `git push` block |
| [`HandoffKeeper`](infra.md#handoffkeeper) | class | ♻ A task's handoffs, their count and texts |
| [`LastLineTags`](infra.md#lastlinetags) | class | ♻ A table of last-line tags to handlers |
| [`UsageMeter`](infra.md#usagemeter) | class | ♻ One session's token counting, with the one token-field map (`TOKEN_KINDS`) |
| [`AgentKit`](infra.md#agentkit) | class | ♻ What every agent module repeated (provide, reset, grants, open, take back), and the `AGENT_*` manifest declarations |
| [`mcp_door`](infra.md#mcp_door) | module | ♻ The door's stdio relay (`python -m assistant.infra.mcp_door`) and its app-side `DoorServer` |

### [App kit](app_kit.md)
Shared by the main app and the independent apps; standard library only. `from app_kit import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`window`](app_kit.md#window) | functions | ♻ Edge app window: `open_app_window`, `close_app_windows`, `raise_window`, `flash_window`, `devtools_port` |
| [`load_layered`](app_kit.md#load_layered) | function | ♻ A TOML file plus its `.local` override, deep-merged |
| [`local_path`](app_kit.md#local_path) | function | ♻ A config file's `.local` override path |
| [`merge`](app_kit.md#merge) | function | ♻ Deep-merge one dict over another (a module's `module.toml` under its config section) |
| [`module_docs`](app_kit.md#module_docs) | functions | ♻ A module's own `docs/` folder: `docs_settings`, `doc_pages`, `page_title`, `tools_page` (its tools page from its menu) |
| [`CompanionApp`](app_kit.md#companionapp) | class | ♻ Launch a companion app if needed, call its API, read its event stream, quit it if we launched it; restart it on a reload when its code changed. `CompanionHandover`: one module copy's handover of it |
| [`local_guard`](app_kit.md#local_guard) | functions | ♻ Refuse other hosts and other origins: `require_loopback`, `local_request`, `LOOPBACK_HOSTS` |

### [Test kit](testkit.md)
The fakes and helpers every test may use, central or a module's own; for tests only. `from assistant.testkit import ...`

| Item | Kind | Summary |
|------|------|---------|
| [Helpers](testkit.md#helpers) | functions, fakes | ♻ `make_config`, `wait_until`, `pre_grant` / `pre_grant_kinds` (a saved grant, no card), `module_config` (a module's `module.toml` under its section), `stand_in` (a module another `needs`), `free_port`, `sample_card` (an access card), `Speaker`, `Calculator`; a page's `ui_port` and `read_events` |
| [Pages and a voice_in stand-in](testkit.md#pages-and-a-voice_in-stand-in) | functions, fake | ♻ `request`, `post`, `next_item` (a module's local page over raw HTTP), `FakeVoiceIn` (stands in for voice_in), `clip_event` / `dropped_event` (the snip events) |
| [The fake `claude` and agent fakes](testkit.md#the-fake-claude-and-agent-fakes) | fakes | ♻ `FAKE` (the fake `claude -p`, run by path), `FAKE_JOB_UI`, `start_hub`, `next_matching`, `report`, `StubSession`, `StubContext`, `FakeAgent`, `agent_module`, `status` |

### [Core host](core.md) (internal)
The stable host. Modules never use these directly. `from assistant.core import ...`

| Item | Kind | Summary |
|------|------|---------|
| [`App`](core.md#app) | class | Wires the core together and runs the enabled modules |
| [`StartupError`](core.md#startuperror) | exception | The configured modules can't start together |
| [`resolve_modules`](core.md#resolve_modules) | function | Select enabled modules, validate dependencies, return start order |
| [`LifecycleManager`](core.md#lifecyclemanager) | class | Init, start, and stop modules in dependency order; activate, deactivate, reload, and add at runtime |
| [`loader`](core.md#loader) | functions | Find the modules by folder (`find_modules`); every module's `app/` folder on the import path (`add_app_folders`); fresh import of a module's package; what may be reloaded |
| [`ScopedContext`](core.md#scopedcontext) | class | The `ModuleContext` implementation; undoes registrations on close |
| [`SessionLogs`](core.md#sessionlogs) | class | The `ctx.logs` port, backed by the launch's `LogSession` |
| [`GeneratedFiles`](core.md#generatedfiles) | class | Writes `generated/` (module list, directory, dependencies) at start and on every module state change |
| [`PermissionsHandler`](core.md#permissionshandler) | class | The permissions handler, part of the core and always on: access lists, saved grants, cards, the review, grant calls |
| [`PermissionsPort`](core.md#permissionsport) | class | Each module's `ctx.permissions`, bound to its id, forwarding to the handler |
| [`PermissionsMenu`](core.md#permissionsmenu) | class | The grant calls `permissions.grants / grant / request / revoke` on the core's menu |
| [`CommandRouter`](core.md#commandrouter) | class | One handler per command; timeouts, cancellation, `Result`s |
| [`EventBus`](core.md#eventbus) | class | Non-blocking publish with isolated, bounded subscribers |
| [`Container`](core.md#container) | class | DI restricted to shared contracts |
| [`is_shared_contract`](core.md#is_shared_contract) | function | Whether a type is a contract from `assistant.contracts` |
| [`MenuTools`](core.md#menutools) | class | The core's adapter from a module's `Menu` to `IToolProvider` |
| [`dispatch_tool`](core.md#dispatch_tool) | function | The `InvokeTool` handler |
| [`CoreMenu`](core.md#coremenu) | class | The core's own menu (`modules.*`), id `core` |
