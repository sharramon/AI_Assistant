# Module folders: where each module and agent lives, before and after the restart

A read-only check, made 2026-11-13 at about noon, after the overnight run (commit `a0338ea`). Nothing was changed, launched, turned on or off, or restarted. Every point below comes from a file or a config line, named next to it.

## A. The modules and their folders

All 14 modules are in `src/assistant/modules/<id>/`. Their group comes from each module's `docs/docs.toml` (`group = ...`).

| Module | Group | module.py | module.toml | app/ | tests/ | docs/ | workspace/ |
|---|---|---|---|---|---|---|---|
| agent_hub | core | ✓ | ✓ | | ✓ | ✓ | |
| assistant_view | core | ✓ | ✓ | | **none** | ✓ | |
| console_io | core | ✓ | ✓ | | ✓ | ✓ | |
| main_assistant | core | ✓ | ✓ | | ✓ | ✓ | |
| talker | core | ✓ | ✓ | | ✓ | ✓ | |
| task_agents | core | ✓ | ✓ | | ✓ | ✓ | |
| temp_ui | core | ✓ | ✓ | | ✓ | ✓ | |
| usage | core | ✓ | ✓ | | ✓ | ✓ | |
| voice_in | **core** | ✓ | ✓ | ✓ voice_service | ✓ | ✓ | |
| cv | add-on | ✓ | ✓ | ✓ cv_tool | ✓ | ✓ | ✓ (gitignored) |
| echo_orchestrator | add-on | ✓ | ✓ | | ✓ | ✓ | |
| html_viewer | add-on | ✓ | ✓ | ✓ html_viewer | ✓ | ✓ | |
| job_search | add-on | ✓ | ✓ | | ✓ | ✓ | ✓ (gitignored) |
| voice_notes | add-on | ✓ | ✓ | | ✓ | ✓ | |

`src/` holds only `app_kit`, `assistant` (and `assistant.egg-info`). `config/` holds only `default.toml`, `local.toml` and `modules.toml`: no `config/<id>.toml` exists yet (they're optional), and `config/permissions.toml` doesn't exist yet either (see B).

**voice_in is a core module in the code:** `src/assistant/modules/voice_in/docs/docs.toml` says `group = "core"`, and it's on at launch (`config/modules.toml`: `enabled = [..., "voice_in", "usage"]`). The approved picture draws it in the core too (voice_notes is the add-on that needs it), so the code and the picture agree: voice_in stays core (settled with you, 2026-11-13). Item 19's tripwire (`tests/test_module_folders.py:885`) covers only the add-ons (from the same `group` keys), so voice_in has no "nothing outside its folder" check.

**The rezi helper is not a module.** It's a kind of helper in `task_agents` (`[agents.rezi]` in `src/assistant/modules/task_agents/module.toml`), and its folders are in `config/local.toml` (`[modules.task_agents.agents.rezi]`: `workspace = "C:/Jobs/rezi"`). The Rezi connection itself is part of cv (`rezi_url`, `token_file` in cv's `module.toml`). Its design note is `docs/next-steps/rezi-module.md`.

**Still outside a module folder:**
- `data/permissions.toml`: the saved grants, still the live file. It's copied to `config/permissions.toml` once, at the next start (`config/default.toml`, `[core.permissions]` comment).
- The repo-level `tests/` folder: 47 files. Most are core tests, but some import core modules directly (`test_swap_every_module.py`, `test_usage.py`, `test_talker_agents.py` import agent_hub, talker, temp_ui, usage).
- `scripts/voice_two_pass_check.py`: a voice check that sits in the repo's `scripts/`, not in voice_in's folder.
- The repo-root `workspace/` folder (gitignored): `nonsense_test.txt`, `poems.txt`, `voice_check.py`, left over from earlier tests.
- `logs/cv_agent.jsonl` and other `.jsonl` files at the root of `logs/` (last written 06:44), outside any launch folder.
- Outside the repo (only copied, never removed): `C:\Jobs\CV_Module`, `C:\Jobs\CV\.claude`, `C:\Jobs\rezi\cv_agent`, `C:\Jobs\rezi\cv_tool`, `C:\Jobs\rezi\rezi`.

## B. Each agent's working folder and access list

`claude` is started with `cwd` = the agent's workspace (`src/assistant/infra/profile_agent.py:75`). Its command line has no `--setting-sources` (`src/assistant/infra/claude_session.py:54-78`), so `claude`'s default settings sources load: your user settings (`C:\Users\you\.claude\settings.json` exists; there's no user CLAUDE.md), the project's, and a local one. CLAUDE.md files load from the working folder and every folder above it (Claude Code's normal behavior). So **any agent whose workspace is inside the repo loads the repo's `CLAUDE.md`.** I didn't verify whether `claude` started in a sub-folder also uses the repo root's `.claude/settings.json` (the edit-tracker hook). The two workspaces have no `settings.json` of their own, only `.claude/skills/`.

A relative `workspace` resolves against the app's current folder (the repo) in `access_items` (`agent_access.py:62`, `Path.resolve()`). cv and job_search resolve theirs from their own module folder first (`in_module_folder`, used at `cv/module.py:878` and `job_search/module.py:75`).

### After the restart (the config and code as they are now)

| Agent | Working folder | In the repo? | Access list asked (`access_items`) | Card? | Loads the repo's CLAUDE.md |
|---|---|---|---|---|---|
| **cv_agent** | `src/assistant/modules/cv/workspace` (cv `module.toml` `[agent] workspace = "workspace"`) | yes | workspace; read `C:/Jobs/CV`; write `src/assistant/modules/cv` (its own folder); Chrome. The output folder `<workspace>/out` is inside the workspace, so it isn't added (`worker.py:120`) | yes, new: the saved grant names `workspace:C:\Jobs\CV_Module` | yes. The workspace has no CLAUDE.md of its own; its skills are `.claude/skills/cv-writing` |
| **job_search_agent** | `src/assistant/modules/job_search/workspace` (job_search `module.toml` `workspace = "workspace"`) | yes | workspace; read `C:/Jobs`, `C:/Projects/Resume`; write `C:/Jobs/CV` (`documents` in `config/local.toml`); write `src/assistant/modules/job_search`; python `C:/Projects/Resume/.venv/Scripts/python.exe`; Chrome | yes, new: the saved grant names `workspace:C:\Jobs\CV` | yes, **plus** its own `workspace/CLAUDE.md` (the job project's, copied) |
| **rezi** (task_agents helper) | `C:/Jobs/rezi`, and a launched one in `C:/Jobs/rezi/<name>` (`task_agents/module.py:327`) | no | workspace; read `C:/Jobs/CV`, `C:/Projects/AI_Assistant/docs`; Chrome (no own-folder write: `own_folder=False`) | **probably none**: the list matches the saved grant, and the saved grant also holds 20+ items it added later: a write on `src/assistant/modules/cv`, `pip install mcp pypdf`, pytest, ruff, `build_docs.py`, writes on docs pages | no (not under the repo) |
| **helper** (task_agents) | `C:\Projects\assistant-helper` (`workspace = "../assistant-helper"`, from the repo), launched ones in `.../<name>` | no | workspace only | none: matches the saved grant | no |
| **Main Assistant** | the repo (`workspace = "."`) | yes | read `.`; write `.`, `.claude/skills`, `.claude/agents`; the 10 `allowed_commands` (main_assistant `module.toml`). It isn't asked on a card; it's its standing config | none | yes, by design |
| **Talker** (and each tab's Talker) | no `cwd` set (talker `module.toml` has `# cwd = "..."`; `talker/session.py:139`), so the app's current folder: the repo | yes | none: it has no tools | none | yes |

**Would anything still start an agent in an old folder after the restart?** Not cv_agent or job_search_agent: no config line names `C:\Jobs\CV_Module` as a workspace, and job_search's workspace is no longer `C:\Jobs\CV`. But the old folders are still **reached**:
- job_search_agent may **write** `C:\Jobs\CV` (`documents`) and **read** all of `C:\Jobs` (which includes `CV_Module` and `rezi`) and `C:\Projects\Resume`, whose Python it runs.
- `job_search/workspace/job_paths.json` has `"cv_output": "C:/Jobs/rezi/rezi/out"`: the old cv output folder (the "job UI looks in the old folder" issue). cv now writes to `src/assistant/modules/cv/workspace/out`. **Fixed 2026-11-13:** `cv_output` is `../../cv/workspace/out` (relative to the workspace), overridable in a gitignored `job_paths.local.json`; the old folder's files were copied there.
- rezi works in `C:\Jobs\rezi`, which still holds the old `cv_agent`, `cv_tool` and `rezi` folders.

### Now, in the running app (launched 02:19, not restarted)

The running app's log is `logs/2026-11-13_02-19-03_wtf/assistant.log`, still being written. It shows no reload or module on/off after 02:51 (cv and job_search were turned on and off between 02:45 and 02:51). So the **code** is what was imported at 02:19. Its closest commit is `2e283b2` (04:19); the overnight work started after it. Its **config sections** were read at 02:19 from the old `config/default.toml` and `local.toml`.

One thing matters here: turning a module on reads that module's `module.toml` fresh from disk (`2e283b2:src/assistant/core/app.py:198-206`, `_config_of` → `loader.module_defaults`, "read fresh each time"), but doesn't re-import its code. So turning a module on now mixes **old code + launch-time sections + new `module.toml` files**:

| Agent | What it would do if turned on now |
|---|---|
| job_search_agent | Starts in the **old folder `C:\Jobs\CV`**. The launch-time `[modules.job_search] workspace = "C:/Jobs/CV"` (`2e283b2:config/default.toml`) wins over the new `module.toml`. Its saved grant matches, so no card. |
| cv_agent | **Probably fails to turn on.** The launch-time config had no `[agent] workspace` for cv (it came from the old `module.toml`: `workspace = "C:/Jobs/CV_Module"`). The new `module.toml` says `"workspace"`, and the old code doesn't resolve it from cv's folder, so it becomes `<repo>/workspace`, with `work_dir` = `<repo>/workspace/work`. The old code refuses that: `if work.is_relative_to(REPO): raise ValueError("cv: work_dir must be outside the repo ...")` (`2e283b2:src/assistant/modules/cv/module.py`, `job_folders`). This follows from the code; I didn't try it. |
| rezi, helper | The same folders as after the restart (launch-time `default.toml` already had `C:/Jobs/rezi` and `../assistant-helper`). |
| Main Assistant, Talker | Unchanged: the repo. |

So until the restart, don't turn cv or job_search on: job_search would work in the old folder, and cv would most likely fail.

## Open points this check adds

1. The repo's `CLAUDE.md` loads into cv_agent's and job_search_agent's sessions after the restart (already on the morning list). The job agent also gets its own copied `CLAUDE.md`, so it gets two.
2. The rezi helper's saved grant keeps more than its access list (writes in the repo's cv module, `pip install`), and a matching list means no new card shows it.
3. ~~`job_paths.json`'s `cv_output` still points at `C:/Jobs/rezi/rezi/out`.~~ Fixed 2026-11-13: it points at cv's `workspace/out`.
4. ~~voice_in is `core` in its `docs.toml`, but the picture shows it as an add-on.~~ Settled 2026-11-13: the picture draws it in the core as well; it stays core.
5. `assistant_view` has no `tests/` folder. The repo root still has `workspace/`, root-level `.jsonl` logs, `scripts/voice_two_pass_check.py` and `data/permissions.toml`.
