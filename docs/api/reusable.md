# Reusable parts index

Every reusable part, one line each. **Check here before writing a helper**; after building, add the part here and keep its Used by line current. The rule: [principle 13](../architecture/principles.md); where parts live: [Reusable parts](../architecture/reusable-parts.md). Back to the [API index](README.md).

*planned* = decided, not built yet.

## Contracts: `assistant.contracts`

| Name | Kind | Purpose | Where | Used by |
|------|------|---------|-------|---------|
| [`ModuleProtocol`](modules.md#moduleprotocol) | protocol | The one interface every module implements (manifest, lifecycle hooks); no behaviour, modules compose their parts | `contracts/module.py` | every module; the core's loader and lifecycle |
| [`ModuleContext`](modules.md#modulecontext) | interface | A module's access to the app: events, commands, contracts, config, log | `contracts/module.py` | every module |
| [`ctx.permissions`](modules.md#modulecontextpermissions) (`ModulePermissions`) | interface | `has` / `request` a permission; the stand-in [`AllowAllPermissions`](core.md#allowallpermissions) allows, warns once per module and permission | `contracts/module.py`, `core/permissions.py`, `core/context.py` | every module's context (`ScopedContext`); callers: `voice_in` (`microphone`, on each start), every module that asks |
| [`Manifest`](modules.md#manifest) | data | Id, one-line `description`, contracts provided / required / optional, `handles` / `sends` (commands), `publishes` / `listens` (events), `permissions` / `optional_permissions` | `contracts/module.py` | every module |
| Event Bus (`ctx.subscribe` / `ctx.publish`) | core | The stream for any event: voice text, agent activity, usage | `core/bus.py` | every module |
| [`InputReceived`](messaging.md#inputreceived) | event | User input from any source | `contracts/messages.py` | `console_io`, `temp_ui`, `voice_in` (`source="voice"`) → `talker`, `echo_orchestrator` |
| [`ResponseReady`](messaging.md#responseready) | event | A reply to present | `contracts/messages.py` | `talker`, `echo_orchestrator` → `console_io`, `temp_ui` |
| [`Menu`](modules.md#menu) | part | A module's actions: items with a schema, checked arguments, read without starting the module, linked to the running copy by the core | `contracts/menu.py` | `html_viewer`, `echo_orchestrator`; the core (`MenuTools`), `scripts/build_docs.py` |
| [`IToolProvider`](tools.md#itoolprovider) | contract | Something offering tools by name | `contracts/tools.py` | the core's `MenuTools` (every module menu); called via `InvokeTool` |
| [`ITaskAgent`](agents.md#itaskagent) | contract | An agent that takes tasks, with an optional permission mode | `contracts/agents.py` | `main_assistant` → `agent_hub` |
| [`AgentActivity`](agents.md#agentactivity) | event | An agent's raw activity | `contracts/agents.py` | `SessionTaskAgent` → `agent_hub`, `assistant_view`, `temp_ui`, `html_viewer` |
| [`SessionUsage`](agents.md#sessionusage) | event | One agent's context and usage | `contracts/agents.py` | `SessionTaskAgent`, `talker` → `temp_ui` |
| [`PermissionMode`](agents.md#permissionmode) | enum | A task agent's mode: `manual`, `auto` | `contracts/agents.py` | `SessionTaskAgent`, `main_assistant`, `talker`, `temp_ui` |
| [`SetPermissionMode`](agents.md#setpermissionmode) | command | Switch a task agent's mode; any UI or the control panel later | `contracts/agents.py` | `temp_ui` (button), `talker` (Manual only) → `agent_hub` |
| [`PermissionModeChanged`](agents.md#permissionmodechanged) | event | A task agent's mode was set, and when it applies | `contracts/agents.py` | `SessionTaskAgent` → `talker`, `temp_ui` |
| [`StartListening`](messaging.md#startlistening), [`StopListening`](messaging.md#stoplistening) | command | Turn the mic on and off; any UI may send them | `contracts/voice.py` | `temp_ui` → `voice_in` |
| [`ListeningState`](messaging.md#listeningstate) | enum | The mic's state: `idle`, `starting`, `listening`, `dropped`, `finishing`, `failed` | `contracts/voice.py` | `VoiceState` |
| [`VoiceState`](messaging.md#voicestate) | event | The mic's state changed, for the button | `contracts/voice.py` | `voice_in` → `temp_ui` |
| [`VoiceTranscript`](messaging.md#voicetranscript) | event | Live and final voice text; the public stream | `contracts/voice.py` | `voice_in` → `temp_ui`, any subscriber |

## Voice service: `voice_service`

Its own app; never imports `assistant`. The protocol is shared with its Python clients; the rest is used inside the service and is where new engines and audio sources plug in.

| Name | Kind | Purpose | Where | Used by |
|------|------|---------|-------|---------|
| [Voice service protocol](messaging.md#the-voice-service-protocol) | models, functions | The `/ws/listen` messages (with `MicDropped`, `MicBack`), `ErrorCode`, `parse_client_message`, `parse_service_message`, `dump`, `ProtocolError` | `voice_service/protocol.py` | `voice_service` server (`server.py`, `session.py`), `voice_in` client (the only part of the service it imports) |
| [`SttEngine`, `SttStream`](messaging.md#the-voice-services-parts) | ABCs | A speech engine (`load`, `new_stream`) and one session's stream (`accept`, `partial`, `finish`, optional `set_prompt` and `cancel`); `load_engine` picks one by name, once per role (live, final) | `voice_service/engines/__init__.py` | `ZipformerEngine`, `WhisperEngine`, `FakeEngine`, `ListenSession` (both engines; the `voice-clean` thread), `transcribe`; the Nemotron engine (step 7, *planned*) |
| [Two-pass real check](../architecture/voice.md#two-passes-live-text-cleaned-piece-by-piece) | script | The service in-process with the real models over WAVs fed at speech speed: CPU, partial lag, per-piece times, queue, wait after stop, text vs whole-recording whisper. Config overrides in memory only | `scripts/voice_two_pass_check.py` | the two-pass measurements (2026-11-03); the engine comparison (step 7, *planned*) |
| [`AudioSource`](messaging.md#the-voice-services-parts) | ABC | Where a session's PCM16 chunks come from: `start(on_chunk, on_lost)`, `stop()` | `voice_service/audio.py` | `MicSource`, `FakeSource`, `FileSource`, `ListenSession` (through a factory: a fresh source to reopen a dropped mic); `RemoteSource` for `/ws/audio` (later) |
| [`FileSource`](messaging.md#the-voice-services-parts) | class | A 16 kHz mono WAV in chunks, read whole or fed like a mic; the one WAV reader | `voice_service/audio.py` | `transcribe_file`, `FakeSource.from_wav`, the engine comparison (step 7, *planned*) |
| [`transcribe`, `transcribe_file`](messaging.md#the-voice-services-parts) | functions | Text from an engine and a source (or a WAV path), with timings; no server, no mic | `voice_service/transcribe.py` | the `transcribe` command, the whisper measurements (2026-11-03), the engine comparison (step 7, *planned*) |
| [`FakeSource`, `FakeEngine`](messaging.md#the-voice-services-parts) | classes | Audio from a list or a WAV file; an engine that reveals a set text. Test and offline-check doubles | `voice_service/audio.py`, `voice_service/engines/fake.py` | `tests/test_voice_service.py`, `tests/test_voice_in.py` (the real service app on a local port), offline engine checks (`FakeSource.from_wav`); the engine comparison (step 7, *planned*) |

## Main-app helpers: `assistant.infra`

| Name | Kind | Purpose | Where | Used by |
|------|------|---------|-------|---------|
| [`load_config`](infra.md#load_config) | function | The app's TOML config plus `local.toml` | `infra/config.py` | `__main__`, tests |
| [`setup_logging`](infra.md#setup_logging) | function | Root logging from `[logging]` | `infra/log.py` | `__main__`, tests |
| [`LogSession`](infra.md#logsession), [`LogSink`](infra.md#logsink) | class | One log folder per launch; one file in it | `infra/log.py` | `__main__`, every transcript |
| [`theme_slug`](infra.md#theme_slug) | function | Folder-safe theme words | `infra/log.py` | `LogSession`, `talker` |
| [`ClaudeSession`](infra.md#claudesession) | class | One `claude -p` stream-json process; its command may be a callable read on each start; live `set_permission_mode`; extra `env` | `infra/claude_session.py` | `talker`, `main_assistant` (callable command, `env` for the edit hook), `SessionTaskAgent` |
| [`claude_command`](infra.md#claude_command) | function | The `claude` command line, with `disallowed` rules | `infra/claude_session.py` | `talker`, `main_assistant` (`disallowed` for Auto's `git push` block) |
| [`path_rule`](infra.md#path_rule) | function | A permission rule for a folder | `infra/claude_session.py` | `main_assistant` |
| [`SessionTaskAgent`](infra.md#sessiontaskagent) | class | An `ITaskAgent` on a `ClaudeSession`, with handoffs, the permission mode, the context reminder, and the edit note's log line | `infra/session_agent.py` | `main_assistant`; every task agent later |
| [`session_usage`](infra.md#session_usage) | function | A session's usage as `SessionUsage` | `infra/session_agent.py` | `SessionTaskAgent`, `talker` |
| [`ContextWatch`](infra.md#contextwatch) | class | Says once when a context passes a size; re-arms when it's back under | `infra/context_watch.py` | `talker` (`context_warning`), `SessionTaskAgent` (`context_reminder`) |
| [`agent_tags`](infra.md#agent_tags) | functions | Read `<<TAG: …>>` tags, SHOW arguments, `NEED:` and `HANDOFF:` lines | `infra/agent_tags.py` | `talker` (also `RESTART_READY`), `html_viewer` module, `SessionTaskAgent` |

## Shared with the independent apps: `app_kit`

| Name | Kind | Purpose | Where | Used by |
|------|------|---------|-------|---------|
| [`window`](app_kit.md#window) | functions | Edge app window: open, close, raise, DevTools port | `app_kit/window.py` | `temp_ui`, HTML viewer app (`viewer.py`, `snip.py`) |
| [`load_layered`](app_kit.md#load_layered) | function | A TOML file plus its `.local` override | `app_kit/config.py` | `load_config`, `voice_service` (`config.py`) |
| [`local_path`](app_kit.md#local_path) | function | A config file's `.local` override path (`voice.toml` → `voice.local.toml`) | `app_kit/config.py` | `load_layered`, `voice_service` (`server.py`: the engine watch) |
| [`CompanionApp`](app_kit.md#companionapp) | class | Launch, call, stream, and quit a companion app | `app_kit/companion.py` | `html_viewer` module, `voice_in` (launches `voice_service` on the first click; `voice_service` answers its `/health` ping and JSON `POST /quit`) |
