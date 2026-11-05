# Module library

Every module in one place: what it does and its interface (the tools on its menu, the commands it handles and calls, the events it publishes and listens to). Each name links to the module's own page. The data types are listed below the table, with links to their API entries. Back to the [overview](README.md).

> **Hand-written** from the code, checked 2026-11-04. Since 2026-11-05 the manifest carries the description, the commands (`handles`, `sends`) and the events (`publishes`, `listens`); generating the table from them is next (module system, chunk 2). A test (`tests/test_module_docs.py`) checks that every module has a row here and a page. It becomes generated once the manifests carry the data ([generated later](#generated-later)).

## Modules

<!-- library:start (hand-written until generated from the manifests) -->

| Module | What it does | On | Tools (menu) | Handles | Calls | Publishes | Listens to |
|--------|--------------|----|--------------|---------|-------|-----------|------------|
| [`voice_in`](../modules/voice_in.md) | Speech to text; launches the voice service app | yes | none | `StartListening`, `StopListening` | none | `VoiceState`, `VoiceTranscript`, `InputReceived` | none |
| [`voice_notes`](../modules/voice_notes.md) | Speak into a page of notes; the words never go to the Talker | yes | none | none | `StartListening`, `StopListening` | none | `VoiceState`, `VoiceTranscript` |
| [`html_viewer`](../modules/html_viewer.md) | View, edit, highlight and snip HTML; launches the viewer app | yes | `viewer.open`, `viewer.highlight`, `viewer.tabs` | `InvokeTool` (its tools) | none | `ViewerTabsChanged`, `ViewerClip` | `AgentActivity` |
| [`talker`](../modules/talker.md) | Talks with you; hands work to the Agent Hub | yes | none | none | `StartTask`, `GetTaskStatus`, `SendToTask`, `CancelTask`, `AnswerPermission`, `SetPermissionMode`, `InvokeTool` | `ResponseReady`, `SessionUsage`, `SessionTheme`, `ResetRequested`, `ShutdownRequested` | `InputReceived`, `TaskUpdated`, `SessionUsage`, `ResetRequested`, `PermissionModeChanged`, `ViewerTabsChanged`, `ViewerClip`, `ViewerClipDropped` |
| [`main_assistant`](../modules/main_assistant.md) | The worker: does the tasks (provides `ITaskAgent`) | yes | none | none (called through `ITaskAgent`) | `ReportTask` | `AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged` | `ResetRequested` |
| [`agent_hub`](../modules/agent_hub.md) | Task state and routing between the agents | yes | none | `ListAgents`, `StartTask`, `GetTaskStatus`, `SendToTask`, `CancelTask`, `ReportTask`, `AnswerPermission`, `SetPermissionMode` | `ITaskAgent` methods | `TaskUpdated` | `AgentActivity` |
| [`temp_ui`](../modules/temp_ui.md) | Temporary two-pane page: worker and Talker, mic, usage, permissions | yes | none | none | `ListModules`, `StartListening`, `StopListening`, `AnswerPermission`, `SetPermissionMode`, `InvokeTool` | `InputReceived`, `ResetRequested`, `ViewerClipDropped` | `InputReceived`, `ResponseReady`, `TaskUpdated`, `AgentActivity`, `AgentStateChanged`, `PermissionModeChanged`, `SessionUsage`, `ViewerClip`, `VoiceState`, `VoiceTranscript`, `ModuleStateChanged` |
| [`console_io`](../modules/console_io.md) | Terminal 1: type and read replies | yes | none | none | none | `InputReceived`, `ShutdownRequested` | `ResponseReady` |
| [`assistant_view`](../modules/assistant_view.md) | Terminal 2: view-only agent activity | no | none | none | none | none | `AgentActivity`, `AgentStateChanged`, `TaskUpdated` |
| [`echo_orchestrator`](../modules/echo_orchestrator.md) | Stand-in orchestrator: echoes, `/tools` | no | none | none | none | `ResponseReady` | `InputReceived` |

The core itself handles the [module control](../api/control.md) commands (`ListModules`, `ActivateModule`, `DeactivateModule`, `ReloadModule`, `AddModule`), routes `InvokeTool` to the module that offers the tool, and publishes `ModuleStateChanged`.

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

## Generated later

> **Planned**, with the module-shape refactor (change note `docs/next-steps/module-shape-refactor.md`, items 2 and 5).

A script reads each module's `Manifest` and menu and rewrites the table between the `library:start` and `library:end` markers before the docs build. It needs:

| Column | Source | Today |
|--------|--------|-------|
| What it does | `Manifest.description` | planned (refactor item 5) |
| Handles | `Manifest.handles` | planned (refactor item 2) |
| Publishes | the announced events | planned (refactor item 5) |
| Listens to | a listened-events list in the manifest | not yet in the refactor note; added there as an open point |
| Tools | the module's `ToolSpec`s, readable without starting it | today only from a running module's `tools()`; open point in the note |
| Calls | none of the above; stays hand-written or is dropped | hand-written |

The data types table can then be generated from `assistant.contracts`, linking each type to its API anchor.
