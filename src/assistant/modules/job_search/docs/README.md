# job_search: the job agent and its menu

## Purpose

The job agent, bundled with its own module: one big agent (id `job_search_agent`) that works in the job project ([job project](job-project.md)), applies to one job per session and runs job searches, plus its `job.*` menu. Off at launch (turn it on with `modules.on`). Design: [working together](../../../../../docs/architecture/agents.md#working-together).

## Wrapper

| Field | Value |
|-------|-------|
| id | `job_search` |
| provides | [`ITaskAgent`](../../../../../docs/api/agents.md#itaskagent), the job agent (only the Hub calls it) |
| requires / optional | none |
| permissions | `agent.access`: it asks for its config's access list when turned on ([access lists](../../../../../docs/architecture/permissions.md#access-lists-built)) |

## Config

`[modules.job_search]`: `ProfileAgent`'s keys plus `agent_id` (default `job_search_agent`: the module id plus `_agent`; transcript `job_search_agent.jsonl`). Shipped: workspace `C:/Chang/Jobs/CV`, reads `C:/Chang/Jobs` and JobRadar, `python` (JobRadar's Python, any arguments), `tools = "default"`, `chrome = true`. These keys are its access list, asked for on one card ([`access_items`](../../../../../docs/api/infra.md#agent_access)). `permission_mode` takes Manual modes only: every session starts in Manual.

`[modules.job_search.ui]` (optional, not part of the access list): `script` (default `<workspace>/Recruiters/scripts/job_ui.py`), `python` (default the section's `python`, JobRadar's, as `job_ui.cmd` uses), `port` (8781), `page` (`/tracker`). With no script or Python, the agent still runs and `job.open_ui` says what's missing.

## Code and tests

- `src/assistant/modules/job_search/module.py`, `ui.py`
- `tests/test_job_search.py`, `tests/fake_job_ui.py` (a stand-in job UI); `CompanionApp`'s command-line mode in `tests/test_app_kit.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), [the job project](job-project.md), and `docs.toml` (its docs tab and group)
