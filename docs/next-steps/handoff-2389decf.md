# Handoff: cv module, one folder plus the CV Tool build (task 2389decf)

> **Status: building (2026-11-09).** Main Assistant task 2389decf. This note carries on from [handoff-cv-tool-build.md](handoff-cv-tool-build.md). Read that first; it holds the chunk plan and the cvlib/server design. The guide is the cv module's overview page, `src/assistant/modules/cv/docs/README.md` ("Design: the CV Tool flow" and "Build state"), plus [cv-uses-cv-tool.md](cv-uses-cv-tool.md) and [cv-agent-folders.md](cv-agent-folders.md).

## The user's go (2026-11-09): the whole build, two parts

**Standing rules:**
- cv reloads are approved; ask before any app restart or anything very risky.
- Never answer cv_agent's questions, approvals or the access card yourself; pass them to the user.
- Don't touch the other agents' uncommitted edits: `infra/session_agent.py`, `handoff_keeper.py`, `job_search/module.py`, `tests/test_agents.py`, `tests/test_worker_parts.py`.
- **Copy, never move or delete.** Leave all originals until the user says they can go.
- Batch the work. Run one build and test per chunk, and after each chunk report plainly what's live and what isn't.

### Part 1: one home for the cv agent (Option B, all recommendations taken)
- **New workspace and home: `C:\Chang\Jobs\CV_Module`** (it doesn't exist yet). Layout:
  - `.claude\skills\cv-writing\SKILL.md` and `rules\*.md`
  - `.claude\state\`
  - `data\confirmed_facts.json`
  - `cv_tool\`: the CV Tool's data (`jobs\`, `inbox\`, `outbox\`, `rezi_requests\`, `cache\`, profiles)
  - `work\`, `applied\`, `docs\`, `scripts\`
- **Copy these:**
  - from `C:\Chang\Jobs\rezi\cv_agent`: `work\`, `applied\`, `docs\`, `scripts\`, `.claude\state\`;
  - the skill: `docs\cv-writing-preferences\SKILL.md` → `.claude\skills\cv-writing\SKILL.md`. Fix its step 4 to the CV Tool's Submit;
  - the rule notes from memory, `C:\Users\sharr\.claude\projects\C--Chang-Jobs-rezi-cv-agent\memory\`, into `rules\`: `cv-style-no-parentheses-semicolons`, `cv-style-action-to-result`, `cv-min-font-9pt-measured`, `cv-section-order-default`, `rezi-pdf-download-auto`, `rezi-write-sections-scrambles-experience`, `cv-tool-scope`, `cv-tool-rezi-request`, `never-script-cv-folder-copy-first`. Drop anything that conflicts with "never download Rezi's PDF", and **skip** `user-wants-rezi-export-not-local-build.md`;
  - **all 14 notes plus `MEMORY.md`** into the new memory folder, `C:\Users\sharr\.claude\projects\C--Chang-Jobs-CV-Module\memory\` (`claude` names the folder after the workspace path);
  - `C:\Chang\Jobs\rezi\cv_tool\data\confirmed_facts.json` → `CV_Module\data\`. **Merge** the three fact notes (`user-fact-system-design`, `user-facts-soylent-no-aws`, `user-facts-hooli-v5-confirmed`) into the **copy** only. Read the JSON's shape first (`words`, `phrases`, …).
- **The one old CV Tool job (Hooli)** stays in `C:\Chang\Jobs\rezi\cv_tool\jobs\` as a record. Its `job.json` holds 18 absolute paths.
- **Edit:**
  - `module.toml`:
    - `[agent] workspace = "C:/Chang/Jobs/CV_Module"`;
    - `job_skills` = `data/confirmed_facts.json`;
    - a new `rules_dir = ".claude/skills/cv-writing"`, relative to the workspace; the gate loads `SKILL.md` plus every file in `rules\`;
    - a new `[tool]` table: `port = 8771`, `data_dir = "C:/Chang/Jobs/CV_Module/cv_tool"`, `cv_dir`.
  - The tests: `cv/tests/test_job_start.py` lines 27, 161 and 163 name `C:/Chang/Jobs/rezi/cv_agent`. Line 27 is the ExampleCorp fixture under `work\pdf-reader-check`; point it at the CV_Module copy.
  - The docs: cv `README.md` (the `workspace` row; the `output_dir` row stays) and `architecture.md` L359.
  - The job agent's skill: `C:\Chang\Jobs\CV\.claude\skills\apply-session\SKILL.md` L35 names `C:\Chang\Jobs\rezi\cv_agent\applied`; change it to `C:\Chang\Jobs\CV_Module\applied`.
  - `src/cv_tool/cvlib.py`: `DEFAULT_DATA` and `DEFAULT_RULES` move to the CV_Module paths. The module passes `--data-dir`, `--rules-dir` and `--agent-work` anyway.
- **The access list changes** (the workspace line), so the card asks the user when cv reloads or turns on. **Don't answer it.** The old grant is in `data/permissions.toml` L7–8.
- **Bonus:** the Rezi helper's workspace, `C:\Chang\Jobs\rezi`, no longer contains cv_agent's.

### Part 2: the build (follow the overview page's flowchart)
- **Code placement (decided):** the CV Tool's code stays in `src/cv_tool/`. `CompanionApp` runs `python -m <package>`, and inside `cv/` that would import the module's code into the app. The module still owns it: it launches it, feeds it jobs and stops it, and the app's docs and tests sit with the module.
- **Chunk 1:** finish the app. See [handoff-cv-tool-build.md](handoff-cv-tool-build.md), "Session 3", for `agent_round`, `job_status`, `job_result` and `server.py`.
  - `py_compile` `cvlib.py` first.
  - In `import_request`, also accept a `content` dict, since the module sends the content read by `pdf_read`.
  - `app.js`:
    - L15: `tool()` returns `job?.tool || pickedTool || ""`, with no Internal default.
    - L71: the bar shows "pick one" when empty.
    - L172, L241, L359: say "cv_agent picks it up (cv.tool_status)".
    - First Draft and `#loopRun` say "pick Internal or Rezi first" when there's no pick.
    - L389: the 3 s poll also reads the server's `_fresh` list.
  - The old `server.py` is 278 lines in `C:\Chang\Jobs\rezi\cv_tool`. Model the new one on html_viewer's `viewer.py`:
    - `require_loopback` on bind;
    - `local_request(Host, Origin)` on every request, 403 otherwise;
    - POST JSON only, 415 otherwise;
    - `/api/quit`;
    - `load_layered` + `merge` for `src/cv_tool/cv_tool.toml`;
    - `open_app_window(url, profile, size="1500,950")`;
    - `raise_window(pid, "CV Tool")`;
    - `close_app_windows(profile)`.
  - Add `__init__.py` and `__main__.py`.
  - Tests in `cv/tests/test_cv_tool.py`.
- **Chunk 2, the module side:**
  - `CompanionHandover(ctx.handover, "cv_tool", host, 8771, args=[...], ping="/api/ping")` (signature in `app_kit/companion.py` L197). `export_state` returns the guard and the companion.
  - **The gate never opens the app.** cv_agent calls `cv.open_tool(job_dir)` when the user tells it to. That item starts the app, imports the job and returns the app's job id.
  - The other items: `cv.tool_status`, `cv.tool_round`, `cv.tool_result` (refuses a PDF with text under 9 pt). They use only the app's API, so they work with no window (headless later).
  - `cv.check_fonts` uses pymupdf span sizes. Check pymupdf is in the repo venv first; if it isn't, ask the app.
  - `CvRequest.tool`: Internal, Rezi or none.
  - The `rules_dir` loading.
  - Check that a fresh session after a handoff gets the gate's text again (`SessionTaskAgent`, `cv/handoff.py`).
- **Chunk 3, the prompt (`worker.py`): 5 steps.**
  1. Job & CV: the gate.
  2. Pick: the request's `tool`, else a `NEED:` to pick in the CV Tool's tab 2.
  3. First Draft.
  4. ATS Loop: to 90, at most 5 rounds, or only unbacked terms left.
  5. The user's Submit, read back with `cv.tool_result`.

  The prompt must also say:
  - Wait for the user to say "open the UI and start", then call `cv.open_tool`.
  - Edit only the CV's own content and send it with `rezi.write_resume`.
  - Use Chrome only to read the ATS score, categories and keywords. If it ever edits in Chrome, copy the same change into the content before the next PDF.
  - With Rezi picked, open the job's Rezi resume in the user's own Chrome at First Draft, keep that tab through the loop, and reload it after each write.
  - Never download Rezi's PDF.
  - The final PDF is `CV_Test_<Company>_final.pdf`.
  - First Draft ends with a `NEED:` for the user's review.
- **Chunk 4:** tests, ruff and the docs: the cv `README`, `architecture` and `tools`, the module library, `reusable.md` if anything is shared, and the overview page's **Build state** table. Rebuild the HTML. Run the architecture-check.
- **Chunk 5:** `RELOAD: cv` (approved). Confirm with `list_modules` and `show_menu cv`. The access card goes to the user.
- **Chunk 6: ExampleCorp #1.** The job agent's task 73aebe5d (paused): `hub.send` it, or `hub.start` fresh if that's refused.
  - The job: base CV `CV_Test_ExampleCorp.pdf`, the JD as text, `tool` unset.
  - Notes for cv_agent:
    - one simulation platform, Isaac Sim only;
    - don't claim Isaac Lab, MuJoCo, RL policy training, reward functions or domain randomization;
    - the real sim-to-real link: the G1 teleop checked in Isaac Sim before the robot, and the GR00T locomotion integration;
    - lead Skills with Python.
  - Then cv_agent **waits for the user** to tell it to open the UI and start.

## Done this session (2026-11-09), docs only, no source code
- **The design docs:**
  - The flow is merged into the cv overview page: "Design: the CV Tool flow" and "Build state".
  - `cv-module-flow.md` is kept until the user says it can go.
  - Scratch copies are in `docs/scratch/`.
- **Decisions written:**
  - [cv-agent-folders.md](cv-agent-folders.md): Option B.
  - [cv-uses-cv-tool.md](cv-uses-cv-tool.md): cv_agent opens the app with `cv.open_tool`, the gate doesn't, and headless comes later.
  - [handoff-cv-tool-build.md](handoff-cv-tool-build.md): the `opener` is dropped.
- **The user's base CV was restored:** `C:\Chang\Jobs\CV\CV_Test_SWE.odt` was copied from `cv_agent\work\recovery\` (419,432 bytes, hash checked).
- **Facts from the logs** (for the docs, already in the overview page):
  - cv_agent writes to Rezi only with `rezi.write_resume` and reads the score and keywords in Chrome.
  - `generate_keywords` timed out, and the API never gives a score.
  - It made Chrome edits in Hooli round 2 and in Wayne.
  - It downloaded Rezi's PDF in Hooli rounds 2–4, before the rule.
  - The Hooli run (2026-11-08) used the old app by hand; Submit was never pressed.
- **Code state (start of session 5):** `src/cv_tool/cvlib.py` edited but untested; no `server.py`. Nothing reloaded.

## Session 5 (2026-11-09): Part 1 copies done, chunk 1 written, blocked on pymupdf

**Done:**
- **`C:\Chang\Jobs\CV_Module` made, all by copying** (originals untouched): `work\`, `applied\`, `docs\`, `scripts\` and `.claude\state\` from `rezi\cv_agent` (450 files vs 439 source, plus new dirs); `.claude\skills\cv-writing\SKILL.md` (copied as is, **not yet edited**); the 9 rule notes into `.claude\skills\cv-writing\rules\` (copied as is, **not yet cleaned**); `data\confirmed_facts.json` (copied, **fact notes not yet merged**); empty `cv_tool\{jobs,inbox,outbox,rezi_requests}`. Memory: all 13 notes + `MEMORY.md` copied to `C:\Users\sharr\.claude\projects\C--Chang-Jobs-CV-Module\memory\`.
- **`app.js`:** `tool()` has no default (`""`); `PICK_FIRST` message on First Draft, Draft from score and `#loopRun`; bar says "pick one"; the three "Tell the Main Assistant" texts now say "cv_agent picks it up (cv.tool_status)". (The 3 s `/api/inbox` poll already returns the server's fresh list, see below.)
- **`cvlib.py`:** defaults → `C:\Chang\Jobs\CV_Module\cv_tool` and `...\.claude\skills\cv-writing`; `configure(..., facts="")` sets `FACTS` (default `<data_dir>\..\data\confirmed_facts.json` if it exists); `confirmed()`/`save_confirmed()` use `FACTS`; `rule_files()` (SKILL.md + `rules\*.md`) and `rules()` (file + first rule line, frontmatter skipped); `import_request` takes a `content` dict and `work_dir`; new `agent_round(r)`, `_round_answer`, `job_status(jid)`, `job_result(jid)` at the end (as designed in handoff-cv-tool-build "Session 3"; Internal job with no score → `internal_round`; `request_id` → Rezi round; Rezi PDF never taken).
- **New files:** `src/cv_tool/server.py` (class `Tool`: `require_loopback`, `local_request` on every request → 403, POST JSON only → 415, `/api/quit`, `/api/window {job}` raises or opens the Edge window via `open_app_window(size="1500,950")`, `close_app_windows` on stop, `_fresh` imports returned by `/api/inbox`; module calls `/api/job/import`, `/api/job/status?id=`, `/api/round`, `/api/job/result?id=`, `/api/rules`; `settings()` = defaults → `cv_tool.toml` + `.local` → CLI flags `--port --window app|none --no-window --data-dir --cv-dir --rules-dir --agent-work --facts --profile`; profile default `window_profile("cv_tool")`), `__init__.py`, `__main__.py`, `cv_tool.toml` (port 8771, CV_Module paths).

**Blocker, needs the user (install = risky):** `pymupdf` is **not in the repo venv** (`ModuleNotFoundError`), and `cvlib` needs it throughout (font widths, PDF text, page PNGs, `font_sizes`). `CompanionApp` runs the app with the app's own `sys.executable`. Next session: check what Python `C:\Chang\Jobs\rezi\cv_tool\cv_tool.cmd` used (it has pymupdf), then **NEED: Risky:** ask to `pip install pymupdf` into `.venv` (and add it to `pyproject.toml`, e.g. a `cv` extra), recommending yes. Same need covers `cv.check_fonts` in the module. Nothing compiled/tested yet beyond that import failure.

**Next, in order:**
1. Resolve pymupdf (ask). Then `py_compile` + import `cv_tool.server`; add `cv_tool` to ruff `known-first-party`; tests in `src/assistant/modules/cv/tests/test_cv_tool.py` (temp `data_dir`: import with `content`, `job_status`, `agent_round` export + score, `job_result`, `font_sizes`, `render` nothing under 9 pt, server ping/403/415/quit on a free port with `--window none`).
2. Clean the rule copies in CV_Module: `SKILL.md` step 4 → the CV Tool's Submit, base CVs are PDFs, `cv-tool-rezi-request.md` rewritten to the `cv.tool_status`/`cv.tool_round` flow and no Rezi PDF; drop "Related: user-wants-rezi-export-not-local-build" links; old `rezi\cv_tool` paths → CV_Module. Merge the 3 fact notes into `CV_Module\data\confirmed_facts.json` `notes` (Soylent = 3D scene data to browser, not video, not "real-time"; G1 teleop "real-time data and state feedback" is backed; "Led a 5-person team" G1 is CV-backed).
3. Chunks 2–6 as in "Part 1 → Edit" and "Part 2" above (module.toml, CompanionHandover, `cv.open_tool/tool_status/tool_round/tool_result/check_fonts`, `CvRequest.tool`, `rules_dir` gate loading, test paths, the 5-step prompt, docs + HTML, reload, ExampleCorp).

## The user's change to the plan (2026-11-09, after session 6): docs in every chunk

- **Don't leave the docs for the end.** Each chunk updates the cv module's own docs (`src/assistant/modules/cv/docs/`) in the same chunk:
  - `architecture.md`: a diagram of the code as built, laid out after the main flow diagram ("Design: the CV Tool flow");
  - `tools.md` and the API pages: the new `cv.open_tool` and `cv.tool_*` items and the CV Tool app (`src/cv_tool`: its routes, settings and launch);
  - the overview's **Build state** table and the diagram marks: only what is actually live is marked live.
- A new shared helper goes into `docs/api/reusable.md` with its Used by line.
- After each big chunk: rebuild the HTML with the docs-html skill (`build_docs.py`), then run the architecture-check skill.
- **pymupdf is NOT approved yet.** Ask before installing it into `.venv`, as a `NEED: Risky:` question with the full question and a recommendation in the NEED line. Ask as soon as the work that doesn't need it (the module side, the rules, the prompt and their docs) is done and checked.
- **Every architecture-check (after each big chunk and before the final report) also checks the design and the code against `docs/architecture/principles.md` and `docs/architecture/reusable-parts.md`:** build it once and reuse existing parts (e.g. `rezi_json._split_head`, `CompanionHandover`, `local_guard`, `app_kit.window`); the thin-module + companion-app pattern exactly as `html_viewer` uses it (the app never imports `assistant`); clean module boundaries and contracts. List every place where the code or the flowchart breaks a rule, then fix it or ask the user. Never skip a mismatch silently. (Known one to raise: `tool.py` importing `rezi_json`'s private `_split_head`/`_BULLET`; make them public within the cv module, or justify it.)
- Order: chunk A = module side + gate + `CvRequest.tool` + module.toml + their tests and docs; chunk B = rules cleanup and fact merge (CV_Module) + the 5-step prompt + docs; then the pymupdf NEED; chunk C = the app's tests (`test_cv_tool.py`) + app docs; then `RELOAD: cv` and ExampleCorp.

## At the restart (2026-11-09): what's done, what's left, the hand checks

- **Done:** the whole CV Tool build (live since the cv reload); ExampleCorp at First Draft v2, Rezi Score 90 (Content 90, Format 99, Optimization 100, Best Practices 73, Application Ready 90), one page, nothing under 9 pt, Rezi resume `00000000-0000-0000-0000-0000000000b1`; the job's folder `C:\Chang\Jobs\CV_Module\work\2026-11-09_ExampleCorp_StaffEngineerWidgetDesign\` (its `handoff.md` has cv_agent's notes). The Hub's stale-task fix at the source (`TaskRecord.holder`, `_close_replaced`), `cv.tool_draft`, `cv.tool_internal_round`, the truth check (PDF CVs, confirmed phrases, hyphenated terms), the sign-in prompt: built, 742 tests pass, loaded by this restart.
- **Open question from cv_agent (task 152d6243, may not survive the restart):** "Please review the ExampleCorp First Draft (v2, Rezi Score 90, one page) in the CV Tool. Do you want any edits? And for each of these, is it true for you and OK to add: Synthetic Data Generation, physics simulation, embodied AI, experimental skills, sim-to-real transfer?" If the task is gone after the restart, start cv_agent again on the same job (cv.task as before; the gate reuses the day's folder) and tell it the First Draft v2 is in the CV Tool and waits for the review.
- **Hand checks after the restart:** (1) `hub.agents`: cv_agent shows no stale 20c1d08e; (2) type on cv_agent's tab: the message reaches its live task, not a stale one; (3) the cv menu has `cv.tool_draft` and `cv.tool_internal_round`; (4) in the CV Tool, "modular" and "sim-to-real" are no longer flagged "not on your CVs"; (5) with an Internal job: `cv.tool_draft` with `apply`, then `cv.tool_internal_round`, shows the score and the missing keywords with no agent.
- **Left:** your review of the First Draft, then the ATS Loop and your Submit; the cv manifest's one-line description still says "checked by Rezi, your yes" (fix); commit (nothing committed); the old copies (`C:\Chang\Jobs\rezi\cv_agent`, `rezi\cv_tool`, the memory notes) stay until you say they can go; the job agent's paused task 73aebe5d is obsolete (ExampleCorp was sent from the Main Assistant).

## Session 7, later (2026-11-09): live, ExampleCorp at First Draft v2; three fixes built, not live

- **Live:** cv reloaded with chunks A–C (access card allowed 4/4); pymupdf 1.28.2 in `.venv`. ExampleCorp runs as cv_agent task **152d6243** (my child), First Draft v2 in the CV Tool; the Rezi request `2026-11-09_ExampleCorp_20261109-155236` is pending, no score; the user signed in to Rezi in Chrome, but their reply bounced.
- **Built and tested (742 pass, ruff clean, docs rebuilt), NOT live:**
  1. **Stale Hub task** (`agent_hub/tasks.py`): `open_task_of` takes the newest open task (tab messages went to the stale 20c1d08e left by the cv reloads); `send`/`cancel` close a record the agent says it doesn't hold. Test: `agent_hub/tests/test_stale_task.py`. Needs an agent_hub reload, but `AgentHubModule.busy` refuses while any record is open and records aren't handed over, so only `reload now` (drops every open task record: 2389decf, 152d6243, 73aebe5d) or an app restart makes it live. **Asked the user.**
  2. **Internal path with no agent:** `cvlib.apply_internal_draft`, route `/api/draft/internal/apply`, `keyword_lists` falls back to the last Internal round; items `cv.tool_draft`, `cv.tool_internal_round` (`tool.py` `draft`, `internal_round`).
  3. **Truth check:** `corpus()` reads `.pdf`/`.odt`/`.docx` CVs, `known()` takes the confirmed `phrases`' words and hyphenated terms whose parts are known, `configure()` resets the cache; facts' `notes` and job notes are deliberately NOT backing.
  4. **Sign-in:** the prompt says cv_agent checks both Rezi sign-ins itself (`rezi.status` / `rezi.sign_in`; Chrome: ask with NEED, reload, check). Design and code agreed apart from the prompt's missing Chrome case and the Hub routing bug.
  Items 2–4 need a cv reload; it waits while cv_agent holds 152d6243 (busy), and it restarts the CV Tool app (code changed).

## Session 7 (2026-11-09): chunks A and B done, waiting on the pymupdf answer

- **Chunk A (built, tested, not live):** `cv/tool.py` (`tool_settings`, `tool_content`, `CvTool` on `CompanionHandover`); `module.py` (`cv.open_tool`, `cv.tool_status`, `cv.tool_round`, `cv.check_fonts`, `cv.tool_result`, `_job_folder`, `_tool_call`, `export_state` = `{guard, tool}`, `settings` gains `rules_dir` and `tool`, `cv.task` gains `tool`); `job_start.py` (`rules_dir`: SKILL.md + rules/*.md, then `job_skills`; the block names `cv.open_tool`); `data.py` (`ToolPick`, `TOOL_PICKS`, `CvRequest.tool`; approved no longer needs Rezi's match); `handoff.py` (5 steps); `worker.py` (the 5-step prompt); `module.toml` (workspace CV_Module, `rules_dir`, `job_skills` = facts, `[tool]`); `rezi_json.split_head` made public; tests `test_tool.py` new, `test_worker.py`/`test_job_start.py` updated. 136 cv tests pass, ruff clean. `pyproject.toml`: `cv_tool` first-party, a scoped ruff ignore for `cvlib.py`, and a `cv = ["pymupdf>=1.24"]` extra (declared only). Docs: cv README (status, diagram marks, the 5 steps, config, Build state), architecture ("The CV Tool: code as built", class + sequence diagrams), tools (the five items), `reusable.md` and `app_kit.md` Used by lines; HTML rebuilt.
- **Chunk B (done, outside the repo):** CV_Module `SKILL.md` and 7 rule notes cleaned; 3 fact notes merged into `CV_Module\data\confirmed_facts.json` (17 notes); `apply-session` SKILL L35 → `CV_Module\applied`.
- **Next:** the pymupdf NEED (asked at the end of session 7). On yes: install, then `test_cv_tool.py` (the app: import with content, status, agent_round, result, font_sizes, render ≥ 9 pt, server ping/403/415/quit on a free port with `--window none`), a `src/cv_tool` docs section, the final architecture-check, `RELOAD: cv` (the access card goes to the user), ExampleCorp.

## Session 6 (2026-11-09): read only, nothing changed. Findings so the next session can write at once

**pymupdf, still the blocker:** the system Python `C:\Users\sharr\AppData\Local\Programs\Python\Python312\python.exe` (3.12.7) has **PyMuPDF 1.28.2**, and the old `cv_tool.cmd` ran `pythonw -I server.py` with it. `.venv` has only `pypdf 7.0.0`. `CompanionApp.ensure_running` always runs `sys.executable` (`app_kit/companion.py` L115); changing that is an `app_kit` change, so it needs a restart. **Plan:** do all the work that doesn't need pymupdf (below), then end with one `NEED: Risky: pip install pymupdf==1.28.2 into .venv, and add a `cv = ["pymupdf>=1.24"]` extra to pyproject.toml. The CV Tool and its tests need it. Recommend yes.` The module side never imports pymupdf: `cv.check_fonts` asks the app (`small_text` from `/api/round` and `/api/job/result`).

**Already checked, no change needed:**
- **A handoff's fresh session gets the gate's rules again.** `JobStartAgent.assign` passes `task.model_copy(text=text + block)` to the inner agent, and `_continue_fresh` sends `HANDED_OFF.format(text=task.text)` (`session_agent.py` L547, `handoff_keeper.py` L8). The one gap: a job given later by `message()` gets the block only in that message. Say so in the docs.
- **`src/cv_tool/server.py` is complete**: the routes, the guard, 415 on non-JSON, `/api/quit`, `/api/window`, `settings()`. `cvlib.agent_round/job_status/job_result/import_request(content=, work_dir=)` exist (L742, L1379–1454). `submit` already names `CV_Test_<slug>_final.pdf` (L1334).

**The app's content shape** (`cvlib.parse_cv` L180): `{name, contact: [str | {text, href, visible}], summary: str, skills: [[label, text]], experience: [{title, company, dates, bullets: [str]}], education: [{degree, detail: [str]}], awards: [str], publications: [str], education_first}`.

**The plan to write (one pass per file):**
- **New `src/assistant/modules/cv/tool.py`:**
  - `tool_content(content: CvContent, degree_first=False) -> dict`: CvContent sections → the app's shape. Reuse `rezi_json._split_head` (Role, Company | Dates) and `rezi_json._BULLET`. contact[0] = name; later contact lines split on `|`, linkedin/http parts → `{text, href, visible: True}`; summary lines joined; skills `Label: text` → `[label, text]`; experience/projects head lines → entries, bullets added; education: non-bullet degree lines start `{degree, detail: []}`, others → detail; awards/publications bullets stripped.
  - `CvTool` class around `CompanionHandover(ctx.handover-part, "cv_tool", host, port, args=[--port, --window none, --data-dir, --cv-dir, --rules-dir, --facts, --agent-work work_dir], ping="/api/ping", label="CV Tool", log=ctx.log)`, with `open(job_dir)` (read `job_start.json` → company, role, jd text from `jd_file`, `base_cv_copy`; `read_pdf` → `tool_content`; `POST /api/job/import` with `tool` from the request; then `POST /api/window {job}`) → `{job_id, tool, window}`; `status`, `round`, `result` (refuse when `small_text` isn't empty: name the lines, "shorten or ask, never shrink").
- **`module.py`:** `init` builds `CvTool` from `settings["tool"]`. `export_state` → `{"guard": guard.as_value(), "tool": tool.export()}`, and `ResumeGuard.from_value(ctx.handover.get("guard") if dict else ctx.handover)`. Give `CompanionHandover` the `tool` part. `stop` → `await tool.stop()`. Items: `cv.open_tool(job_dir)`, `cv.tool_status(job_id)`, `cv.tool_round(job_id, content?, export?, score?, categories?, matched?, missing?, issues?, changes?, note?, request_id?, tool?)`, `cv.tool_result(job_id)`, `cv.check_fonts(job_id)` (the current PDF's `small_text` from the app). `cv.task` gains `tool` (Internal | Rezi). `settings()` gains `tool` (host 127.0.0.1, port 8771, data_dir, cv_dir, rules_dir resolved, facts) and `rules_dir` (relative to the workspace). `JobStart(..., rules_dir=)`.
- **`job_start.py`:** `JobStart.__init__(..., rules_dir=None)`. `load_skills` loads `rules_dir/SKILL.md`, then `rules_dir/rules/*.md` sorted (listed at every job, so a new rule needs no reload; a missing dir or SKILL.md → JobStartError), then `skills`. `start_block`'s text: drop "cv.build … exports the final PDF"; say the CV Tool's Submit makes the final PDF.
- **`data.py`:** `CvRequest.tool: Literal["Internal", "Rezi"] | None = None`.
- **`handoff.py`:** in `task_text`, "the 8 steps" → "the 5 CV Tool steps".
- **`worker.py`:** the 5-step prompt as in "Chunk 3" above (also the docstring). `worker_prompt` stays the same, with target 90 and max_rounds 5 from the config.
- **`module.toml`:** `[agent] workspace = "C:/Chang/Jobs/CV_Module"`; `job_skills = ["data/confirmed_facts.json"]`; `rules_dir = ".claude/skills/cv-writing"`; `[tool] host = "127.0.0.1"`, `port = 8771`, `data_dir = "C:/Chang/Jobs/CV_Module/cv_tool"`, `facts = ""` (→ `<workspace>/data/confirmed_facts.json`).
- **Tests:** `cv/tests/test_job_start.py` L27, L161, L163 → the CV_Module paths. A new `cv/tests/test_tool.py` (`tool_content` on `pdf_fixture`, the gate's `rules_dir` loading, `CvRequest.tool`, the items against a fake app via `http_transport` or a monkeypatched `CompanionApp.call`), and `test_cv_tool.py` for the app (`pytest.importorskip("pymupdf")`). Add `cv_tool` to ruff's `known-first-party`.
- **Outside the repo** (`CV_Module`, copies only):
  - `SKILL.md`: L11 `.odt` → `.pdf`. Step 4 → "the user presses Submit in the CV Tool; cv.tool_result reads it". Step 3: the feedback goes through `cv.tool_round`, not files. Layout L41: `scripts/font_sizes.py` → `cv.check_fonts`. L29 "Don't lead with Python" stays as the general rule; ExampleCorp' note overrides it for that job.
  - `rules/cv-tool-rezi-request.md`: rewrite to `cv.tool_status` (the pending `rezi_request`) and `cv.tool_round` (`request_id`, the score fields, no pdf). Drop the "pdf" and "link_round_pdf" parts and "the user says run request".
  - `rules/rezi-pdf-download-auto.md`: the results-folder line → `cv.tool_round`.
  - `cv-tool-scope`: the path → `src/cv_tool` and `CV_Module\cv_tool`.
  - Every rule: remove `[[user-wants-rezi-export-not-local-build]]`. `rezi\cv_agent` / `rezi\cv_tool` paths → CV_Module.
  - `data/confirmed_facts.json` `notes`: add "G1 teleop: 'real-time data and state feedback' over CycloneDDS/Zenoh is backed", "'Led a 5-person team developing Unitree G1 teleoperation' at Example Tech is CV-backed", "Soylent: 3D scene data, not video; don't call it real-time", "Hooli v6: Problem solving, Collaboration, Adaptability go in the Summary story; Technical communication stays in Skills".
- **Docs:** the cv `README` (the workspace row and **Build state**), `architecture.md` (L359 and the CV Tool section), `tools.md` (the new items), the module library, and the `apply-session` SKILL L35 → `CV_Module\applied`. Then `build_docs.py`, the architecture-check, then the pymupdf NEED, then tests, `RELOAD: cv`, ExampleCorp.
