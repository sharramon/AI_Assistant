# agent_hub: who is doing what

## Purpose

Holds the authoritative task state and routes work between the Talker and the task agents, and keeps the **focus** (the agent you're talking to). Not an AI; launches nothing. On by default. Design: [agents](../architecture/agents.md), [working together](../architecture/agents.md#working-together).

## Wrapper

| Field | Value |
|-------|-------|
| id | `agent_hub` |
| provides / requires | provides [`IModuleDoor`](../api/tools.md#imoduledoor), the agents' one MCP door to the module menus, and [`IAgentNames`](../api/agents.md#iagentnames), the agent ids in use; requires nothing |
| optional | [`ITaskAgent`](../api/agents.md#itaskagent) (every task agent; it never imports one) |
| permissions | none |

## Interface

| | |
|---|---|
| Tools | [the Hub's menu](../api/agents.md#the-hubs-menu): `hub.agents`, `hub.status`, `hub.start`, `hub.send`, `hub.cancel`, `hub.focus`, `hub.answer`, `hub.mode` (the Talker only; `hub.mode` is Manual only), `hub.suggest_focus` (the coordinator only) |
| Handles | [`ListAgents`](../api/agents.md#listagents), [`StartTask`](../api/agents.md#starttask), [`GetTaskStatus`](../api/agents.md#gettaskstatus), [`SendToTask`](../api/agents.md#sendtotask), [`CancelTask`](../api/agents.md#canceltask), [`ReportTask`](../api/agents.md#reporttask), [`AnswerPermission`](../api/agents.md#answerpermission), [`SetPermissionMode`](../api/agents.md#setpermissionmode), [`SetFocus`](../api/agents.md#setfocus) |
| Calls | the agents' `ITaskAgent` methods, including `note` (words for the coordinator's next turn) |
| Publishes | [`TaskUpdated`](../api/agents.md#taskupdated), [`FocusChanged`](../api/agents.md#focuschanged), [`FocusSuggested`](../api/agents.md#focussuggested) |
| Listens to | [`AgentActivity`](../api/agents.md#agentactivity) (kept per task as a view, not state), [`AgentNotice`](../api/agents.md#agentnotice) (passed to that agent's `note`) |

## Owns and launches

- **The module door** (built 2026-11-05): a [`DoorServer`](../api/infra.md#mcp_door), a local HTTP endpoint (`door_host`, `door_port`, default a free port; `door = false` turns it off) behind the stdio relay each `claude` session starts. Each session gets its own token from `mcp_config(caller)`; the door passes the caller that token proves as `InvokeTool.caller`, so a session can't call as someone else. A reload hands the port and tokens to the new copy, so running sessions keep their door.
- **Task records**: id, agent, text, parent task, [`TaskState`](../api/agents.md#taskstate), the held flag, recent activity. State changes only from commands, so dropped events can't corrupt it.
- **The focus** (built 2026-11-05): the coordinator at launch, kept across a Hub reload, back to the coordinator when the focused agent stops. The Hub checks on every `AgentStateChanged` and `ModuleStateChanged`, and says the move with `FocusChanged` (`previous` is the gone agent), so the page leaves the dead tab at once (2026-11-06). A `need` or `permission` from an agent out of focus is **held** (stored once, on its task) until you focus that agent; `SetFocus` releases it in `FocusChanged`.
- **The cap and the folder check**: besides the coordinator (not counted), at most `max_extra_agents` agents (3 by default) have an open task at once; a task is refused when its agent's `write_folders` overlap a running agent's.
- **The coordinator's feed**: every other agent's `milestone`, `done` and `failed`, and each focus move, go to the coordinator's `note`, read at the end of its next message. Never an interrupt, never a wake.
- **Agent names** (built 2026-11-05): the claimed ids and the module holding each ([`IAgentNames`](../api/agents.md#iagentnames), checked with [`check_agent_id`](../api/infra.md#agent_names)). Every `ProfileAgent` claims its id on start and releases it on stop; a taken id is refused with a free one named. The claims are kept across a Hub reload (handed over as `claims`, shown in `export_state`). Safety net: two agents with one id (one skipped the claim) are seen once, the first one, in `hub.agents`, `ListAgents` and routing, and the clash is logged once. Design: [agent names](../architecture/agents.md#agent-names).

## Inner workings

```mermaid
flowchart LR
    Talker["<b>the main tab's Talker</b>"]
    Hub["<b>Agent Hub</b><br/>tasks · focus · held"]
    Coord["<b>coordinator</b><br/>main_assistant"]
    Agent["<b>other task agent</b><br/>ITaskAgent"]
    UI["temp UI"]
    HTalker["<b>a helper tab's Talker</b><br/>one per tab"]

    Talker -- "hub.* via the door<br/>(caller: talker)" --> Hub
    Coord -- "hub.* via the door<br/>(caller: main_assistant)" --> Hub
    UI -- "AnswerPermission ·<br/>SetPermissionMode" --> Hub
    Hub -- "assign · message · cancel" --> Agent
    Agent -- "ReportTask<br/>(milestone · need · done…)" --> Hub
    Hub -- "note: milestones ·<br/>ends · focus" --> Coord
    Hub -- "TaskUpdated ·<br/>FocusChanged" --> Talker
    HTalker -- "hub.send(agent_id)<br/>its own agent" --> Hub
    Hub -- "its agent's TaskUpdated ·<br/>held items released" --> HTalker
```

**Agent talkers** (built 2026-11-05): each tab has its own Talker; the Hub keeps the focus and every **!**. While you're in another tab, an agent's questions, replies (`TaskInfo.reply`) and ends (`done`, `failed`) are held (`TaskUpdated.held`) and released in `FocusChanged.released` when you open its tab, finished tasks included. `hub.send` takes an `agent_id`, so a helper tab's Talker sends to its own agent.

Flows: [task assignment](../architecture/agents.md#task-assignment), [progress request](../architecture/agents.md#progress-request), [clarification](../architecture/agents.md#clarification), [working together](../architecture/agents.md#working-together).

## Config

`[modules.agent_hub]`: `coordinator` (default `main_assistant`), `max_extra_agents` (default 3: big agents besides the coordinator with an open task at once), `door`, `door_host`, `door_port`.

## Code and tests

- `src/assistant/modules/agent_hub/module.py`: `AgentHubModule`, the small coordinator (commands, events, the menu, the door, the running-agent lookup and the coordinator's feed)
- `tasks.py`: `TaskBoard` and `TaskRecord` (the task records and their state machine, the cap, the folder check); `focus.py`: `Focus` (the focus and releasing what was held); `names.py`: `AgentNames` and `RESERVED_AGENT_IDS` (split 2026-11-08)
- `tests/test_agents.py`, `tests/test_multi_agent.py`, `tests/test_mcp_door.py`, `tests/test_agent_names.py`, `tests/test_agent_hub_parts.py`

## Planned

`SetPermissionMode` routing moves to the [permissions handler](../architecture/permissions.md) when it is built. The big agents beside the Main Assistant are built ([`task_agents`](task_agents.md)); the Talker's open-task table, the Main Assistant's delegating, the UI's agent tabs with the **!** and the job agent are chunks 4 onward of the multi-agent change note.
