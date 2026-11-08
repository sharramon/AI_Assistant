# Temp UI: a plus button to open your own agent tab

> **Status: built (waiting on you) (2026-11-05).** Approved with (b) for question 1 and the recommendations for 2 to 4, plus the × confirmation (below). No restart: `RELOAD: task_agents` and `RELOAD: temp_ui`, then press **+** and try **×**. **Later:** `ctx.permissions.is_you(caller)`, so `task_agents` reads the permissions handler's one `you` list instead of its own `YOU = ("temp_ui",)`; do it with the next core change (it changes a contract, so it needs a restart).

## As built (2026-11-05)

- **Decided:** question 1 is (b), with `temp_ui` treated as you inside `task_agents` for now. Questions 2 to 4 follow the recommendations: the first-task box stays, the × is in, and `helper` is the only kind.
- **The × asks first:** every tab except the Main Assistant's has a **×**. It shows "Close this agent?", names the agent, says any running task will be cancelled, and has **Close** and **Cancel** buttons. Nothing closes until you press Close. Then:
  - The agent's running task is cancelled first.
  - **A launched helper** is closed with `agents.close`, which frees its name.
  - **A module's agent** is closed by turning its module off with `modules.off`. For the job agent that's `job_search`, and turning it back on brings the agent back with its saved grant.
  - **An autostarted helper** isn't closed; its × says to turn `task_agents` off.
  - Closing the agent you're talking to moves you back to the Main Assistant.
- **Where it lives:**
  - The page part is `temp_ui/static/agent_tabs.js`, hooked in by one line in `showAgents`.
  - The server part is `temp_ui/agent_tabs.py`, behind one route, `POST /agent-tabs` (`kinds`, `turn_on`, `open`, `close`). This replaces the two routes the proposal planned.
  - `temp_ui` also sends `GetTaskStatus` and `CancelTask`, and reads `IAgentNames` (optional) to find which module an agent belongs to.
- **How the new tab appears:** `task_agents` publishes `AgentStateChanged` once the helper is provided, and the temp UI rebuilds its tabs.
- **Failures:** a failure after the access card (the card denied, or the helper not starting) goes to the log. The status line in the worker pane that the proposal planned isn't built. A denied card already says it was denied.
- **Tests:** `tests/test_agent_tabs.py`, 5 tests:
  - opening idle and with a task, the free names, and a taken or bad name
  - a denied access card opens nothing
  - closing: the Main Assistant refused, an autostarted helper refused, a busy helper's task cancelled then the helper closed, the job agent closed by turning off `job_search`
  - the panel turning the helpers on
  - the page and its warning text

**Asked:** "an option to be able to press a plus symbol and open my own job task AI by myself, just in case I want a separate agent to be working on something that I don't want the main agent" to do.

**Why:** today a helper starts only when the Main Assistant calls `agents.launch` during one of its tasks, and you allow its card. You can't open one yourself, so the Main Assistant is always in the loop.

**Touches:** `temp_ui` (the button, a small form, two routes), `task_agents` (`agents.launch` and `agents.kinds` when the caller is you), their tests, and docs (`docs/modules/temp_ui.md`, `docs/modules/task_agents.md`, [agents: launching a helper](../architecture/agents.md#launching-a-helper), the module library). No new contract, unless you pick the option in open question 1 that adds one.

## How it works

1. **The button:** a **+** at the end of the agent tabs above the worker feed. It shows even when only the Main Assistant's tab is there.
2. **What you pick:** clicking it opens a small form in the worker pane:
   - **Kind:** a dropdown of the kinds from `agents.kinds` (today only `helper`). Each kind shows its description.
   - **Name:** filled in with a free name for that kind (`helper`, or `helper_2` if that's taken). You can type your own, like `flight_search`.
   - **First task** (optional): leave it empty to open an idle tab and type to it afterwards.
   - **Open** / **Cancel**.
3. **Names:** the same rules as every agent. `agents.kinds` also returns a free name per kind, worked out with `free_agent_id` over `IAgentNames.taken()`. On Open, `agents.launch` checks the name with `IAgentNames.check` (or `check_agent_id` when no Hub runs). A bad, reserved or taken name is refused at once. The form shows the reason and fills in the free name it suggests. You gave the name, so nothing is picked for you: you click Open again.
4. **The cards:**
   - **No launch card.** Your click on Open is your yes, so the `request_approval` card is skipped. That card exists to ask you about a launch that an agent proposed.
   - **The access card still applies.** The kind's access list goes through `request_access` as it does now. A saved grant for the kind answers at once. Otherwise the usual access card shows in the Talker pane. Deny, and no tab opens.
5. **The new tab:** on Allow (or with a saved grant), `task_agents` builds the helper the way it does today: `ProfileAgent`, folder `<kind workspace>/<name>`, transcript `<name>.jsonl`. It then provides the helper, and starting the helper claims its name.
   - The temp UI rebuilds its tabs from `ListAgents`, so the new tab appears. The page remembers the name it asked for and sends `SetFocus` to it once it shows up, so you're talking to it straight away.
   - With a first task, that task starts right away (`StartTask`, no parent, so it's your task and not the Main Assistant's child). With no first task, your first message to the focused tab starts one. This already works today: the Talker's PASS calls `hub.send`, which starts a task when the focused agent has none.
   - The Hub's cap (`max_extra_agents`) and its folder check apply when the task starts.
6. **Closing:** a small **×** on the tab of a helper you launched calls `agents.close`. It works only when the helper has no task, and it frees the name. See open question 3.

## Plumbing

The temp UI already calls menu items as you (`InvokeTool` with caller `temp_ui`, as it does for `permissions.revoke`). It adds two routes that reuse that path:
- `POST /agent-kinds` → `agents.kinds`
- `POST /new-agent` → `agents.launch(name, kind, task)`. With no first task, `task` is empty.

In `task_agents`, `agents.launch` gets a second path for when the caller is you:
- **No open task needed** and **no approval card**. The name and kind checks are unchanged.
- **The build runs in the background**, so the call returns at once and doesn't hit the command timeout while the access card waits. The call itself returns refusals (kind, name). A failure after that (access denied, or the helper doesn't start) goes to the log and to a status line in the worker pane ("helper_2 wasn't opened: …").

Agents calling `agents.launch` work exactly as before. If the module isn't on, the form says "Helpers are off" and offers to turn them on through `modules.on task_agents` (the core's menu).

## Reused ([index](../api/reusable.md))

`agents.kinds` / `agents.launch` / `agents.close`, `IAgentNames` (`check`, `taken`), `free_agent_id` / `check_agent_id`, `request_access` and the access card, `ProfileAgent`, `ListAgents` / `SetFocus` and the tab bar, the Hub's PASS-starts-a-task path, and `InvokeTool` as `temp_ui`. Nothing new beyond the two routes, the form, and the "caller is you" branch.

## Tests

- **`tests/test_agent_names.py`:**
  - a launch from `temp_ui` with no task builds an idle helper with no approval card
  - a launch with a first task starts it with no parent
  - a taken name is refused and the free name is suggested
  - `agents.kinds` returns a free name per kind
  - a denied access card opens nothing
  - an agent caller still needs its open task and the card (the existing tests)
- **`tests/test_temp_ui.py`:**
  - `/agent-kinds` and `/new-agent` call the menu items as `temp_ui`
  - the page's agents item lists the new helper
  - `/new-agent` with `task_agents` off says so
- **Then you:** press **+**, open `helper` with no task, allow the access card if it shows, check that the tab opens and takes the focus, type a small task to it, and close it with **×**.
- `pytest` and `ruff`, then the docs rebuild.

## Loading it

If you pick option (b) in open question 1, there's no contract change and no restart: `RELOAD: task_agents` and `RELOAD: temp_ui` load it into the running app. `job_search` stays on.

## Open questions

1. **How does `task_agents` know the caller is you?** The permissions handler already keeps that list (`you = ["temp_ui"]`), but modules can't read it. Two options:
   - (a) Add `ctx.permissions.is_you(caller)`. The rule lives in one place, but it's a contract change, so the app needs a restart.
   - (b) For now, treat caller `temp_ui` as you inside `task_agents`, and move it to (a) with the next core change.

   **Recommended: (a)**, because it builds the rule once. Pick (b) if you'd rather test without a restart.
2. **A first-task box on the form, or only an idle tab?** **Recommended: keep the optional box.** It's one field, and empty means idle.
3. **The × to close a tab, now or later?** **Recommended: now.** It reuses `agents.close`, and without it the names you open stay taken until `task_agents` stops.
4. **Kinds:** today there's only `helper`, a general helper working in `../assistant-helper`. **Recommended: leave the kinds as they are.** A new kind (a second job-style agent, say) is a config section you can add any time.
