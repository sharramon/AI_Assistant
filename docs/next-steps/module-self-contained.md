# Self-contained modules, like downloadable extensions

> **Status: building (2026-11-06).** Approved with the user's answers ([Decisions](#decisions-2026-11-06)); steps 0 to 2 are built, the [standard layout](#the-standard-docs-layout-decided-2026-11-06) is built, and the eight central modules stay in the main docs (decision 8: `usage`, `console_io` and `assistant_view` were moved back) ([Build progress](#build-progress-and-next)). Umbrellas (roles) are designed only, not to be built yet.

**Asked:** "the module rules should be acting almost like independent apps where they can have all of their own documentation, their launches … put them into their own folders, so that later we can build them out as apps … download that on the fly, like extensions." The main system should only query a module through the directory and its menu (the tools). It should not hold or need every module's docs, because later there may be a library of modules by other people, so the core can't know what exists.

**Why:** today a module is self-contained only in its code. Its doc page, its config, its tests and its doc tab all live in central places, and some core and shared code names specific modules. A module can't be lifted out or dropped in.

**Touches:** every module folder, `docs/modules/`, `docs/architecture/module-library.md`, `config/default.toml`, `tests/`, `scripts/build_docs.py`, `tests/test_module_docs.py`, a few lines in `core/`, `infra/` and `contracts/`, and the independent apps `src/html_viewer/` and `src/voice_service/`.

## Step 1: the audit (what lives outside each module's folder)

**The same for every module:**
- **Docs:** `docs/modules/<id>.md`, which must be linked from `docs/modules/README.md` (checked by `tests/test_module_docs.py`).
- **Library row:** a row in the generated library (`docs/architecture/module-library.md`). That part is already discovered: `build_docs.py` imports each module folder and reads its manifest and menu.
- **Config:** a `[modules.<id>]` section in `config/default.toml`. `ctx.config` is exactly that section (`core/app.py:195`).
- **Doc tab:** a hand-written entry in `MODULE_TABS` (`build_docs.py:62-114`). The build fails if a module page has no tab.
- **HTML:** the build only converts `.md`. It finds pages through fixed sections (`SECTIONS`, line 45) and copies only `img/` folders. **A module can't ship its own HTML pages.** That blocks the CV module, which has to design and write its own pages.

| Module | Inside its folder | Outside its folder |
|---|---|---|
| `console_io` | code | page; tab "Stand-ins"; `default.toml:13-14`, and `:188` (logging.stderr kept false for it); tests in `test_control`, `test_find_modules`, `test_module_docs` (expects it first) |
| `talker` | code, prompt, session | page; tab "Agents"; `agents/runtime.md` sections; `default.toml:16-24`; ~10 test files |
| `main_assistant` | code | page; `runtime.md`; `default.toml:26-58`; named as the default coordinator (`:61`) and reviewer (`:167`); `scripts/hooks/edit_tracker.py`; `.claude/state/main_assistant-task.txt` |
| `agent_hub` | code | page; the Hub's menu in `api/agents.md`; `default.toml:60-63`; owns `IModuleDoor`, `IAgentNames` and the Hub commands in `contracts/` |
| `task_agents` | code | page; `default.toml:65-94` (the helper kinds); `test_task_agents`, `test_agent_tabs`; `tests/support.py` imports it |
| `job_search` | code | page; `default.toml:96-110`; its grant in `data/permissions.toml`; 5 test files |
| `temp_ui` | code, `page.html`, `static/` | page; `runtime.md:52-85`; `default.toml:116-120`; named as "you" (`:170`); `scripts/restart_app.ps1` |
| `voice_in` | code, cleanup, line | page; its tab also holds `architecture/voice.md` (647 lines); `api/messaging.md` voice section; `default.toml:134-148` and command timeouts (`:175`); the `voice` extra; owns all of `contracts/voice.py` |
| `voice_notes` | code, `page.html` | page; tab; `default.toml:150-155`; `test_voice_notes` |
| `usage` | code | page; tab; `UsageLedger` in `infra/`; `default.toml:112-114` |
| `html_viewer` | code | page; its tab also holds `architecture/html-viewer.md`; `default.toml:122-132`; owns `ViewerTabsChanged`, `ViewerClip`, `ViewerClipDropped` in `contracts/messages.py`; `test_html_viewer`, `test_menu`, `test_swap_every_module` |
| `assistant_view`, `echo_orchestrator` | code | pages; tab "Stand-ins"; `echo.say` in `api/tools.md`; `restart_app.ps1` (assistant_view) |
| app `src/html_viewer/` | the whole app | `pyproject.toml` entry point; `architecture/html-viewer.md`; `restart_app.ps1`; tests in `tests/` |
| app `src/voice_service/` | the whole app | `config/voice_service.toml`; entry point and `voice` extra; `architecture/voice.md`, `api/messaging.md`, `api/reusable.md`; `scripts/voice_two_pass_check.py`; 4 test files; CI installs `.[dev,voice]` |

**Core and shared code that names a module** (the core should name none):
- `core/permissions/handler.py:55,117-150`: `REVIEWER = "main_assistant"`, `you=("temp_ui",)`.
- `infra/agent_names.py:13`: `RESERVED_AGENT_IDS` = main_assistant, talker, core, hub.
- `infra/session_agent.py:421-423`: the `<<SHOW:>>` tag calls `viewer.open` / `viewer.highlight` by name.
- `infra/agent_profile.py:70`: the prompt names the `task_agents` menu.
- `contracts/voice.py:22`: `TALKER = "talker"`. `contracts/door.py`: "Provided by `agent_hub`" (docstring).
- `app/__main__` and `modules/__init__` name none. That part is already good.

**Between modules:** no module imports another module's package. They are coupled by ids and tool names: `temp_ui` uses `voice_in`, `usage`, `task_agents`, `main_assistant` and `viewer.open`. `talker` uses `hub.*`, `usage.*` and `viewer.*`. `agent_hub` and `task_agents` both have `TALKER = "talker"`.

**Packaging:** one distribution holds `assistant`, `app_kit`, `html_viewer` and `voice_service`. There is no packaging per module.

## Step 2: the target layout

```
src/assistant/modules/<id>/
  __init__.py, module.py      manifest + menu (as today)
  module.toml                 its config defaults ([modules.<id>] moves here)
  docs/
    README.md                 the module's page (was docs/modules/<id>.md)
    *.md                      more pages (e.g. voice.md for voice_in)
    *.html                    pages the module wrote itself, shipped as they are
    img/
    docs.toml                 tab title, order, which pages go in the nav
  tests/                      its own tests (shared fakes stay in tests/)
  app/ or a companion entry   for a module with its own app: how it launches
```

- **Config:** each module ships its defaults in `module.toml`. The app's `config/default.toml` keeps only `enabled`, the core's own settings, and overrides. The loader merges defaults → `default.toml` → `local.toml`, so `ctx.config` stays the same section it is today.
- **Docs build:** `build_docs.py` discovers `src/assistant/modules/*/docs/`. It also accepts a folder with only `docs/` and no code yet, like `cv`. Markdown is converted as today. **HTML pages are copied as they are** into `docs/html/modules/<id>/` and listed in the nav, without being rewritten. The tab comes from `docs.toml`, so `MODULE_TABS` and `docs/modules/<id>.md` go away. `docs/modules/README.md` becomes a generated index.
- **Module library:** already generated from the manifests. Each row also links to the module's own docs folder. The directory (`ListModules`) can give that link too, so agents find a module's docs through the directory rather than a central folder.
- **Tests:** `pytest` also collects `src/assistant/modules/*/tests/`. Shared fakes (`tests/support.py`, `fake_claude.py`) stay central, as a test kit.
- **The core names no module:** the ids it needs become **roles** set in config (`[roles] coordinator = "main_assistant"`, `talker = "talker"`, `you = ["temp_ui"]`, `page_viewer = "viewer"`). The permissions handler, `RESERVED_AGENT_IDS`, the SHOW tag and the `TALKER` constants read those roles. A missing role means "not available", not a crash.
- **Independent apps:** `src/html_viewer/` and `src/voice_service/` each get their own `docs/`, `tests/` and config defaults (`voice_service/voice_service.toml`) in their own folder, the same way.

## Migration order (tests and ruff pass after each)

0. **Support both layouts** (no module moves yet). The loader merges `module.toml` when it exists. The build discovers `modules/*/docs/` (Markdown and HTML) and falls back to `MODULE_TABS` and `docs/modules/` for modules that haven't moved. Pytest collects module test folders. *Needs an app restart* (core loader). The build is a script, so no restart for it.
1. **Pilot `echo_orchestrator`**, the smallest: page, tests and a `docs.toml` into its folder (it has no config).
2. **`cv`** (docs only, no code yet): its HTML page is picked up by the new build.
3. **One at a time, the self-contained features:** `voice_notes`, `html_viewer`, `job_search`, and `voice_in` (with `voice.md`) unless it's made central. Not the eight [central modules](#decisions-2026-11-06) (decision 8): their docs stay in the main docs. Moving docs and tests needs no reload. Moving config defaults needs a `RELOAD: <id>`.
4. **Roles instead of ids** in `core/permissions`, `infra/agent_names`, `infra/session_agent` (SHOW), `infra/agent_profile`, `contracts/voice.py`. *Needs a restart* (core, infra, contracts).
5. **The independent apps' docs, tests and config** into their own folders.
6. **Remove the fallbacks:** `MODULE_TABS`, the `docs/modules/<id>.md` pages, and the per-module sections of `default.toml`. Update `test_module_docs.py`, the docs-html skill and the architecture pages (modules, reusable parts, the overview's Parts table).

**Still needs a restart after all this:** changes to the core, `contracts`, `infra` and `app_kit`, and a module that brings a new contract. A module's code, docs, tests and config defaults then reload or rebuild without one.

## The CV module's first page (done now, at the user's request)

`cv_module_workflow.html` (written by Rezi, 2026-11-06) goes word for word into `src/assistant/modules/cv/docs/`. The folder has no `__init__.py`, so the loader skips it (`loader.find_modules`), and nothing in `docs/html/` or `docs/modules/` changes. Until step 0 is built, the build doesn't publish it, so it's read from that folder directly. Its wording is older than Rezi's notes (`rezi-mcp-findings.md` v4) on three points: Chrome only inside the rezi module, no Rezi AI writer in v1, and tasks through the Hub rather than `rezi.tailor_cv`. It is left unchanged until the user says otherwise.

## Decisions (2026-11-06)

**Principle:** the main AI learns what a module does by querying the module itself (its menu, its tool descriptions, and its own docs through the directory: `modules.docs`), not from the project's dev notes or central docs. This goes into the architecture docs ([modules](../architecture/modules.md), [principles](../architecture/principles.md)) with step 6.

1. **Config defaults in `module.toml`, `default.toml` only for `enabled` and overrides:** yes.
2. **Module-only design pages** (`voice.md`, `html-viewer.md`) **move into the module's `docs/`:** yes. Cross-cutting pages stay central.
3. **A module's own HTML pages: the standard frame, always** (answered 2026-11-06). Every module's docs follow one standard layout, so you know where things are whatever the module: see [the standard docs layout](#the-standard-docs-layout-decided-2026-11-06). The frame is the standard, not an opt-in: the `frame` setting is gone.
4. **Contracts owned by one module stay in `assistant.contracts`** for now: yes.
5. **Umbrellas (roles): designed, not built yet.** See below. Until then the core keeps naming the modules it names today (step 4 is on hold).
6. **No package per module yet,** but the folder layout is designed as if each module could become its own downloadable package, developed in isolation: its code, `module.toml`, `docs/` and `tests/` in its folder, with no imports of another module's package. Its tests use only the shared test kit (`tests/support.py`, the root `conftest.py`).
7. **Change notes about one module stay in `docs/next-steps/`:** yes.
8. **Central modules stay in the main docs** (answered 2026-11-06). **The rule:** a module that's part of the main app and its window stays central; a self-contained feature (`html_viewer`, `cv`, `job_search`, `voice_notes` and the like) gets its own folder and the three standard pages. **Central (eight):** `agent_hub`, `talker`, `main_assistant`, `task_agents` (the agent runtime: every message goes through the Hub, and every helper runs through `task_agents`), `usage` (the app's tally, shown in its window), `console_io`, `assistant_view` (the terminals) and `temp_ui` (the window). **Why:** they're how the app itself works, so their docs belong with the app's docs, not in a folder as if they were a downloadable extension. They keep `docs/modules/<id>.md`, their `MODULE_TABS` entries ("Agents", "usage", "Stand-ins and terminals") and their `default.toml` sections, and they're exempt from the move and the three standard pages. `usage`, `console_io` and `assistant_view` had been moved and were moved back (their central pages restored, `console_io`'s `module.toml` back into `[modules.console_io]`, `usage`'s menu test back in `tests/test_usage.py`). The build names them in `CENTRAL_MODULES` (`scripts/build_docs.py`) and refuses a central module that has its own docs folder or no central page. **Open:** where `echo_orchestrator` and `voice_in` go.

### The standard docs layout (decided 2026-11-06)

- **One layout for every module:** the same tabs across the top and the same sidebar down the side. Each module with its own docs gets its own sidebar group, then Related (only if it names any) and App-wide. A group with nothing in it is left out, so a small module shows less in the same layout.
- **Three standard pages, required, always first and in this order:**
  - **Overview** (`docs/README.md`): purpose, wrapper, config, code and tests.
  - **Architecture** (`docs/architecture.md`): interface, what it owns and launches, inner workings, planned.
  - **Tools** (`docs/tools.md`): generated by the build from the module's own menu (`app_kit.module_docs.tools_page`), so it's always right. It's written into the module's folder, so the core's `modules.docs` lists it and the main AI reads it by asking the module (and `modules.menu` gives the same items live). Hand-written text before the `tools:start` marker and after `tools:end` is kept; the part between is regenerated. A module with no code yet (`cv`) gets "No menu yet" there, and its planned menu goes in the notes.
- **Other pages are optional** (`docs.toml` `pages` orders them after the standard three). An HTML page a module wrote opens inside the standard frame (`frame.html?src=<page>`), so it needs no tabs or menu of its own.
- **Who needs them:** every module except the eight central modules (decision 8), which are exempt and keep their central page.
- **Kept true by tests:** the build refuses a moved module that lacks one of the three pages. `test_every_module_has_the_three_standard_pages` fails for any module that has no own folder with all three, except the central modules and those in `NOT_MOVED_YET`, a list in that test that only shrinks: a moved module must leave it, it may not name a module that doesn't exist, and it never holds a central module. `test_central_modules_keep_their_central_page` checks the central ones keep `docs/modules/<id>.md` and have no own folder. `test_every_modules_tools_page_is_current` fails when a tools page is out of date with its menu.

### Umbrellas: modules that do the same job (the user's design, not built yet)

- **An umbrella** is one kind of job: voice input, page viewer, coordinator, chat UI. Modules by different people that do that job all sit under one umbrella.
- **Every umbrella has a standard set of tools**, a menu every module under it must expose (e.g. the page viewer's `open`, `highlight`, `tabs`). The main AI uses any module under it the same way without knowing which one it is. The core checks a module's menu against its umbrella's tool set when the module loads, and refuses the module if it doesn't match.
- **A default per umbrella**, picked by the user in settings (`[umbrellas] page_viewer = "html_viewer"`). Calls to the umbrella's tools (and the core's own needs, e.g. the SHOW tag, the permissions reviewer, "you") go to the default.
- **Asking and switching:** core menu items, for example `umbrellas.list` (each umbrella, its tool set, its modules, its default) and `umbrellas.set_default(umbrella, module_id)`, so the user or an agent can switch while the app runs, with no restart. Switching turns on the new default if needed. It is saved like a grant.
- **How it relates to the contracts:** an umbrella's tool set is the menu side of a contract. Where a contract exists (`IVoice` for voice input, `IModuleDoor`), the umbrella is that contract plus its standard menu, and its default is the provider `requires` resolves to when several modules provide it (today two providers of a required contract is an error). Where there's no contract (the page viewer), the umbrella's tool set is its whole definition. The umbrella definitions (name, tool set, optional contract) live with the contracts in `assistant.contracts`, so a new umbrella needs a restart and a new module under an existing one doesn't.
- **To discuss before building:** tool names inside an umbrella (shared names like `page_viewer.open`, or each module's own names mapped), and what happens to a call while the default is switching.

## Build progress and next

**Done (2026-11-06; 520 tests pass, ruff clean, docs rebuilt):**
- **Step 0, both layouts supported.** Core: `loader.module_folder`, `loader.module_defaults` (`module.toml`, read fresh on each context, so a reload picks it up), `LifecycleManager.module_class`, `App._config_of` (defaults with the `[modules.<id>]` section merged over them, for `ctx.config` and `start_on_use`), the core menu's `modules.docs`. `app_kit.merge` and `app_kit/module_docs.py`. Build (`scripts/build_docs.py`): `module_doc_folders()` finds every `src/assistant/modules/*/docs/` (a docs-only folder too); its pages go to `docs/html/modules/<id>/` (Markdown rendered, HTML and images copied as written); `module_tabs()` adds each to the tab its `docs.toml` names; `check_module_tabs` refuses both layouts at once, a moved module still in `MODULE_TABS`, unknown `docs.toml` keys and missing pages; `frame.html` and `frame = ...` are built (the frame refuses `..`, schemes and absolute paths); the library row links to the module's own README. Tests: `testpaths` includes `src/assistant/modules`, and the autouse fixture moved to a root `conftest.py`. New `tests/test_module_layout.py`; `tests/test_module_docs.py` accepts either layout.
- **Step 1, pilot `echo_orchestrator`:** its page is `src/assistant/modules/echo_orchestrator/docs/README.md` (with `docs.toml`: `tab = "Stand-ins and terminals"`), its own tests are `tests/test_echo.py` in its folder (the echo test moved out of `tests/test_menu.py`), and `docs/modules/echo_orchestrator.md` is gone. Its use as a stand-in in the core's tests stays in `tests/`.
- **Step 2, `cv`:** its page now publishes as written to `docs/html/modules/cv/cv_module_workflow.html`, in a new "cv" tab (no `docs.toml`, so it isn't framed). It opens outside the docs' menu until decision 3 is answered.
- API docs: `app_kit.md` (`merge`, `module_docs`), `control.md` (`modules.docs`), `core.md` (`module_class`, `module_folder`, `module_defaults`, `App`'s config), `reusable.md` and the API index.

**Architecture check (after step 0 and the pilot):** modular. The build and the core find a module's docs and defaults through its folder and know no module by name; `MODULE_TABS` and `docs/modules/` now hold only the modules that haven't moved. Reuse: one reader (`app_kit.module_docs`) for the core and the build, and one `merge`. Two things to watch:
- A moved module's page links into the app's docs by relative path (`../../../../../docs/api/...`). That works in this repo but breaks if the module is downloaded alone. **Proposed:** a module links to the app's docs only through `[related]` in its `docs.toml`, and its README keeps those links few. Decide this before moving the big modules.
- Not updated yet: the architecture pages (modules, reusable parts, the overview's Parts table), the page template in `docs/modules/README.md`, and the docs-html skill. They change with step 6.

**Done (2026-11-06, second session; 526 tests pass, ruff clean, docs rebuilt):**
- **The standard layout** (above): `app_kit.module_docs` (`STANDARD_PAGES`, the standard order in `doc_pages`, `tools_page`, `tools_intro`, `tools_notes`; `frame` dropped from `SETTINGS_KEYS`); `build_docs.py` (`write_tools_pages` before the checks, the three-pages check, a sidebar group per moved module with the standard names, every HTML page framed). Tests in `tests/test_module_layout.py`.
- **Step 3: `usage`, `console_io`, `assistant_view` moved** (moved back the same day: they're central, decision 8). Each had `docs/README.md`, `architecture.md`, `tools.md` (generated) and `docs.toml`; their `docs/modules/<id>.md` pages, their `MODULE_TABS` entries and their `default.toml` sections are gone. `console_io`'s `prompt` default is in its `module.toml`. `usage`'s menu test moved to `usage/tests/test_usage.py`; the cross-part usage tests stay in `tests/`. `echo_orchestrator` was split into the three pages too.
- **`cv`:** rezi wrote its three pages and `docs.toml`; `cv_module_workflow.html` was removed (its content is in those pages).
- **Not yet in the permanent docs:** the standard layout goes into `architecture/modules.md`, the page template in `docs/modules/README.md` and the docs-html skill with step 6.

**Standard pages, every module (2026-11-06):** all three for `echo_orchestrator` and `cv`. Four still have one central page and get the three as they move, in step 3 (`NOT_MOVED_YET`): `job_search`, `voice_in`, `voice_notes`, `html_viewer`. The eight central modules keep their central page for good (decision 8).

**App:** step 0 and this session changed `app_kit` (the core's `modules.docs` uses it), so the running app needs a restart to list pages in the standard order. `console_io`'s default went back into `default.toml` with the same value, so it needs no reload.

**Next (one session per few modules):**
1. Step 3, one module at a time: `voice_notes`, `html_viewer`, `voice_in` (with `voice.md`, unless it's made central), `job_search`. The central modules' tabs stay. For each: `docs/README.md` from `docs/modules/<id>.md` (links rewritten), `docs/docs.toml` (`tab`, and `related` from its `MODULE_TABS` entry), drop it from `MODULE_TABS` (a tab whose modules have all moved goes away, and its `related` moves to one of its modules' `docs.toml`), point `docs/modules/README.md` at the new page, move tests that test only this module into `<id>/tests/`, and move its `[modules.<id>]` defaults into `module.toml` (keep only overrides in `default.toml`; then `RELOAD: <id>`). Rebuild, run tests and ruff after each.
2. Then step 5 (the independent apps) and step 6 (remove the fallbacks, update the architecture pages). Step 4 (roles) waits for the umbrella build.

**Restart:** step 0 changed the core and `app_kit`, so the running app needs a restart to get `modules.docs` and `module.toml`. The echo pilot moved only docs and tests, so nothing to reload.
