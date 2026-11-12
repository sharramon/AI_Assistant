# Handoff: personal-data cleanup and module docs into modules

**Asked (2026-11-12):** replace real application details with placeholders, untrack scratch and temp pages, extend `.gitignore`, and move each module's docs into its own folder. No push, no history rewrite, no git config change.

## Done (2026-11-12)

- `bf17b1f` Placeholders: 205 replacements in 25 files (made-up names: ExampleCorp, Acme Bio, Globex, Umbrella, Initech, Jane Doe; Rezi IDs zeroed; the test_rezi_items fixture's name, school, degree, dates and bullets).
- `0730d84` Untracked `docs/temp/job-project-overview.html` and the five `scratch/*.html` pages (still on disk, ignored). `.gitignore`: secrets, `*.local.*`, `data/`, CV formats, tokens, snips, Jobs/Recruiters, scratch and temp. `module-folders.html` now lives in `docs/next-steps/`; `build_docs.py` (`copy_hand_pages`) copies `docs/next-steps/*.html` into `docs/html-next-steps/`.
- `f71b54b` Docs rebuilt.
- **The `cv_prefix` setting (answers 1, 3, 5), commit "cv_prefix setting":**
  - `cv/data.py`: `CV_PREFIX` (repo default `CV_Test_`), `cv_prefix()`, `check_cv_prefix()` (letters, digits, `_`, `-`), `set_cv_prefix()` (recompiles `BASE_CV_NAME`). The module's init calls `set_cv_prefix(settings["cv_prefix"])`; `settings()` checks it; `output_path(..., prefix=None)` uses it; `tool_settings` passes it; `CvTool` launches the CV Tool with `--cv-prefix`; the worker prompt fills `{cv_prefix}`. Menu descriptions say `<cv_prefix>*.pdf`.
  - `src/cv_tool`: `cvlib.configure(..., cv_prefix=)` sets `cvlib.CV_PREFIX`, used for finding base CVs, the corpus and every PDF name; `server.py` has the `cv_prefix` default, key and `--cv-prefix` flag; `cv_tool.toml` has `cv_prefix = "CV_Test_"`.
  - The real prefix is only in the two gitignored files: `config/local.toml` (`[modules.cv] cv_prefix`) and `src/cv_tool/cv_tool.local.toml`. No tracked file has it (`git grep` checked); it stays in git history (no rewrite, as asked).
  - Tests, cv docs and comments use `CV_Test_`. The cv README's config table has the `cv_prefix` row. A test checks the default and that a bad prefix is refused.
  - Deleted `test_the_cancelled_examplecorp_job_as_a_case` with its `EXAMPLECORP` constant and fixture (answer 3).
  - `tests/test_module_docs.py::test_main_docs_never_link_into_next_steps` allows the one link `docs/architecture/README.md` → `../../html-next-steps/module-folders.html` (answer 5).
  - ruff clean; full suite: all passed (798).
  - Design note: the prefix is module-level state in `cv/data.py` (set at init) because `CvRequest`'s validator has no settings; a reload re-imports and sets it again.

## Module docs move: done (2026-11-12), commits "module docs move" and "docs rebuilt"

Finished in a second session: the docs-html skill updated (central `SECTIONS`, tabs and groups from `docs.toml`, a new module's own `docs/` folder), wording checked (no "central", no `docs/modules` outside next-steps history), docs built (72 pages, every module's `tools.md` generated, the library split into Core modules and Add-ons), ruff clean, full suite 800 passed. Architecture check: every module's docs are found by folder, the build knows no module by name, the grouping lives only in each `docs.toml`; the layout and groups are written in the module library's "Module pages" section. Left as is: `config/voice_service.toml` still names the old `docs/architecture/voice.md` in a comment (config untouched); the `app_kit.module_docs` change (`group` key) needs an app restart to reach the running app. Nothing pushed.

**What the first session did (in the same commit):**

- `scratch/move_module_docs.py` (gitignored, one-off, already run; don't run again) split each `docs/modules/<id>.md` into `src/assistant/modules/<id>/docs/README.md` (Purpose, Wrapper, Config, Code and tests + a `docs/` line) and `architecture.md` (Interface, Owns and launches, Inner workings, Shown, Planned); moved `architecture/voice.md` → `voice_in/docs/voice-service.md`, `architecture/html-viewer.md` → `html_viewer/docs/viewer-app.md`, `job-project/README.md` → `job_search/docs/job-project.md`; wrote every module's `docs.toml` (`group`, `tab`, `pages`, `related`); rewrote every relative link (anchors to the right split page) in docs, next-steps, archive, next-steps `*.html`, root README/CLAUDE.md, `.claude/**/*.md`; replaced plain-text old paths in `src/**/*.py`. `docs/modules/` and `docs/job-project/` are deleted. `docs/modules/README.md`'s template is now the "Module pages" section of `architecture/module-library.md`.
- Tabs: core group first (Agents: agent_hub, main_assistant, talker, task_agents, usage; Terminals and temp UI: assistant_view, console_io, temp_ui; voice_in), then add-ons (cv, echo_orchestrator, html_viewer, job_search, voice_notes, each its own tab). A separator before each group.
- `scripts/build_docs.py`: `CENTRAL_MODULES`, `MODULE_TABS`, `TAB_KEYS`, `PROJECT_TABS`, `MODULE_INDEX` removed; `SECTIONS = (architecture, agents, api)`; `GROUPS`; `module_tabs()` from docs.toml only, sorted by group; `check_module_tabs()` requires a docs folder per module package, a valid `group`, no mixed-group tab; `nav_data` one sidebar group per module; `library_block()` writes "### Core modules" and "### Add-ons" tables.
- `app_kit/module_docs.py`: `group` in `SETTINGS_KEYS` and the docstring (shared helper: say in the summary an app restart picks it up). `docs/api/app_kit.md` docs.toml table has `group`. cv and echo `docs.toml` have `group = "add-on"` (echo's old tab dropped). `job_search/module.py` docstring path; `next-steps/extension-marketplace.md` row.
- Tests rewritten: `tests/test_module_docs.py` (groups, no docs/modules, job project in job_search tab, library rows per group) and `tests/test_module_layout.py` (no `NOT_MOVED_YET`/central test; bad-docs.toml cases with `group`).

**Next steps it listed (all done):**

1. Update `.claude/skills/docs-html/SKILL.md` lines 12-21 (SECTIONS, tabs from docs.toml with group, a new module = its own `docs/` folder with the three pages and `docs.toml`; no `docs/modules/`, no `MODULE_TABS`, no Job project tab).
2. Check the new pages' wording: the "Planned" lines no longer say "central"; titles of the architecture pages (`# <id>: architecture`); `grep` for leftover `docs/modules`, "central module", "Stand-ins and terminals" outside next-steps history.
3. Run `.\.venv\Scripts\python scripts\build_docs.py` (it generates each new `tools.md` and the grouped library), then ruff and the full suite; fix failures (hand loops to the `debugger` subagent).
4. Architecture check; commit "module docs move" then "docs rebuilt". No push. Mention: `config/voice_service.toml` still names the old `docs/architecture/voice.md` in a comment (config left untouched); app restart needed for the `app_kit` change.

## The plan for the move (answers 2 and 4)

**The user's decisions (2026-11-12):**

- **Every module's docs into its own folder**, the eight modules decided central on 2026-11-06 too (this replaces that decision). Each gets README, architecture and tools (generated from its menu) plus `docs.toml`. Central docs keep only the core host, architecture overview, API reference, principles, agents docs and next-steps.
- **Grouping in the docs** (tabs or sidebar; not where the files live, which is always the module folder): **Core group**: agent_hub, talker, main_assistant, temp_ui, console_io, task_agents, usage, voice_in, assistant_view (for now). **Add-ons**: cv, job_search, html_viewer, voice_notes, echo_orchestrator.
- **Move** `docs/job-project/README.md` into `src/assistant/modules/job_search/docs/` (drop `PROJECT_TABS` / `job-project` from `SECTIONS` in `build_docs.py`).

**Steps:**

- Move each `docs/modules/<id>.md` into `src/assistant/modules/<id>/docs/` (README, architecture, tools, plus a `docs.toml` with its tab, group and related links from `MODULE_TABS`). Move `architecture/html-viewer.md` into html_viewer's docs. `architecture/voice.md` covers the voice service app and voice_in: move it into voice_in's docs only if it is truly about that one module.
- Remove `CENTRAL_MODULES` and its checks in `build_docs.py` and its expectations in `tests/test_module_docs.py`; trim `MODULE_TABS`; add the Core / Add-ons grouping. Keep `docs/modules/README.md` as the index or fold it into the module library. Fix every link (overview Pages list, module library, api pages, agents docs, test expectations).
- Rebuild, ruff, the full suite, then commit "module docs move" and "docs rebuilt". No push.
- Not in scope, noted: personal paths in `config/default.toml`, `cv/module.toml`, `cv_tool.toml`, `.claude/`; the tracked `spikes/` scripts.

No Chrome tabs are open for this task.
