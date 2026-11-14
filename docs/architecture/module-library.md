# Module library

This page lists every module, what it does and its interface: the tools on its menu, the commands it handles and sends, and the events it publishes and listens to. Each name links to the module's own docs. The data types are listed below the tables, with links to their API entries. What a module is, and how it is found and reached, is on [modules](modules.md). Back to the [overview](README.md).

> **Generated:** `scripts/build_docs.py` rewrites the tables between the `library:start` and `library:end` markers. It reads each module's `Manifest` (description, contracts, `handles`, `sends`, `publishes`, `listens`) and its `Menu` without starting the module, and takes the group from the module's `docs.toml`. "On" is the default on-list in `config/modules.toml`. To change a row, change the module's manifest or menu, not the table. `tests/test_module_docs.py` fails when the tables are stale or a module has no docs. The data types below are written by hand.

## Module pages

Every module keeps its docs in its own folder, `src/assistant/modules/<id>/docs/`, next to its code and tests, so a module's docs move with it. The main docs hold only the app-wide pages: this architecture, the agents docs, the API reference (the core only) and the principles.

Each module's folder has three standard pages, first and in this order, and a `docs.toml` ([`module_docs`](../api/app_kit.md#module_docs)):

| Page | Sections |
|------|----------|
| `README.md`, its overview | Purpose (and its status: on by default, off by default, or planned), Wrapper (its manifest), Config (its settings: the defaults in its `module.toml`, which your `config/<id>.toml` overrides; [configuration](core.md#configuration)), Code and tests (paths only) |
| `architecture.md` | Interface (tools, commands it handles and sends, events it publishes and listens to), Owns and launches (processes, windows, ports, files, companion apps), Inner workings (one diagram and a few lines), Planned |
| `tools.md` | Its menu, generated from the module's own `Menu` by the docs build; notes go after the generated part |

Other pages are optional. A module that launches its own app keeps that app's full design in its folder: [the voice service](../../src/assistant/modules/voice_in/docs/voice-service.md) in `voice_in`, [the HTML viewer app](../../src/assistant/modules/html_viewer/docs/viewer-app.md) in `html_viewer`, and [the job project](../../src/assistant/modules/job_search/docs/job-project.md) in `job_search`.

**Groups.** The `group` in `docs.toml` decides whether a module is core or an add-on ([the core line](modules.md#the-three-rules)). **Core modules** are what the app can't start without: `agent_hub`, `talker`, `main_assistant`, `task_agents`, `usage`, `voice_in`, `temp_ui`, `console_io` and `assistant_view`. **Add-ons** are every other module: `cv`, `job_search`, `html_viewer`, `voice_notes`, and the `echo_orchestrator` stand-in. The docs list the core modules' tabs first, then the add-ons', and the tables below use the same split.

## Modules

<!-- library:start (generated from the manifests and menus by scripts/build_docs.py; don't edit) -->

### Core modules

| Module | What it does | On | Menu | Contracts | Handles | Calls | Publishes | Listens to |
|--------|--------------|----|------|-----------|---------|-------|-----------|------------|
| [`console_io`](../../src/assistant/modules/console_io/docs/README.md) | Terminal 1: type and read replies | yes | none | none | none | `ShutdownRequested` | `InputReceived` | `ResponseReady` |
| [`agent_hub`](../../src/assistant/modules/agent_hub/docs/README.md) | Task state and routing between the agents, and who you're talking to | yes | `hub.agents`, `hub.status`, `hub.start`, `hub.send`, `hub.cancel`, `hub.answer`, `hub.mode`, `hub.focus`, `hub.suggest_focus` | optional `ITaskAgent`; uses `IAgentNames` | `ListAgents`, `StartTask`, `GetTaskStatus`, `SendToTask`, `CancelTask`, `ReportTask`, `AnswerPermission`, `SetFocus`, `DeliverMessage`, `AgentNotice`, `ResetRequested`, `ReviewAccessList` | `SetPermissionMode`, `AddCardNotes` | `TaskUpdated`, `FocusChanged`, `FocusSuggested` | `AgentActivity`, `AgentStateChanged`, `ModuleStateChanged`, `PermissionModeChanged` |
| [`main_assistant`](../../src/assistant/modules/main_assistant/docs/README.md) | The worker: does the tasks the Talker hands over | yes | none | provides `ITaskAgent`; uses `IModuleDoor`, `IAgentNames`, `IPageOpener` | none | `ReportTask`, `StartProvider`, `ReloadModule`, `AddModule` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged` | `ModuleStateChanged` |
| [`talker`](../../src/assistant/modules/talker/docs/README.md) | Talks with you, one Talker per agent tab; hands work to the Agent Hub | yes | `talker.reset` | optional `IModuleDoor`; uses `IPageOpener`, `IAgentNames` | none | `InvokeTool`, `AnswerPermissionRequest`, `ListAgents`, `StartProvider`, `ResetRequested`, `ShutdownRequested` | `ResponseReady`, `SessionUsage`, `SessionTheme` | `InputReceived`, `TaskUpdated`, `FocusChanged`, `FocusSuggested`, `SessionUsage`, `PermissionModeChanged`, `PermissionRequested`, `PermissionChanged`, `AgentStateChanged`, `ModuleStateChanged`, `html_viewer.tabs_changed`, `html_viewer.clip`, `temp_ui.clip`, `temp_ui.clip_dropped` |
| [`temp_ui`](../../src/assistant/modules/temp_ui/docs/README.md) | Temporary two-pane page: worker and Talker, mic, usage, permissions | yes | none | optional `IAgentNames`; uses `IPageOpener` | none | `ListModules`, `ListAgents`, `SetFocus`, `StartListening`, `StopListening`, `AnswerPermission`, `AnswerPermissionRequest`, `SetPermissionMode`, `InvokeTool`, `StartProvider`, `GetTaskStatus`, `CancelTask`, `ResetRequested` | `InputReceived`, `temp_ui.clip`, `temp_ui.clip_dropped` | `InputReceived`, `ResponseReady`, `TaskUpdated`, `AgentActivity`, `AgentStateChanged`, `FocusChanged`, `PermissionModeChanged`, `SessionUsage`, `VoiceState`, `VoiceTranscript`, `ModuleStateChanged`, `PermissionRequested`, `PermissionChanged`, `html_viewer.clip`, `temp_ui.clip` |
| [`voice_in`](../../src/assistant/modules/voice_in/docs/README.md) | Speech to text; launches the voice service app | yes | none | provides `IVoice` | `StartListening`, `StopListening` | none | `VoiceState`, `VoiceTranscript`, `InputReceived` | none |
| [`usage`](../../src/assistant/modules/usage/docs/README.md) | Every agent's tokens since launch, sub-agents under their parent | yes | `usage.total`, `usage.agents`, `usage.mine` | none | none | `ListAgents` | none | `SessionUsage`, `AgentStateChanged`, `ModuleStateChanged` |
| [`assistant_view`](../../src/assistant/modules/assistant_view/docs/README.md) | Terminal 2: view-only agent activity | no | none | none | none | none | none | `AgentActivity`, `AgentStateChanged`, `TaskUpdated` |
| [`task_agents`](../../src/assistant/modules/task_agents/docs/README.md) | Helper agents launched by name from kinds in config, each a task agent the Hub can start and focus | no | `agents.kinds`, `agents.launch`, `agents.close` | provides `ITaskAgent`; uses `IModuleDoor`, `IAgentNames`, `IPageOpener`, `ITaskAgent` | none | `ReportTask`, `StartProvider`, `ReloadModule`, `AddModule`, `StartTask`, `GetTaskStatus` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged` | `ModuleStateChanged`, `PermissionChanged` |

### Add-ons

| Module | What it does | On | Menu | Contracts | Handles | Calls | Publishes | Listens to |
|--------|--------------|----|------|-----------|---------|-------|-----------|------------|
| [`cv`](../../src/assistant/modules/cv/docs/README.md) | Tailors a CV for one job with Rezi: one clean page, checked by Rezi, your yes; its worker cv_agent | no | `rezi.sign_in`, `rezi.status`, `rezi.list_resumes`, `rezi.read_resume`, `rezi.get_resume_format`, `rezi.write_resume`, `rezi.generate_keywords`, `rezi.search_jobs`, `rezi.get_job_details`, `cv.task`, `cv.read_result`, `cv.open_tool`, `cv.tool_status`, `cv.tool_round`, `cv.tool_draft`, `cv.tool_internal_round`, `cv.check_fonts`, `cv.tool_result`, `cv.read`, `cv.build`, `cv.compare`, `cv.report` | provides `ITaskAgent`; uses `IModuleDoor`, `IAgentNames`, `IPageOpener` | none | `ReportTask`, `StartProvider`, `ReloadModule`, `AddModule`, `StartTask`, `GetTaskStatus`, `DeliverMessage`, `AgentNotice` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged`, `ResponseReady`, `cv.job_finished`, `cv.job_submitted` | `ModuleStateChanged`, `PermissionChanged`, `TaskUpdated` |
| [`echo_orchestrator`](../../src/assistant/modules/echo_orchestrator/docs/README.md) | Stand-in orchestrator: echoes, /tools | no | `echo.say` | optional `IToolProvider` | none | `ListModules`, `GetMenu` | `ResponseReady` | `InputReceived` |
| [`html_viewer`](../../src/assistant/modules/html_viewer/docs/README.md) | View, edit, highlight and snip HTML; launches the viewer app | no | `viewer.open`, `viewer.highlight`, `viewer.tabs` | provides `IPageOpener` | none | none | `html_viewer.tabs_changed`, `html_viewer.clip` | none |
| [`job_search`](../../src/assistant/modules/job_search/docs/README.md) | The job agent (applies to jobs, runs searches in the job project), with its job.* menu | no | `job.open_ui`, `job.search`, `job.tailor_cv` | provides `ITaskAgent`; uses `IModuleDoor`, `IAgentNames`, `IPageOpener` | none | `ReportTask`, `StartProvider`, `ReloadModule`, `AddModule`, `DeliverMessage`, `ActivateModule`, `InvokeTool`, `AgentNotice` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged` | `ModuleStateChanged`, `PermissionChanged`, `cv.job_finished`, `cv.job_submitted` |
| [`voice_notes`](../../src/assistant/modules/voice_notes/docs/README.md) | Speak into a page of notes; the words never go to the Talker | no | none | requires `IVoice` | none | none | none | `VoiceState`, `VoiceTranscript` |

**The core** (the host, not a module) handles `AnswerPermissionRequest`, `AddCardNotes`, `SetPermissionMode`, `InvokeTool`, `ListModules`, `GetMenu`, `ActivateModule`, `StartProvider`, `DeactivateModule`, `ReloadModule`, `AddModule`, `RemoveModule`, `ShutdownRequested` (the [module control](../api/control.md) commands among them; `InvokeTool` goes to the module whose menu has the item). It provides `IAgentNames`, `IModuleDoor`, offers its own menu as `core` (`modules.list`, `modules.menu`, `modules.docs`, `modules.on`, `modules.off`, `modules.reload`, `modules.add`, `modules.remove`, `permissions.grants`, `permissions.grant`, `permissions.request`, `permissions.revoke`), and publishes `ModuleStateChanged`, `PermissionRequested`, `PermissionChanged`.

<!-- library:end -->

**What the generated tables don't show yet:**

- **The core's own side.** Besides the line above, the core handles `GetMenu`, `StartProvider`, `ShutdownRequested`, `SetPermissionMode`, `AnswerPermissionRequest` and `AddCardNotes`. Its menu, under the id `core`, holds `modules.list`, `modules.menu`, `modules.docs`, `modules.on`, `modules.off`, `modules.reload`, `modules.add` and `modules.remove`, plus `permissions.grants`, `permissions.grant`, `permissions.request` and `permissions.revoke`. It also publishes the cards, `PermissionRequested` and `PermissionChanged` ([core](core.md), [modules](modules.md#the-cores-menu)). The generator doesn't write this yet.
- **job_search listens to `ModuleStateChanged` once.** Its manifest lists the event twice (once through the agents' shared list), so the row shows it twice.

## Data types

These are the types that travel between modules. The table gives the main fields; the API entry has them all.

| Type | Kind | Carries | API |
|------|------|---------|-----|
| `InputReceived` | event | `text`, `source`, `conversation_id` | [messaging](../api/messaging.md#inputreceived) |
| `ResponseReady` | event | `text`, `conversation_id`, `correlation_id` | [messaging](../api/messaging.md#responseready) |
| `ShutdownRequested` | command (the core handles it) | `reason`, `restart` | [messaging](../api/messaging.md#shutdownrequested) |
| `SessionTheme` | event | `text` | [messaging](../api/messaging.md#sessiontheme) |
| `StartListening` | command | `send_as_input` | [messaging](../api/messaging.md#startlistening) |
| `StopListening` | command | `discard`; the result has the final text | [messaging](../api/messaging.md#stoplistening) |
| `VoiceState` | event | `state` (`ListeningState`), `reason`, `detail` | [messaging](../api/messaging.md#voicestate) |
| `VoiceTranscript` | event | `session_id`, `text`, `settled_chars`, `final` | [messaging](../api/messaging.md#voicetranscript) |
| `ModuleEvent` | event (a named event) | `name` (`<module>.<what>`), `source` (stamped by the core), `data` (plain JSON) | [messaging](../api/messaging.md#moduleevent) |
| `html_viewer.tabs_changed` | named event | `tabs`, `active`, `highlights` | [html_viewer](../../src/assistant/modules/html_viewer/docs/architecture.md#events) |
| `html_viewer.clip`, `temp_ui.clip` | named events | `id`, `image_path`, `file`, `heading` | [html_viewer](../../src/assistant/modules/html_viewer/docs/architecture.md#events), [messaging](../api/messaging.md#moduleevent) |
| `temp_ui.clip_dropped` | named event | `id` | [messaging](../api/messaging.md#moduleevent) |
| `cv.job_finished`, `cv.job_submitted` | named events | the job's folder, its state, who to tell (`reply_to`) | [cv](../../src/assistant/modules/cv/docs/architecture.md) |
| `InvokeTool` | command | `name`, `args`, `caller` (stamped) | [tools](../api/tools.md#invoketool) |
| `StartTask` | command | `text`, `context` | [agents](../api/agents.md#starttask) |
| `DeliverMessage` | command | `agent_id`, `text`, `sender`; never into a turn | [agents](../api/agents.md#delivermessage) |
| `GetTaskStatus` | command | `task_id` | [agents](../api/agents.md#gettaskstatus) |
| `SendToTask` | command | `task_id`, `text`, `resume` | [agents](../api/agents.md#sendtotask) |
| `CancelTask` | command | `task_id` | [agents](../api/agents.md#canceltask) |
| `AnswerPermission` | command (a control command: only you or a relay) | `task_id`, `allow` | [agents](../api/agents.md#answerpermission) |
| `SetPermissionMode` | command (the core handles it; Auto only from you) | `agent_id`, `mode` (`PermissionMode`) | [agents](../api/agents.md#setpermissionmode) |
| `ListAgents` | command | none; the result lists `AgentInfo` | [agents](../api/agents.md#listagents) |
| `ReportTask` | command | the report's kind and text, a `need`'s `key` | [agents](../api/agents.md#reporttask) |
| `TaskUpdated` | event | `task_id`, `state`, `kind`, `text` | [agents](../api/agents.md#taskupdated) |
| `AgentActivity` | event | an agent's raw activity | [agents](../api/agents.md#agentactivity) |
| `AgentStateChanged` | event | an agent's `state` (`AgentState`: active or idle) | [agents](../api/agents.md#agentstatechanged) |
| `PermissionModeChanged` | event | the mode, `now` or `next_task` | [agents](../api/agents.md#permissionmodechanged) |
| `SessionUsage` | event | context now, tokens since launch | [agents](../api/agents.md#sessionusage) |
| `SetFocus` | command (the Hub handles it) | `agent_id` | [agents](../api/agents.md#setfocus) |
| `FocusChanged` | event | `agent_id`, `previous`, `released` | [agents](../api/agents.md#focuschanged) |
| `FocusSuggested` | event | `agent_id`, `reason`, `by` | [agents](../api/agents.md#focussuggested) |
| `ResetRequested` | command (the Hub handles it) | `agent_id` (a task agent; a Talker session is reset by `talker.reset`) | [agents](../api/agents.md#resetrequested) |
| `AgentNotice` | command (the Hub handles it) | `agent_id`, `text`; labelled with the sending module | [agents](../api/agents.md#agentnotice) |
| `PermissionRequested` | event (the card) | `request_id`, `module_id`, `subject`, `action` (access, grant, revoke, message, confirm), `reason`, `items` | [messaging](../api/messaging.md#permissionrequested) |
| `AnswerPermissionRequest` | command (the core handles it; only you or a relay) | `request_id`, `allow`, `keep`, `remember` | [messaging](../api/messaging.md#answerpermissionrequest) |
| `PermissionChanged` | event (closes the card) | `module_id`, `subject`, `granted`, `request_id`, `text` | [messaging](../api/messaging.md#permissionchanged) |
| `ReviewAccessList` | command (the Hub handles it) | `request_id`, `reviewer`, `who`, `reason`, `items`, `warnings`, `timeout` | [messaging](../api/messaging.md#reviewaccesslist) |
| `AddCardNotes` | command (the core handles it) | `request_id`, `notes`, `reviewed` | [messaging](../api/messaging.md#addcardnotes) |
| `ListModules` | command | none; the result lists `ModuleInfo` | [control](../api/control.md#listmodules) |
| `GetMenu` | command | `module_id`; the result lists its `ToolSpec`s | [control](../api/control.md#getmenu) |
| `ActivateModule` | command | `module_id` | [control](../api/control.md#activatemodule) |
| `StartProvider` | command | `contract` (by name, such as `"IPageOpener"`) | [control](../api/control.md#startprovider) |
| `DeactivateModule` | command (a control command) | `module_id`, `with_dependents` | [control](../api/control.md#deactivatemodule) |
| `ReloadModule` | command (a control command) | `module_id`, `now` | [control](../api/control.md#reloadmodule) |
| `AddModule` | command (a control command) | `package`, `activate` | [control](../api/control.md#addmodule) |
| `RemoveModule` | command (a control command) | `module_id`, `purge` | [control](../api/control.md#removemodule) |
| `ModuleStateChanged` | event | a module's new `ModuleState` | [control](../api/control.md#modulestatechanged) |

The data types table could be generated from `assistant.contracts` the same way as the module tables, with each type linked to its API anchor. That isn't built.
