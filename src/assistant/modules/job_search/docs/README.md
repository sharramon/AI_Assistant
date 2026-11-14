# job_search: the job agent and its menu

## Purpose

The job agent, bundled with its own module: one big agent (id `job_search_agent`) that works in the job project ([job project](job-project.md)), applies to one job per session and runs job searches, plus its `job.*` menu. Off at launch (turn it on with `modules.on`). Design: [working together](../../../../../docs/architecture/agents.md#working-together).

## Wrapper

| Field | Value |
|-------|-------|
| id | `job_search` |
| provides | [`ITaskAgent`](../../../../../docs/api/agents.md#itaskagent), the job agent (only the Hub calls it) |
| requires / optional | none |
| needs | none (`needs = []`, [`Manifest.needs`](../../../../../docs/api/modules.md#manifest), since 2026-11-13): turning job_search on turns on only job_search. cv comes on only when the job agent needs a CV: its `job.tailor_cv` turns cv on then ([on-demand chaining](../../../../../docs/architecture/modules.md#dependencies); in Manual cv_agent's access card shows at that moment), sends `cv.task` for the agent and hears cv's named events. If cv can't come on (a Deny, a failure, or no answer in `cv_wait` seconds), the agent is told and asks you whether to use your chosen PDF untailored. The code reaches cv only through `ActivateModule`, its menu (`cv.task`) and its named events |
| packages | none (its job UI and searches run with JobRadar's own Python) |
| permissions | `agent.access`: it asks for its config's access list when turned on ([access lists](../../../../../docs/architecture/permissions.md#access-lists-built)) |

## Config

Defaults in `module.toml` in this module's folder, with their comments; your `config/job_search.toml` (top-level keys, gitignored; `[modules.job_search]` in `config/local.toml` still works, last) only overrides them, key by key ([how a module's config is built](../../../../../docs/api/core.md#app)). `config/default.toml` has no section for it.

The keys: `ProfileAgent`'s, plus `cv_wait` (default 600: seconds `job.tailor_cv` waits for cv to come on, your answer on its card included) and `agent_id` (default `job_search_agent`: the module id plus `_agent`; transcript `job_search_agent.jsonl`). Shipped: workspace `workspace` (the module's own `workspace/`, gitignored; a relative path is from the module's folder, [`in_module_folder`](../../../../../docs/api/infra.md#agent_access)), `documents` empty (your CV folder, read and write, set in the gitignored `config/local.toml`; it joins `write_dirs`), reads `C:/Jobs` and JobRadar, `python` (JobRadar's Python, any arguments), `tools = "default"`, `chrome = true`. These keys are its access list, asked for on one card ([`access_items`](../../../../../docs/api/infra.md#agent_access)). `permission_mode` takes Manual modes only: every session starts in Manual.

**Your data folder** (module layout step 1, 2026-11-13): `data_folder = "C:/…"` (outside the repo) in the gitignored `config/job_search.toml` is then the agent's workspace (the job project, its state, scripts and `job_paths.json`). At its first use the old workspace is copied in (never moved or deleted) and the copy's relative `job_paths.json` paths (the `cv_output` link into cv's workspace) are written absolute, from the old place; the new workspace asks with a new access card. Unset, nothing moves ([`data_folder`](../../../../../docs/api/infra.md#agent_access)). `repo_claude_md = false`: the agent skips the repo's CLAUDE.md and gets the short developer rules in its prompt; its project's own CLAUDE.md, in its workspace, still loads.

`[modules.job_search.ui]` (optional, not part of the access list): `script` (default `<workspace>/Recruiters/scripts/job_ui.py`), `python` (default the section's `python`, JobRadar's, as the old `job_ui.cmd` used), `port` (8781), `page` (`/tracker`). With no script or Python, the agent still runs and `job.open_ui` says what's missing.

## Code and tests

- `src/assistant/modules/job_search/module.py`, `ui.py`, `module.toml` (defaults, `needs`, `packages`)
- `tests/` in this folder, on the [test kit](../../../../../docs/api/testkit.md) only: `test_job_search.py` (the agent, its menu, the job UI, its config under `module.toml`, cv left off at start, `job.tailor_cv` turning a fake cv on, a Deny, a failure and the `cv_wait` timeout) and `test_cv_events.py` (cv's named events). The stand-in job UI is `fake_job_ui.py` in the test kit (`FAKE_JOB_UI`); `CompanionApp`'s command-line mode is tested in `tests/test_app_kit.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), [the job project](job-project.md), and `docs.toml` (its docs tab and group)
