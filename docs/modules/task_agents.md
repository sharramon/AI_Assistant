# task_agents: helper agents launched by name from kinds in config

## Purpose

Builds the helper agents beside the Main Assistant from *kinds* of helper in config. Each helper is a task agent the Agent Hub can start, focus and hold questions for. A helper is launched by name for one task, only with your yes; a kind with `autostart = true` also starts at launch. Off at launch (turn it on with `modules.on`). Design: [working together](../architecture/agents.md#working-together), [launching a helper](../architecture/agents.md#launching-a-helper).

## Wrapper

| Field | Value |
|-------|-------|
| id | `task_agents` |
| provides | [`ITaskAgent`](../api/agents.md#itaskagent), once per helper (only the Hub calls them) |
| requires / optional | none (uses [`IAgentNames`](../api/agents.md#iagentnames) when the Hub runs) |
| permissions | `agent.access`: each kind's access list is asked for on one card ([access lists](../architecture/permissions.md#access-lists-built)) |

## Interface

| | |
|---|---|
| Tools | `agents.kinds` (the kinds of helper, each with a free name, and the helpers running), `agents.launch(name, task="", kind="helper")` (from an agent: propose a helper for one task, which needs the task; you get a card, and it starts only if you allow it. From you, the temp UI's **+**: opens it with no launch card, the task optional), `agents.close(agent_id)` (close a launched helper with no task, and free its name) |
| Handles | nothing: each helper is called through `ITaskAgent` |
| Calls | [`ctx.permissions.request_set`](../api/modules.md#modulecontextpermissions) per kind (through [`request_access`](../api/infra.md#agent_access)); [`ReportTask`](../api/agents.md#reporttask) (`milestone` from `STATUS:` lines, `need`, `permission`, `done`, ...); [`StartTask`](../api/agents.md#starttask) (a launched helper's task, as the caller's child) and [`GetTaskStatus`](../api/agents.md#gettaskstatus) (the caller's open task); [`IAgentNames`](../api/agents.md#iagentnames) (`check` at launch, `claim` / `release` through `ProfileAgent`); [`request_approval`](../api/agents.md#itaskagentrequest_approval) on the caller of `agents.launch`; the [Hub's menu](../api/agents.md#the-hubs-menu) through the door, under each helper's own id |
| Publishes | [`AgentActivity`](../api/agents.md#agentactivity), [`AgentStateChanged`](../api/agents.md#agentstatechanged), [`SessionUsage`](../api/agents.md#sessionusage), [`PermissionModeChanged`](../api/agents.md#permissionmodechanged) |
| Listens to | [`ResetRequested`](../api/agents.md#resetrequested) (for one of its helpers) |

## Owns and launches

- **Kinds, not agents:** each section under `[modules.task_agents.agents.<kind>]` is a kind of helper (its prompt, access and workspace). A helper is a [`ProfileAgent`](../api/infra.md#profileagent) (an `AgentProfile`, a `ClaudeSession` and a `SessionTaskAgent`). Its `claude` process starts on its first task, a fresh one per task. Its prompt is the helper prompt with the kind's `prompt` (its role) and the helper's half of the shared block (`STATUS:` for the coordinator, `NEED:` for you).
- **Launched by name:** `agents.launch(name, task, kind)` checks the kind, the name (`IAgentNames.check`, or [`check_agent_id`](../api/infra.md#agent_names) when no Hub runs) and that the caller is an agent with an open task. The Talker, or a caller with no task, is refused with "hand it to the Main Assistant". Then it asks the caller to put it to you ([`request_approval`](../api/agents.md#itaskagentrequest_approval)): the permission card. On Allow it asks for the kind's access list inside that approved run (`request_access(subject=kind, wait=True)`; a saved grant answers at once, otherwise it waits for the card, and Deny fails the launch). Then it builds the helper in `<kind workspace>/<name>` (it reads the kind's workspace, transcript `<name>.jsonl`), provides it, starts it (which claims its name), and sends `StartTask` with the caller's task as parent, so the Hub's cap and folder check apply. The outcome reaches the caller as its next message. Deny or no answer: nothing is built.
- **Opened by you** (the temp UI's **+**; caller `temp_ui`, treated as you here until `ctx.permissions.is_you` exists): no open task and no launch card are needed, and the task is optional. The kind and name are checked at once; the access card and the build run in the background (`busy` says "opening …" meanwhile), so the call returns at once. A failure after that is logged. With no task the helper is idle until your first message to its tab; with one, the task is your own (no parent). Either way `AgentStateChanged` is published once it's provided, so UIs add its tab. `agents.kinds` gives each kind's `free_name` ([`free_agent_id`](../api/infra.md#agent_names) over the taken names).
- **Closing:** `agents.close(agent_id)` stops a launched helper that has no task, frees its name and takes it back with [`ctx.withdraw`](../api/modules.md#modulecontextwithdraw). Then it publishes `AgentStateChanged` for it, as a launch does, so the helper's tab's Talker closes at once and the usage tally marks its rows closed. A launch that fails after providing its helper is taken back the same way.
- **Autostart:** a kind with `autostart = true` starts at launch. `instances = N` gives `<kind>`, `<kind>_2`, ...; with more than one, each writes only `<workspace>/<its id>` and reads the rest, so the Hub's folder check lets them run together.
- **Access per kind:** a grant is saved per kind, so `helper_2` and every launched helper share `helper`'s. On start, every autostart kind's list is asked for at once. While any card waits, the start ends with one `AccessPending` naming them, and your Allow turns the module on. The helpers are then built from each kind's granted config (`instances(kind, config)`).
- **Grants live** (built 2026-11-06, after the restart): it listens to `PermissionChanged` for every kind ([`watch_grant`](../api/infra.md#agent_access)). A kind's new grant reaches all its helpers through `set_access`: autostarted ones get `instances(kind, base)[id]`, launched ones `launched_config(name, base)`, the same function a launch uses (its own sub-folder, the kind's workspace read-only, its transcript). Each helper is built with `subject=kind`, so it may ask with `permissions.request`.
- **Names:** the Hub's rules ([agent names](../architecture/agents.md#agent-names), [`check_agent_id`](../api/infra.md#agent_names)). A taken or reserved name is refused, and the refusal names a free one.

Launched helpers end with the module. A reload restarts every helper in it, so it waits while any of them has a task. A big agent with code of its own (a menu, workers) is bundled with its own module instead, on the same `ProfileAgent` (the multi-agent note's decision); the job agent is the first.

## Config

`[modules.task_agents]`: defaults for every kind. `[modules.task_agents.agents.<kind>]`: one kind, with the keys of `[modules.main_assistant]` plus `description`, `prompt`, `autostart` (start at launch; default false) and `instances` (how many to autostart). The shipped `helper` kind works in `../assistant-helper` (outside the repo, which the Main Assistant writes) and isn't autostarted.

## Code and tests

- `src/assistant/modules/task_agents/module.py`; `src/assistant/infra/profile_agent.py`
- `tests/test_task_agents.py` (two agents at once, `STATUS:` to the coordinator, `NEED:` held until focused, the cap refusing a fourth extra agent, the door under each agent's name, a kind's grant reaching all its helpers, an idle session restarting on a grant and a busy one waiting)
- `tests/test_agent_names.py` (launch proposes, allowed, denied, refused from the Talker or with no task)
- `tests/test_agent_tabs.py` (opened by you: idle or with a task, free names, a denied access card, closing)
