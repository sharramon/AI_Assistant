# Handoff: personal-data cleanup and module docs into modules

**Asked (2026-11-12):** replace real application details with placeholders, untrack scratch and temp pages, extend `.gitignore`, and move each module's docs into its own folder. No push, no history rewrite, no git config change.

## Done (2026-11-12)

- `bf17b1f` Placeholders: 205 replacements in 25 files (made-up names: ExampleCorp, Acme Bio, Globex, Umbrella, Initech, Jane Doe; Rezi IDs zeroed; the test_rezi_items fixture's name, school, degree, dates and bullets). The CV prefix was replaced only in `docs/next-steps/` and `docs/job-project/` (`CV_Test_`).
- `0730d84` Untracked `docs/temp/job-project-overview.html` and the five `scratch/*.html` pages (still on disk, ignored). `.gitignore`: secrets, `*.local.*`, `data/`, CV formats, tokens, snips, Jobs/Recruiters, scratch and temp. `module-folders.html` now lives in `docs/next-steps/`; `build_docs.py` (`copy_hand_pages`) copies `docs/next-steps/*.html` into `docs/html-next-steps/`.
- `f71b54b` Docs rebuilt.
- ruff clean. pytest: 797 passed, 1 skipped, 1 failed. The failure was there before this work: `test_main_docs_never_link_into_next_steps`, from the "Currently fixing" link in `docs/architecture/README.md`.

## Waiting on the user

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
