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
| needs | none ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): a core module, it needs no other module by id |
| packages | none |

## Config

None: its `module.toml` holds only `needs = []` and `packages = []`.

## Code and tests

- `src/assistant/modules/usage/module.py`, `module.toml`
- In this folder's `tests/` (on the [test kit](../../../../../docs/api/testkit.md)): `test_usage_module.py` (its `module.toml`, the menu)
- Centrally, with shared parts and other modules: `tests/test_usage.py` (`ClaudeSession`'s sub-agent tally, `UsageLedger`, closed agents with `agent_hub`, the temp UI's total and the Talker's `[Usage]` line)
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
