# cv agent: everything in one folder

> **Status: proposed (2026-11-09).** Part of [cv-uses-cv-tool.md](cv-uses-cv-tool.md). Nothing is moved yet. Read only so far.

**Asked (2026-11-09):** put what cv_agent needs in one place, the way the other agents have it. Today it's spread over five places, and that confuses the agent too.

## How the other agents do it

| Agent | Workspace (read and write) | Its skills | Its memory | Reads besides |
|---|---|---|---|---|
| Job search agent | `C:\Chang\Jobs\CV`: its whole project | `C:\Chang\Jobs\CV\.claude\skills\` (apply-session, fill-application, …), found by `claude` on its own | Claude's memory for that folder (`~\.claude\projects\C--Chang-Jobs-CV\memory\`) | `C:\Chang\Jobs`, `C:\Chang\Git_projects\Resume` |
| Rezi helper (`task_agents`) | `C:\Chang\Jobs\rezi` | none | Claude's memory for that folder | `C:\Chang\Jobs\CV`, this repo's `docs` |
| **cv_agent today** | `C:\Chang\Jobs\rezi\cv_agent` | a skill in `docs\cv-writing-preferences\` (not where `claude` looks, so the gate pastes it in) | 14 notes: rules, facts and one stale note mixed | `C:\Chang\Jobs\CV`, plus the output folder |

**The pattern:** one project folder is the workspace. Its skills sit in `.claude\skills\`, where `claude` finds them by itself, and its data sits next to them. The base CVs are read-only, from outside. The app's code stays in this repo.

## What cv_agent has today, in five places

1. **Code:** the cv module in this repo (`src/assistant/modules/cv/`) and the CV Tool's new copy (`src/cv_tool/`).
2. **Workspace** `C:\Chang\Jobs\rezi\cv_agent`: `work\` (one folder per job), `docs\cv-writing-preferences\SKILL.md`, `scripts\`, `applied\`.
3. **Memory** `~\.claude\projects\C--Chang-Jobs-rezi-cv-agent\memory\`: the style, layout and Rezi rules, the CV Tool notes, three fact notes, and the stale `user-wants-rezi-export-not-local-build.md`.
4. **CV Tool data** `C:\Chang\Jobs\rezi\cv_tool`: `jobs\`, `data\confirmed_facts.json`, `inbox\`, `outbox\`, `rezi_requests\`, and the old app's code.
5. **Base CVs** `C:\Chang\Jobs\CV` (the job agent's project).

## Proposed layout

```
C:\Chang\Jobs\rezi\cv_agent\          ← cv_agent's workspace (same path: its memory stays bound to it)
  .claude\skills\cv-writing\
    SKILL.md                          ← today's cv-writing-preferences, step 4 fixed to the CV Tool's Submit
    rules\*.md                        ← style, layout, 9 pt, Rezi and CV Tool rules (copied from memory)
  data\confirmed_facts.json           ← your confirmed facts (copied from cv_tool\data, plus the 3 fact notes)
  cv_tool\                            ← the CV Tool's data: jobs\ inbox\ outbox\ rezi_requests\ cache\ profiles
  work\<date>_<Co>_<Role>\            ← one job (unchanged)
  docs\  scripts\  applied\           ← unchanged
```

| Stays where it is | Why |
|---|---|
| The cv module's code (`src/assistant/modules/cv/`) and the CV Tool's code (`src/cv_tool/`) | It's code: the app reloads and launches it from the repo. cv_agent never needs to read it |
| Base CVs in `C:\Chang\Jobs\CV`, read only | They're yours and the job agent's. The gate copies the base PDF into the job's `work\` folder |
| Claude's memory folder | `claude` keeps it outside the workspace by design, tied to the workspace path. With the rules and facts moved out, it holds only small notes |

## Who reads and writes what

| Side | Reads | Writes |
|---|---|---|
| **cv_agent** | its workspace (all of the above); `C:\Chang\Jobs\CV` | its workspace. In `cv_tool\` only through the `cv.tool_*` items, never by hand (said in its prompt and the skill) |
| **cv module** (in the app) | the workspace's skill, rules and facts (the gate pastes them into each task); the base CV | `work\<job>\` (the gate); the CV Tool's API |
| **CV Tool app** | `cv_tool\`, `data\confirmed_facts.json`, the skill's `rules\` | `cv_tool\` only |

## What changes

**The access list (your call, asked on the card when cv turns on):**
- Workspace: unchanged, `C:\Chang\Jobs\rezi\cv_agent`.
- `read_dirs`: `C:\Chang\Jobs\CV` stays. The output folder `C:\Chang\Jobs\rezi\rezi\out` can go once `cv.build` is no longer the final PDF.
- Nothing new: the facts and the CV Tool's data move inside the workspace, so no line for `C:\Chang\Jobs\rezi\cv_tool` is needed.

**`module.toml`:**
- `rules_dir = ".claude/skills/cv-writing"` (a relative path is from the workspace, like `job_skills` today). The gate loads `SKILL.md` and every file in `rules\`.
- `job_skills` = `data/confirmed_facts.json`. The memory note `never-script-cv-folder-copy-first.md` moves into `rules\`.
- `[tool] data_dir = "C:/Chang/Jobs/rezi/cv_agent/cv_tool"`, `port = 8771`.

**Moves, all copies first:**
- The style, layout, Rezi and CV Tool notes go from memory into the skill's `rules\`.
- `confirmed_facts.json` is copied to `data\`.
- New CV Tool jobs go in `cv_agent\cv_tool\`. Old jobs (Wayne, Hooli, Vandelay…) store absolute paths in their `job.json`, so they stay in `C:\Chang\Jobs\rezi\cv_tool\jobs\` as a read-only record and aren't moved.
- `cv_tool.cmd` is pointed at the new data folder.

## Which earlier decisions it changes

| Decision | Before | Now |
|---|---|---|
| The rules' folder | `src/assistant/modules/cv/rules/` in the repo | `cv_agent\.claude\skills\cv-writing\rules\`: the agent's own skill, which `claude` finds itself. Still the module's general rules, loaded by the gate for every cv job. They're no longer in git |
| The CV Tool app's code | `src/cv_tool/` | **Unchanged** |
| The CV Tool's data | `C:\Chang\Jobs\rezi\cv_tool` | `cv_agent\cv_tool\` for new jobs; the old folder kept as a record |
| `confirmed_facts.json` | stays in `cv_tool\data\` | `cv_agent\data\confirmed_facts.json`, a copy, plus the three fact notes merged into it (your data file, so your yes first) |
| The memory notes | copied into `rules/` and the facts, originals kept | Same, into the workspace's skill and `data\`. Originals kept until you say they can go. `user-wants-rezi-export-not-local-build.md` is dropped from the copy |

**Recommended:** yes to all of it. It matches the job agent, and `claude` finds the skill without the gate. The one thing lost is git history for the rules. If you want that, the rules can stay in the repo and the workspace skill points to them, but then they're in two places again.

## Option B: everything under `C:\Chang\Jobs\CV_Module`

**Asked (2026-11-09):** instead of keeping `C:\Chang\Jobs\rezi\cv_agent`, give cv_agent a new home, `C:\Chang\Jobs\CV_Module` (it doesn't exist yet).

```
C:\Chang\Jobs\CV_Module\              ← cv_agent's new workspace
  .claude\skills\cv-writing\SKILL.md  ← the skill
  .claude\skills\cv-writing\rules\    ← style, layout, 9 pt, Rezi, CV Tool rules
  .claude\state\                      ← its task state (copied)
  data\confirmed_facts.json           ← your facts
  cv_tool\                            ← the CV Tool's data: jobs\ inbox\ outbox\ rezi_requests\ cache\ profiles
  work\<date>_<Co>_<Role>\            ← one job (copied over: ExampleCorp and the others)
  applied\  docs\  scripts\           ← copied from cv_agent
```

**The code stays in the repo** in both options. The app finds its modules by folder under `src/assistant/modules/`, and `CompanionApp` starts the CV Tool with `python -m cv_tool` from the repo's `src/`. Only data and the agent's files move.

**What moving it takes (checked 2026-11-09):**

| Part | What changes |
|---|---|
| Claude's memory | It's kept by workspace path: today `~\.claude\projects\C--Chang-Jobs-rezi-cv-agent\memory\` (14 notes + `MEMORY.md`). The new workspace gets a new, empty folder (`C--Chang-Jobs-CV-Module`), so the notes must be **copied** there. Old session transcripts stay behind; nothing needs them. With the rules and facts moved into the skill and `data\`, few notes remain |
| Access list and saved grant | The workspace line changes, so the card asks you again when cv turns on. The grant in `data\permissions.toml` (`workspace:C:\Chang\Jobs\rezi\cv_agent`, `read:C:\Chang\Jobs\CV`, `read:…\rezi\rezi\out`, `chrome`) is replaced by your answer. **Your call** |
| `module.toml` | `workspace = "C:/Chang/Jobs/CV_Module"`. `work_dir`, `job_skills` and `rules_dir` follow it, because their relative paths are from the workspace. `read_dirs` keeps `C:/Chang/Jobs/CV`. The CV Tool's `data_dir` becomes `C:/Chang/Jobs/CV_Module/cv_tool`. `output_dir` (`rezi\rezi\out`, the old `cv.build` output) can stay until `cv.build` is dropped |
| CV Tool code | `DEFAULT_DATA` in `src/cv_tool/cvlib.py` (set in this build anyway) |
| Old CV Tool job | One job folder in `C:\Chang\Jobs\rezi\cv_tool\jobs`, whose `job.json` has 18 absolute paths. It stays where it is as a read-only record, the same as in the first proposal |
| Tests | `cv/tests/test_job_start.py` names `C:/Chang/Jobs/rezi/cv_agent` three times (the ExampleCorp PDF fixture under `work\pdf-reader-check`, the default `work_dir`, the skill path) |
| Docs | The cv module's `README.md` and `architecture.md` (the workspace and output folder) |
| The job agent's project (outside the repo) | `C:\Chang\Jobs\CV\.claude\skills\apply-session\SKILL.md` line 35 names `C:\Chang\Jobs\rezi\cv_agent\applied`, so it needs one line changed. `Recruiters\scripts\job_ui.py` reads `rezi\rezi\out`, which stays for now |
| cv_agent's scripts, `cv_tool.cmd` | Nothing in them names `C:\Chang\Jobs\rezi` |
| An overlap that goes away | The Rezi helper (`task_agents`) has the workspace `C:\Chang\Jobs\rezi`, which today **contains** cv_agent's workspace. With `CV_Module`, the two no longer overlap |

**Costs:** copying the memory notes to the new name, a new access card, one line in the job agent's skill, and the three test paths. It needs a cv reload, not an app restart. All of it is copying, and the old `C:\Chang\Jobs\rezi\cv_agent` and `cv_tool` stay until you say they can go.

**Recommended: Option B.**
- It's one clearly named place for the whole cv module's data, next to `C:\Chang\Jobs\CV` the way the job agent has it.
- It ends the overlap with the Rezi helper's workspace.
- The extra cost over the first proposal is small: copying the memory notes and answering the new card.

**Your check:**
0. Option B (`C:\Chang\Jobs\CV_Module`) or keep `C:\Chang\Jobs\rezi\cv_agent`? Either way, with the layout above.
1. Rules in the workspace's skill rather than in the repo?
2. New CV Tool jobs in `cv_agent\cv_tool\`, with the old jobs left where they are?
3. Copy `confirmed_facts.json` into `cv_agent\data\` and merge the three fact notes into it?
