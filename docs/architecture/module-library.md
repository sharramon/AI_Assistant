# Module library

Every module in one place: what it does and its interface (the tools on its menu, the commands it handles and calls, the events it publishes and listens to). Each name links to the module's own page. The data types are listed below the table, with links to their API entries. Back to the [overview](README.md).

> **Generated** (since 2026-11-05): `scripts/build_docs.py` rewrites the table between the `library:start` and `library:end` markers from each module's `Manifest` (description, contracts, `handles`, `sends`, `publishes`, `listens`) and its `Menu`, read without starting the module. "On" is the default config's `modules.enabled`. Change a module's manifest or menu, not this table; a test (`tests/test_module_docs.py`) fails when the table is stale or a module has no page. The data types below are still hand-written.

## Modules

<!-- library:start (generated from the manifests and menus by scripts/build_docs.py; don't edit) -->

| Module | What it does | On | Menu | Contracts | Handles | Calls | Publishes | Listens to |
|--------|--------------|----|------|-----------|---------|-------|-----------|------------|
| [`console_io`](../modules/console_io.md) | Terminal 1: type and read replies | yes | none | none | none | none | `InputReceived`, `ShutdownRequested` | `ResponseReady` |
| [`agent_hub`](../modules/agent_hub.md) | Task state and routing between the agents; hosts the agents' door to the module menus | yes | none | provides `IModuleDoor`; optional `ITaskAgent` | `ListAgents`, `StartTask`, `GetTaskStatus`, `SendToTask`, `CancelTask`, `ReportTask`, `AnswerPermission`, `SetPermissionMode` | `ListModules`, `GetMenu`, `InvokeTool` | `TaskUpdated` | `AgentActivity` |
| [`main_assistant`](../modules/main_assistant.md) | The worker: does the tasks the Talker hands over | yes | none | provides `ITaskAgent` | none | `ReportTask` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged` | `ResetRequested` |
| [`talker`](../modules/talker.md) | Talks with you; hands work to the Agent Hub | yes | none | none | none | `StartTask`, `GetTaskStatus`, `SendToTask`, `CancelTask`, `AnswerPermission`, `SetPermissionMode`, `InvokeTool` | `ResponseReady`, `SessionUsage`, `SessionTheme`, `ResetRequested`, `ShutdownRequested` | `InputReceived`, `TaskUpdated`, `SessionUsage`, `ResetRequested`, `PermissionModeChanged`, `ViewerTabsChanged`, `ViewerClip`, `ViewerClipDropped` |
| [`temp_ui`](../modules/temp_ui.md) | Temporary two-pane page: worker and Talker, mic, usage, permissions | yes | none | none | none | `ListModules`, `StartListening`, `StopListening`, `AnswerPermission`, `SetPermissionMode`, `InvokeTool` | `InputReceived`, `ResetRequested`, `ViewerClipDropped` | `InputReceived`, `ResponseReady`, `TaskUpdated`, `AgentActivity`, `AgentStateChanged`, `PermissionModeChanged`, `SessionUsage`, `ViewerClip`, `VoiceState`, `VoiceTranscript`, `ModuleStateChanged` |
| [`html_viewer`](../modules/html_viewer.md) | View, edit, highlight and snip HTML; launches the viewer app | yes | `viewer.open`, `viewer.highlight`, `viewer.tabs` | none | none | none | `ViewerTabsChanged`, `ViewerClip` | `AgentActivity` |
| [`voice_in`](../modules/voice_in.md) | Speech to text; launches the voice service app | yes | none | provides `IVoice` | `StartListening`, `StopListening` | none | `VoiceState`, `VoiceTranscript`, `InputReceived` | none |
| [`voice_notes`](../modules/voice_notes.md) | Speak into a page of notes; the words never go to the Talker | yes | none | requires `IVoice` | none | none | none | `VoiceState`, `VoiceTranscript` |
| [`assistant_view`](../modules/assistant_view.md) | Terminal 2: view-only agent activity | no | none | none | none | none | none | `AgentActivity`, `AgentStateChanged`, `TaskUpdated` |
| [`echo_orchestrator`](../modules/echo_orchestrator.md) | Stand-in orchestrator: echoes, /tools | no | `echo.say` | optional `IToolProvider` | none | none | `ResponseReady` | `InputReceived` |

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
| `ViewerTabsChanged` | event | `tabs`, `active`, `highlights` | [messaging](../api/messaging.md#viewertabschanged) |
| `ViewerClip` | event | `id`, `image_path`, `file`, `heading` | [messaging](../api/messaging.md#viewerclip) |
| `ViewerClipDropped` | event | `id` | [messaging](../api/messaging.md#viewerclipdropped) |
| `InvokeTool` | command | `name`, `args` | [tools](../api/tools.md#invoketool) |
| `StartTask` | command | `text`, `context` | [agents](../api/agents.md#starttask) |
| `GetTaskStatus` | command | `task_id` | [agents](../api/agents.md#gettaskstatus) |
| `SendToTask` | command | `task_id`, `text`, `resume` | [agents](../api/agents.md#sendtotask) |
| `CancelTask` | command | `task_id` | [agents](../api/agents.md#canceltask) |
| `AnswerPermission` | command | `task_id`, `allow` | [agents](../api/agents.md#answerpermission) |
| `SetPermissionMode` | command | `agent_id`, `mode` (`PermissionMode`) | [agents](../api/agents.md#setpermissionmode) |
| `ListAgents` | command | none; the result lists `AgentInfo` | [agents](../api/agents.md#listagents) |
| `ReportTask` | command | the report's kind and text | [agents](../api/agents.md#reporttask) |
| `TaskUpdated` | event | `task_id`, `state`, `kind`, `text` | [agents](../api/agents.md#taskupdated) |
| `AgentActivity` | event | an agent's raw activity | [agents](../api/agents.md#agentactivity) |
| `AgentStateChanged` | event | an agent's `busy` and `working` | [agents](../api/agents.md#agentstatechanged) |
| `PermissionModeChanged` | event | the mode, `now` or `next_task` | [agents](../api/agents.md#permissionmodechanged) |
| `SessionUsage` | event | context now, tokens and ~$ since launch | [agents](../api/agents.md#sessionusage) |
| `ResetRequested` | event | `agent_id` | [agents](../api/agents.md#resetrequested) |
| `ListModules` | command | none; the result lists `ModuleInfo` | [control](../api/control.md#listmodules) |
| `ModuleStateChanged` | event | a module's new `ModuleState` | [control](../api/control.md#modulestatechanged) |

The data types table could be generated from `assistant.contracts` the same way, linking each type to its API anchor (not done yet).
