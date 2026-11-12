# job_search: the job agent and its menu

## Purpose

The job agent, bundled with its own module: one big agent (id `job_search_agent`) that works in the job project ([job project](../job-project/README.md)), applies to one job per session and runs job searches, plus its `job.*` menu. Off at launch (turn it on with `modules.on`). Design: [working together](../architecture/agents.md#working-together).

## Wrapper

| Field | Value |
|-------|-------|
| id | `job_search` |
| provides | [`ITaskAgent`](../api/agents.md#itaskagent), the job agent (only the Hub calls it) |
| requires / optional | none |
| permissions | `agent.access`: it asks for its config's access list when turned on ([access lists](../architecture/permissions.md#access-lists-built)) |

## Interface

| | |
|---|---|
| Tools | `job.search(days)`: answers at once; the result reaches the caller as an [`AgentNotice`](../api/agents.md#agentnotice) at its next turn. A **stub** today: the notice says the runner isn't built. `job.open_ui()`: opens the job UI in its own window on the Tracker, every time: starts the server first if it isn't answering, closes the job UI window already open, then opens a fresh one, so there's only ever one; gives `{url, launched, window}`, or `not_available` if it can't start |
| Handles | nothing: the agent is called through `ITaskAgent`, the menu through `InvokeTool` |
| Calls | [`ctx.permissions.request_set`](../api/modules.md#modulecontextpermissions) on start (through [`request_access`](../api/infra.md#agent_access)); [`ReportTask`](../api/agents.md#reporttask); the [Hub's menu](../api/agents.md#the-hubs-menu) through the door, as `job_search_agent`; [`IAgentNames`](../api/agents.md#iagentnames) (`ProfileAgent` claims the id on start, releases it on stop) |
| Publishes | [`AgentActivity`](../api/agents.md#agentactivity), [`AgentStateChanged`](../api/agents.md#agentstatechanged), [`SessionUsage`](../api/agents.md#sessionusage), [`PermissionModeChanged`](../api/agents.md#permissionmodechanged), [`AgentNotice`](../api/agents.md#agentnotice) |
| Listens to | [`ResetRequested`](../api/agents.md#resetrequested) (for the job agent) |

## Owns and launches

- **Its access, asked for on start:** `start` asks for the whole list in one request (`request_access`, subject `job_search_agent`). If the saved grant matches the list, the agent is built at once. Otherwise a card opens and the start ends with `AccessPending`, so the module stays off; your Allow turns it on. A denied card leaves it off. The agent is built from the config cut down to what you allowed, and anything outside it asks with a normal card.
- **Grants live** (built 2026-11-06, after the restart): it listens to `PermissionChanged` for its subject ([`watch_grant`](../api/infra.md#agent_access)) and calls `set_access(granted_config(...))`, so a widened grant reaches it with no off and on (an idle open session restarts once; a busy one at its next session). The agent may ask for more itself with `permissions.request`, and reads your snips with no card.
- **One [`ProfileAgent`](../api/infra.md#profileagent)** with the job prompt: one job per session; `HANDOFF:` instead of the project's `handoff.ps1`; never submit or send (the user submits); confirm before any search. Its `claude` process starts on its first task, a fresh one per task, in Manual.
- **Chrome:** `chrome = true` starts its session with `--chrome` (the Claude in Chrome tools).
- **Searches:** each `job.search` is a background task, cancelled on stop. A reload waits while the agent has a task or a search runs.
- **The job UI** (built 2026-11-10, `ui.py`: `JobUi`): the job project's `Recruiters/scripts/job_ui.py`, what `job_ui.cmd` runs, a local server at `127.0.0.1:8781` with the Tracker, Job stack, Live search and Keywords pages. `job.open_ui` launches it the way `cv.open_tool` launches the CV Tool, through [`CompanionHandover`](../api/app_kit.md#companionapp), but by its command line (`job_ui.cmd`'s: JobRadar's Python, `-I`, the script, plus `--port` and `--no-browser`), because it's another project's script with no JSON ping and no quit call: its ping is any 200 from `/tracker`, and the module's stop ends the server only if this module launched it (one you started yourself stays). The module opens the window itself, an Edge app window on its own profile (`window_profile("job_ui")`), whether it launched the server now or found it running. Each call first closes the window on that profile ([`close_app_windows`](../api/app_kit.md#window): that window and nothing else; none open, nothing to close), then opens a fresh one ([`open_app_window`](../api/app_kit.md#window)), so there's only ever one job UI window (the user's decision, 2026-11-10). It's always its own window, never a tab: without Edge, `job.open_ui` answers `not_available` instead of `open_app_window`'s browser-tab fallback, and the server always runs with `--no-browser`, so it opens no tab or window of its own. A job UI you start by hand with `job_ui.cmd` opens its own Chrome window, which isn't on that profile, so `job.open_ui` can't close it. A reload hands the running server to the new copy. Items that read or update the Tracker may follow.
- **"Open the UI" means `job.open_ui`** (the user's wish, 2026-11-10): one line, `UI_SHORTCUT` in `module.py`, is in the job agent's prompt and in its default description. The tab's Talker reads that description in its prompt ("{agent}'s job: …"), and so does `hub.agents`. So "open the UI" or "open the job UI" means calling `job.open_ui` straight away, with no searching for a tool and no looking in the folder. The Talker calls it itself when it has the door; without the door it hands the request to the agent.

## Config

`[modules.job_search]`: `ProfileAgent`'s keys plus `agent_id` (default `job_search_agent`: the module id plus `_agent`; transcript `job_search_agent.jsonl`). Shipped: workspace `C:/Chang/Jobs/CV`, reads `C:/Chang/Jobs` and JobRadar, `python` (JobRadar's Python, any arguments), `tools = "default"`, `chrome = true`. These keys are its access list, asked for on one card ([`access_items`](../api/infra.md#agent_access)). `permission_mode` takes Manual modes only: every session starts in Manual.

`[modules.job_search.ui]` (optional, not part of the access list): `script` (default `<workspace>/Recruiters/scripts/job_ui.py`), `python` (default the section's `python`, JobRadar's, as `job_ui.cmd` uses), `port` (8781), `page` (`/tracker`). With no script or Python, the agent still runs and `job.open_ui` says what's missing.

## Code and tests

- `src/assistant/modules/job_search/module.py`, `ui.py`
- `tests/test_job_search.py`, `tests/fake_job_ui.py` (a stand-in job UI); `CompanionApp`'s command-line mode in `tests/test_app_kit.py`

## Planned

- The real `job.search` runner (the project's `sweep.py` with JobRadar's Python, 10 to 15 minutes), replacing the stub.
