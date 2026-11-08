# main_assistant: the worker agent

## Purpose

A `claude` session with file tools that does the work handed to it by the Agent Hub. On by default. It is the **coordinator** (`[modules.agent_hub] coordinator`): other agents' milestones and ends, and each focus move, reach it at the end of its next message ([working together](../architecture/agents.md#working-together)). Design: [agents](../architecture/agents.md), [the Main Assistant on its own](../agents/runtime.md#the-main-assistant-on-its-own).

## Wrapper

| Field | Value |
|-------|-------|
| id | `main_assistant` |
| provides | [`ITaskAgent`](../api/agents.md#itaskagent) (only the Hub calls it) |
| requires / optional | none |
| permissions | none declared; its file and shell access are its `claude` rules (config below) |

## Interface

| | |
|---|---|
| Tools | none |
| Handles | nothing: it is called through `ITaskAgent` (`assign`, `message`, `cancel`, `answer_permission`, `set_permission_mode`, `note`) |
| Calls | [`ReportTask`](../api/agents.md#reporttask) (`progress`, `milestone` from its `STATUS:` lines, `reply`, `need`, `permission`, `done`, `failed`); the [Hub's menu](../api/agents.md#the-hubs-menu) through the door |
| Publishes | [`AgentActivity`](../api/agents.md#agentactivity), [`AgentStateChanged`](../api/agents.md#agentstatechanged), [`SessionUsage`](../api/agents.md#sessionusage), [`PermissionModeChanged`](../api/agents.md#permissionmodechanged) |
| Listens to | [`ResetRequested`](../api/agents.md#resetrequested) |

## Owns and launches

- **A `claude -p` process** per task (`fresh_sessions`), through the shared [`SessionTaskAgent`](../api/infra.md#sessiontaskagent) and [`ClaudeSession`](../api/infra.md#claudesession). It starts with the module and stops with it.
- **Its transcript** in the launch's log folder.
- **Its setup** through the shared [`ProfileAgent`](../api/infra.md#profileagent) (like every big agent) and its [`AgentProfile`](../api/infra.md#agentprofile) (`coordinator=True`): folders (`write_folders`, for the Hub's folder check), rules, command line, and the prompt with the shared block on `STATUS:` and `NEED:`. Its id `main_assistant` is claimed from the Hub on start ([agent names](../architecture/agents.md#agent-names)); as its module's own id, it's allowed.
- **Launching helpers** (built 2026-11-05): the coordinator's block tells it to use `agents.kinds` / `agents.launch` / `agents.close` on `task_agents`' menu, only when you asked for a helper, naming it from the task. `agents.launch` puts the question to you as the permission card on its task (`request_approval`); it ends its turn and gets the outcome as its next message ([launching a helper](../architecture/agents.md#launching-a-helper)).
- **The module door** in each new session (built 2026-11-05): `IModuleDoor.mcp_config("main_assistant")`, read at each session start, becomes `--mcp-config`. Its tools `list_modules` and `show_menu` are allowed; `use_item` asks with the card in Manual. The prompt tells it to use them. `door = false` in its config turns it off. It doesn't list `IModuleDoor` as `optional` (the Hub lists `ITaskAgent`, and the two would be circular), so its first session may start before the door is up; the next task's fresh session has it.

## Inner workings

```mermaid
flowchart LR
    Hub["<b>Agent Hub</b>"]
    STA["SessionTaskAgent<br/>task · handoffs · mode"]
    Claude["claude -p<br/>built for Manual or Auto"]
    Out["AgentActivity · usage ·<br/>state · mode"]

    Hub -- "ITaskAgent.assign / message" --> STA
    STA --> Claude
    Claude -- "stream events" --> STA
    STA -- ReportTask --> Hub
    STA --> Out
```

Each session's command line and prompt are built for the permission mode at that moment: Manual at every launch, Auto only from the UI button. A `HANDOFF:` line starts a fresh session from a note ([fresh sessions and handoffs](../agents/runtime.md#fresh-sessions-and-handoffs)).

## Config

`[modules.main_assistant]`: `workspace`, `tools`, `permission_mode`, `read_dirs`, `write_dirs`, `allowed_commands`, `fresh_sessions`, `max_handoffs`, `context_reminder`, `edit_note`, `permission_prompts`, `permission_timeout`, `transcript`, `model`.

## Code and tests

- `src/assistant/modules/main_assistant/module.py`; the agent itself is `src/assistant/infra/session_agent.py`, its setup `infra/agent_profile.py`
- `tests/test_agents.py`, `test_permission_mode.py`, `test_edit_note.py`, `test_multi_agent.py`

## Planned

From the module-shape refactor: it calls module tools through the **directory and menu** (its SHOW lines are sent as `InvokeTool` by its `SessionTaskAgent`), and module control becomes core tools it can use with your approval.
