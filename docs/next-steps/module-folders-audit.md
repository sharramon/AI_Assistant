# Module folders: what was promised, what was done, and why it was called done

> **Status: findings complete (2026-11-13).** Sections 1–3 checked; section 4 waits on the user. Read-only investigation. Nothing was changed except this note, its row in the [next-steps list](README.md) and the rebuilt HTML: no code, no grants, no module on or off, no restart, no commit.

**Asked:** the user's plan [module-folders.html](module-folders.html) (commit `cce352c`, 2026-11-11 23:36, made with snips in that session) was taken as done, but most of it isn't. Find out what it promised, what is really there, where it was reported done and what that report was based on, and propose safeguards.

## 1 and 2: every item the plan promised, checked against the code (2026-11-13)

Checked against the files themselves (folder listings, `config/default.toml`, `pyproject.toml`, `contracts/messages.py`, `infra/show_pages.py`, imports in module tests, `data/permissions.toml`), not against notes.

| # | The plan's words (quoted) | Today | Done? |
|---|---|---|---|
| 1 | Companion apps into the module: "voice_in/ · voice_service app", "html_viewer/ · viewer app", cv "app/ ← src/cv_tool" | `src/voice_service`, `src/html_viewer`, `src/cv_tool` are still top-level in `src/`; `pyproject.toml` still has their entry points | **not done** |
| 2 | Config defaults in the module: "module.toml defaults", "config/ … your choices only", "one file per module" | Only `cv` has a `module.toml`. `config/default.toml` still holds `[modules.<id>]` for console_io, talker, main_assistant, agent_hub, task_agents (with the kinds), job_search, temp_ui, html_viewer, voice_in, voice_notes. `config/voice_service.toml` still central. No per-module files in `config/` | **not done** (cv only) |
| 3 | agent_hub's cv_agent entry into cv: "[agent] cv_agent ← agent_hub's section" | cv_agent's own settings are in `cv/module.toml` `[agent]` (agent_id, workspace, read_dirs, chrome, mode). agent_hub's part, `named_only = ["cv_agent"]`, is still in `[modules.agent_hub]` in `config/default.toml` (corrected 2026-11-13 after a second look at `module.toml`) | **partly** |
| 4 | Tests into the module: "all cv tests, on the core test kit"; job_search, html_viewer, voice_notes, voice_in, task_agents, usage "tests" | Still central in `tests/`: `test_job_search`, `fake_job_ui`, `test_html_viewer`, `test_voice_notes`, 7 voice files, `test_task_agents`, `test_usage`. Only cv, job_search (1 file), agent_hub and echo have a `tests/` folder | **partly** (cv, agent_hub, echo) |
| 5 | "public test kit (from tests/support)"; reason 3: module tests must not import central test files | Still imported: `cv/tests/test_worker.py` (`tests.test_agents`), `agent_hub/tests/test_gate.py` (`tests.test_multi_agent`), `test_end_waiting.py` and `test_end_report_race.py` (`tests.test_agents`). No public test kit | **not done** |
| 6 | Docs into the module: "own docs" for every module | Every module has its own `docs/` (README, architecture, tools, `docs.toml`); `docs/modules/` and `docs/job-project/` are gone (`c0d2a5d`, `ee67133`) | **done** |
| 7 | Packages into the module: "pymupdf · ruff rule ← pyproject", "voice packages" | `cv` and `voice` extras and the `src/cv_tool/cvlib.py` ruff rule are still in `pyproject.toml` | **not done** |
| 8 | Viewer types out of the core: "html_viewer/ … its events · SHOW handling" | `ViewerTabsChanged`, `ViewerClip`, `ViewerClipDropped` still in `contracts/messages.py`; `infra/show_pages.py` still names `viewer.open` | **not done** |
| 9 | "never core → add-on": temp_ui and talker naming the viewer; "a snip/open slot an add-on can fill" | `temp_ui/module.py:738` still sends `InvokeTool viewer.open`; no slot | **not done** |
| 10 | A "needs" list per module ("needs cv", "needs voice_in", "reads 'needs' lists") | No `needs` key in any manifest or `module.toml`; `requires` still lists contracts only | **not done** |
| 11 | `generated/`: "live module list · installed dependencies · module directory · module library page" | No `generated/` folder; the library page is still `docs/architecture/module-library.md` | **not done** |
| 12 | "saved grants (now data/permissions.toml)" into `config/` | Still `data/permissions.toml` | **not done** |
| 13 | Remove "warns if another module needs it"; the overview adds "removing a module asks whether to purge its settings or keep them" | Nothing in `src/` for either | **not done** |
| 14 | The rule: "nothing of cv lives outside modules/cv/, except your own choices" | cv's app, packages and ruff rule live outside; its agent works in `C:\Chang\Jobs\CV_Module` | **not done** |

**Not in the page's pictures:** the agents' working folders and tools outside the repo (`C:\Chang\Jobs\CV` and `C:\Chang\Jobs`, the Resume project `C:\Chang\Git_projects\Resume` with its `.venv`, `C:\Chang\Jobs\CV_Module`, and the old `C:\Chang\Jobs\rezi`). The plan's rule ("nothing of cv lives outside modules/cv/") implies them but no box names them. The user expects them to be part of "moved into the module folder" (said on 2026-11-13, see section 3), so they're checked too.

**Does another note cover them?** Only the two reports the agents saved today, outside the repo (section 3d). In `docs/next-steps/`, no note plans moving a workspace into a module folder. The one note about an agent's folders, [cv-agent-folders.md](cv-agent-folders.md) (2026-11-09, still marked "proposed"), says the opposite: one project folder **outside** the repo per agent, "the app's code stays in this repo". That is how `C:\Chang\Jobs\CV_Module` came about. The 2026-11-11 plan never revisited that decision, and that note's status was never updated though its move happened.

**The overview's parts table** lists the CV tool at `src/cv_tool/`, the voice service at `src/voice_service/` and the HTML viewer at `src/html_viewer/`. That isn't stale: the folders really are still there (row 1). The table is right about today and wrong only against the plan.

| # | Item | Today | Done? |
|---|---|---|---|
| 15 | job_search_agent works from its module folder | Saved grant (2026-11-05): workspace `C:\Chang\Jobs\CV`, read `C:\Chang\Jobs` and `C:\Chang\Git_projects\Resume`, Resume's `.venv` Python, Chrome. Nothing on `src/assistant/modules/job_search` | **not done** |
| 16 | The old job tools cloned into the module folder | `job_search/` holds `module.py`, `ui.py`, 5 docs, 2 test files. Every skill, script and piece of job state is still in `C:\Chang\Jobs\CV`. The job agent's own read-only comparison says the same: "the tools were never cloned" (`C:\Chang\Jobs\CV\Recruiters\docs\job_workspace_move_plan_2026-11-13.md`) | **not done** |
| 17 | cv_agent works from its module folder | Saved grant (2026-11-13): workspace `C:\Chang\Jobs\CV_Module`, read the repo. Its `added` list names writes on `src/cv_tool`, `cv/docs` and `tests`, but they aren't in its `granted` list, so I can't tell whether they're live | **not done** |
| 18 | The old cv tools cloned | Yes, in two halves: `rezi\cv_tool` → `src\cv_tool` (and the cv module around it), `rezi\cv_agent` → `C:\Chang\Jobs\CV_Module` (cv_agent's report, `C:\Chang\Jobs\CV_Module\cv-tools-move-plan.md`). The copy went to a folder outside the repo, not into `modules/cv/` | **done, but not into the module folder** |

**Summary:** of the 14 items in the plan's pictures, one is done (docs), two are partly done (tests for three modules; cv's `[agent]` section), eleven are not. Of the four workspace items, the cv code was cloned but neither agent's workspace moved.

## 3: where it was reported done, and on what

Searched one source at a time; each result was written here as it came in.

### 3a. Git history (since the plan, `git log --since=2026-11-11`)

11 commits. The plan is `cce352c` (11-11 23:36). `4e9a822` (23:58) adds "Currently fixing: self-contained module folders" to the overview. The only commit that calls anything a move is `c0d2a5d` (11-12 03:18), **"Module docs move: every module's docs in its own folder…"**, with `ee67133` rebuilding the HTML. **No commit says the module-folders plan is done.** Its message names docs only; nothing after it touches the plan's other items (all commits since are docs, placeholders or the `cv_prefix` setting).

### 3b. Next-steps notes (`grep` for module folders / docs move in `docs/next-steps/`)

- **The only "done" in a note** is [handoff-privacy-cleanup.md](handoff-privacy-cleanup.md), heading "**Module docs move: done (2026-11-12)**". That task was asked as "move each module's docs into its own folder", alongside the privacy cleanup. Its evidence is real but only for docs: the build (72 pages), ruff, the full suite (800 passed), and an architecture check that docs are found by folder. **It never names the module-folders plan, and never lists the plan's other items as still open.** Its only scope note is a list of personal paths left alone.
- The overview's "Currently fixing" (from `4e9a822`) still says the module-folders work is in progress; it was never changed to done.
- An older plan, [module-self-contained.md](module-self-contained.md) (2026-11-06), audited the same gaps (apps in `src/`, `[modules.<id>]` sections in `default.toml`, central tests, core naming modules). Its status is still "building" (steps 0–2 and the docs layout). The module-folders plan of 2026-11-11 is its follow-up, and neither note links to the other.
- No note says the plan's items 1–5 or 7–14 were done.

### 3c. The app's logs (the Talker's and the Main Assistant's transcripts)

The plan, its commits and the docs move all ran in one app launch, `logs/2026-11-10_22-58-47_launch-the-job-agent/` (it ran from 11-10 to 11-12). In order:

| When | Who | What was said (log line in `talker.jsonl` unless named) |
|---|---|---|
| 11-11 23:21–23:50 | user | Asked whether modules are separate and downloadable (L33), shaped the page with snips (L147: "for cv this layout will still live in its own folder in modules/cv. Do make it truly modular"), asked about purging config (L189) and whether to edit modules in place (L200) |
| 11-11 23:50 | Talker | Answered the design questions (L207). **No build task was proposed** |
| 11-11 23:52 | user | "Okay for now, commit in chunks that make sense … then ask me for the pushes" (L208) |
| 11-11 23:52 | Talker | Handed the Main Assistant a **commit-only** task: the page went in as "the new … module-folders.html page and its next-steps notes" (L214) |
| 11-11 23:53 | user → Talker | "Add a 'currently fixing' section … and a link to module-folders.html" (L215); the Talker's ASK folded it into the last commit (L229) → `4e9a822`. The overview then said the work was under way, though no task was building it |
| 11-12 00:31 | user | During the privacy cleanup: "Also do the modules hold their own docs? They should" (L291) |
| 11-12 00:31 | Talker | "Only partly … **That's one of the steps in the self-contained plan**" (L298). The only time the docs move was linked to the plan, and it was linked as one step |
| 11-12 00:51 | Talker | Decision 2, "where module docs live", asked and answered (L314, L331) |
| 11-12 03:18 | Main Assistant → Talker | "[Task update: done] The privacy cleanup and **the module docs move are finished**" (L362; commits then `df9abe7`/`a8f12f4`, now `c0d2a5d`/`ee67133` after the history rewrite) |
| 11-12 03:18 | Talker → user | "Every module's docs live in its own folder, with the core modules first and the add-ons after … Ruff is clean and all 800 tests pass" (L367). True, but nothing said the rest of the plan was still open |
| 11-12 04:41 | restart message | `2026-11-12_04-41-44_i-want-you-to-try/` (talker.jsonl and main_assistant.jsonl, line 1): "**Done:** … the module docs move [is] built and committed". Its "**Left:**" list names the restart, the git cleanup and personal paths. **It names none of the plan's other items** |
| 11-13 03:50 | user | In the job agent's tab: "I thought we did an update to move everything into the new module folders" (`2026-11-13_02-19-03_wtf/talker.jsonl` L327) |
| 11-13 ~03:55 | user | "you'll see that I asked for everything to be restructured then ported into the module folders … When I give you literal … pictures and instructions and then you say it gets done, and it's NOT DONE" (same log, L341) |

**What I couldn't verify:** I searched the Talker's transcript and the restart message, not every line of the Main Assistant's 11-10 transcript (152 hits for these words, mostly its own file reads). I found no message that says the whole plan or "the module move" is done. Claude Code sessions run outside the app aren't in `logs/`.

### 3d. The two agents' own reports (2026-11-13)

Each agent was asked in its own tab whether its tools were cloned into its module folder. They checked their own module, not where "done" was reported.

- **Job agent:** `C:\Chang\Jobs\CV\Recruiters\docs\job_workspace_move_plan_2026-11-13.md` (its read-only tools comparison; log `2026-11-13_02-19-03_wtf/talker-job_search_agent.jsonl` L502–L514). Finding: "**the tools were never cloned**". `job_search/` holds the wrapper only (3 code files, 5 docs, 2 tests). The CLAUDE.md, 6 skills, about 30 scripts, the UI pages and all job state are in `C:\Chang\Jobs\CV`, running on the Resume `.venv`.
- **cv agent:** `C:\Chang\Jobs\CV_Module\cv-tools-move-plan.md` (log `talker-cv_agent.jsonl` L40–L75). Finding: "**the clone happened, in two halves**". `C:\Chang\Jobs\rezi\cv_tool` → `src\cv_tool` (plus the cv module), and `rezi\cv_agent` → `C:\Chang\Jobs\CV_Module`. Unchanged files match by MD5. Nothing needed lives only in the old setup, but **the workspace has not moved into the module folder**.

**Where they agree:**
- Neither agent's workspace is in its module folder.
- Both say the same things block the move or would break it: the Hub refuses an agent whose write folder overlaps the Main Assistant's whole-repo grant; a session under the repo would load the repo's `CLAUDE.md` and skills; Claude's memory is keyed to the folder path (22 and 28 notes); hard-coded paths would quietly keep using the old folder; personal data could reach git.
- Both say the "every module edits itself" change in the Hub comes first.
- Both match this audit's code check (rows 15–18).

**Where they differ:**
- **The clone:** done for cv (outside the repo), not done for job_search. That's a real difference between the modules, not a disagreement.
- **The target:** cv proposes everything in `modules/cv/workspace/` (already gitignored as `workspace/`). job_search proposes tools in the module but data kept in `C:\Chang\Jobs\CV`, which goes against the plan's rule.
- **Python:** cv already runs on the app's `.venv`. job_search needs the Resume `.venv` (jobspy, requests) and advises against adding them to the app's.
- **`.gitignore`:** cv says the existing rules cover its data. job_search lists gaps for its files (`StartUp/`, `UnderRadar/`, a personal `CLAUDE.md`, `*.png`, `*.tsv`).
- **cv's app:** cv's plan still keeps `src\cv_tool` outside the module ("or `src\cv_tool` moves under the module"), so on its own it would leave row 1 open.

### 3e. Conclusion: why it was taken as done

1. **The plan was never started as a build.** After it was approved, the only tasks were "commit" and "add Currently fixing". No task, change note or checklist ever said "build the module-folders plan". `module-self-contained.md` (2026-11-06) is the closest, and it predates this plan and stops at its docs steps.
2. **A narrower task with a similar name finished.** The docs move came out of the privacy cleanup. It was reported as "the module docs move", and its evidence (build, ruff, 800 tests) was true for docs only.
3. **No report listed what was still open.** The done message, the Talker's summary and the restart's "Left:" list never said "items 1–5 and 7–14 of the module-folders plan are still not started". Read next to "Currently fixing: module folders", "the module docs move is done" sounds like the move.
4. **The agents' folders were outside every plan.** The plan's picture doesn't name them, and the one note on them (`cv-agent-folders.md`) put them outside the repo on purpose.

So no report I found said anything false. It was reported done by omission: a true report about part of the plan, with nothing that kept the rest open.

## 4: safeguards (proposed, not built)

1. **A plan gets a checklist before work starts.** When the user gives a plan as pictures or an HTML page, the first step writes a Markdown change note listing every item, quoting the plan's own words, one row each. The work, the handoffs and the final report refer to those rows by number.
2. **"Done" only after a check against the code itself.** An item is marked done only after a check of the files (a listing, a grep, a test that fails when the item is missing), with the evidence written in the row. Passing tests, a commit or an earlier note are not evidence for an item they don't test.
3. **Never close a plan without a done and not-done list.** A final report or handoff on a plan ends with the full checklist: done, partly done, not done, out of scope. A scope cut (for example "docs only for now") is written there in the user's words with its date, and the rest stays open.
4. **Name the narrowed scope in every report.** When a task covers part of a plan, its title and every report say so ("module **docs** move, part 1 of the module-folders plan, items 2–14 still open"), so neither the Talker nor the user reads "module move: done" as the whole plan.
5. **The overview's "Currently fixing" and the next-steps row move with the checklist.** They stay until every row is done or the user drops it, and they show the count (for example "1 of 14 done").
6. **A test as the tripwire.** A test per finished item (no `src/<app>` outside its module, no `[modules.<id>]` defaults in `default.toml`, no module test importing `tests.test_*`) makes "done" checkable and stops it from slipping back. These would fail today, so they're added as each item is built.
7. **Grants and workspaces are part of "moved".** Moving a module includes its agent's saved grant and workspace, checked in `data/permissions.toml`, not only its code.

8. **An approved plan is either started or marked "not started".** When the user approves a plan page, the Talker asks once whether to build it now. If the answer is "not now", the plan's status says "approved, not started" with the date, and "Currently fixing" says the same. A plan never sits as "current work" with no task behind it.
9. **A "Left:" list includes every open plan the work touched.** Done reports, handoffs and restart messages end with the open items of each plan the work belonged to, not only the task's own leftovers.
10. **Plans that change an earlier decision say so.** When a new plan reverses an older note (here, workspaces outside the repo in `cv-agent-folders.md`), it names that note, and the old note's status is updated.

These change how agents work (prompts, skills, a test), so they need the user's yes before any is built.
