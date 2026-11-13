# Module folders: every module in its own folder, checked item by item

**Count: 19 of 20 done** (items 1 to 18 and 20).

**Architecture check after the core chunk (items 11–16):** modularity OK (item 15's tripwires scan the core group, `core/`, contracts, infra and `app_kit` for an add-on's id or tool names and pass; every module has its `module.toml`); reuse OK (config layering reuses `load_layered` / `merge`; page opening is one helper, `open_page`; start on use is one search for tools and contracts); fit OK (`config/` holds only your choices and the on/off list, `generated/` only what the core writes, grants in `config/`; `modules.remove` goes through the same risky ask as the other core menu items).

**Architecture check after the add-on chunk (items 7–10):** modularity OK (a grep of `core/`, `contracts/`, `infra/` and `app_kit` for the add-ons' ids finds only comments and examples, plus `infra/show_pages.py`'s `viewer.open`, which item 15 moves behind a slot); reuse OK (every app move reused `add_app_folders` and `launch_env`; temp_ui's test helpers joined `assistant.testkit`); fit OK (each add-on's defaults, `needs` and `packages` are in its `module.toml`, read by the core with no names).

**Architecture check after the cv chunk (items 2–6):** modularity OK (no cv-specific code in the core, contracts, infra or `app_kit`, only examples in comments; every module's `app/` is checked never to import `assistant`); reuse OK (`add_app_folders`, `launch_env`, `apply_module_toml` and `assistant.testkit` are in the reusable index with Used by lines); fit OK (the core reads `needs` and `packages` from any `module.toml`, no names).

## Morning list, kept as the run goes

- **App restart needed:** item 1 (`infra/agent_access.py`, the Hub's folder check); item 2 (`Manifest.needs`, the core's loader, registry and lifecycle); item 3 (`AgentInfo.named_only`, `ProfileAgent`, the Hub); item 4 (`add_app_folders` in the core's loader, `launch_env` in `CompanionApp`: **until the restart, the running app can't launch the CV Tool**, since `src/cv_tool` is gone); item 6 (`Manifest.packages`, `apply_module_toml`); item 8 (the viewer's event types left the contracts: **until the restart, the running app can't launch the viewer, and viewer tab notes and snips don't reach the Talker or temp_ui**; `.venv\Scripts\html-viewer.exe` is broken for good, run it as html_viewer's README says).
- **App restart needed, item 9:** until the restart, the running app launches the voice service from `src/voice_service`, which is gone, so **the mic fails**. `.venv\Scripts\voice-service.exe` is broken for good; run `python -m voice_service` with `modules/voice_in/app` on `PYTHONPATH`.
- **App restart needed, item 17:** cv_agent works from `modules/cv/workspace/` only after the restart (the running app keeps `CV_Module`). **Hand checks:** cv_agent's access card shows again (the grant's fingerprint changed); run one smoke job.
- **Open issue, item 17 (also item 18):** cv_agent's session now starts inside the repo, so **the repo's `CLAUDE.md` and `.claude/` settings load into it**, and Claude Code may file its auto-memory under the repo's key rather than the workspace's (memory was copied to the workspace key). `AgentProfile` / `claude_command` have no setting-sources option today. Simplest fixes: a setting-sources option on `AgentProfile`, or a short `workspace/CLAUDE.md` that overrides the repo's. Not built overnight (it changes how every agent's `claude` starts); decide in the morning.
- **Old folders left for you to delete (item 17):** `C:\Chang\Jobs\CV_Module` (copied: 1,575 files, 198.6 MB; not copied: `cv_tool\.chrome_print`, `.claude\state`, `cv-tools-move-plan.md`) and the old memory key `%USERPROFILE%\.claude\projects\C--Chang-Jobs-CV-Module` (28 notes copied). Delete them once the smoke job works.
- **App restart needed, item 16:** the core menu's `modules.remove` (new command `RemoveModule`).
- **App restart needed, item 15:** the new contract `IPageOpener` and the core command `StartProvider`. The running app keeps its old code in memory until then (and can't launch the viewer since item 8). **Hand check:** temp_ui's Open in viewer button brings the window to the front; a SHOW tag with html_viewer off turns it on and opens the page.
- **App restart needed, item 14:** the core writes `generated/modules.json`, `directory.json` and `dependencies.json` only after a restart. **Hand check:** they appear after the start and change when a module is turned on or off.
- **Flaky test seen, item 14:** `voice_in/tests/test_voice_pieces.py::test_closing_the_socket_cancels_the_running_piece_and_frees_the_slot[True]` failed once in a full run and passed on rerun (unrelated to item 14). Worth a look.
- **App restart needed, item 13:** the permissions handler reads and writes `config/permissions.toml`. **Hand check:** after the first start, `config/permissions.toml` exists with your old grants, and `data/permissions.toml` is still there (yours to delete once you're happy).
- **App restart needed, item 12:** `load_config` reads `config/modules.toml` and `config/<id>.toml`. Behavior stays the same (you have no `config/<id>.toml` yet; `config/local.toml` still loads last).
- **Your local config, item 11:** the rezi helper kind's real folders left the committed defaults (now `../assistant-rezi`, reading `docs`). They were added for you to `config/local.toml` (`[modules.task_agents.agents.rezi]`: `workspace` and `read_dirs`, as before), so nothing changes. Check that section once.
- **Note, item 11:** `.claude/state/reset-instructions.md` was missing when checked. Talker tests used to delete it on stop (fixed in item 11: tests now point `restart_note` into tmp). If a restart catch-up note was expected there, it's gone; the next restart writes a fresh one.
- **Hand check, item 10:** after the restart, `modules.on voice_notes` turns voice_in on first.
- **Hand check, item 9:** after the restart, click the mic in temp_ui, speak, and see the text reach the Talker; open voice_notes and record once.
- **Hand check, item 8:** after the restart, open a page from the chat, take a snip, paste an image, drop a snip with ×, and see the Talker's `[Viewer] open:` line.
- **Hand check, item 7:** after the restart, turning job_search on turns cv on first (it needs cv); cv shows its access card if its grant isn't saved.
- **Hand check, item 4:** after the restart, `cv.open_tool` opens the CV Tool from `modules/cv/app/cv_tool/`.
- **Hand checks:** at the next start, cv_agent's and job_search_agent's access cards show once more (item 1 adds their module folder to the list, so the fingerprint changed).
- **App restart needed, item 18:** job_search_agent works from `modules/job_search/workspace/` only after the restart. **Hand checks:** its access card shows again; `job.open_ui` opens the job UI from the workspace; one dry apply session up to the form (no submit). Same open issue as item 17 (the repo's `CLAUDE.md` loads into its session). Open: decision 49 (`cv_output`).
- **Old folders left for you to delete (item 18):** `C:\Chang\Jobs\CV\.claude`, `C:\Chang\Jobs\CV\Recruiters\scripts` and the copied `Recruiters\docs` state (not the archive, which stays), and the old memory key `%USERPROFILE%\.claude\projects\C--Chang-Jobs-CV`. Your CVs and documents in `C:\Chang\Jobs\CV` stay. Delete them once the dry apply session works.
- **Old folders left for you to delete:** see items 17 and 18 above.

> **Status: building (started 2026-11-13, overnight, unattended, in Auto).** The user approved the plan ([module-folders.html](module-folders.html), section 3) and this overnight run: commit, this checklist, then the migration in this order. The morning report goes at the top of this page when the run ends.

## What we are doing

Making every module truly self-contained: each module's code, companion app, defaults, dependency list (`needs`), packages, tests, docs and its agent's working folder live in its own folder `src/assistant/modules/<id>/`. Beside the modules sit `config/` (your own choices only, one file per module, plus the saved grants) and `generated/` (built by the core, never hand-edited, safe to delete).

## Why we are doing it

The rule from the approved picture: **nothing of cv lives outside `modules/cv/`, except your own choices in `config/cv.toml`. Delete `modules/cv/` and nothing of cv is left behind.** Every other add-on (job_search, html_viewer, voice_notes) has the same shape, and so do the core modules that own an app or tests. Today a module's pieces sit in five places (`src/<app>`, `config/default.toml`, `tests/`, `pyproject.toml`, folders outside the repo), so a module can't be added, swapped or removed whole. The [audit](module-folders-audit.md) found 1 of 14 picture items done, and the plan was reported done by omission. This checklist exists so that can't happen again.

## How we are doing it

- One numbered item at a time, in the order below. Each item has **What** (one sentence), **Why** (one sentence), **How** (the steps) and **Done when** (a check against the code: a file listing, a grep or a test, never a report).
- After each item: the full `pytest` and `ruff check`, the Done-when check run against the code, then it's marked done here with the evidence, and committed on its own.
- Each item adds its tripwire test to `tests/test_module_folders.py` (safeguard 6), so a done item can't slip back.
- Docs move with the code: the module's `docs/`, the API and reusable indexes, the architecture overview, rebuilt with `build_docs.py`.
- Nothing outside the repo is deleted: old folders are copied, never removed, and listed for you to delete.
- No app restart, no reload, no module on or off during the run. Whatever needs one goes on the morning list.

## Decisions made overnight

For you to review. Each picks the option closest to the approved picture.

1. **The module folder stays `src/assistant/modules/<id>/`.** The picture's `core/` and `modules/` boxes are the two groups the docs already use (`group = "core"` or `"add-on"` in each `docs.toml`). Moving the packages to a top-level `modules/` folder would rename every import and the loader's search path, for no gain in self-containment.
2. **A companion app moves into its module as `app/<its package>/`**, unchanged inside: `modules/cv/app/cv_tool/`, `modules/html_viewer/app/html_viewer/`, `modules/voice_in/app/voice_service/`. The app keeps its own import name, so it still never imports `assistant` (the independence rule and its test hold). The core puts each module's `app/` folder on the import path, found by folder with no names. Tests and launches get the same path.
3. **Packages:** each module lists its pip packages in its `module.toml` (`packages = [...]`), and the `cv` and `voice` extras leave `pyproject.toml`. A module's ruff exceptions go in its own `ruff.toml` (extending the root one). Nothing gets installed overnight.
4. **`needs` is a list of module ids** in `module.toml` (`needs = []`). The core reads it: turning a module on also turns on what it needs, and turning off a module others need is refused. `requires` (contracts) stays as it is.
5. **Agents' working folders:** each agent works in `modules/<id>/workspace/`, which is already gitignored (`workspace/`). Its files are **copied** from the old folder, and the old one is left for you to delete. **Your documents** (your base CVs and cover letters in `C:\Chang\Jobs\CV`) count as your own choices, not module files. They stay where they are, named in config (`cv_dir`, job_search's `documents`), with read access (job_search also gets write access, since it writes per-company CVs there today).
6. **job_search keeps JobRadar's Python** (`C:\Chang\Git_projects\Resume\.venv`). Nothing new is installed. A module venv with a `requirements.txt` is noted for later.
7. **Saved grants move to `config/permissions.toml`** (gitignored, since it holds your paths). The core reads it there, and on the first start copies `data/permissions.toml` across if the new file is missing. The old file is left in place.
8. **`generated/`** is a gitignored folder at the repo root. The core writes the live module list, the module directory and the installed dependencies there. The module library page stays in the docs build too (the docs need it), and a copy goes to `generated/`.
9. **Viewer types leave the core:** `ViewerTabsChanged`, `ViewerClip` and `ViewerClipDropped` become html_viewer's named events (`ModuleEvent`, `html_viewer.*`). temp_ui and the SHOW handling call a generic "open a page" slot that any add-on can fill. html_viewer fills it today.
10. **task_agents helpers don't get their module folder** (item 1): they're generic helpers, several run at once, and none is `task_agents`' own agent, so `request_access(..., own_folder=False)`.
11. **Part 1's cv commit is one commit** (`010ecb6`): the named events, the job-to-cv events, the cv fixes and the base_ rename share files, so they couldn't be split cleanly.
12. **Startup adds what's needed** (item 2): a module in `modules.enabled` whose `needs` aren't listed still gets them started (decision 4: on means its needs on too). A missing contract provider still fails startup.
13. **A needed module that fails at startup skips its dependents** (item 2), with no `StartupError`: cv waiting on its access card counts as failed at startup, and job_search needing it would otherwise stop the whole app. `module.toml`'s `needs` replaces any written in code.
14. **The Hub keeps `[modules.agent_hub] named_only` as an empty fallback** (item 3): an agent's own `named_only = true` (read by `ProfileAgent`, carried on `AgentInfo`) is the source; the Hub's list stays readable for an agent not built from a profile, empty by default.
15. **Finding app folders lives in the core, launching them in `app_kit`** (item 4): `add_app_folders()` (core loader: at startup, reload, add, and in `conftest.py`) puts every `modules/*/app` on the import path; `CompanionApp` launches `python -m <app>` with `launch_env` (its folder first on `PYTHONPATH`). Items 8 and 9 reuse both.
16. **The CV Tool's defaults are its module's workspace** (item 4): `cvlib.WORKSPACE` = `modules/cv/workspace` (with a made-up `cvs` folder for running it by hand); the cv module still passes its real folders on the command line.
17. **The test kit is `assistant.testkit`** (item 5), moved from `tests/` (`support.py`, `fake_claude.py`, `fake_job_ui.py`, and the agent fakes from `test_agents.py` / `test_multi_agent.py`), with no pytest code; the `hub` fixture stays in `tests/test_agents.py`. The loader counts it as shared code (not reloadable). No cv-only test was left in `tests/`, so none moved.
18. **cv lists only pymupdf** (item 6): it also uses `pypdf` and `mcp`, which were never in `pyproject.toml`; adding them to cv's `packages` is left for you. `cv_tool` left ruff's `known-first-party` (the `src` glob over `modules/*/app` covers every app). cv's `ruff.toml` extends the root config and keeps the cache at the root.
19. **job_search's tests use a stand-in cv** (item 7): `needs = ["cv"]` means job_search can't start without a cv module, so the tests start a bare `stand_in("cv")` (test kit) rather than the real cv with its access card. Its `module.toml` keeps the job paths that were already committed; item 18 replaces them.
20. **The SHOW-to-viewer mapping (`show_page`) moves in item 15, not item 8**: it's called by the Talker and the worker (core), so it waits for the page-opener slot instead of moving into an add-on that core code would then import.
21. **The dropped-snip event is `temp_ui.clip_dropped`** (item 8), not `html_viewer.clip_dropped`: a module may publish named events only under its own id, and the drop (and the pasted image, `temp_ui.clip`) come from temp_ui. html_viewer publishes `html_viewer.tabs_changed` and `html_viewer.clip`.
22. **The Talker's and temp_ui's snip tests sit in `tests/test_viewer_listeners.py`** (item 8) until item 11 moves the core modules' tests. The `html-viewer` script entry left `pyproject.toml` (it can't resolve without a reinstall); html_viewer's README says how to run the app by hand.
23. **`test_voice_notes.py` went straight to `voice_notes/tests/`** (item 9), not `voice_in/tests/`, so item 10 only adds voice_notes' `module.toml`. It uses voice_in's test rig, which is allowed since voice_notes needs voice_in.
24. **temp_ui's shared test helpers moved into the test kit** (item 9: `assistant.testkit.pages`: `request`, `post`, `next_item`, `FakeVoiceIn`), so no module test imports `tests.*`.
25. **The voice service's defaults sit next to its code** (item 9: `app/voice_service/voice_service.toml`, like `cv_tool.toml`), and its local override is `voice_service.local.toml` beside it (gitignored). No `config/voice_service.local.toml` existed, so nothing was left behind.
26. **voice_in gets no `ruff.toml`** (item 9): it has no ruff rules of its own; the tripwire's `MOVED_OUT` has a `ruff` flag for that.
27. **The `StartListening` / `StopListening` timeouts stay in `[core.command_timeouts]`** (item 9): they're core settings. `scripts/build_docs.py` calls `add_app_folders()` before importing modules.
28. **voice_notes' `module.toml` holds only its two old defaults** (item 10: `port`, `window`); `host` and `window_profile` keep their defaults in code, so the settings it sees are unchanged (a test checks). It keeps `requires IVoice` beside `needs = ["voice_in"]`.
29. **Every core module has `needs = []`** (item 11): each runs alone in tests; task_agents uses the Hub only when it's on.
30. **The rezi helper kind ships with neutral folders** (item 11: `../assistant-rezi`, reading `docs`); your real ones went to `config/local.toml`. A test checks no committed kind holds a drive path. A kind never inherits task_agents' own `needs` / `packages` (`NOT_KIND_KEYS`).
31. **Tests never write the repo's `logs/` or `.claude/state/`** (item 11): the root `conftest.py` sends transcripts and the Talker's `restart_note` to tmp.
32. **Central tests that stay** (item 11): those that run several modules together or test the core or a shared part with one module as an example (`test_agents`, `test_restart`, `test_multi_agent`, `test_permission_mode`, `test_mcp_door`, `test_app`, `test_directory`, `test_menu`, `test_reload`, `test_control`, `test_usage`, `test_access_cards` and the like). The tripwire flags a central test that names exactly one module and isn't on its reasoned list.
33. **Small test moves** (item 11): `test_show_tag_arguments` was dropped (covered by `tests/test_agent_tags.py`); the `flash_window` test went to `tests/test_app_kit.py`; assistant_view has no `tests/` (covered by `test_swap_every_module`); the test kit gained `clip_event`, `dropped_event`, `ui_port`, `read_events`, `sample_card`, and `pre_grant_kinds` merges a module's `module.toml`.
34. **`config/` layout** (item 12): `config/modules.toml` is committed (the shipped on/off list, `enabled` at top level); `config/<id>.toml` files are yours and gitignored (`config/*.toml` except `default.toml` and `modules.toml`), none shipped. A module's settings load: `module.toml` → `[modules.<id>]` in `default.toml` (empty now) → `config/<id>.toml` → `config/<id>.local.toml` → `[modules.<id>]` in `config/local.toml`. The on/off list: `modules.toml` → `modules.local.toml` → `[modules] enabled` in `local.toml`. `default`, `local`, `modules`, `permissions` and `voice_service` are never module files. A missing `modules.toml` means nothing enabled. New helper `module_config_ids`.
35. **The old grants path is named once** (item 13): `OLD_GRANTS` beside `copy_old_grants(new, old)` in `core/permissions/store.py`, run when the handler is built from config; it copies only if the new file is missing, never edits or deletes the old one, and the old file stays on the protected list. Tests point the old path into tmp.
36. **`generated/` is one small core part** (item 14: `GeneratedFiles` in `core/generated.py`), built by `App` from `[core] generated_dir` (`"generated"` in `default.toml`; unset means nothing is written, so tests never write the repo). One write after startup, then one per state change from the lifecycle callback beside `ModuleStateChanged`; atomic, a failure only logged. `directory.json` includes the core's own menu. Not in the reusable index (only `App` uses it).
37. **Pages open through `IPageOpener`** (item 15: `open(path, quote, heading, front)`, `contracts/pages.py`), which html_viewer provides; callers use `open_page(ctx, ...)` in `infra/show_pages.py` (looked up per call; `NO_PAGE_VIEWER` when none). `show_page` is only the SHOW-tag parser now; `show_command`, `VIEWER_OPEN` and `VIEWER_HIGHLIGHT` are gone. Agent modules' `AGENT_USES` gained `IPageOpener`.
38. **Start on use, by contract** (item 15): a new core command `StartProvider(contract=...)` turns on the off module that lists the contract in `manifest.provides` and has `start_on_use = true`; it shares one search with the old tool-name path (`App._start_on_use`). No name of an add-on in the core.
39. **The groups come from each module's `docs.toml`** (item 15): voice_in is in the core group there and echo_orchestrator is an add-on, unlike the item 11 list. The tripwire uses `docs.toml`, so changing a module's group there changes what it checks. **For you to review:** whether voice_in belongs in the core group (the picture drew it with the add-ons).
40. **The tripwire** (item 15) reads string literals and imports in the core group, `core/`, contracts, infra and `app_kit`, skipping docstrings, and allows an add-on's named events (decision 9). The door's and the prompt's "e.g. `viewer.open`" examples now say `modules.docs`.
41. **`modules.remove(module_id, settings="keep"|"purge")`** (item 16) asks first, then sends `RemoveModule`. It refuses while a module needs it: active and `needs` it (or requires a contract only it provides), or listed in `enabled` with `needs` naming it, even while off. It turns the module off and drops it from this run's list (`modules.add` brings it back). `purge` deletes only `config/<id>.toml` and `config/<id>.local.toml`; the shared names (`local`, `default`, `modules`, `permissions`, `voice_service`) never count. It never rewrites `config/modules.toml` or deletes the module folder: the result tells you to.
42. **cv's job folders may sit in the repo, but only inside its own `workspace/`** (item 17): before, cv refused any work folder in the repo, so the new default wouldn't start. `[agent] workspace = "workspace"` (relative to the module folder), `output_dir` unset means `<workspace>/out`, and an output folder inside the workspace gets no read item of its own on the card. Your `config/local.toml` had no `CV_Module` key, so nothing there changed.
43. **pytest skips `workspace` folders** (item 17: `norecursedirs` in `pyproject.toml`): the copied workspace holds old test scripts.
44. **Your documents and company lists stay in `C:\Chang\Jobs\CV`** (item 18, decision 5): the CVs, cover letters, `2025/`, `2026/`, `StartUp/`, `UnderRadar/`, `_upload/` and the old `Recruiters/docs/archive/` weren't copied. The scripts find them through `workspace/job_paths.json`.
45. **One shared helper for a module's relative folders** (item 18): `in_module_folder(module_id, path)` in `infra/agent_access.py` (reusable index), used by cv and job_search; cv's private `_from_here` is gone.
46. **`documents` is a write folder** (item 18): the job agent saves per-company CVs there. The committed default is empty; your real folder is in the gitignored `config/local.toml` (`[modules.job_search] documents`).
47. **The job agent's memory notes were copied** (24 files) to the workspace's memory key; the old key is left.
48. **apply-session sends `jd_text`** to `cv.task`, since cv_agent won't read the job workspace.
49. **Open, not fixed overnight:** `cv_output` in the job project still points at the old rezi output folder, so new cv PDFs won't show in the job UI until it's pointed at cv's `workspace/out`. Left for you because it changes where the job UI looks for your CVs.

## The safeguards (from the audit, section 4)

| # | Safeguard | Where it's built |
|---|---|---|
| 1 | A plan gets a numbered checklist before work starts | This page; the rule is in the `architecture-check` skill ("Plans and checklists") |
| 2 | "Done" only after a check against the code | Every item's **Done when** below; the same skill section |
| 3 | Never close a plan without a done and not-done list | The morning report at the top of this page; the skill section |
| 4 | Name the narrowed scope in every report | The skill section (reports name the item numbers, and the count) |
| 5 | "Currently fixing" shows the count | The overview's "Currently fixing" names this checklist with its count |
| 6 | A test as the tripwire | `tests/test_module_folders.py`, one test per finished item |
| 7 | Grants and workspaces are part of "moved" | Items 1, 17 and 18 check `config/permissions.toml`, not only the code |
| 8 | An approved plan is started or marked "approved, not started" | The skill section; this plan's next-steps row says "building" |
| 9 | A "Left:" list includes every open plan the work touched | The skill section |
| 10 | A plan that reverses an older decision names that note and updates it | Done: [cv-agent-folders.md](cv-agent-folders.md) now says it's replaced by item 17 |

## The items

### 1. Every module can edit itself by default: **done** (2026-11-13)

**Checked:** `test_module_agent_edits_its_own_folder`, `test_a_module_agent_runs_beside_the_main_assistant`, `test_two_agents_on_one_module_folder_are_refused_with_the_folder_named` and `test_the_folder_rule` pass; the phrase "can't run while the Main Assistant has a task" is gone from `config/` and `docs/` (only this page quotes it); full suite 845 passed, 2 deselected; ruff clean. **Needs an app restart.**

- **What:** each module's agent gets a saved write grant on its own module folder only, and the Hub stops refusing it for overlapping the Main Assistant's whole-repo grant.
- **Why:** both agents' reports name this as the first blocker: a workspace inside the repo is refused whenever the Main Assistant has a task (`agent_hub/tasks.py`, "would write …, which main_assistant's open task writes").
- **How:**
  1. In the agents' access-list code (`infra/agent_access.py`), add `write:<the module's own folder>` to every module agent's list by default. Never a parent folder or another module's folder.
  2. In the Hub's folder check (`agent_hub/tasks.py`), ignore an overlap where one side's folder is a parent of the other's (a whole-repo grant versus a module folder). Keep refusing two agents with the same folder or the same module folder.
  3. Make the refusal message name the folder that clashed and both agents' grants for it, so it's clear which folder is the wrong one.
  4. Tests: the default grant names only the module's own folder; a module agent runs beside a Main Assistant task; two agents on the same module folder are still refused, and the message names that folder.
  5. Docs: the agent_hub architecture page, `docs/architecture/permissions.md`, and the comment in `config/default.toml` ("An agent writing inside this repo can't run while the Main Assistant has a task").
- **Done when:** `tests/test_module_folders.py::test_module_agent_edits_its_own_folder` and the Hub's overlap tests pass; `git grep` finds no "can't run while the Main Assistant has a task" in the docs or config.

### 2. cv: a `needs` list: **done** (2026-11-13)

**Checked:** `cv/module.toml` line 5 is `needs = []`; `Manifest.needs` in `contracts/module.py`; `test_cv_declares_needs`, `test_turning_on_a_module_turns_on_what_it_needs`, `test_turning_off_a_needed_module_is_refused` and `test_a_missing_needed_module_is_named` pass; full suite 849 passed, 2 deselected; ruff clean. **Needs an app restart.**

- **What:** `modules/cv/module.toml` has `needs = []`, and the core reads `needs` from every module's manifest.
- **Why:** the picture's "dependency list (new)": today `requires` lists contracts only, so nothing knows that job_search needs cv.
- **How:** add `needs: tuple[str, ...]` to `Manifest` (contracts), read from `module.toml`; the registry checks that every needed module exists; the lifecycle turns needed modules on first and refuses to turn off one that an active module needs. Tests in `tests/test_module_folders.py` and the core's tests. Docs: `docs/api/modules.md` (`Manifest`), `docs/architecture/modules.md`.
- **Done when:** `cv/module.toml` contains `needs = []`; `Manifest` has `needs`; a test turns on a module that needs another and sees both on, and a test refuses turning off a needed module.

### 3. cv: the `[agent]` section is complete: **done** (2026-11-13)

**Checked:** `config/default.toml` has no `cv_agent`; `cv/module.toml` `[agent]` has `named_only = true`; `test_cv_agent_is_named_only_from_its_own_section` and `test_a_free_pick_never_lands_on_a_named_only_agent` pass; full suite 851 passed, 2 deselected; ruff clean. **Needs an app restart.**

- **What:** everything about cv_agent lives in cv's `[agent]` section, including what agent_hub held for it (`named_only = ["cv_agent"]` in `config/default.toml`).
- **Why:** the picture: "[agent] cv_agent ← agent_hub's section"; the audit's row 3 is only partly done.
- **How:** add `named_only = true` to `[agent]` in `cv/module.toml`; agent_hub learns the named-only agents from the agents themselves (the module or the profile reports it) instead of its own list; remove `named_only = ["cv_agent"]` from `[modules.agent_hub]`. Tests; docs for agent_hub and cv.
- **Done when:** `git grep -n "cv_agent" config/default.toml` finds nothing; a test shows cv_agent is still named-only (`hub.start` without its name never picks it).

### 4. cv: the CV Tool app moves into `modules/cv/app/`: **done** (2026-11-13)

**Checked:** `src/cv_tool` doesn't exist; `modules/cv/app/cv_tool/__main__.py` exists; `test_no_app_outside_its_module`, `test_every_module_app_never_imports_assistant` and cv's `test_cv_tool.py` pass; `cv_tool.local.toml` stays gitignored (`*.local.*`); full suite 854 passed, 2 deselected; ruff clean. **Needs an app restart.**

- **What:** `src/cv_tool/` moves to `src/assistant/modules/cv/app/cv_tool/`, with `cv_tool.toml` next to it.
- **Why:** the picture: "app/ ← src/cv_tool".
- **How:** `git mv`; the core puts each module's `app/` folder on the import path (by folder, decision 2) and so does the test setup (`conftest.py`); `CvTool` launches it with that path; replace the hard-coded `C:/Chang/Jobs/CV_Module` defaults in `cv_tool.toml` and `cvlib.py` with paths relative to the module's workspace (decision 5); the independence test covers the new place. Docs: cv's pages, the overview's parts table, `docs/architecture/reusable-parts.md` if it names the path.
- **Done when:** `src/cv_tool` doesn't exist; `modules/cv/app/cv_tool/__main__.py` exists; the CV Tool tests pass from the new place; `test_module_folders.py::test_no_app_outside_its_module` passes for cv. **Needs an app restart** (the import path and the running cv module).

### 5. cv: all cv tests in the module, on a public core test kit: **done** (2026-11-13)

**Checked:** `git grep -E "from tests\.|import tests\.|from tests import" src/assistant/modules` finds nothing; `git ls-files tests` has no cv file; `test_module_tests_use_only_the_testkit`, `test_no_cv_only_test_is_central` and `test_only_tests_import_the_testkit` pass; full suite 857 passed, 2 deselected; ruff clean. No restart needed.

- **What:** every cv test lives in `modules/cv/tests/`, and module tests import shared helpers only from a public test kit, never from `tests.test_*`.
- **Why:** the picture: "all cv tests, on the core test kit" and "public test kit (from tests/support)"; the audit's row 5 lists the central imports.
- **How:** create `src/assistant/testkit/` (the fakes and helpers modules need: the fake `claude`, the app builders now in `tests/test_agents.py` and `tests/test_multi_agent.py`); point `cv/tests/test_worker.py` and the agent_hub tests at it; move any cv test still in `tests/` into the module. Add it to the reusable index.
- **Done when:** `git grep -n "from tests\.\|import tests\." src/assistant/modules` finds nothing; `git ls-files tests | grep -i cv` finds nothing cv-only; the tripwire test passes.

### 6. cv: packages and the ruff rule move out of `pyproject.toml`: **done** (2026-11-13)

**Checked:** `pyproject.toml` has no line matching `cv` or `pymupdf`; `cv/module.toml` has `packages = ["pymupdf>=1.24"]`; `modules/cv/ruff.toml` exists; `test_no_module_package_in_pyproject` and `test_packages_come_from_module_toml` pass; full suite 859 passed, 2 deselected; ruff clean. **Needs an app restart** (`Manifest.packages`, the loader).

- **What:** pymupdf is listed in `cv/module.toml` (`packages`), and the cvlib ruff exceptions are in `modules/cv/ruff.toml`.
- **Why:** the picture: "packages: pymupdf · ruff rule ← pyproject".
- **How:** add `packages = ["pymupdf>=1.24"]` to `module.toml` and the `packages` field to `Manifest`; remove the `cv` extra and the `src/cv_tool/cvlib.py` per-file ignore from `pyproject.toml`; add `modules/cv/ruff.toml` with `extend` to the root config and the per-file ignore. Nothing is installed.
- **Done when:** `pyproject.toml` has no `cv`, `pymupdf` or `cv_tool` line; `ruff check` is clean; the tripwire test (no module package in `pyproject.toml`) passes.

### 7. job_search: defaults, needs and tests in the module: **done** (2026-11-13)

**Checked:** `job_search/module.toml` line 6 is `needs = ["cv"]`; `config/default.toml` has no `modules.job_search`; `tests/test_job_search.py` is gone and its tests pass from `modules/job_search/tests/`; `test_job_search_has_its_module_toml` passes; the merged config equals the old one (a test); full suite 862 passed, 2 deselected; ruff clean. Takes effect at the next start (with items 1–6's restart).

- **What:** `modules/job_search/module.toml` holds job_search's defaults (from `[modules.job_search]` in `config/default.toml`) and `needs = ["cv"]`, and its tests (`tests/test_job_search.py`, `tests/fake_job_ui.py`) live in its `tests/`.
- **Why:** the picture: "job_search/ code · docs · tests · needs cv".
- **How:** create `module.toml`, move the defaults (your own paths go to `config/local.toml`, never committed), and move the tests onto the test kit. Docs.
- **Done when:** `module.toml` exists with `needs = ["cv"]`; `config/default.toml` has no `[modules.job_search]` defaults; `tests/test_job_search.py` is gone and its tests pass from the module.

### 8. html_viewer: its app, events, SHOW handling and tests in the module: **done** (2026-11-13; the SHOW handling moves in item 15, decision 20)

**Checked:** `src/html_viewer` doesn't exist; `git grep "ViewerClip\|ViewerTabsChanged" src/assistant/contracts` finds nothing; `tests/test_html_viewer.py` is gone and its tests pass from `modules/html_viewer/tests/`; `test_viewer_events_left_the_contracts` and `test_no_app_outside_its_module` (with `src/html_viewer`) pass, and a child process runs `python -m html_viewer --help` from the module; full suite 866 passed, 2 deselected; ruff clean. **Needs an app restart** (contracts).

- **What:** `src/html_viewer/` moves to `modules/html_viewer/app/html_viewer/`, its events leave the core contracts (decision 9), the SHOW-to-viewer mapping (`infra/show_pages.py`) moves into html_viewer, and its tests move into its folder.
- **Why:** the picture: "html_viewer/ code · viewer app · docs · tests · its events · SHOW handling".
- **How:** `git mv`; `module.toml` with its defaults and `needs = []`; viewer events become `ModuleEvent`s (`html_viewer.tabs_changed`, `html_viewer.clip`, `html_viewer.clip_dropped`) and their listeners subscribe by name; `show_page` asks the slot from item 15 instead of naming `viewer.open`; the `html-viewer` entry point is updated. Docs and the API indexes.
- **Done when:** `src/html_viewer` doesn't exist; `git grep -n "ViewerClip\|ViewerTabsChanged" src/assistant/contracts` finds nothing; `tests/test_html_viewer.py` is gone and its tests pass from the module. **Needs an app restart** (contracts).

### 9. voice_in: the voice service app, packages and tests in the module: **done** (2026-11-13)

**Checked:** `src/voice_service` doesn't exist; `modules/voice_in/app/voice_service/__main__.py` exists; `pyproject.toml` has no `voice` extra, no voice package and no `voice-service` script; no `tests/test_voice*` file is left; `test_voice_in_app_packages_and_tests_are_in_its_folder` and the voice tests pass from the module; full suite 867 passed, 2 deselected; ruff clean. **Needs an app restart.**

- **What:** `src/voice_service/` moves to `modules/voice_in/app/voice_service/`, the `voice` packages go into `voice_in/module.toml`, `config/voice_service.toml` becomes the app's defaults in its folder, and the 7 voice test files move into `voice_in/tests/`.
- **Why:** the picture: "voice_in/ voice_service app · docs · tests · voice packages".
- **How:** `git mv`; app path (decision 2); the `voice-service` entry point; remove the `voice` extra from `pyproject.toml`; fix the old `docs/architecture/voice.md` comment. Docs.
- **Done when:** `src/voice_service` doesn't exist; `pyproject.toml` has no `voice` extra; no `tests/test_voice*` file is left; the voice tests pass from the module. **Needs an app restart.**

### 10. voice_notes: defaults, needs and tests in the module: **done** (2026-11-13)

**Checked:** `voice_notes/module.toml` has `needs = ["voice_in"]`; `config/default.toml` has no `[modules.voice_notes]` section (only a comment pointing at the module); its tests and `test_voice_notes_has_its_module_toml` pass from the module (33 passed with the tripwires); full suite 869 passed, 2 deselected; ruff clean. Takes effect at the next start.

- **What:** `modules/voice_notes/module.toml` with its defaults and `needs = ["voice_in"]`, and `tests/test_voice_notes.py` moved into its folder.
- **Why:** the picture: "voice_notes/ code · page · docs · tests · needs voice_in".
- **How:** as item 7.
- **Done when:** `module.toml` exists with `needs = ["voice_in"]`; no `[modules.voice_notes]` defaults in `config/default.toml`; its tests pass from the module.

### 11. The core modules: defaults and tests in each module: **done** (2026-11-13)

**Checked:** all 14 module folders have a `module.toml` (a listing finds none without); `config/default.toml`'s sections are only `[modules]` (`enabled`), `[core]`, `[core.permissions]`, `[core.command_timeouts]` and `[logging]`; `test_core_agent_modules_have_their_module_toml_and_tests` and the every-module tripwire pass; module-only tests moved (agent_hub, talker, main_assistant, task_agents, console_io, usage, temp_ui); full suite 888 passed, 2 deselected; ruff clean. Takes effect at the next start.

- **What:** agent_hub, talker, main_assistant, console_io, temp_ui, task_agents (its kinds as defaults), usage, assistant_view and echo_orchestrator each get a `module.toml` with their defaults and `needs`, and their tests in their own `tests/`.
- **Why:** the picture's core box: "own docs · tests", "kinds as defaults", and the rule that the core modules that own tests have the same shape.
- **How:** per module: `module.toml` from its `[modules.<id>]` section, its central test files moved onto the test kit. Tests that check the whole app (`test_swap_every_module.py` and the like) stay central.
- **Done when:** every module folder has a `module.toml`; `config/default.toml` has no `[modules.<id>]` defaults left (only core settings); the tripwire lists no module-only test file under `tests/`.

### 12. `config/`: your choices only, one file per module: **done** (2026-11-13)

**Checked:** `config/modules.toml` exists (committed, the `enabled` list), `config/default.toml` has no `enabled`; `git check-ignore` matches `config/cv.toml` and not `config/modules.toml`; `test_a_modules_settings_load_from_its_config_file_over_its_module_toml` and the config tests pass; full suite 892 passed, 2 deselected; ruff clean. **Needs an app restart** (infra).

- **What:** `config/<id>.toml` holds your own choices for a module, `config/modules.toml` says which add-ons are on, and `config/*.local.toml` are the local overrides.
- **Why:** the picture: "config/: your choices only · kept across downloads · one file per module · which add-ons are on · local overrides".
- **How:** `load_config` reads in this order: the module's `module.toml`, `config/default.toml` (core settings), `config/<id>.toml`, then the `.local` overrides; your current `config/local.toml` choices stay readable (no file of yours is deleted). Tests; `docs/api/infra.md`, `docs/architecture/core.md`.
- **Done when:** a test loads a module's settings from `config/<id>.toml` over its `module.toml`; `config/modules.toml` exists; the app's config tests pass. **Needs an app restart** (infra).

### 13. Saved grants in `config/`: **done** (2026-11-13)

**Checked:** `git grep -n "data/permissions.toml" src` finds only `store.py:31` (the copy's constant); `git check-ignore config/permissions.toml` succeeds; `test_a_grant_is_saved_to_config_permissions_toml` passes (a grant saved there, and the one-time copy); no real `config/permissions.toml` was made, and `data/permissions.toml` is untouched; full suite 895 passed, 2 deselected; ruff clean. **Needs an app restart** (core).

- **What:** the permissions handler reads and writes `config/permissions.toml`.
- **Why:** the picture: "saved grants (now data/permissions.toml)" belong in `config/`, since they're your decisions.
- **How:** decision 7; gitignore `config/permissions.toml`; tests; `docs/architecture/permissions.md`.
- **Done when:** `git grep -n "data/permissions.toml" src` finds only the one-time copy; a test shows a grant saved to `config/permissions.toml`; `git check-ignore config/permissions.toml` succeeds. **Needs an app restart** (core).

### 14. `generated/`: **done** (2026-11-13)

**Checked:** `git check-ignore generated/` prints `generated/`; `tests/test_generated.py` passes (the three files appear at start; `generated/` deleted is written again on the next on/off); `build_docs.py` writes `generated/module-library.md`; full suite 898 passed, 2 deselected (see the flaky note in the morning list); ruff clean. **Needs an app restart** (core).

- **What:** the core writes `generated/modules.json` (the live module list), `generated/directory.json` (the module directory), `generated/dependencies.json` (each module's `needs` and `packages`), and the docs build writes `generated/module-library.md`.
- **Why:** the picture: "generated/: built by the core · never hand-edited · safe to delete".
- **How:** decision 8; gitignore `generated/`; written at start and on every module state change; a test deletes it and sees it written again.
- **Done when:** the test passes; `git check-ignore generated/` succeeds. **Needs an app restart** (core).

### 15. The needs arrows: never core → add-on: **done** (2026-11-13)

**Checked:** `git grep -n "viewer\.open"` over temp_ui, talker and infra finds nothing; the three new tripwires in `tests/test_module_folders.py` pass; `tests/test_show_pages.py` and `tests/test_start_on_use.py` pass (a fake opener, none provided, start on use by contract); full suite 910 passed, 2 deselected; ruff clean. **Needs an app restart** (new contract and core command).

- **What:** no core module names an add-on: temp_ui stops sending `InvokeTool viewer.open` directly and uses a slot an add-on fills ("plugs in").
- **Why:** the picture: "'needs' arrows point one way: add-on → core, or add-on → add-on · never core → add-on", with the crossed-out arrow from temp_ui and talker to html_viewer.
- **How:** a contract `IPageOpener` (`open(path, quote, heading)`) in the contracts. html_viewer provides it, and temp_ui, the Talker and `show_page` ask the container for it (none: they say so). A tripwire test scans the core group's modules for an add-on's id or tool names.
- **Done when:** `git grep -n "viewer\.open" src/assistant/modules/temp_ui src/assistant/modules/talker src/assistant/infra` finds nothing; the tripwire passes. **Needs an app restart** (new contract).

### 16. Removing a module asks: purge its settings or keep them: **done** (2026-11-13)

**Checked:** `tests/test_remove_module.py` passes (refuse with the dependents named, keep, purge of only the two files, the ask first); `tests/test_directory.py` lists `modules.remove` on the core's menu; full suite 914 passed, 2 deselected; ruff clean. **Needs an app restart** (core command, contracts, infra).

- **What:** the core's menu gets `modules.remove`, which refuses while another module needs it and asks you whether to purge `config/<id>.toml` or keep it.
- **Why:** the overview's plan line: "removing a module asks whether to purge its settings or keep them".
- **How:** a core menu item, `risky`, which asks first; it never deletes the module folder itself (that's yours to do); tests.
- **Done when:** the tests for refuse, keep and purge pass. **Needs an app restart** (core).

### 17. cv_agent works from `modules/cv/workspace/`: **done** (2026-11-13; one open issue, see the morning list)

**Checked:** `git grep -n "CV_Module" src` finds nothing; `modules/cv/workspace/.claude/skills/cv-writing/SKILL.md` and `modules/cv/workspace/cv_tool/submits_seen.json` exist; `git check-ignore` matches the workspace (`.gitignore: workspace/`) and `git status --porcelain` lists nothing under it; `test_cv_agent_works_from_its_module_workspace` and the cv tests (159) pass; full suite 915 passed, 2 deselected; ruff clean. Nothing in `C:\Chang\Jobs\CV_Module` was changed. **Needs an app restart.**

- **What:** cv_agent's working files are copied from `C:\Chang\Jobs\CV_Module` into `modules/cv/workspace/`, its config and grant point there, and its memory notes are copied to the new folder's memory key.
- **Why:** the rule (nothing of cv outside its folder); cv_agent's own plan (`C:\Chang\Jobs\CV_Module\cv-tools-move-plan.md`, section 5).
- **How:** copy per cv_agent's step-1 table (skills and rules, facts, `cv_tool` data with `submits_seen.json`, `work\`, `applied\`, `scripts\`, `docs\`; not `.chrome_print`, not `.claude\state`); copy memory from `~\.claude\projects\C--Chang-Jobs-CV-Module\memory` to `…\C--Chang-Git-projects-AI-Assistant-src-assistant-modules-cv-workspace\memory`; `[agent] workspace` → the new folder, `output_dir` → `<workspace>/out`; the tests and docs that name `CV_Module`; check `git status` shows nothing from `workspace/`. The old folder is left for you.
- **Done when:** `git grep -n "CV_Module" src` finds nothing; `modules/cv/workspace/.claude/skills/cv-writing/SKILL.md` and `…/cv_tool/submits_seen.json` exist; `git status --porcelain` lists nothing under `workspace/`; the cv tests pass. **Hand check:** the access card at the next start (the grant's fingerprint changes), and one smoke job.

### 18. job_search_agent works from `modules/job_search/workspace/`: **done** (2026-11-13; open issues, see the morning list)

**Checked:** `modules/job_search/workspace/CLAUDE.md` and `…/Recruiters/scripts/job_ui.py` exist (587 files, 7.9 MB copied); a grep of the workspace's `.py` files for `C:\Chang\Jobs\CV` finds nothing (the folder is named only in `job_paths.json`, read by `job_paths.py`, and in the prompt and skills as where your documents stay); `git status --porcelain` lists nothing under `workspace/`; pytest collects nothing from it (`norecursedirs`); `test_job_search_agent_works_from_its_module_workspace` passes; full suite 917 passed, 2 deselected; ruff clean. The apply-session skill's `CV_Module\applied` now names cv's `workspace\applied`. Nothing in `C:\Chang\Jobs\CV` was changed. **Needs an app restart.**

- **What:** the job project's tools, prompt and state are copied from `C:\Chang\Jobs\CV` into `modules/job_search/workspace/`, their hard-coded paths go through one paths file, and the config and grant point there.
- **Why:** the rule; the job agent's report (`C:\Chang\Jobs\CV\Recruiters\docs\job_workspace_move_plan_2026-11-13.md`, section 5) found the tools were never cloned.
- **How:** copy per its "Files to clone" table, plus `Recruiters\docs\` state, not the history it lists under "Don't clone". Your CV and cover-letter files stay in `C:\Chang\Jobs\CV` (decision 5). Add `workspace/job_paths.json` and switch the scripts to it. Keep the job project's tests out of the app's pytest run. Set `[modules.job_search] workspace` → the new folder, `documents` = `C:/Chang/Jobs/CV` (read and write). Keep JobRadar's Python (decision 6). Copy the memory notes. `ui.py`'s default script path. Docs (`job-project.md`).
- **Done when:** `modules/job_search/workspace/CLAUDE.md` and `…/Recruiters/scripts/job_ui.py` exist; a grep of the copied scripts finds `C:\Chang\Jobs\CV` only in `job_paths.json`; `git status` lists nothing under `workspace/`; pytest collects nothing from the workspace. **Hand check:** the access card, `job.open_ui`, one dry apply session up to the form.

### 19. The rule holds for every add-on

- **What:** one tripwire checks the whole rule: no add-on file outside its folder (no `src/<app>`, no module packages in `pyproject.toml`, no `[modules.<id>]` defaults, no module-only test in `tests/`, no agent workspace outside the repo in config).
- **Why:** the picture's rule ("delete `modules/cv/` and nothing of cv is left behind"), for every add-on, kept true from now on.
- **How:** collect the per-item tripwires into one test per add-on in `tests/test_module_folders.py`, and update the overview (the parts table's locations, "Currently fixing").
- **Done when:** `pytest tests/test_module_folders.py` passes with a test per add-on.

### 20. Every module's docs in its own folder: **done** (2026-11-12, before this checklist)

- **What:** every module has `docs/` with README, architecture, a generated tools page and `docs.toml`.
- **Why:** the picture: "own docs" for every module.
- **How:** done in commit `c0d2a5d` (the module docs move).
- **Done when:** `scripts/build_docs.py`'s `check_module_tabs()` requires a `docs/` folder for every module package, and the build passes. **Checked 2026-11-13:** the build wrote 72 pages with no error.
