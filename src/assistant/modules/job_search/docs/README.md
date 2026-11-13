# job_search: the job agent and its menu

## Purpose

The job agent, bundled with its own module: one big agent (id `job_search_agent`) that works in the job project ([job project](job-project.md)), applies to one job per session and runs job searches, plus its `job.*` menu. Off at launch (turn it on with `modules.on`). Design: [working together](../../../../../docs/architecture/agents.md#working-together).

## Wrapper

| Field | Value |
|-------|-------|
| id | `job_search` |
| provides | [`ITaskAgent`](../../../../../docs/api/agents.md#itaskagent), the job agent (only the Hub calls it) |
| requires / optional | none |
| needs | `cv` ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): turning job_search on turns cv on first, and cv can't be turned off while job_search is on. The code still reaches cv only through its menu (`cv.task`) and its named events |
| packages | none (its job UI and searches run with JobRadar's own Python) |
| permissions | `agent.access`: it asks for its config's access list when turned on ([access lists](../../../../../docs/architecture/permissions.md#access-lists-built)) |

## Config

Defaults in `module.toml` in this module's folder, with their comments; `[modules.job_search]` in the app's config (your `config/local.toml`) only overrides them, key by key ([how a module's config is built](../../../../../docs/api/core.md#app)). `config/default.toml` has no section for it.

The keys: `ProfileAgent`'s, plus `agent_id` (default `job_search_agent`: the module id plus `_agent`; transcript `job_search_agent.jsonl`). Shipped: workspace `C:/Chang/Jobs/CV`, reads `C:/Chang/Jobs` and JobRadar, `python` (JobRadar's Python, any arguments), `tools = "default"`, `chrome = true`. These keys are its access list, asked for on one card ([`access_items`](../../../../../docs/api/infra.md#agent_access)). `permission_mode` takes Manual modes only: every session starts in Manual.

`[modules.job_search.ui]` (optional, not part of the access list): `script` (default `<workspace>/Recruiters/scripts/job_ui.py`), `python` (default the section's `python`, JobRadar's, as `job_ui.cmd` uses), `port` (8781), `page` (`/tracker`). With no script or Python, the agent still runs and `job.open_ui` says what's missing.

## Code and tests

- `src/assistant/modules/job_search/module.py`, `ui.py`, `module.toml` (defaults, `needs`, `packages`)
- `tests/` in this folder, on the [test kit](../../../../../docs/api/testkit.md) only: `test_job_search.py` (the agent, its menu, the job UI, its config under `module.toml`, cv turned on first; cv is a `stand_in`) and `test_cv_events.py` (cv's named events). The stand-in job UI is `fake_job_ui.py` in the test kit (`FAKE_JOB_UI`); `CompanionApp`'s command-line mode is tested in `tests/test_app_kit.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), [the job project](job-project.md), and `docs.toml` (its docs tab and group)
