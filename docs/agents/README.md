# Agents

How we run and work with the agents: setup, experiments, and what we've learned. How they fit the system (who is who, where each works, which CLAUDE.md it loads) is on the [Agents architecture page](../architecture/agents.md).

The Talker, the Main Assistant and the Agent Hub start with `python -m assistant`, shown in the [temp UI](runtime.md#temp-ui). See [Agent runtime](runtime.md) and [self-improvement](self-improvement.md).

## Roles

| Agent | Job | Implementation |
|-------|-----|----------------|
| **Talker** | Talks with you; hands off work; reports progress; relays questions. One per agent tab | `claude -p` session, faster model (`sonnet`), no built-in tools, only the module door's three tools |
| **Main Assistant** | Your main AI: reasons, plans, does the work, coordinates the other agents | `claude -p` session (Claude Code) with file tools, working in the repo |
| **Module agents** | A specialist bundled with its add-on: `cv_agent` (cv), `job_search_agent` (job_search) | A `ProfileAgent` working in its module's workspace or your data folder |
| **Helpers** | One-task agents from a kind of helper in config (`task_agents`), launched by name with your yes | A `ProfileAgent` working in `<kind workspace>/<name>`, outside the repo by default |
| **Subagents** | Claude Code's own subagents inside one session | `debugger` (`.claude/agents/debugger.md`, sonnet) for debugging loops and broad searches. They have no id and never reach the Hub |

## How the sessions run

- Each agent is one `claude -p --input-format stream-json --output-format stream-json` process. The Talker's is **long-lived**, so it keeps the conversation. The Main Assistant gets a **fresh one per task**, and per handoff within a task, so a task's context holds only that task ([fresh sessions and handoffs](runtime.md#fresh-sessions-and-handoffs)).
- **Worker context and batching:** the Main Assistant is reminded at 150k and hands off to a fresh session by itself; its prompt says to batch edits, and a hook adds a note to its second edit to a file, once per file. Neither interrupts it ([runtime](runtime.md#fresh-sessions-and-handoffs), [decision](../architecture/decisions.md#decided)).
- **Usage:** each session's context now (what every call resends) and its tokens since launch (tokens only), worker and Talker apart. The Talker always knows both and warns you past 150k; the temp UI shows the selected tab's pair live. A Reset starts either one fresh.
- Messages in and out are **JSON lines** over stdin and stdout. The owning module, through [`ClaudeSession`](../api/infra.md#claudesession), writes the agent's input and reads its event stream.
- **Transcripts for debugging:** every line in and out goes to a transcript per agent (`talker.jsonl`, `main_assistant.jsonl`, …; `transcript` in each module's config, a file name), next to the app's own `assistant.log`, in one folder per launch: `logs/<start time>_<theme>/` ([Logging](../architecture/core.md#logging)).
- Agents never talk to each other directly; everything goes through the Hub's menu on the module door, and the core.
- Started with `--strict-mcp-config`, so your claude.ai MCP connectors aren't loaded; the module door is the only MCP server a session sees.
- Runs on your **Claude subscription** (terms checked for personal use). The session layer stays swappable to an API key.

## Permissions

- **Talker:** no built-in tools; only the module door's three tools (list modules, show a menu, use an item). Every item it uses passes the core's one gate.
- **Main Assistant:** the same access as Claude Code in this repo (decided 2026-10-26). Every built-in tool (`tools = "default"`, shell included), `acceptEdits` mode, and the repo as its working folder, so it loads `CLAUDE.md` and reads the docs like Claude Code does. Settings in its `module.toml` (`modules/main_assistant/`; your `config/main_assistant.toml`, or `[modules.main_assistant]` in `config/local.toml`, overrides them): (`workspace`, `read_dirs`, `write_dirs`, `allowed_commands`):

  | Access | Where |
  |--------|-------|
  | Read and write, without asking | the whole repo, including its own source, plus `.claude/skills` and `.claude/agents` (listed in `write_dirs` because `claude` treats `.claude/` as sensitive) |
  | Run, without asking | `allowed_commands`: the tests (`.\.venv\Scripts\python -m pytest`), `.\.venv\Scripts\ruff check`, the docs build, read-only git (`git status`, `git diff`, `git log`, `git show`), and `Get-ChildItem`, `Get-Content`, `Select-String`, with any arguments |
  | **Asks you, each time** | other shell commands (git commit, push, reset, checkout, deleting files, installs, network, scripts it writes itself), the rest of `.claude/`, anything outside the repo |

  Its `debugger` subagent works under the same rules; its requests come to you the same way.

  Both agents' prompts state these permissions, so they don't have to find out by trying. The [repo zones](../architecture/permissions.md#repo-zones) are recorded; see that page for which are enforced.
- **Module agents and helpers:** each asks for its access list on one card when its module turns on (a helper: at launch). A module agent also gets a write grant on its own module folder; a helper doesn't ([permissions](../architecture/permissions.md)).
- **Permission requests:** when an agent uses a tool its rules don't allow, the request comes to you: Allow / Deny buttons on a card in the temp UI's Talker pane, or tell the Talker yes or no. Each answer covers that one use. Unanswered requests are denied after 10 minutes (`permission_timeout`). The Talker never answers on its own.
- **"You" means both.** To you the Talker and the Main Assistant are one assistant, and both prompts say so.

## Limits

- Each agent runs **one task at a time**. Besides the Main Assistant, at most `max_extra_agents` agents (3 by default) have an active task at once ([working together](../architecture/agents.md#working-together)).
- No scheduling, queues or distributed machinery until needed.

## Workflow skills

Project skills in `.claude/skills/`, used by Claude Code and the Main Assistant alike. `CLAUDE.md` says when each applies.

| Skill | What it's for | When |
|-------|---------------|------|
| `batching` | The batching rules that keep the step count and per-step cost down | Before any multi-step task (several reads, edits, builds, or questions) |
| `architecture-first` | Confirms the use-case, checks the architecture docs and API reference so code gets reused, keeps those docs updated | Before non-trivial edits, or a change touching more than one function or file |
| `architecture-check` | Checks what was just built for modularity, reuse, and fit with the main app, then updates the architecture docs and flowcharts to match (built and planned marked); the final report gets an "Architecture check" section naming the diagrams updated | After each big chunk of a multi-chunk build, and before the final report |
| `docs-html` | Regenerates the browsable HTML in `docs/html/` | Whenever a file under `docs/` (Markdown) is created, edited, renamed, or deleted |

## Pages

- [Agent runtime](runtime.md): how the agents are spawned, behave, and talk to each other
- [Self-improvement](self-improvement.md): the plan for the assistant to read and change its own code and docs, and how permissions get granted
- [Two-Claude spike](spike.md): the disposable experiment and its findings
