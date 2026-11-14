# Module layout step 1: checklist

**Status:** built unattended 2026-11-13 (Auto), item by item, each ticked when its tests passed. **Waits for an app restart and your hand checks** (infra changed); nothing is committed.

Step 1 of the [module layouts](module-layouts.html) page ("add-ons stay in the repo, the line made hard"), with the CLAUDE.md part from [agents and CLAUDE.md](agent-claude-md-options.md) (option C, recommended). The order of fixing: this is item 4.

Where the pages leave a choice open, the option taken is marked **Chosen:** with why.

## Items

### 1. The line made hard: the checks beyond R1's three rules ☑

R1 (`tests/test_boundaries.py`) already checks appendix B's three rules for module code, core settings and needs. Two holes are left:

- **1a. The shared code imports no module.** `assistant.core`, `assistant.contracts`, `assistant.infra` and `app_kit` never import `assistant.modules.<id>` (any module, core group too): the core finds modules by folder, so the arrow from the core to a module is never code. Today item 15 checks only that they don't *name an add-on*.
- **1b. The core starts without any add-on** (rule 1: "the core is what the app can't start without"). The core group alone resolves (`resolve_modules`: needs, required contracts, single providers), both with the shipped on-list and with every core module on; and the shipped on-list (`config/modules.toml`) turns on no add-on.
- Files: `tests/test_boundaries.py` (each check a function over a folder, with a planted bad tree, as R1's).
- Done when: both pass on the real tree and each catches its planted break.

### 2. The repo's CLAUDE.md imports only a short overview ☑

- **Chosen:** a new page `docs/architecture/short-overview.md` (≈ 1k tokens: what the app is, the core line, where things live, where to read next), because the overview (`README.md`, ≈ 4.7k tokens, with the parts table) is the docs' front page and stays whole. CLAUDE.md drops both `@` imports (overview ≈ 4.7k, API index ≈ 6.1k tokens) for that one, and links the full overview and the API index instead. Its other instructions stay.
- **The API index covers the core only:** the five rows of `docs/api/README.md` that named an add-on (`IPageOpener`, `ModuleEvent`, the snip constants, `IVoice`, "Tools offered today") say it without the add-on; each module's tools stay on its own docs page (the module library links them).
- Files: `CLAUDE.md`, `docs/architecture/short-overview.md` (new), `docs/api/README.md`, `docs/architecture/README.md` (Pages list).
- Tests (`tests/test_module_layout.py`, new): CLAUDE.md's only `@` import is the short overview; the short overview stays short (under 6,000 characters) and names no add-on; the API index names no add-on id and no add-on menu item.
- Done when: the tests pass, and every link of the new page resolves (`test_module_docs`).

### 3. Module agents skip the repo's CLAUDE.md (`claudeMdExcludes`) ☑

- `claude_command` gets `settings` (a dict), passed as `--settings <json>`. `AgentProfile` gets `repo_claude_md` (default true) and `module_docs`; with `repo_claude_md = false` its command passes `{"claudeMdExcludes": [the repo's CLAUDE.md files]}` and appends the short developer-rules file to the prompt, with its module's docs page named (option C's README pointer).
- **Chosen:** the developer rules live in `src/assistant/infra/developer_rules.md` (beside the code that reads it, not in `docs/`, so the docs build and a step-2 move don't change what a running agent loads); `ProfileAgent` names the module's own `docs/README.md` from its module id.
- **Chosen:** the switch is a config key, `repo_claude_md = false`, set in cv's `[agent]` and job_search's module.toml, so which agents skip it is visible in their defaults; the Main Assistant, the Talker and the `task_agents` helpers keep loading it (they work on the whole repo).
- **Tried once in a live session (2026-11-13, claude 2.1.325):** from `modules/cv/workspace`, a session without the setting said its context held CLAUDE.md's "Read the docs before searching the code"; with `--settings '{"claudeMdExcludes":["C:/…/AI_Assistant/CLAUDE.md"]}'` it said no, in both the forward-slash and the backslash form. The app uses the forward-slash form.
- Files: `src/assistant/infra/claude_session.py`, `agent_profile.py`, `profile_agent.py`, `agent_access.py` (`REPO_FOLDER`, `repo_claude_md_files`), `developer_rules.md` (new); `modules/cv/module.toml`, `modules/job_search/module.toml`.
- Tests: `tests/test_module_layout.py` (the command line, the profile, the rules text); cv's and job_search's own tests (their agents' profiles skip it).
- Done when: those pass and the Main Assistant's command has no `--settings`.

### 4. Agent data in a data folder named by `config/<id>.toml` ☑

- A `data_folder` key in a module's config: yours, in `config/<id>.toml` (gitignored). Set, the module's agent works there (its workspace, so everything kept under the workspace follows: cv's `work/`, `out/`, `cv_tool/`, rules and facts; the job project's state, scripts and `job_paths.json`). **Unset, nothing moves:** the agent works in its module's `workspace/` as today.
- It must be outside the repo (`ValueError` otherwise): your data never sits in the repo tree once it's set.
- **Chosen (the migration):** the first time a data folder is used and it's missing or empty, the module's old `workspace/` is **copied** into it (never moved, never deleted; `__pycache__` skipped). A data folder that already holds files is used as it is. job_search then rewrites the copy's relative `job_paths.json` paths (the `cv_output` link into cv's workspace) as absolute ones from the old place, so the copied scripts still find them. The old workspace stays until you delete it.
- **Chosen:** no data folder is set for you: the folder is your choice, so this build sets none and nothing of yours moves until you write `data_folder = "…"` in `config/cv.toml` or `config/job_search.toml`. A new workspace target changes the access list, so the next turn-on asks with a new card.
- The code-versus-data split inside the workspaces (skills and scripts into the module folder, committed) is **not** done here: see Left open.
- Files: `src/assistant/infra/agent_access.py` (`data_folder`, `copy_data_once`), `infra/__init__.py`; `modules/cv/module.py`, `modules/job_search/module.py`, their module.toml comments.
- Tests: `tests/test_module_layout.py` (the key, the outside-the-repo rule, the copy once, never a delete); cv's and job_search's tests (the workspace and its derived folders follow; the paths file fixed).
- Done when: those pass and item 17's, 18's and 19's tripwires still pass unchanged (nothing set: today's place).

### 5. Docs ☑

- `docs/api/infra.md` (`claude_command`'s `settings`, `AgentProfile`'s two fields, `data_folder`, `copy_data_once`, `repo_claude_md_files`), `docs/api/reusable.md`, `docs/architecture/agents.md` (which CLAUDE.md each agent loads), `docs/architecture/README.md` (the order's item 4, the Pages list), cv's and job_search's module docs (the data folder, the rules file).
- Done when: `test_module_docs` passes.

## As built

- **Item 1:** `tests/test_boundaries.py` has two more checks, each with a planted break: `module_imports` (the shared code imports no `assistant.modules` package, relative imports resolved) and `core_alone` (the core group resolves alone, with the shipped on-list and with every core module on; the shipped on-list names no add-on). 10 tests there pass.
- **Item 2:** `CLAUDE.md` imports only `docs/architecture/short-overview.md` (about 2.8k characters, names no add-on) and links the full overview and the API index. Five rows of `docs/api/README.md` no longer name an add-on.
- **Item 3:** `claude_command(settings=...)` → `--settings <json>`; `AgentProfile.repo_claude_md` / `module_folder`; `repo_claude_md_files()` and `developer_rules()` in `agent_profile.py`; the rules in `infra/developer_rules.md`; `ProfileAgent` names its module's folder from `ctx.module_id`. `repo_claude_md = false` in cv's `[agent]` and job_search's module.toml. The Main Assistant, the Talker and the helpers are unchanged (no `--settings`).
- **Item 4:** `data_folder(module_id, config)` and `copy_data_once(source, target)` in `infra/agent_access.py` (with `REPO_FOLDER`); cv's `settings` returns `data_folder` / `data_from` and its `init` copies once; job_search's `job_config` uses it and its `init` calls `copy_job_data` (copy, then `fix_copied_paths` on the copy's `job_paths.json`). No data folder is set.
- **Tests:** `tests/test_module_layout.py` (9), `tests/test_boundaries.py` (10, 4 new), `modules/cv/tests/test_layout.py` (4), `modules/job_search/tests/test_layout.py` (4). With `test_module_folders`, `test_module_docs`, the agent tests and cv's, job_search's, main_assistant's and task_agents' own tests: 344 passed; ruff clean.
- **Files needing a restart:** `src/assistant/infra/claude_session.py`, `agent_profile.py`, `profile_agent.py`, `agent_access.py`, `__init__.py`, `developer_rules.md` (new). No core or contracts file changed.

## Left open

- **Your data folder isn't set:** pick a folder outside the repo and write `data_folder = "C:/…"` in `config/cv.toml` and `config/job_search.toml` (gitignored). At the next turn-on each module copies its workspace there once and asks with a new access card. The old `modules/<id>/workspace/` stays until you delete it.
- **The code in the workspaces** (cv's `.claude/skills` and `scripts/`, the job project's skills, `Recruiters/scripts` and `job_paths.py`) still lives in the data, copied with it. Moving it into the module folder (committed) means deciding what in it is personal (the job project's `CLAUDE.md` holds your profile) and how the agent finds skills outside its working folder: a decision for you, not built.
- **The live check of the whole agent** (a cv or job session started by the app after the restart): only the bare `claude -p` check was run. After the restart, ask cv_agent whether it sees the repo's CLAUDE.md, and whether the job agent still sees its project's CLAUDE.md.
- **Docs HTML** not rebuilt here (the caller runs one build); the new page `docs/architecture/short-overview.md` needs it.
