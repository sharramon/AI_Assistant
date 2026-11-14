# Module layout step 2: checklist

**Status:** built unattended 2026-11-13 (Auto), item by item, each ticked when its tests passed. **Waits for an app restart** (core and infra changed). Nothing is moved and nothing is committed: the mechanism is built, the default keeps today's layout, and the move itself is a step for you (the last section).

Step 2 of the [module layouts](module-layouts.html) page ("add-ons in their own folder outside the repo", flowchart 3 and its list L, A, D, T, C, P). The order of fixing: this is item 6. Step 1 is in [module-layout-step1-checklist.md](module-layout-step1-checklist.md).

Where the page leaves a choice open, the option taken is marked **Chosen:** with why.

## Items

### 1. One config line: `[core] module_folders` ☑

- `config/default.toml` gets `module_folders = []` under `[core]`, with a comment: each entry an absolute folder that holds module folders directly (`C:/AddOns` holding `cv/`, `job_search/`, ...). Yours go in `config/local.toml`.
- **Chosen:** absolute paths only (a relative one is refused), because the core will move to a server and a path from the current folder would change with where the app is launched. `~` is expanded.
- **Chosen:** empty by default, so with nothing configured the app finds exactly today's modules from exactly today's folder.
- Files: `config/default.toml`.
- Done when: the default config loads with the key, and `test_boundaries`' rule 2 (the core's settings name no add-on) still passes.

### 2. The loader finds modules in the outside folders ☑

- **Chosen (the page's L):** the outside folders are appended to `assistant.modules.__path__` at startup, so an outside module keeps its import name `assistant.modules.<id>`, and `find_modules`, `app_folders` / `add_app_folders`, `import_fresh`, reload, `modules.add` and `module_folder` work unchanged. The repo's folder stays first.
- `loader.configured_module_folders(config)` reads and checks the key (a list of absolute strings; `LoadError` otherwise); `loader.add_module_folders(folders)` checks each is a folder and appends it once.
- **Chosen:** a module id found in two folders (the repo's and an outside one, or two outside ones) is **refused at startup** (`LoadError`, "Startup failed: ..."), never silently shadowed by the first folder: the copy that runs must be the one you meant.
- `find_modules(root, folders=())` adds the folders first; `__main__.run_app` passes the configured ones and turns a `LoadError` into a startup failure.
- Files: `src/assistant/core/loader.py`, `src/assistant/core/__init__.py`, `src/assistant/__main__.py`.
- Tests (`tests/test_outside_modules.py`, new, with `tmp_path`): a fake add-on (with an `app/` package) in an outside folder is found, its app imports, it starts in an `App`, it's reloaded with new code; `modules.add` of a second one there works; a duplicate id in two folders is refused; a relative or missing folder is refused; nothing configured leaves `__path__` as it was.
- Done when: those pass and `test_find_modules`, `test_reload`, `test_control` still pass.

### 3. `agent_access` gives the right folder ☑

- **Chosen:** one lookup of where modules live, `module_roots()` in `infra/agent_access.py`, read from the `assistant.modules` package's path (the loader's list, so the two never disagree); the repo's folder when nothing else is set. `module_folder`, `in_module_folder` and `module_folder_of` (the Hub's folder check) look in every root. `MODULES_FOLDER` stays the repo's folder.
- Files: `src/assistant/infra/agent_access.py`, `src/assistant/infra/__init__.py`.
- Tests: an outside module's own folder is its write grant and its relative `workspace`'s base; `module_folder_of` finds it; the outside folder itself is no module's folder.
- Done when: those pass and `test_module_folders`' item 1 tests still pass.

### 4. The docs build picks up outside modules' docs ☑

- `scripts/build_docs.py`: `module_dirs()` (the repo's modules folder, then the configured ones, added through the loader) replaces the fixed `MODULES_DIR` in `module_doc_folders`, `check_module_tabs` and `module_classes`; the library row links each module's README by its real place. Output is unchanged: a module's pages still publish to `docs/html/modules/<id>/`.
- **Chosen:** a page outside `docs/` on another drive is named by its absolute path (no relative path exists across drives on Windows).
- Files: `scripts/build_docs.py`.
- Tests: with an outside fake add-on, its docs folder is found, its tab is in the add-ons group, `check_module_tabs` passes, its pages publish under `docs/html/modules/<id>/` and its library row links its folder.
- Done when: those pass and `test_module_docs` still passes.

### 5. Boundary and module-folder tests cover every folder ☑

- `tests/test_boundaries.py`: the rules run over every module root (the configured ones too), and two new rules: **a module outside the repo is an add-on** (the core group stays in the repo: "repo: core" in flowchart 3), and **no id in two roots**. Each with a planted break in `tmp_path`.
- `tests/test_module_folders.py`, `tests/test_find_modules.py`: the module list from every root, an add-on's folder by `module_folder`, so the item 19 tripwire checks an outside add-on in its real place.
- `conftest.py`: the configured folders added before any test imports a module; a plain `pytest` (its `testpaths`) also collects the outside folders' tests.
- Files: `tests/test_boundaries.py`, `tests/test_module_folders.py`, `tests/test_find_modules.py`, `conftest.py`.
- Done when: the planted breaks are caught and the real tree passes.

### 6. Add-ons don't assume they're in the repo; prompts name the folders from code ☑

- The Main Assistant's prompt names the module folders from `module_roots()` instead of the fixed `src/assistant/modules/`.
- cv's `REPO` (`parents[4]`, wrong, even an `IndexError`, once cv is outside) becomes infra's `REPO_FOLDER`; cv's `test_rezi_mcp` likewise; voice_notes' tests read their files from their own folder, not from the current folder.
- A tripwire: no add-on's code computes the repo from its own path (`parents[n]` with n ≥ 2 on `__file__`) or opens a `src/assistant/modules/...` path.
- Files: `src/assistant/modules/main_assistant/module.py`, `modules/cv/module.py`, `modules/cv/tests/test_rezi_mcp.py`, `modules/voice_notes/tests/test_voice_notes.py`, `tests/test_outside_modules.py`.
- Done when: main_assistant's, cv's and voice_notes' tests pass, and the tripwire passes on the real tree and catches a planted break.

### 7. Docs ☑

- `docs/architecture/core.md` and `modules.md` (found by folder: the extra folders), `docs/api/core.md` (`loader`), `docs/api/infra.md` (`module_roots`, the lookups), `docs/api/reusable.md`; this file's As built, Left open and the how-to.
- Done when: `test_module_docs` passes.


## As built

- **Item 1:** `config/default.toml` `[core] module_folders = []` with its comment. Absolute paths only; `~` expanded.
- **Item 2:** `core/loader.py`: `MODULE_FOLDERS_KEY`, `configured_module_folders(config)`, `add_module_folders(folders)` (appends to `assistant.modules.__path__` once each, after the repo's; `LoadError` for a missing folder or an id in two folders), `find_modules(root, folders=())`. `core/__init__.py` exports `LoadError` and `configured_module_folders`; `__main__.run_app` passes the configured folders and reports a `LoadError` as "Startup failed". Reload, `AddModule`, `app/` folders and `module.toml` needed no change: they already follow the package's path.
- **Item 3:** `infra/agent_access.py`: `module_roots()` (from the package's path, the repo's `MODULES_FOLDER` first); `module_folder` and `module_folder_of` look in every root, so `in_module_folder`, `access_items`' own-folder write and the Hub's `folders_clash` follow. Exported from `assistant.infra`.
- **Item 4:** `scripts/build_docs.py`: `module_dirs()` (config through the loader, then `module_roots`), `module_paths()`, `rel_path` / `shown` / `readme_link`; `module_doc_folders`, `check_module_tabs`, `module_classes` and the library row use them. The repo's output is unchanged (the library rows still read `../../src/assistant/modules/<id>/docs/README.md`).
- **Item 5:** `tests/test_boundaries.py`: every rule over every root (`ROOTS`), and `outside_core` / `ids_twice` with a planted tree (12 tests). `tests/test_module_folders.py` (`module_folders`, `_module_toml`, item 19's per-add-on test by `module_folder`), `tests/test_find_modules.py`, `tests/test_module_docs.py` read every root. `conftest.py` adds the configured folders at import and, on a plain `pytest`, appends them to the collected paths (`pytest_configure`).
- **Item 6:** `main_assistant/module.py`: `worker_prompt()` fills `MODULE_FOLDERS_MARK` from `module_roots` (`src/assistant/modules/<id>/`, then each outside folder); its own test is in `main_assistant/tests/test_main_assistant.py`. cv's `REPO` is `REPO_FOLDER` (was `parents[4]`); cv's `test_rezi_mcp` likewise; voice_notes' tests read from their own folder. The tripwire `climbs_out` in `tests/test_outside_modules.py` (with a planted break).
- **New:** `tests/test_outside_modules.py` (9 tests: nothing configured; bad settings; a fake add-on with an `app/` package in a `tmp_path` folder found, started, reloaded, a second one added with `AddModule`; an id twice refused; its agent's folders; its docs found, checked, tabbed, linked and in the library; the cross-drive link; the tripwire on the real add-ons and on a planted one). `scripts/move_add_on.py` (dry run by default; only run here as a dry run).
- **A check by hand:** with a throwaway config dir (`ASSISTANT_CONFIG_DIR`) naming a throwaway add-on folder, a plain `pytest` collected that add-on's test and the root conftest's fixtures applied to it; both folders deleted afterwards.
- **Tests:** the targeted run (boundaries, module_folders, module_docs, module_layout, control, find_modules, reload, edit_note, outside_modules, swap_every_module; main_assistant's, cv's, voice_notes', agent_hub's and job_search's own): **378 passed**. Ruff: **All checks passed!**
- **Files needing a restart:** `src/assistant/core/loader.py`, `core/__init__.py`, `src/assistant/__main__.py`, `src/assistant/infra/agent_access.py`, `infra/__init__.py`. No contract changed. `main_assistant` and `cv` changed too (a reload each, or the restart).

## Left open

- **The move itself** (yours): nothing was moved. The how-to is below.
- **One CLAUDE.md per add-on** and the **Main Assistant's session-long write grant on the add-ons folder** (flowchart 3): not built. The CLAUDE.md content is yours to write; a grant that ends with the session is a new permissions feature, which needs its own design talk. Until then, the Main Assistant asks with a card before it writes outside the repo (Manual), and the add-on agents keep their own-folder grant (built here).
- **Ruff on an outside folder:** `ruff check` at the repo doesn't see it, and `pyproject.toml`'s `src` glob (`src/assistant/modules/*/app`) doesn't name it. Run `ruff check C:/AddOns` with a `ruff.toml` there that has `extend = "C:/.../AI_Assistant/pyproject.toml"` and `src = ["*/app"]`.
- **The rule "outside the repo"** in cv (`token_file`, `work_dir`) and in `data_folder` still means the repo only; once cv is outside, cv's own folder isn't protected by it. Fine while the add-ons folder has no git, worth a look if it gets one.
- **Two git histories:** a contract change then touches two folders with no single commit, and an add-on's tests need the matching core. Not something code fixes.
- **The extension-marketplace note** (`docs/next-steps/extension-marketplace.md`, "The loader imports only from the repo's own module folder ... no configurable root, no extra path") now disagrees with what step 2 built. Not edited: yours to decide whether that note is superseded.
- **Module docs** still name `src/assistant/modules/<id>/` in their text; after a move they're stale by path only (the build finds them by folder).
- **Docs HTML** not rebuilt here (the caller runs one build).

## How to move an add-on out (for the user)

Do this with the app stopped. Move **cv and job_search together** into the same folder: the job agent's `job_paths.json` reaches cv's output as `../../cv/workspace/out`, which holds only while they're side by side.

1. Restart the app once first with this build and check it still starts as before (`module_folders = []`).
2. Pick a folder outside the repo, e.g. `C:/AddOns`. Commit or stash the add-on's uncommitted work first: the copy takes the folder as it is on disk, its gitignored `workspace/` included.
3. Dry run, then copy: `.\.venv\Scripts\python scripts\move_add_on.py cv C:/AddOns` (says what it would do), then the same with `--yes`. It refuses a core module, a relative or in-repo target, and a target that already has the module. Without the script: copy `src/assistant/modules/<id>` to `C:/AddOns/<id>` by hand.
4. Delete the repo's copy (`git rm -r src/assistant/modules/<id>`, or the script's `--delete-old`), and commit that in the repo. While both copies exist the app refuses to start ("module 'cv' is in two folders"), on purpose.
5. In `config/local.toml`: `[core]` then `module_folders = ["C:/AddOns"]`.
6. Restart the app. `modules.list` shows the add-on as before; its agent's next turn-on asks with a new access card (its own folder changed).
7. Check: `.\.venv\Scripts\python -m pytest` (a plain run collects `C:/AddOns`' tests too), and `.\.venv\Scripts\python scripts\build_docs.py` (its docs still publish under `docs/html/modules/<id>/`).
8. Optional: `git init` in `C:/AddOns` with a `.gitignore` naming `*/workspace/` and `__pycache__/`; a `CLAUDE.md` per add-on; a `ruff.toml` (Left open).

To undo: copy the folder back into `src/assistant/modules/`, empty `module_folders`, restart.