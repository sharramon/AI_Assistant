# Job agent: run the job project from the assistant

> **Status: built (waiting on you), 2026-11-05.** Built with the [multi-agent](multi-agent.md) build as the `job_search` module ([page](../modules/job_search.md)): the job agent `job_search_agent` (renamed by [agent-names](agent-names.md); a `ProfileAgent` in `C:\Chang\Jobs\CV`, Chrome tools, Manual) and its `job.search` menu item, a **stub** that answers through `AgentNotice`. Question 1 is settled by [agent-permissions](agent-permissions.md) (built 2026-11-05): the access list is config keys, asked for on one card. Still open: the real search runner (`sweep.py` with JobRadar's Python). Needs an app restart. How the job project works today is on the [Job project](../job-project/README.md) page.
>
> **Tested by hand (2026-11-05, after the restart):** `modules.on job_search` showed the access card ("not reviewed": `main_assistant` was busy). You allowed all 5 items, and `job_search` turned on. `job_search_agent` is in the Hub (Manual, free) and took the focus. Its tab opened in the temp UI: the log shows tab clicks moving the focus between it and `main_assistant`. The grant is saved in `data/permissions.toml`, and `permissions.grants` lists it with `matches: true`. `job.search` (the stub) answered "Search started". Not yet tried: giving the agent a real task, and the revoke from the Grants screen.

## What you decided

- **Launch the job project as another Claude instance**, local first, with a fresh session per job as the project does now.
- **First, wrap it in our module structure** so it works with the Main Assistant. How to make it run comes after that.

## The wrapper

| Part | What it is | There today? |
|---|---|---|
| Module | `src/assistant/modules/job_agent/`, a wrapper like every module: `Manifest(id="job_agent")` providing `ITaskAgent`, with its permissions, and a menu of tools (apply to the next job, run a search) in the [module shape](module-shape-refactor.md) | No. The menus and the directory are planned in that change |
| The agent | An `ITaskAgent` backed by [`SessionTaskAgent`](../api/infra.md#sessiontaskagent) and `ClaudeSession`, working in `C:\Chang\Jobs\CV`. Claude picks up that folder's `CLAUDE.md` and skills by itself | Yes, both reused as they are |
| One session per job | A fresh session per task, as the Main Assistant does; this replaces `handoff.ps1` | Yes |
| Reports | `ReportTask` (progress, need, done, failed) to the Hub, which publishes `TaskUpdated` for the Talker. The Hub finds the agent through `get_all(ITaskAgent)` | Yes, no Hub change |

## What's missing

| Gap | Today | Needed |
|---|---|---|
| Naming the agent | `StartTask` gives the work to the first free agent | An optional `StartTask.agent_id` (a contract change), and a way for the Talker to name it |
| Following several tasks | The Talker follows one task at a time and ignores updates from others | Track tasks by agent; usage per agent |
| Folder and access code | The code that builds the command line and the access list sits inside `main_assistant` | Move it to shared infra (principle 13), with a config section per agent: working folder, read and write folders, allowed commands, prompt add-on |
| Chrome | The worker runs with `--strict-mcp-config`, so it has no Chrome tools | The Claude in Chrome tools for the job agent: forms, LinkedIn, the Sheet |
| The hand-off | `handoff.ps1` opens a window and kills its own `claude.exe` | The job agent's prompt says: end with a `HANDOFF:` line, don't run `handoff.ps1`. Nothing changes in the job folder |

## Asking it questions, and knowing when it's done

- **"Is the job agent still going?":** `GetTaskStatus` gives the task's state and recent activity without interrupting it.
- **A question or instruction mid-run:** `SendToTask` (interrupt, reply, continue).
- **Done, a question for you, or failed:** `ReportTask` → Hub → `TaskUpdated` → the Talker, which tells you.
- **The Main Assistant** has no way to send Hub commands today, so only the Talker can do the above. Whether it should is question 2.

## Permissions outside this project

The job agent works outside this repo, so it gets its own access list (built with `path_rule`), not the Main Assistant's. Since 2026-11-05 the list is config keys in `[modules.job_search]`: `workspace`, `read_dirs`, `python` (added: JobRadar's Python, any arguments), `allowed_commands` and `chrome`. When the module is turned on, the whole list is asked for on one card, and the grant is saved for `job_search_agent` ([permissions](../architecture/permissions.md#access-lists-built)). Anything outside the list comes to you as an Allow / Deny card through the Hub, as before. It always starts in Manual mode.

## Later: cloud agents

A cloud agent can't see `C:\Chang\Jobs\CV` (not a git repo), the `.odt` CVs, JobRadar's Python or your logged-in Chrome. Its status would come from checking a remote API over and over, through its own `ITaskAgent` adapter, and it means sending job data off the machine. A later step, for the web-only half of a search at most.

## Open questions for you

1. **The job agent's permissions.** Proposed: read and write `C:\Chang\Jobs\CV`; read `C:\Chang\Jobs` and JobRadar (`C:\Chang\Git_projects\Resume`); run JobRadar's Python; use Chrome; Manual mode; never submit or send anything. **Settled (built 2026-11-05):** the list is in config, with the `python` key added, and is asked for on one card when the module is turned on ([note](agent-permissions.md)).
2. **May the Main Assistant start or question the job agent itself**, or only you through the Talker for now? Recommended: only you, for now.
