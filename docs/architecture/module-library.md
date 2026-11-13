# Module library

Every module in one place: what it does and its interface (the tools on its menu, the commands it handles and calls, the events it publishes and listens to). Each name links to the module's own docs. The data types are listed below the tables, with links to their API entries. Back to the [overview](README.md).

> **Generated** (since 2026-11-05): `scripts/build_docs.py` rewrites the tables between the `library:start` and `library:end` markers from each module's `Manifest` (description, contracts, `handles`, `sends`, `publishes`, `listens`) and its `Menu`, read without starting the module, and its group from its `docs.toml`. "On" is the default config's `modules.enabled`. Change a module's manifest or menu, not these tables; a test (`tests/test_module_docs.py`) fails when they are stale or a module has no docs. The data types below are still hand-written.

## Module pages

Every module keeps its docs in its own folder, `src/assistant/modules/<id>/docs/`, next to its code and tests (decided 2026-11-12; it replaces the 2026-11-06 rule that kept eight modules' pages in the main docs). The main docs hold only the app-wide pages: this architecture, the agents docs, the API reference and the principles.

Each module's folder has three standard pages, first and in this order, and a `docs.toml` ([`module_docs`](../api/app_kit.md#module_docs)):

| Page | Sections |
|------|----------|
| `README.md`, its overview | Purpose (and its status: on by default, off by default, or planned), Wrapper (its manifest), Config (its `[modules.<id>]` section), Code and tests (paths only) |
| `architecture.md` | Interface (tools, commands it handles and calls, events it publishes and listens to), Owns and launches (processes, windows, ports, files, companion apps), Inner workings (one diagram and a few lines), Planned |
| `tools.md` | Its menu, generated from the module's own `Menu` by the docs build; notes go after the generated part |

Other pages are optional: a module that launches its own app keeps that app's full design there ([the voice service](../../src/assistant/modules/voice_in/docs/voice-service.md) in `voice_in`, [the HTML viewer app](../../src/assistant/modules/html_viewer/docs/viewer-app.md) in `html_viewer`, and [the job project](../../src/assistant/modules/job_search/docs/job-project.md) in `job_search`).

**Groups.** `docs.toml`'s `group` places a module in the docs, never its files. **Core modules** are part of the main app and its window: `agent_hub`, `talker`, `main_assistant`, `task_agents`, `usage`, `voice_in`, `temp_ui`, `console_io` and `assistant_view` (for now). **Add-ons** are features on top: `cv`, `job_search`, `html_viewer`, `voice_notes`, and the `echo_orchestrator` stand-in. The core modules' tabs come first in the docs, then the add-ons', and the tables below follow the same split.

## Modules

<!-- library:start (generated from the manifests and menus by scripts/build_docs.py; don't edit) -->

### Core modules

| Module | What it does | On | Menu | Contracts | Handles | Calls | Publishes | Listens to |
|--------|--------------|----|------|-----------|---------|-------|-----------|------------|
| [`console_io`](../../src/assistant/modules/console_io/docs/README.md) | Terminal 1: type and read replies | yes | none | none | none | none | `InputReceived`, `ShutdownRequested` | `ResponseReady` |
| [`agent_hub`](../../src/assistant/modules/agent_hub/docs/README.md) | Task state and routing between the agents, and who you're talking to; hosts the agents' door to the module menus | yes | `hub.agents`, `hub.status`, `hub.start`, `hub.send`, `hub.cancel`, `hub.answer`, `hub.mode`, `hub.focus`, `hub.suggest_focus` | provides `IModuleDoor`, `IAgentNames`; optional `ITaskAgent` | `ListAgents`, `StartTask`, `GetTaskStatus`, `SendToTask`, `CancelTask`, `ReportTask`, `AnswerPermission`, `SetPermissionMode`, `SetFocus`, `DeliverMessage` | `ListModules`, `GetMenu`, `InvokeTool` | `TaskUpdated`, `FocusChanged`, `FocusSuggested` | `AgentActivity`, `AgentNotice`, `AgentStateChanged`, `ModuleStateChanged` |
| [`main_assistant`](../../src/assistant/modules/main_assistant/docs/README.md) | The worker: does the tasks the Talker hands over | yes | none | provides `ITaskAgent`; uses `IModuleDoor`, `IAgentNames`, `IPageOpener` | none | `ReportTask`, `StartProvider` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged` | `ResetRequested`, `ModuleStateChanged` |
| [`talker`](../../src/assistant/modules/talker/docs/README.md) | Talks with you, one Talker per agent tab; hands work to the Agent Hub | yes | none | optional `IModuleDoor`; uses `IPageOpener` | none | `InvokeTool`, `AnswerPermissionRequest`, `ListAgents`, `StartProvider` | `ResponseReady`, `SessionUsage`, `SessionTheme`, `ResetRequested`, `ShutdownRequested` | `InputReceived`, `TaskUpdated`, `FocusChanged`, `FocusSuggested`, `SessionUsage`, `ResetRequested`, `PermissionModeChanged`, `PermissionRequested`, `PermissionChanged`, `AgentStateChanged`, `ModuleStateChanged`, `html_viewer.tabs_changed`, `html_viewer.clip`, `temp_ui.clip`, `temp_ui.clip_dropped` |
| [`temp_ui`](../../src/assistant/modules/temp_ui/docs/README.md) | Temporary two-pane page: worker and Talker, mic, usage, permissions | yes | none | optional `IAgentNames`; uses `IPageOpener` | none | `ListModules`, `ListAgents`, `SetFocus`, `StartListening`, `StopListening`, `AnswerPermission`, `AnswerPermissionRequest`, `SetPermissionMode`, `InvokeTool`, `StartProvider`, `GetTaskStatus`, `CancelTask` | `InputReceived`, `ResetRequested`, `temp_ui.clip`, `temp_ui.clip_dropped` | `InputReceived`, `ResponseReady`, `TaskUpdated`, `AgentActivity`, `AgentStateChanged`, `FocusChanged`, `PermissionModeChanged`, `SessionUsage`, `VoiceState`, `VoiceTranscript`, `ModuleStateChanged`, `PermissionRequested`, `PermissionChanged`, `html_viewer.clip`, `temp_ui.clip` |
| [`voice_in`](../../src/assistant/modules/voice_in/docs/README.md) | Speech to text; launches the voice service app | yes | none | provides `IVoice` | `StartListening`, `StopListening` | none | `VoiceState`, `VoiceTranscript`, `InputReceived` | none |
| [`usage`](../../src/assistant/modules/usage/docs/README.md) | Every agent's tokens since launch, sub-agents under their parent | yes | `usage.total`, `usage.agents`, `usage.mine` | none | none | `ListAgents` | none | `SessionUsage`, `AgentStateChanged`, `ModuleStateChanged` |
| [`assistant_view`](../../src/assistant/modules/assistant_view/docs/README.md) | Terminal 2: view-only agent activity | no | none | none | none | none | none | `AgentActivity`, `AgentStateChanged`, `TaskUpdated` |
| [`task_agents`](../../src/assistant/modules/task_agents/docs/README.md) | Helper agents launched by name from kinds in config, each a task agent the Hub can start and focus | no | `agents.kinds`, `agents.launch`, `agents.close` | provides `ITaskAgent`; uses `IModuleDoor`, `IAgentNames`, `IPageOpener`, `ITaskAgent` | none | `ReportTask`, `StartProvider`, `StartTask`, `GetTaskStatus` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged` | `ResetRequested`, `ModuleStateChanged`, `PermissionChanged` |

### Add-ons

| Module | What it does | On | Menu | Contracts | Handles | Calls | Publishes | Listens to |
|--------|--------------|----|------|-----------|---------|-------|-----------|------------|
| [`cv`](../../src/assistant/modules/cv/docs/README.md) | Tailors a CV for one job with Rezi: one clean page, checked by Rezi, your yes; its worker cv_agent | no | `rezi.sign_in`, `rezi.status`, `rezi.list_resumes`, `rezi.read_resume`, `rezi.get_resume_format`, `rezi.write_resume`, `rezi.generate_keywords`, `rezi.search_jobs`, `rezi.get_job_details`, `cv.task`, `cv.read_result`, `cv.open_tool`, `cv.tool_status`, `cv.tool_round`, `cv.tool_draft`, `cv.tool_internal_round`, `cv.check_fonts`, `cv.tool_result`, `cv.read`, `cv.build`, `cv.compare`, `cv.report` | provides `ITaskAgent`; uses `IModuleDoor`, `IAgentNames`, `IPageOpener` | none | `ReportTask`, `StartProvider`, `StartTask`, `GetTaskStatus`, `DeliverMessage` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged`, `ResponseReady`, `AgentNotice`, `cv.job_finished`, `cv.job_submitted` | `ResetRequested`, `ModuleStateChanged`, `PermissionChanged`, `TaskUpdated` |
| [`echo_orchestrator`](../../src/assistant/modules/echo_orchestrator/docs/README.md) | Stand-in orchestrator: echoes, /tools | no | `echo.say` | optional `IToolProvider` | none | none | `ResponseReady` | `InputReceived` |
| [`html_viewer`](../../src/assistant/modules/html_viewer/docs/README.md) | View, edit, highlight and snip HTML; launches the viewer app | no | `viewer.open`, `viewer.highlight`, `viewer.tabs` | provides `IPageOpener` | none | none | `html_viewer.tabs_changed`, `html_viewer.clip` | none |
| [`job_search`](../../src/assistant/modules/job_search/docs/README.md) | The job agent (applies to jobs, runs searches in the job project), with its job.* menu | no | `job.open_ui`, `job.search` | provides `ITaskAgent`; uses `IModuleDoor`, `IAgentNames`, `IPageOpener` | none | `ReportTask`, `StartProvider`, `DeliverMessage` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged`, `AgentNotice` | `ResetRequested`, `ModuleStateChanged`, `PermissionChanged`, `cv.job_finished`, `cv.job_submitted` |
| [`voice_notes`](../../src/assistant/modules/voice_notes/docs/README.md) | Speak into a page of notes; the words never go to the Talker | no | none | requires `IVoice` | none | none | none | `VoiceState`, `VoiceTranscript` |

The core itself handles the [module control](../api/control.md) commands (`ListModules`, `ActivateModule`, `DeactivateModule`, `ReloadModule`, `AddModule`), routes `InvokeTool` to the module whose menu has the item, and publishes `ModuleStateChanged`.

<!-- library:end -->

## Data types

What travels between modules. Fields are the main ones; the API entry has them all.

| Type | Kind | Carries | API |
|------|------|---------|-----|
| `InputReceived` | event | `text`, `source`, `conversation_id` | [messaging](../api/messaging.md#inputreceived) |
| `ResponseReady` | event | `text`, `conversation_id`, `correlation_id` | [messaging](../api/messaging.md#responseready) |
| `ShutdownRequested` | event | `reason`, `restart` | [messaging](../api/messaging.md#shutdownrequested) |
| `SessionTheme` | event | `text` | [messaging](../api/messaging.md#sessiontheme) |
| `StartListening` | command | `send_as_input` | [messaging](../api/messaging.md#startlistening) |
| `StopListening` | command | `discard`; the result has the final text | [messaging](../api/messaging.md#stoplistening) |
| `VoiceState` | event | `state` (`ListeningState`), `reason`, `detail` | [messaging](../api/messaging.md#voicestate) |
| `VoiceTranscript` | event | `session_id`, `text`, `settled_chars`, `final` | [messaging](../api/messaging.md#voicetranscript) |
| `html_viewer.tabs_changed` | named event | `tabs`, `active`, `highlights` | [html_viewer](../../src/assistant/modules/html_viewer/docs/architecture.md#events) |
| `html_viewer.clip`, `temp_ui.clip` | named events | `id`, `image_path`, `file`, `heading` | [html_viewer](../../src/assistant/modules/html_viewer/docs/architecture.md#events), [messaging](../api/messaging.md#moduleevent) |
| `temp_ui.clip_dropped` | named event | `id` | [messaging](../api/messaging.md#moduleevent) |
| `InvokeTool` | command | `name`, `args` | [tools](../api/tools.md#invoketool) |
| `StartTask` | command | `text`, `context` | [agents](../api/agents.md#starttask) |
| `DeliverMessage` | command | `agent_id`, `text`, `sender`; never into a turn | [agents](../api/agents.md#delivermessage) |
| `GetTaskStatus` | command | `task_id` | [agents](../api/agents.md#gettaskstatus) |
| `SendToTask` | command | `task_id`, `text`, `resume` | [agents](../api/agents.md#sendtotask) |
| `CancelTask` | command | `task_id` | [agents](../api/agents.md#canceltask) |
| `AnswerPermission` | command | `task_id`, `allow` | [agents](../api/agents.md#answerpermission) |
| `SetPermissionMode` | command | `agent_id`, `mode` (`PermissionMode`) | [agents](../api/agents.md#setpermissionmode) |
| `ListAgents` | command | none; the result lists `AgentInfo` | [agents](../api/agents.md#listagents) |
| `ReportTask` | command | the report's kind and text, a `need`'s `key` | [agents](../api/agents.md#reporttask) |
| `TaskUpdated` | event | `task_id`, `state`, `kind`, `text` | [agents](../api/agents.md#taskupdated) |
| `AgentActivity` | event | an agent's raw activity | [agents](../api/agents.md#agentactivity) |
| `AgentStateChanged` | event | an agent's `state` (`AgentState`: active or idle) | [agents](../api/agents.md#agentstatechanged) |
| `PermissionModeChanged` | event | the mode, `now` or `next_task` | [agents](../api/agents.md#permissionmodechanged) |
| `SessionUsage` | event | context now, tokens since launch | [agents](../api/agents.md#sessionusage) |
| `ResetRequested` | event | `agent_id` | [agents](../api/agents.md#resetrequested) |
| `ListModules` | command | none; the result lists `ModuleInfo` | [control](../api/control.md#listmodules) |
| `ModuleStateChanged` | event | a module's new `ModuleState` | [control](../api/control.md#modulestatechanged) |

The data types table could be generated from `assistant.contracts` the same way, linking each type to its API anchor (not done yet).
