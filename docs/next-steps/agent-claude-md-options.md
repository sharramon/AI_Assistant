# Agents and the repo's CLAUDE.md: options

**Status:** proposal, nothing changed (2026-11-13). For your decision.

## The problem

Claude Code reads every `CLAUDE.md` in the folder it starts in and in each folder above it. cv_agent (`modules/cv/workspace`) and job_search_agent (`modules/job_search/workspace`) now start inside the repo, so each of their sessions gets the repo's `CLAUDE.md` with its imported architecture overview and API index: developer rules they don't need, thousands of tokens on every turn, and rules that can steer them (read the docs first, use the architecture skills). The job agent also loads its own copied `CLAUDE.md`, so it gets two.

## The exact option

- **`claudeMdExcludes`**: a Claude Code setting, an array of globs or absolute paths of `CLAUDE.md` files not to load. It applies to user, project and local memory files. Checked in the installed `claude` 2.1.323's settings schema; not tried in a live session.
- **Per session:** `claude --settings '{"claudeMdExcludes":["<repo>/CLAUDE.md"]}'`. `claude_command` (`infra/claude_session.py`) has no `--settings` today, so it would be one more argument there, set from `AgentProfile`.
- **Not usable:**
  - `--bare` skips CLAUDE.md but also hooks, auto-memory and the OAuth sign-in, so it needs `ANTHROPIC_API_KEY`.
  - `--safe-mode` also drops skills, and cv and the job agent need theirs.
  - `--setting-sources user` skips the repo's `.claude/settings.json`, not CLAUDE.md.

## Three ways

| | Tokens | Deep code edits | Safety of your data |
|---|---|---|---|
| **A. As now:** workspaces in the repo | High: the repo rules and both indexes every turn | Good: the agent has the repo rules | Weakest: your CVs and job state sit in the repo tree, kept out only by `.gitignore` |
| **B. `claudeMdExcludes`:** workspaces stay in the repo | Low | Worse: an agent editing cv's code no longer sees the repo rules | Same as A |
| **C. Data outside the repo:** the working folder (your data) outside, a saved write grant on the module's own folder for code edits, and a pointer to the module's README in the agent's prompt | Low: no repo CLAUDE.md loads | Good enough: the agent reads its module's docs when it edits code | Best: nothing personal sits in the repo tree |

**Recommended: C.** It saves the tokens like B, keeps your data out of the repo for good, and the README pointer gives the agent the module's own rules when it edits code. Deep edits across modules stay with the Main Assistant, which keeps the whole project.

## Code in the module folder, your data outside

The rule "nothing of a module outside its folder except your choices in config" fits C if your data counts as one of your choices: the config names where your data lives.

- **In the module folder (committed):** code, tools, scripts, skills, defaults, tests, docs.
- **In a data folder that config points at (outside the repo by default, never committed):** CVs, job state, applications, outputs.

What's in the two workspaces today (files, counted 2026-11-13):

| Workspace | Code (moves to the module folder) | Your data (goes to the data folder) |
|---|---|---|
| `cv/workspace` | `.claude/skills` (14), `scripts/` (46, with fonts and the kept Katalyst scripts) | `work/` (1,100+, mostly run folders and checks), `cv_tool/` (340: jobs, outbox, Rezi requests), `out/` (3), `applied/` (1), `data/` (2, with `confirmed_facts.json`); `docs/` (20) to sort: next-steps notes and writing preferences |
| `job_search/workspace` | `.claude/skills` (24), `Recruiters/scripts` (22), `job_paths.py` | `Recruiters/docs` (546: job state, applications), `CLAUDE.md` (it holds your profile), `job_paths.json` |

How the rest would work:

- **Paths file:** one data-folder key in the module's config (`config/<id>.toml`, yours). The job project's `job_paths.json` then lives in that data folder or is made from the key, so no script names a real path.
- **Grants:** the agent's workspace is the data folder; a write on its own module folder is a separate line of the same card.
- **`modules.remove`:** purge still deletes only the module's config files. The data folder is never deleted, or asked about on its own line.

Moving to C means a migration per agent (copy the data out, point the config, a new access card), much like items 17 and 18. Not started.
