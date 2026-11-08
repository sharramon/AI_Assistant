# Closing a helper's tab ends its Talker at once, and its usage row says "closed"

> **Status: built (waiting on you), 2026-11-06.** Found by hand check 6 of the `agent-talkers` change note. Approved as written on 2026-11-06: both fixes, closed rows greyed and kept in the totals. Built: `task_agents.close_item` publishes `AgentStateChanged` and logs "Closed helper"; `usage` notes the agents it has seen (`ListAgents` on `AgentStateChanged` / `ModuleStateChanged`), marks `closed` in `usage.agents` and hands the seen set over on reload; `temp_ui` asks for the tally again when an agent leaves its tabs and greys closed rows ("· closed"). Tests: `test_usage.py::test_a_closed_agents_rows_say_closed_and_stay_in_the_total`, and `agents.close`'s event in `test_agent_names.py`. Left: `RELOAD: task_agents`, `RELOAD: usage`, `RELOAD: temp_ui`, then redo hand check 6.

**Asked:** hand check 6 failed. After you closed the helper's tab (its ×), both usage rows, `helper` and `talker:helper`, were still in the usage dropdown. Find out what closing a tab should do, what it actually does, and where it goes wrong.

## What should happen

From the `agent-talkers` note ("How a tab's Talker starts and ends") and the `plus-agent-tab` note: the × on a helper you opened with **+** cancels its task, then calls `agents.close`. That stops the helper's `claude` session and frees its name. The tab's Talker **closes when its agent is gone**: the talker module re-reads `ListAgents` on `AgentStateChanged` and `ModuleStateChanged`, and closes the session of any agent that's no longer listed. No doc says what happens to a closed agent's usage row. The ledger keeps every agent's usage "since launch".

## What actually happened (this launch's log)

- 23:07:38: "Opened helper helper (helper), idle" and "Talker for helper's tab opened". The helper was opened with **+**, so the × took the `agents.close` path.
- Between 23:17:56 and 23:18:53: you pressed ×. Nothing is logged, because `agents.close` writes no log line.
- 23:19:01: "Talker for helper's tab closed: its agent is gone", at the same moment as "Task 657a3e72 started on main_assistant". The Talker closed only because the Main Assistant's next state change made it re-read `ListAgents`.
- Processes now: the only `claude` processes running are the main Talker's and the Main Assistant's. Neither the helper's process nor its Talker's is still running.

So **the processes do end** (the helper's at the close, its Talker's late, at the next unrelated agent event), but **the usage rows stay**.

## The two causes

1. **`agents.close` tells no one.** `TaskAgentsModule.close_item` (`task_agents/module.py`) stops the helper and withdraws it, but publishes nothing. The talker module only checks for gone agents on `AgentStateChanged` / `ModuleStateChanged`, so the helper's Talker stays open until some other agent's state changes. That could be seconds or hours later. Opening a helper does publish an event (`AgentStateChanged`, "UIs add its tab"), but closing one doesn't. The temp UI's tab disappears only because the temp UI re-reads `ListAgents` itself after its own close call. The other close path, `modules.off` for the job agent, is fine: it publishes `ModuleStateChanged`. The test (`test_a_helper_tabs_talker_starts_on_use_..._closes_with_its_agent`) uses `DeactivateModule`, so it never covered `agents.close`.
2. **The usage ledger never removes or marks a row.** `UsageLedger` keeps every agent's latest totals since launch, on purpose, so the total stays honest. Nothing tells it, or the dropdown, that an agent has ended, so `helper` and `talker:helper` look just like live agents.

## Proposed fix

1. **`agents.close` says the helper is gone.** After `_take_back`, `close_item` publishes `AgentStateChanged(agent_id=<name>, busy=False, working=False)`, the same event a launch sends, and logs "Closed helper <name>". The talker module's existing `_refresh_agents` then closes that tab's Talker at once (its process ends, and its history is kept in case the name comes back). No new part: the event and the handler already exist. One test: `agents.close` on an opened helper closes its Talker session straight away.
2. **A closed agent's usage stays in the totals, and its row is marked closed** (proposed; change it if you'd rather drop the rows). The `usage` module also listens to `AgentStateChanged` / `ModuleStateChanged` and re-reads `ListAgents`. An agent that was listed before and isn't now is *closed*. Its row, and the rows nested under it (its Talker `talker:<name>`, its sub-agents), get `"closed": true` in `usage.agents`. The temp UI's dropdown shows such a row greyed, with "closed". Totals don't change, because the money was spent. If the name comes back (a new helper with the same name), the mark clears and its numbers carry on, as the ledger already does for a restarted session. The mark lives in the `usage` module, not in `UsageLedger` (`assistant.infra`), so the ledger stays plain and needs no restart. Tests: a row is marked closed when its agent leaves `ListAgents`, its Talker row too, and the total is unchanged.

Alternatives for 2: drop the closed rows but keep their numbers in the total (the dropdown no longer adds up), or leave the rows unmarked as today (the check's expectation changes instead).

## Touches

`task_agents` (fix 1), `usage` and `temp_ui` (fix 2: the dropdown's greyed row). Docs: the module pages [task_agents](../modules/task_agents.md), [usage](../modules/usage.md) and [temp_ui](../modules/temp_ui.md), and the `usage.agents` entry in the API pages. Check [reusable](../api/reusable.md) for `UsageLedger`'s Used by line (unchanged).

## Restart?

**No restart.** All three are modules, so they reload while the app runs: `RELOAD: task_agents`, `RELOAD: usage`, `RELOAD: temp_ui`. No contract, core, infra or `app_kit` change. Then redo hand check 6: open a helper with **+**, use its tab once, close it, and check that the log says "Talker for helper's tab closed" at once and that both rows read "closed" in the dropdown.
