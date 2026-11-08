# Usage: tokens only, clearer labels, two token fixes

> **Status: built (waiting on you), 2026-11-07.** Approved with both recommendations (short labels; the cost field removed entirely). Tests (all 635) and ruff pass; the docs are rebuilt. Needs one app restart, then the hand checks below.

## Build progress (2026-11-07)

**Finished in the last run:** the full suite passes, including the sub-agent published once (the `subagents` filter fixed it). The docs no longer mention ~$ or `cost_usd` ([usage module](../modules/usage.md), `api/infra.md`, the generated module library). The temp UI's per-tab header (item 5) was already in the code and its server-side test passes.

**Done earlier (code; nothing reloaded or restarted):**
- **`infra/claude_session.py`:** no cost. `id` (uuid per object). Sub-agent tokens come per turn from `model_usage_since_last_result`, with cumulative `modelUsage` as a fallback, less the session's own calls since the last result. They're shared among the sub-agents that returned this turn, by last-call size; with none, they go under `unnamed`. Without per-turn numbers, the last-call numbers are used. `subagents` leaves out rows with no tokens yet; that line was the last edit and hasn't been tested.
- **The rest of the code:** `contracts/agents.py` (`SessionUsage`: `cost_usd` removed, `session` added), `infra/session_agent.py` (`session_usage` / `subagent_usage` send `session`; no cost in `_publish_usage`), `infra/usage_ledger.py` (tokens only; banks when the `session` id changes, or on falling numbers when there's no id), `modules/usage/module.py` (texts), `modules/talker/session.py` (`describe_usage(context, used)`, short labels, no ~$), `modules/talker/prompt.py`, `modules/temp_ui/module.py` and `page.html` (tokens only, new tooltip).
- **Tests:** `tests/fake_claude.py` (no `total_cost_usd`; the SUBAGENT turn sends `model_usage_since_last_result`), `tests/test_agents.py` and `tests/test_usage.py` (rewritten, with new tests for the shares, `unnamed` and the session id). Ruff passed before the last edit.

**Next:**
1. **Tests:** run the full suite. The last failure was `test_a_subagents_usage_is_published_once_under_its_parent`: the sub-agent was published twice, first with zeros. The `subagents` filter above should fix it. Then run ruff.
2. **Docs:** remove ~$ / cost and add `session`: [usage module](../modules/usage.md), `api/agents.md` (`SessionUsage`), `api/infra.md` (`ClaudeSession`, `session_usage`, `UsageLedger`), `api/README.md`, `api/reusable.md` if it says cost, `architecture/module-library.md`, `agents/runtime.md`, `agents/README.md`, `modules/README.md`. Find them with `Grep "cost_usd|~\$"` outside `docs/html*` and `archive`. Then rebuild the docs.
3. **Architecture check:** reuse and fit; it's a short one.
4. **Status:** set this note and its Pending row to `built (waiting on you)`: one app restart, then the hand checks below. Ask the user about the restart in a NEED; don't restart or reload.

**Asked:** "I don't need the dollar amounts; keep just the token counts." Label them clearly, and make the two cheap token fixes: a restart must not drop earlier totals, and check whether sub-agent counts cover all their calls.

**Why:** the ~$ is the `claude` tool's own estimate at pay-as-you-go API prices (`total_cost_usd`), not what a subscription bills, so it misleads. The token counts are what you trust. "Used" also looked like new text when it actually counts the cached context resent on every call.

## What changes

1. **Remove the ~$ everywhere it is shown or sent:**
   - **Contract:** `SessionUsage.cost_usd` is dropped.
   - **Counting:** `ClaudeSession` stops reading `total_cost_usd`, and `cost_usd` goes away. `session_usage` and `subagent_usage` stop sending it.
   - **Usage module:** `UsageLedger` and the `usage.total / agents / mine` results drop `cost_usd`.
   - **Talker:** the `[Usage]` line and `describe_usage` drop the ~$, and the Talker's prompt text about it goes too.
   - **Temp UI:** the header total, the dropdown rows and the tooltip drop the ~$.
   - **Tests:** `test_usage`, `test_agents` and `fake_claude` drop it.
   - **Docs:** the [usage module](../modules/usage.md), `api/agents.md` (`SessionUsage`), `api/infra.md`, `api/README.md`, `module-library.md`, `agents/runtime.md` and `modules/README.md`.
2. **Labels.** In the line: `worker: context 45k (last call), used 3.2M (incl. resent cache)`. In the Talker's prompt and the UI tooltip, the full meaning: "context" is the size of the latest call, about what each next call resends. "Used" adds up every call's input, cache writes, cache reads and output since launch, so cached context counts again on every call. It measures work done, not new text.
3. **Restarts can't drop earlier totals.** Today the ledger guesses that a new session started when any number goes down. If a fresh session's first report is already bigger in every number, the old totals are lost. The fix: `SessionUsage` gets a `session` id, a new one per `ClaudeSession` object. When the id changes, the ledger banks the old totals. Restarts of the process inside one session object already carry over, as today.
4. **Sub-agent counts. Checked: they cover only the last call.** In the log of 2026-11-06 (`main_assistant.jsonl`, line 392), an Explore sub-agent with 41 tool uses reported `input 2, cache write 707, cache read 98,361, output 7,168`, which adds up to its `totalTokens` of 106,238. That is the shape of one call: fresh input of 2 and about 99k of context. A run of about 40 calls would report millions. A debugger with 3 tool uses showed the same shape. So today a sub-agent's row shows roughly its final context, not its work.
   - **Fix (recommended):** take sub-agent tokens from each turn's `result`. Its `modelUsage` includes sub-agents (verified 2026-11-05 in [usage tallies](usage-tallies.md)), and its `usage` is the parent's own calls. The difference is all the sub-agents' tokens for that turn. If one sub-agent ran in the turn, its row gets it. If several ran, it's shared in proportion to their last-call sizes, and the parent's total is exact either way.
   - **Unconfirmed until built:** whether `modelUsage` counts a sub-agent's every call when it uses tools. The 2026-11-05 check used a sub-agent with no tools. A test on the real `claude` tool comes first in the build.
5. **The temp UI's header follows the selected tab** (a bug the user found, 2026-11-07). Clicking through agent tabs didn't switch the worker and Talker contexts to that agent's pair. Now the page keeps every agent's own context by id (`SessionUsage` with `kind = "claude"`; sub-agents and tools left out). The header shows the selected tab's worker (`<id>`) and its Talker (`talker` for the Main Assistant's tab, `talker:<id>` for a helper's). **Used** shows that pair's tokens since launch, with their sub-agents, from the `usage` module's rows. It redraws on a tab change, on new usage for any agent and on each new tally. Code: `temp_ui/module.py` (`_on_usage`, every agent's item replayed on connect) and `page.html` (`renderUsage`, called from `showAgents`). Test: `test_temp_ui_keeps_every_agents_context_by_id_so_a_tab_shows_its_own_pair`.

## Restart or reload

- **One app restart:** the contract (`SessionUsage`) and `infra` (`ClaudeSession`, `session_usage`, `UsageLedger`) change.
- It can be batched with the other restarts already waiting. No reload alone is enough.

## Hand checks after the restart

1. **The usage line:** the `[Usage]` line shows no ~$, and its labels read as above.
2. **The temp UI:** the total and the dropdown show tokens only, and the tooltip explains context and used.
3. **Sub-agent counts:** ask the Main Assistant for a task that uses an Explore sub-agent with several tool calls. Its row should now be in the millions-of-tokens range for a long run, not about one context.
4. **Totals survive a reload:** note "all agents used", reload `task_agents` (with your yes), then send a message. The total must not drop.
5. **The header follows the tab:** with two or more agent tabs open, click each in turn. The header's Worker and Talker contexts and its Used must change to that agent's own numbers (they should match its rows in the usage dropdown). Stay on a helper's tab while it works: its numbers update there, and the Main Assistant's don't show.

## Open questions

1. **Short labels in the line, or the full sentence every time?** Recommended: short in the line (`(last call)`, `(incl. resent cache)`), full text in the prompt and tooltip, to keep each line small.
2. **Drop cost from the contract, or keep the field unused?** Recommended: drop it. A module that wraps a paid API could add a cost back later as its own field.
