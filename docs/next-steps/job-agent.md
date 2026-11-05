# Job agent: run the job project from the assistant

> **Status: proposed (2026-11-04).** A plan only; nothing is built. How the job project works today is on the [Job project](../job-project/README.md) page. Building it changes a contract (`StartTask`) and shared infra, so it will need an app restart.

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

The job agent works outside this repo, so it gets its own access list (built with `path_rule`), not the Main Assistant's. Anything outside the list comes to you as an Allow / Deny card through the Hub, as today. It starts in Manual mode. The list itself is question 1.

## Later: cloud agents

A cloud agent can't see `C:\Chang\Jobs\CV` (not a git repo), the `.odt` CVs, JobRadar's Python or your logged-in Chrome. Its status would come from checking a remote API over and over, through its own `ITaskAgent` adapter, and it means sending job data off the machine. A later step, for the web-only half of a search at most.

## Open questions for you

1. **The job agent's permissions.** Proposed: read and write `C:\Chang\Jobs\CV`; read `C:\Chang\Jobs` and JobRadar (`C:\Chang\Git_projects\Resume`); run JobRadar's Python; use Chrome; Manual mode; never submit or send anything.
2. **May the Main Assistant start or question the job agent itself**, or only you through the Talker for now? Recommended: only you, for now.
