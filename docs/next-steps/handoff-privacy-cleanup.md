# Handoff: personal-data cleanup and module docs into modules

**Asked (2026-11-12):** replace real application details with placeholders, untrack scratch and temp pages, extend `.gitignore`, and move each module's docs into its own folder. No push, no history rewrite, no git config change.

## Done (2026-11-12)

- `bf17b1f` Placeholders: 205 replacements in 25 files (made-up names: ExampleCorp, Acme Bio, Globex, Umbrella, Initech, Jane Doe; Rezi IDs zeroed; the test_rezi_items fixture's name, school, degree, dates and bullets). The CV prefix was replaced only in `docs/next-steps/` and `docs/job-project/` (`CV_Test_`).
- `0730d84` Untracked `docs/temp/job-project-overview.html` and the five `scratch/*.html` pages (still on disk, ignored). `.gitignore`: secrets, `*.local.*`, `data/`, CV formats, tokens, snips, Jobs/Recruiters, scratch and temp. `module-folders.html` now lives in `docs/next-steps/`; `build_docs.py` (`copy_hand_pages`) copies `docs/next-steps/*.html` into `docs/html-next-steps/`.
- `f71b54b` Docs rebuilt.
- ruff clean. pytest: 797 passed, 1 skipped, 1 failed. The failure was there before this work: `test_main_docs_never_link_into_next_steps`, from the "Currently fixing" link in `docs/architecture/README.md`.

## The user's answers (2026-11-12), to do next

1. **Yes, a `cv_prefix` setting.** Repo default `CV_Test_`; the real prefix goes in gitignored local config: create `config/local.toml` (it doesn't exist yet) with `[modules.cv]` `cv_prefix = "<real prefix>"`, and `src/cv_tool/cv_tool.local.toml` with `cv_prefix = ...`. The real value is in git history and in the old notes' wording; take it from `git show bf17b1f~1:src/assistant/modules/cv/data.py` (`BASE_CV_NAME`). Plan, no edits made yet:
   - `cv/data.py`: `CV_PREFIX = "CV_Test_"`, `cv_prefix()`, and `set_cv_prefix(p)`, which checks the value (letters, digits, `_`, `-`) and recompiles `BASE_CV_NAME`; the `_pdf` validator and the `base_cv` description use it.
   - `cv/module.py`: `settings()` reads and checks `cv_prefix` and returns it; the module's init (line ~217, after `settings(...)`) calls `set_cv_prefix`; `output_path(..., prefix=None)` defaults to `cv_prefix()`; menu descriptions (lines 94, 97, 150, 359, 568, 637, 731, 765) say `<cv_prefix>*.pdf`; `tool_settings(...)` gets the prefix.
   - `cv/worker.py`: the prompt's three mentions become `{cv_prefix}`, passed in `worker_prompt` from `settings["cv_prefix"]`.
   - `cv/tool.py`: `tool_settings` returns `cv_prefix`; `CvTool` passes `--cv-prefix`.
   - `cv/module.toml`: `cv_prefix = "CV_Test_"` (and fix the cv_dir comment).
   - `src/cv_tool/server.py`: the `cv_prefix` default, the `--cv-prefix` flag, the key list, passed to `cvlib.configure`. `cvlib.py`: `configure(..., cv_prefix="CV_Test_")` sets a global `CV_PREFIX`, which replaces the literals at lines 168, 347, 353, 692, 695, 698, 1136 and 1460. `cv_tool.toml`: `cv_prefix = "CV_Test_"`.
   - Then the placeholder script (`scratch/cleanup_replace.py`, ignored) with `PREFIX_DIRS` widened to `src/` (cv tests, cv/docs, comments in content.py, pdf_read.py, odt.py), or a direct replace of `CV_Test` → `CV_Test` in those files. Check that no real prefix is left outside the two local files.
2. **Every module's docs into its own folder**, the eight "central" modules too (this replaces the 2026-11-06 decision; remove `CENTRAL_MODULES` and its checks in `build_docs.py`, and its expectations in `tests/test_module_docs.py`). Each gets README, architecture and tools (generated) plus `docs.toml`. Central docs keep only the core host, architecture overview, API reference, principles, agents docs and next-steps. Docs grouping (tabs or sidebar), not location: **Core group**: agent_hub, talker, main_assistant, temp_ui, console_io, task_agents, usage, voice_in, assistant_view. **Add-ons**: cv, job_search, html_viewer, voice_notes, echo_orchestrator.
3. **Yes, delete** `cv/tests/test_job_start.py::test_the_cancelled_examplecorp_job_as_a_case` and its `EXAMPLECORP` constant and `examplecorp_untouched` fixture if nothing else uses them.
4. **Yes, move** `docs/job-project/README.md` into `src/assistant/modules/job_search/docs/` (drop `PROJECT_TABS` / `job-project` from `SECTIONS` in `build_docs.py`).
5. **Keep the link**: add an exception in `tests/test_module_docs.py::test_main_docs_never_link_into_next_steps` for `docs/architecture/README.md` → `../../html-next-steps/module-folders.html`.

Commits after: "cv_prefix setting", "module docs move", "docs rebuilt". ruff and the full suite before each. No push.

## Asked before the answers (kept for the record)

1. **The CV prefix in code.** `cv/data.py` (`BASE_CV_NAME`), `cv/module.py` (`output_path`, tool descriptions), `cv/worker.py` (the prompt) and `src/cv_tool/cvlib.py` (finding base CVs, naming output PDFs) use the real prefix as a rule, and the cv tests and `cv/docs` follow it. Recommended: a `cv_prefix` setting (`cv/module.toml` and `cv_tool.toml`, repo default `CV_Test_`, the real value in the gitignored `.local` overrides), then tests and docs use `CV_Test_`.
2. **Central modules.** `build_docs.py` `CENTRAL_MODULES` (user decision, 2026-11-06) keeps agent_hub, talker, main_assistant, task_agents, usage, console_io, assistant_view and temp_ui in `docs/modules/`. The new ask names task_agents and usage too. Recommended: move every module, each with the three standard pages (README, architecture, tools generated from its menu).
3. `cv/tests/test_job_start.py::test_the_cancelled_examplecorp_job_as_a_case` read a real CV copy outside the repo. With the placeholder name it is now always skipped. Recommended: delete it.
4. `docs/job-project/README.md` is about the job project, not the core. Recommended: move it into `job_search/docs/`.
5. The pre-existing failure: recommended to make the overview's link to `module-folders.html` plain text.

## Next (part 4, after the answers)

- Move each `docs/modules/<id>.md` into `src/assistant/modules/<id>/docs/` (README, architecture, tools, plus a `docs.toml` with its tab and related links from `MODULE_TABS`). Move `architecture/html-viewer.md` into html_viewer's docs. `architecture/voice.md` covers the voice service app and voice_in: move it into voice_in's docs only if it is truly about that one module.
- Trim `MODULE_TABS` / `CENTRAL_MODULES` in `build_docs.py`; keep `docs/modules/README.md` as the index or fold it into the module library. Fix every link (overview Pages list, module library, api pages, agents docs, tests/test_module_docs.py expectations).
- Rebuild, ruff, the full suite, then commit "module docs move" and "docs rebuilt".
- Not in scope, noted: personal paths in `config/default.toml`, `cv/module.toml`, `cv_tool.toml`, `.claude/`; the tracked `spikes/` scripts.
