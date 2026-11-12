# Usage tallies for all agents

**Status:** built, 2026-11-05: the `SessionUsage` fields `parent` and `kind`, sub-agent tallies in `ClaudeSession`, `UsageLedger`, the `usage` module (`usage.total / agents / mine`), the Talker's `[Usage]` line, and the temp UI's total and dropdown. Needs an app restart (the contract changed). Docs: [usage module](../../src/assistant/modules/usage/docs/README.md).

## What you asked for

1. Every agent (the Main Assistant, each helper, the job agent, the Talker) keeps its own running tally of tokens and ~$, **including the sub-agents it starts**, so it can say how much it has burned.
2. The main window shows the **total across all agents** since the app launched.
3. A **dropdown** shows each agent's share: one row per agent, its sub-agents nested under it.
4. It works for **any module that wraps a tool**, not only `claude` sessions or the job agent.

Only totals since launch. No history over time, no spend alerts, nothing kept after the app closes.

## What exists today

- **`SessionUsage`** (event, `contracts/agents.py`): one agent's numbers. Context now, tokens by kind (input, cache write, cache read, output), and `cost_usd` (`claude`'s own estimate at API prices). The numbers are **running totals since launch**, not per call. Agents are never added together.
- **`ClaudeSession`** (`infra/claude_session.py`) counts them: each assistant line's `usage` once per message id, the output from each turn's `result`, and the cost from the result's `total_cost_usd`. Totals carry over process restarts.
- **`session_usage`** turns a session's numbers into a `SessionUsage`. `SessionTaskAgent` publishes it on every change (so the Main Assistant, helpers and the job agent all do); the Talker publishes its own after each turn.
- **`ContextWatch`** warns once when a context passes a size. It is about context, not spend, and stays as it is.
- **The Talker** puts a `[Usage]` line before each of your messages, but only for "the worker" and itself.
- **The temp UI header** has two meters, Worker and Talker. It only shows usage for agents shown in a pane, so a helper or the job agent in its own tab is dropped.

**Missing:** a total, a per-agent list, sub-agent usage (see below), and a way for a non-`claude` tool to report usage.

## Verified (2026-11-05)

One real run: `claude -p` with the app's own `claude_command` flags (`--input-format stream-json --output-format stream-json --verbose`, `--tools Agent,Task`). The main session called the Agent tool once (`general-purpose`, "reply with pong").

**The sub-agent's own lines don't stream.** Only its prompt shows, as a `user` line with `parent_tool_use_id` (the Agent call's `tool_use` id), `agent_id`, `subagent_type` and `task_description`. No sub-agent `assistant` line, so no per-call `usage` for it. (The sub-agent made no tool calls; one that does wasn't checked.)

**Its usage comes back on the Agent call's result**, in the `user` line with the `tool_result`:
- `tool_use_result.usage`: the sub-agent's tokens by kind (`input_tokens` 2, `cache_creation_input_tokens` 2874, `cache_read_input_tokens` 0, `output_tokens` 4).
- `tool_use_result.agentId`, `agentType`, `resolvedModel`, `totalTokens` (2880), `totalToolUseCount`, `totalDurationMs`.
- Also a `system` line, subtype `task_notification`, with `task_id`, `tool_use_id` and `usage.total_tokens` (total only). `task_started` comes first, with `spawn_depth`.
- No cost per sub-agent anywhere.

**The turn's `result`:**
- `usage` is the **parent's own** calls only (input 4, cache write 5405, cache read 5065, output 157).
- `modelUsage` (per model) and `total_cost_usd` **include the sub-agent**: `inputTokens` 6 = 4 + 2, `cacheCreationInputTokens` 8279 = 5405 + 2874, `outputTokens` 161 = 157 + 4, `costUSD` = `total_cost_usd` = 0.061867.
- `subagent_stats` counts sub-agents (`spawned`, `completed`, `by_type`, `max_depth`), with no usage.

**What it means:**
- Today `ClaudeSession`'s **~$ already includes sub-agents, but its tokens don't.** The design fixes the tokens, not the cost.
- `context_tokens` isn't thrown off: no sub-agent line carries `usage`. Lines with a `parent_tool_use_id` still never change the parent's context, in case a sub-agent with tools streams more.
- A sub-agent **can have its own row for tokens**, keyed by `agentId`, named by `agentType`, nested under its parent. Its ~$ is only part of the parent's; the row shows tokens, and the parent's ~$ covers both.

## Where the totals live

One reusable part, in its own module.

- **`UsageLedger`** (new, `infra/usage_ledger.py`, plain Python, no app imports): takes `SessionUsage` events and keeps, per agent, its latest totals since launch. Gives `total()`, `by_agent()` (sub-agents under their parent), and `mine(agent)` (the agent plus its sub-agents). Nothing in `reusable.md` does this today; `ContextWatch` and `session_usage` are reused as they are.
- **`usage` module** (new, on by default): listens to `SessionUsage`, feeds the ledger, and offers a menu on the door: `usage.total`, `usage.agents`, `usage.mine` (the door knows the caller, so an agent asks for its own tally with no arguments). This is how each agent "knows" its burn: it asks, and nothing extra goes into every turn. It keeps nothing on disk; the tally ends with the app.

**Why running totals, not per-call amounts:** a lost or late event can't throw the sum off; the ledger keeps the latest.

## Tools that aren't `claude` sessions

Any module publishes the same `SessionUsage` for what it wraps (an API call, a script that reports tokens) under its own id. Two new fields on the event make this and sub-agents fit:

- `parent: str = ""`: who started it (a sub-agent's parent agent; a tool's calling agent). The ledger rolls it up into the parent's tally and still lists it apart.
- `kind: str = "claude"`: `claude`, `subagent`, or `tool`, for the dropdown.

A tool that only knows cost, or only tokens, leaves the rest at 0. A sub-agent's cost is 0, since its parent's cost already holds it. A tool with no usage at all publishes nothing.

## What the temp UI shows (throwaway)

Kept small; it's a stand-in until the UI handler is designed.

- The header's two meters become **one total**: `Total 3.4M · ~$4.10`.
- Clicking it opens a **dropdown**: one row per agent (tokens, ~$), the Talker as its own row, and sub-agents nested under their parent (tokens only).
- Context stays where it is today (per pane), since it's about one session, not spend.

## What has to be built

1. **Contract:** `parent` and `kind` on `SessionUsage` (defaults keep every current sender working). **Needs an app restart.**
2. **`ClaudeSession`:** read each Agent call's `tool_use_result.usage` into a per-sub-agent tally (by `agentId`), skip `parent_tool_use_id` lines for context; `session_usage` publishes each sub-agent's tally with `parent` set and cost 0.
3. **`UsageLedger`** with tests (roll-up, a lost event, a restarted session).
4. **`usage` module:** the ledger and the menu; manifest and module page.
5. **Talker:** its `[Usage]` line uses `usage.total` and your focused agent, instead of only "the worker".
6. **Temp UI:** the total and the dropdown.
7. **Docs:** API pages, the reusable index (`UsageLedger`, Used by `usage`), module library; tests, ruff, docs build.

## Decided (2026-11-05)

1. **History after the app closes:** none. The tally is since launch and ends with the app.
2. **Time buckets and history over time:** dropped. Only the totals per agent since launch.
3. **The dropdown:** by agent, with sub-agents nested under their parent agent.
4. **The Talker:** counts in the total, as its own row.
5. **Spend alerts:** none.
6. **Where the ledger lives:** its own `usage` module, not inside `agent_hub`. Usage comes from tools too, not only agents, and the Hub stays about coordination.
