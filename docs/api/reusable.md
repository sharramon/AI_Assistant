# Reusable parts index

Every reusable part, one line each. **Check here before writing a helper**; after building, add the part here and keep its Used by line current. The rule: [principle 13](../architecture/principles.md); where parts live: [Reusable parts](../architecture/reusable-parts.md). Back to the [API index](README.md).

*planned* = decided, not built yet.

## Contracts: `assistant.contracts`

| Name | Kind | Purpose | Where | Used by |
|------|------|---------|-------|---------|
| [`ModuleContext`](modules.md#modulecontext) | interface | A module's access to the app: events, commands, contracts, config, log | `contracts/module.py` | every module |
| [`ctx.permissions`](modules.md#modulecontextpermissions) | interface | `has` / `request` a permission; stand-in allows and logs (*planned*) | `contracts/module.py`, `core/context.py` | `voice_in` (*planned*), every module that asks |
| [`Manifest`](modules.md#manifest) | data | Id, contracts provided / required / optional, permissions (*planned*) | `contracts/module.py` | every module |
| Event Bus (`ctx.subscribe` / `ctx.publish`) | core | The stream for any event: voice text, agent activity, usage | `core/bus.py` | every module |
| [`InputReceived`](messaging.md#inputreceived) | event | User input from any source | `contracts/messages.py` | `console_io`, `temp_ui`, `voice_in` (*planned*) → `talker`, `echo_orchestrator` |
| [`ResponseReady`](messaging.md#responseready) | event | A reply to present | `contracts/messages.py` | `talker`, `echo_orchestrator` → `console_io`, `temp_ui` |
| [`IToolProvider`](tools.md#itoolprovider) | contract | A module offering tools by name | `contracts/tools.py` | `html_viewer`; called via `InvokeTool` |
| [`ITaskAgent`](agents.md#itaskagent) | contract | An agent that takes tasks, with an optional permission mode | `contracts/agents.py` | `main_assistant` → `agent_hub` |
| [`AgentActivity`](agents.md#agentactivity) | event | An agent's raw activity | `contracts/agents.py` | `SessionTaskAgent` → `agent_hub`, `assistant_view`, `temp_ui`, `html_viewer` |
| [`SessionUsage`](agents.md#sessionusage) | event | One agent's context and usage | `contracts/agents.py` | `SessionTaskAgent`, `talker` → `temp_ui` |
| [`PermissionMode`](agents.md#permissionmode) | enum | A task agent's mode: `manual`, `auto` | `contracts/agents.py` | `SessionTaskAgent`, `main_assistant`, `talker`, `temp_ui` |
| [`SetPermissionMode`](agents.md#setpermissionmode) | command | Switch a task agent's mode; any UI or the control panel later | `contracts/agents.py` | `temp_ui` (button), `talker` (Manual only) → `agent_hub` |
| [`PermissionModeChanged`](agents.md#permissionmodechanged) | event | A task agent's mode was set, and when it applies | `contracts/agents.py` | `SessionTaskAgent` → `talker`, `temp_ui` |

## Main-app helpers: `assistant.infra`

| Name | Kind | Purpose | Where | Used by |
|------|------|---------|-------|---------|
| [`load_config`](infra.md#load_config) | function | The app's TOML config plus `local.toml` | `infra/config.py` | `__main__`, tests |
| [`setup_logging`](infra.md#setup_logging) | function | Root logging from `[logging]` | `infra/log.py` | `__main__`, tests |
| [`LogSession`](infra.md#logsession), [`LogSink`](infra.md#logsink) | class | One log folder per launch; one file in it | `infra/log.py` | `__main__`, every transcript |
| [`theme_slug`](infra.md#theme_slug) | function | Folder-safe theme words | `infra/log.py` | `LogSession`, `talker` |
| [`ClaudeSession`](infra.md#claudesession) | class | One `claude -p` stream-json process; its command may be a callable read on each start; live `set_permission_mode` | `infra/claude_session.py` | `talker`, `main_assistant` (callable command), `SessionTaskAgent` |
| [`claude_command`](infra.md#claude_command) | function | The `claude` command line, with `disallowed` rules | `infra/claude_session.py` | `talker`, `main_assistant` (`disallowed` for Auto's `git push` block) |
| [`path_rule`](infra.md#path_rule) | function | A permission rule for a folder | `infra/claude_session.py` | `main_assistant` |
| [`SessionTaskAgent`](infra.md#sessiontaskagent) | class | An `ITaskAgent` on a `ClaudeSession`, with handoffs and the permission mode | `infra/session_agent.py` | `main_assistant`; every task agent later |
| [`session_usage`](infra.md#session_usage) | function | A session's usage as `SessionUsage` | `infra/session_agent.py` | `SessionTaskAgent`, `talker` |
| [`agent_tags`](infra.md#agent_tags) | functions | Read `<<TAG: …>>` tags, SHOW arguments, `NEED:` and `HANDOFF:` lines | `infra/agent_tags.py` | `talker`, `html_viewer` module, `SessionTaskAgent` |

## Shared with the independent apps: `app_kit`

| Name | Kind | Purpose | Where | Used by |
|------|------|---------|-------|---------|
| [`window`](app_kit.md#window) | functions | Edge app window: open, close, raise, DevTools port | `app_kit/window.py` | `temp_ui`, HTML viewer app (`viewer.py`, `snip.py`) |
| [`load_layered`](app_kit.md#load_layered) | function | A TOML file plus its `.local` override | `app_kit/config.py` | `load_config`, `voice_service` (*planned*) |
| [`CompanionApp`](app_kit.md#companionapp) | class | Launch, call, stream, and quit a companion app | `app_kit/companion.py` | `html_viewer` module, `voice_in` (*planned*) |
