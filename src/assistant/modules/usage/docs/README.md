# usage: every agent's tokens since launch

## Purpose

Keeps the usage tally of the whole app: every agent's tokens since the app started (tokens only: the `claude` tool's dollar estimate is at pay-as-you-go API prices, not what a subscription bills, so it isn't kept), with each agent's sub-agents and wrapped tools nested under it, and the Talker as its own row. It listens to [`SessionUsage`](../../../../../docs/api/agents.md#sessionusage) from every sender and keeps one [`UsageLedger`](../../../../../docs/api/infra.md#usageledger). Kept in memory only: nothing is written to disk, and the tally ends with the app. No time buckets, no history, no spend alerts. On at launch.

## Wrapper

| Field | Value |
|-------|-------|
| id | `usage` |
| provides | nothing |
| requires / optional | none |
| permissions | none |

## Config

None.

## Code and tests

- `src/assistant/modules/usage/module.py`
- `tests/test_usage.py`: the menu, `ClaudeSession`'s sub-agent tally, `UsageLedger`, closed agents (with `agent_hub`), the temp UI's total and the Talker's `[Usage]` line
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
