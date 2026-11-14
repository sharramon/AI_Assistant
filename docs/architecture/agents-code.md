# Agents: code layout

How the agent code is laid out: which classes live in which package, and which method calls which. Back to [Agents](agents.md); the ideas behind it are in [Big agents and their modules](agents.md#big-agents-and-their-modules). How the core passes a call along (door, router, gate, bus) is in [core](core.md).

Three topics run through it: **focus and switching**, **agents reporting to the Main Assistant**, and **the module door**. Each has a picture below.

## The layers

Four packages, and every link points up, toward the core and the contracts:

| Package | Holds | Imports |
|---------|-------|---------|
| `contracts` | Interfaces and plain message types: `ITaskAgent`, `IAgentNames`, `IModuleDoor`, `Menu`, `ReportTask`, `TaskUpdated`, `SetFocus`, `FocusChanged`, `FocusSuggested`, `InvokeTool`, `AgentNotice`, `ResetRequested` | nothing of ours |
| `core` | The ports every module plugs into; knows no agent logic. `ScopedContext` (stamps every command's `sent_by`), `CommandRouter`, `EventBus`, `Container`, `Directory`, `CoreDoor` / `ModuleDoor` (`core/door.py`), `Callers` (`core/callers.py`, the agent names and modes), `dispatch_tool` and `MenuTools` (`core/tools.py`, the one gate), the permissions handler | contracts, infra |
| `infra` | Shared helpers: `ClaudeSession`, `SessionTaskAgent`, `ProfileAgent`, `AgentProfile`, `AgentKit`, `MilestoneFeed`, `agent_tags`, `PermissionGate`, `HandoffKeeper`, `DoorServer` and the stdio relay (`mcp_door.py`) | contracts only |
| `modules` | `agent_hub`, `talker`, `main_assistant`, `task_agents` (core modules), `cv`, `job_search` (add-ons), `temp_ui` | contracts and infra, never another module |

- **No line joins two modules.** Each module reaches the others through the core: a command, an event, a tool call or a contract. `tests/test_boundaries.py` checks the imports.
- **Coordination in the Hub, the checks in the core.** Focus, tasks and reports go through `AgentHubModule` and a few contract types. The door, the agent names and the modes are the core's. The core carries the caller (`ScopedContext` stamps `sent_by`; the door sets the caller its token proved; `dispatch_tool` and `MenuTools.invoke_as` pass it on) and checks it at one gate. Why: the checks then work with the Hub off, and a Hub reload can't drop them ([decisions](decisions.md)).
- **Every big agent is a `ProfileAgent`** (`infra/profile_agent.py`): its `AgentProfile`, its `ClaudeSession` and the `SessionTaskAgent` on it, plus the door under its own name (up before any module, so its first session has it). `main_assistant` has one, `job_search` and `cv` each bundle one (`job_search_agent`, `cv_agent`), and `task_agents` builds one per helper. Every agent module builds its agents through `AgentKit` and declares `AGENT_USES` / `SENDS` / `PUBLISHES` / `LISTENS`.
- **Which CLAUDE.md a session loads is set in `AgentProfile.command`.** With `repo_claude_md = false` (a module's own agent: cv's, the job agent) it passes `--settings {"claudeMdExcludes": [the repo's CLAUDE.md files]}` (`repo_claude_md_files`; `ClaudeSession` turns `settings` into `--settings <json>`) and appends the short developer rules (`infra/developer_rules.md`, through `developer_rules(module_folder)`) to the prompt, with its module's folder and docs page named. Otherwise nothing is excluded, and the session loads whatever CLAUDE.md Claude Code finds from its working folder ([which CLAUDE.md each agent loads](agents.md#which-claudemd-each-agent-loads)).
- **The Hub's parts.** `AgentHubModule` (`agent_hub/module.py`) is a small coordinator. It wires the commands, events and its menu to five parts:
  - `TaskBoard` (`tasks.py`): every `TaskRecord` and the task state machine, the cap, the folder check.
  - `Focus` (`focus.py`): the focused agent, its fallback to the coordinator, releasing what a tab held.
  - `Delivery` (`delivery.py`): the `DeliverMessage` handler. Never into a turn; it waits per agent and tries again on every `AgentStateChanged` / `ModuleStateChanged` (`flush`); `later` holds an answer whose agent is in a turn.
  - `MessageGate` (`gate.py`): an agent's `hub.send` to an agent that isn't its child. It asks `ctx.permissions.ask` with `message:<receiver>`, holds the messages behind one card per pair, then hands them to `Delivery.deliver`.
  - `Reviewer` (`review.py`): the `ReviewAccessList` handler. It runs the access-list review as a short task on the board and answers `AddCardNotes`.

  The Hub `uses` `IAgentNames` from the core. It handles `AgentNotice` (`_on_notice` → `ITaskAgent.note`) and `ResetRequested` (`_on_reset` → `ITaskAgent.reset()`) as commands, and listens to `PermissionModeChanged` (`TaskBoard.on_mode_changed` closes the card a switch to Auto answered). It keeps only the running-agent lookup (`_agents`, `_agent`) and the coordinator's feed (`_feed`), which it hands to the parts. A held question is `TaskRecord.held` next to its `question`; `Focus.set` releases it through `TaskBoard.release`.
- **A question is its task record.** On a `need`, `TaskBoard.report` makes the record `idle` with its question and `question_key` and drops its holder (`TaskRecord.asked`); the agent is free. `TaskBoard.send` into an asked record calls `_answer`, which assigns the same task id again ("Answer to your question …"); if the agent is active, `AgentHubModule._send` hands the answer to `Delivery.later`. `export_questions` / `restore` carry the asked records over a Hub reload.
- **The Talker reaches the Hub only through its menu.** Its mode switch and card answers are `hub.mode` (Manual only) and `hub.answer`, both `callers=("talker",)`, like `hub.focus`. The UI sends `SetPermissionMode` and `AnswerPermission` as commands (your own clicks). The core handles `SetPermissionMode` (Auto only from you); the Hub's `hub.mode` sends it on. A Talker session's reset is the Talker's own menu item, `talker.reset`, for you only.
- **SHOW tags go through one helper.** `SessionTaskAgent._show` and the Talker's `SHOW` tag both call [`show_page`](../api/infra.md#show_page) (`infra/show_pages.py`), which opens the page through the page-opener slot ([`IPageOpener`](../api/modules.md#ipageopener), filled by an add-on; started on use with `StartProvider`); each words its own message from the outcome. temp_ui's Open in viewer button uses the same helper's `open_page`.
- **The worker's parts.** `SessionTaskAgent` keeps the task state machine and composes a `PermissionGate` (the one open question, the Auto policy, the `git push` block), a `HandoffKeeper` (handoff count, reminder and reset texts) and a `LastLineTags` table (`_finish_turn` looks up `NEED` / `RELOAD` / `ADD_MODULE` / `HANDOFF`); the session's `UsageMeter` counts tokens. A `NEED` goes through `_ask_user`: it reports the question with its key and drops the task; the agent is `idle` once the Hub has it. The owning module sets the key and the notes with `set_context(key, notes)` (default `default_context`: the handoff note); `assign` of an answer carries on in the live session or adds the notes to a fresh one (`_first_text`).
- **The Talker's parts.** `TalkerModule` routes and holds `hub(name, **args)`, the one call to the Hub's menu (`InvokeTool`); `RestartFlow` (`talker/restart.py`) is the main tab's restart; each `TalkerSession` runs its tags from a table (`_tags`, one `_tag_*` handler each) and uses the module only through its methods for the sessions (`task_started`, `usage_of`, `hub`, `restart`, ...).
- **The feed lives in each agent.** The Hub passes milestones, task ends and focus moves to the coordinator with `ITaskAgent.note`; the agent's `MilestoneFeed` keeps them and `_with_feed` adds them to its next message, its own `CONTINUE` turns included. Nothing wakes the coordinator: an interrupt would cost it a full step at its whole context.

## 1. Focus and switching

Each big box is a class with the file it lives in; the small boxes are its methods. **Solid** arrows are direct calls; **dashed** ones go through the core (`ctx.send` → `CommandRouter` → handler, or `ctx.publish` → `EventBus` → listener, or the door's hop), with the message on the edge.

```mermaid
flowchart LR
  subgraph UI["TempUIModule · modules/temp_ui/module.py"]
    ui_serve["_serve<br/>POST /focus: tab click"]
    ui_focus["_on_focus<br/>marks the tab, clears !"]
    ui_task["_on_task<br/>! when a question is held"]
  end

  subgraph TK["TalkerModule · modules/talker/module.py (the router)"]
    tk_input["_on_input<br/>by InputReceived.agent_id, else the focus"]
    tk_fc["_on_focus<br/>the released items, in their tab's session"]
    tk_sug["_on_suggestion<br/>asks you yes or no"]
    tk_tu["_on_task_updated<br/>to its agent's session"]
    tk_hub["hub(name, args)<br/>InvokeTool hub.*"]
  end

  subgraph TS["TalkerSession ×N · modules/talker/session.py (one per tab)"]
    tk_handle["_handle"]
    tk_turn["_take_turn"]
    tk_tag["_run_tag<br/>_tags: tags act on its partner"]
  end

  subgraph MCL["Main Assistant's claude session"]
    mcl_use["use_item<br/>hub.suggest_focus"]
  end

  subgraph HUB["AgentHubModule · agent_hub/module.py, with Focus (focus.py) and TaskBoard (tasks.py)"]
    h_send_item["send_item · hub.send<br/>agent_id: its child straight in, else the gate<br/>neither (the Talker): the focused agent"]
    h_gate["MessageGate.send<br/>a card, then Delivery.deliver"]
    h_focus_item["focus_item · hub.focus<br/>callers: talker"]
    h_suggest["suggest_focus_item<br/>the coordinator only"]
    h_setfocus["Focus.set<br/>SetFocus handler, releases held"]
    h_focused["Focus.focused"]
    h_report["TaskBoard.report<br/>NEED · PERMISSION · REPLY ·<br/>DONE · FAILED: held unless focused"]
    h_sendtask["TaskBoard.send"]
    h_start["TaskBoard.start"]
    h_updated["TaskBoard._updated"]
    h_feed["_feed<br/>note to the coordinator"]
  end

  ui_serve -. "SetFocus" .-> h_setfocus
  tk_input -- "inbox" --> tk_handle
  tk_fc -- "inbox" --> tk_handle
  tk_sug -- "inbox" --> tk_handle
  tk_tu -- "inbox" --> tk_handle
  tk_handle --> tk_turn
  tk_handle -- "reply's tags" --> tk_tag
  tk_tag --> tk_hub
  tk_hub -. "InvokeTool hub.send<br/>router → gate" .-> h_send_item
  tk_hub -. "InvokeTool hub.focus<br/>after you say yes" .-> h_focus_item
  mcl_use -. "door → router → gate" .-> h_suggest

  h_send_item --> h_focused
  h_send_item -- "task open" --> h_sendtask
  h_send_item -- "no task" --> h_start
  h_send_item -- "not its child" --> h_gate
  h_focus_item --> h_setfocus
  h_setfocus --> h_feed
  h_report --> h_focused
  h_report --> h_updated

  h_suggest -. "FocusSuggested" .-> tk_sug
  h_setfocus -. "FocusChanged(agent_id, released)" .-> tk_fc
  h_setfocus -. "FocusChanged" .-> ui_focus
  h_updated -. "TaskUpdated" .-> tk_tu
  h_updated -. "TaskUpdated" .-> ui_task
```

**How it reads:** a tab click sends `SetFocus`. The four `_on_*` methods on `TalkerModule` pick the session: your words go to their tab's `TalkerSession`, whose `PASS` tag sends them on through `TalkerModule.hub` with `hub.send(agent_id=its partner)`, so they reach that agent's task, or start one. The Main Assistant can only suggest: `hub.suggest_focus` publishes `FocusSuggested`, the tab's Talker asks you, and the focus moves only when you say yes (`FOCUS` → `hub.focus`, an item only the Talkers may use). A question, reply or end from an agent out of focus is held on its task record; `Focus.set` releases it (`TaskBoard.release`) in `FocusChanged`, and that tab's Talker says it then.

## 2. Agents reporting to the Main Assistant

```mermaid
flowchart LR
  subgraph MODS["MainAssistantModule.init · JobSearchModule.start · CvModule · TaskAgentsModule._build"]
    m_new["ProfileAgent(ctx, id, config, prompt)<br/>then AgentKit.add → ctx.provide ITaskAgent"]
  end

  subgraph PA["ProfileAgent · infra/profile_agent.py"]
    pa_init["__init__<br/>profile · session · agent"]
    pa_door["door()<br/>mcp_config under its own id"]
  end

  subgraph PROF["AgentProfile · infra/agent_profile.py"]
    p_from["from_config"]
    p_cmd["command(prompt, mode, door)<br/>repo_claude_md = false:<br/>--settings claudeMdExcludes + developer rules"]
  end

  subgraph STA["SessionTaskAgent · infra/session_agent.py"]
    s_assign["assign(task)"]
    s_message["message(task_id, text)"]
    s_note["note(text)"]
    s_with["_with_feed"]
    s_send["_send<br/>CONTINUE turns too"]
    s_block["_on_block<br/>STATUS lines"]
    s_result["_on_result"]
    s_finish["_finish_turn<br/>LastLineTags: NEED · RELOAD · ADD_MODULE · HANDOFF<br/>else DONE"]
    s_parts["PermissionGate · HandoffKeeper<br/>(composed in)"]
    s_report["_report(kind, text)"]
    s_sendrep["_send_reports<br/>queue, then ctx.send"]
  end

  subgraph FEED["MilestoneFeed · infra/milestone_feed.py"]
    f_add["add(line)"]
    f_take["take(max_lines)"]
  end

  subgraph TAGS["agent_tags · infra/agent_tags.py (functions)"]
    t_status["status_lines"]
    t_last["last_line"]
  end

  subgraph HUB["AgentHubModule · agent_hub/module.py, with TaskBoard (tasks.py)"]
    h_report["TaskBoard.report"]
    h_finish["TaskBoard._finish"]
    h_updated["TaskBoard._updated"]
    h_feed["_feed<br/>coordinator.note(line)"]
  end

  subgraph TK["TalkerModule"]
    tk_tu["_on_task_updated<br/>skips milestones,<br/>the rest to its agent's session"]
  end

  subgraph UI["TempUIModule"]
    ui_task["_on_task<br/>line in the agent's tab"]
  end

  m_new --> pa_init
  pa_init --> p_from
  pa_init -- "the session's command" --> p_cmd
  p_cmd --> pa_door

  s_assign --> s_with
  s_message --> s_with
  s_send --> s_with
  s_with --> f_take
  s_note --> f_add
  s_block --> t_status
  s_block -- "MILESTONE" --> s_report
  s_result --> s_finish
  s_finish --> t_last
  s_finish -- "NEED · DONE · FAILED" --> s_report
  s_report --> s_sendrep
  s_sendrep -. "ReportTask" .-> h_report

  h_report -- "MILESTONE, not the coordinator's" --> h_feed
  h_report -- "DONE · FAILED" --> h_finish
  h_report --> h_updated
  h_finish --> h_updated
  h_finish -- "a helper's task ended" --> h_feed
  h_feed -- "via ITaskAgent" --> s_note

  h_updated -. "TaskUpdated" .-> tk_tu
  h_updated -. "TaskUpdated" .-> ui_task
```

**How it reads:** a helper writes `STATUS: …`. `_on_block` picks it out with `status_lines`, and it reaches the Hub as a `ReportTask` of kind `milestone`. The Hub hands it to the coordinator's agent with `note`, which files it in that agent's `MilestoneFeed`. The Main Assistant sees the feed as one block at the end of its next message, task or `CONTINUE` turn (`_with_feed`). The loop Hub → agent → `ReportTask` → Hub is safe: reports go through the `_send_reports` queue and the router, never back into the same call.

## 3. The module door

```mermaid
flowchart LR
  subgraph AG["ProfileAgent · TalkerSession.command"]
    a_door["mcp_config(own id)"]
  end
  subgraph HDOOR["ModuleDoor · IModuleDoor · core/door.py (bound to the asking module)"]
    door_cfg["mcp_config(caller)<br/>only its own id or an id it claimed"]
  end

  subgraph CS["claude -p · the agent's process"]
    cs_tool["mcp__modules__use_item<br/>name, args"]
  end

  subgraph RELAY["relay · infra/mcp_door.py · own process"]
    r_relay["relay()<br/>JSON-RPC on stdin"]
    r_answer["answer(message, url, token, caller)"]
    r_post["_post"]
  end

  subgraph DS["DoorServer · infra/mcp_door.py"]
    d_cfg["mcp_config(caller)<br/>token_for(caller)"]
    d_serve["_serve<br/>checks token → caller"]
    d_call["call(tool, arguments, caller)"]
  end

  subgraph CTX["CoreDoor · core/door.py (opened by App before the modules)"]
    c_send["router.send(command)<br/>the core's own send, the caller its token proved"]
  end
  subgraph RT["CommandRouter · core/router.py"]
    rt_send["send(command)"]
  end
  subgraph TOOLS["core/tools.py"]
    dt["dispatch_tool · the one gate<br/>start on use first, then for an ask item:<br/>args · callers · confirm card (answers at once)"]
    prov["_providers(name)<br/>MenuTable, then IToolProvider modules"]
    mt_inv["MenuTools.invoke_as(name, args, caller)"]
  end
  subgraph APP["App · core/app.py"]
    app_sou["start on use<br/>module off, item on its menu"]
  end
  subgraph MENU["Menu · contracts/menu.py"]
    m_call["call(module, name, args, caller)"]
    m_allowed["allowed(name, caller)"]
    m_check["check(name, args)"]
  end

  subgraph JOB["JobSearchModule · modules/job_search/module.py"]
    j_search["search(days, caller) · job.search<br/>answers at once (the runner is a stub)"]
  end

  subgraph HUB["AgentHubModule · modules/agent_hub/module.py"]
    h_notice["_on_notice"]
  end
  subgraph JA["SessionTaskAgent · the caller's agent"]
    ja_note["note(text)"]
  end

  a_door --> door_cfg
  door_cfg --> d_cfg

  cs_tool -- "stdio" --> r_relay
  r_relay --> r_answer
  r_answer --> r_post
  r_post -. "HTTP POST /tool + token" .-> d_serve
  d_serve --> d_call
  d_call -- "InvokeTool(name, args, caller)" --> c_send
  c_send --> rt_send
  rt_send --> dt
  dt --> prov
  dt -- "nobody offers it" --> app_sou
  dt --> mt_inv
  mt_inv --> m_call
  m_call --> m_allowed
  m_call --> m_check
  m_call -- "runs the item" --> j_search

  j_search -. "command AgentNotice(agent_id = caller)" .-> h_notice
  h_notice -- "via ITaskAgent" --> ja_note
```

**How it reads:** each session's door config carries a token for its own id, so `DoorServer` knows the caller and the agent can't fake it. A module gets a config only for itself or an agent id it claimed in Callers (`ModuleDoor`). Every module's own `InvokeTool` gets its own id stamped by `ScopedContext.send`; only the core's door passes on the one its token proved. The caller rides on `InvokeTool` through the router and the gate down to the menu item: `Menu.call` checks the item's `callers` and its arguments; for an item marked `ask`, `dispatch_tool` checks them first and opens a `confirm` card. `job.search` returns at once; it sends the `AgentNotice` command for the caller, and the Hub passes it to that agent with `note`, labelled `[job_search]` (the stamped sender), for its next message. The search runner isn't built, so the note says nothing ran.

Two spots that work in a way you might not expect:

- **Start on use comes first.** `dispatch_tool` turns on an off `start_on_use` module before it checks the caller (`core/tools.py:87-92`, then `:105`), so a caller who may not use the item can still switch that module on.
- **The gate doesn't wait for the card.** For an `ask` item it answers "asked on a card" at once; after your Allow the permissions handler runs the step itself ([permissions](permissions.md)).

## Known limits

- **A name in config:** the Hub knows the coordinator by id (`coordinator` in `[modules.agent_hub]`, default `main_assistant`). A replacement Main Assistant must keep that id, or change the setting.
- **Most items ask for themselves:** only the core's `modules.add / remove / reload / off` carry an `ask` mark that `dispatch_tool` checks. Other items that ask (`agents.launch`, `permissions.grant / revoke`) ask in their own code (`request_approval`, a card), so a new risky item must be marked `ask="always"` or `"risky"`, or it won't ask.
- **A bundled agent reloads with its module:** reloading `job_search` restarts its agent, so the reload waits while that agent is busy (`busy()`).
- **The core still names agents in three spots.** `core/callers.py:22` reserves the ids `hub` and `talker`; `core/permissions/handler.py:85` maps a `talker:` prefix to its worker's mode; `core/context.py:53-54,187` lets any module that provides `ITaskAgent` send `ReloadModule` / `AddModule`, while the Allow card for those is asked in infra (`PermissionGate`), so the core trusts the role, not your answer. Each could come from config, like `relays`.
- **The CLAUDE.md exclude list covers only the repo's files** (`infra/agent_profile.py:121-125`). A module agent working under an add-ons folder outside the repo would load any CLAUDE.md it finds in a parent folder there, and the developer rules point at repo paths it may not be able to read.
