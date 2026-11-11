# Handoff: build the CV Tool into the cv module, then run ExampleCorp to First Draft

> **Status: part 1 done, part 2 next (2026-11-09).** Task b31b8901 (Main Assistant).

**The user approved (2026-11-09)**, with the recommended answers in [cv-uses-cv-tool.md](cv-uses-cv-tool.md):
1. The pick: the request names `tool` (Internal or Rezi), else the CV Tool waits for the user.
2. The style, layout, Rezi and 9 pt rules go into the cv module's `rules/` folder, and the fact notes merge into `confirmed_facts.json`. **COPY them: leave the original memory notes in `C:\Users\sharr\.claude\projects\C--Chang-Jobs-rezi-cv-agent\memory\` in place until the user says they can go.** (So also don't remove `user-wants-rezi-export-not-local-build.md` yet.)
3. The final PDF is `CV_Test_<Company>_final.pdf`.

**Standing permissions from the user:** cv reloads are approved for this work, so there's no need to ask. **Ask before any app restart** and before anything very risky. Don't answer cv_agent's questions or approvals; pass them to the user. Don't touch the uncommitted `infra/session_agent.py`, `handoff_keeper.py`, `job_search/module.py`, `tests/test_agents.py` or `tests/test_worker_parts.py` (other agents' edits).

## Part 1: done (this session)
- **PDF in, PDF out is live.** `cv` was reloaded ("now", cutting in on cv_agent's idle task 20c1d08e, the finished PDF build that held only an answered question). The live menu: `cv.task` takes `base_cv` as a `CV_Test_*.pdf`, `cv.read(pdf)`, `cv.build(job_dir)`, `cv.compare(edited_pdf)`, no `odt_path`. 156 cv tests pass. cv_agent is free and in **Manual** mode after the reload.
- **The job agent's three files now name `.pdf`:**
  - `C:\Chang\Jobs\CV\Recruiters\scripts\save_jd.py`: `BASE_PDF`, `company_cvs` lists `.pdf`, `--base` must be an existing `CV_Test_*.pdf` in the CV folder. It compiles.
  - `C:\Chang\Jobs\CV\.claude\skills\apply-session\SKILL.md`, lines 30–36. Lines 43 and 85 (form filling with `.odt`) are left as the plan says.
  - `...\Recruiters\docs\applications\jd\examplecorp-staffengineerwidgetdesign.json`: `base_cv` and `company_cvs_on_disk` are now `CV_Test_ExampleCorp.pdf` (it exists, 2026-11-03).
- `cv-pdf-only.md` status: live. `cv-uses-cv-tool.md` status: approved, building.
- **Not blocking:** `CV_Test_SWE.pdf` (2026-10-22) is older than the emptied `.odt`; ExampleCorp doesn't use it.

## Part 2: in progress (2026-11-09, session 2)

**The user's answers this session (no more questions until First Draft; stop only for an app restart or something very risky):**
- Build the FULL Part 2 including the app move. The CV Tool was always the UI half of the cv module; it was split by mistake.
- Yes to edit cvlib so it accepts a PDF base CV.
- **The rules are the cv module's general rules, not the UI's:** gather the style, layout, Rezi and 9 pt rules into the module's skill in `src/assistant/modules/cv/rules/`, load them through the job-start gate for ALL cv work (not only CV Tool jobs), keep the facts as data in `confirmed_facts.json`. The CV Tool reads them from the module (`rules_dir`), never keeps its own copy. Say this in `cv-uses-cv-tool.md` and the cv docs.
- After the build: reload cv, have the job search agent send ExampleCorp #1 (PDF + JD text), run to First Draft in the CV Tool, stop for the user's review.

**Investigation answer already given to the user** (read-only report): the design came from `logs\2026-11-06_04-28-55_open-two-extra-helpers-one\talker-cv_agent.jsonl` L396, L418, L426, L632, L910, L1067, L1136; written in `cv_tool\README.md` "The flow". Nothing more to report there.

### Chunk 1 (moving the app): half done
Done:
- `src/cv_tool/` made, with `cvlib.py`, `static\` and `assets\` COPIED from `C:\Chang\Jobs\rezi\cv_tool` (originals untouched).
- `src/cv_tool/cvlib.py` edited (not yet compiled or tested):
  - `APP` (code dir) vs data; `configure(data_dir, cv_dir, rules_dir, agent_work)` sets `ROOT, CV_DIR, JOBS, DATA, INBOX, REZI_REQ, REZI_RES, OUTBOX, AGENT_WORK, RULES_DIR` (the old top-level ones were removed); `configure()` is called at the end of the file.
  - `rules()`: the module's rule files (name + first rule line).
  - `CV_TYPES` = .pdf, .odt, .docx; `odt_paras` → `pdf_paras` for PDFs (pymupdf lines, best effort).
  - `font_sizes(pdf)`: text under `MIN_PT` = 9.
  - **9 pt:** `BODY` 7.6 → 9.0; contact 6.4, title, degree and awards 8.5 → `MIN_PT`. The plan only named the 8.5 lines; the 9 pt rule (`cv-min-font-9pt-measured.md`) is about body text, which was 7.6. Bullets that now overflow show red in the app (shorten or ask). Tell the user.
  - The Internal score's 8.5 pt note is now a measured `font_sizes` note.
- **Why not `pdf_read.py` in the app:** the checklist says a companion app never imports `assistant`, and `pdf_read` needs `cv.content` and `cv.odt`. So the module will feed each job's **content** (read with `pdf_read`) to the app's API; the app's own `pdf_paras` is only for a hand-dropped CV. Put this in the docs.

Next, chunk 1:
1. `py_compile src/cv_tool/cvlib.py`; grep it for any `ROOT`/`INBOX`/`OUTBOX` used before `configure()`.
2. Write `src/cv_tool/server.py` from the old one (`C:\Chang\Jobs\rezi\cv_tool\server.py`, 278 lines):
   - config `src/cv_tool/cv_tool.toml` with `load_layered` + `merge` defaults: host 127.0.0.1, **port 8771** (8765–8767 and 8770 are taken), `data_dir`, `cv_dir`, `rules_dir`, `profile` (default `<data_dir>\.edge_profile`).
   - `require_loopback` on bind and `local_request(Host, Origin)` on every request (403 otherwise).
   - `POST /api/quit` (JSON content type only): shut down and `close_app_windows(profile)`.
   - `GET /api/rules`; `POST /api/job/import` (an `import_request` body, for the module).
   - Static files from `cvlib.APP`; `open_app_window(url, profile, size="1500,950")`; the CLI args kept; `running_port` pings the fixed port.
3. `src/cv_tool/__init__.py` and `__main__.py` (`python -m cv_tool`); `README.md` copied into `src/cv_tool/` with paths updated.
4. Tests in `tests/test_cv_tool.py` (or the cv module's tests): import, `pdf_paras` on a fixture PDF (`cv/tests/pdf_fixture.py`), `font_sizes`, `render` has no size under 9, server ping/quit/guard on a temp `data_dir`. Hooli job stays read-only.
5. Run ruff and pytest, then the architecture-check.

### Session 3 (2026-11-09): read only, nothing changed. The design worked out, so the next session can write straight away
Files already read and understood: old `server.py`, `html_viewer/module.py` + `viewer.py` (guard, quit, main loop), `app_kit` API, cv `module.py`, `job_start.py`, `data.py`, `worker.py`, `module.toml`, `cvlib.py` (setup, jobs, `import_request`, `rezi_request`, `apply_result`, `current_pdf`, `loop_state`, `internal_round`, `submit`), `app.js` (tool pick, draft, polling).

**`cvlib.py` additions** (keep the server thin):
- `agent_round(r)`: `job_id` required. `content` (the app's shape: name, contact, summary, skills `[[label, text]]`, experience `[{title, company, dates, bullets}]`, education `[{degree, detail}]`, awards, publications, education_first) is set straight on the job (the agent is the editor; `apply_result` would store it as `rezi_content` for tool Rezi), then `_unsubmit` + save. `export` (default: true when content given): Internal job with no score → `internal_round`; else `export_pdf`; return `pdf` + `small_text` (`font_sizes`). Then the score fields (`request_id, changes, issues, score, categories, matched, missing, note, tool`; tool default the job's) go through `apply_result(upd, "api_<stamp>")`; set the new round's `version` to the export's name. Return `{pdf, small_text, state: loop_state, rules: rules()}`.
- `job_status(jid)`: id, company, role, `tool` ("" = not picked yet), `content`, `text` (`cv_text`), `rezi_resume`, the pending `rezi_request` (`request_id, text, rules` from its file), `loop` (`loop_state`), `ready` (ready.flag exists), `rules`.
- `job_result(jid)`: `{ready: false, submitted}` until `ready.flag`; then `{ready: true, result: result.json, small_text}`.

**`server.py`:** as planned above, plus: every POST must be JSON (415 otherwise); `POST /api/job/import` → `import_request` (pass the job's `base_cv_copy` from work_dir: it's copied into the app's job and parsed there) and add the id to a `_fresh` list that `/api/inbox` also returns, so the open page switches to it; `GET /api/job/status`, `POST /api/round`, `GET /api/job/result`; `POST /api/window {job}` opens the window again if closed, else `raise_window(pid, "CV Tool")`. The server keeps running when the window closes (the module owns its life); `--quit-with-window` for `cv_tool.cmd`.

**`app.js`:** `tool()` returns `job?.tool || pickedTool || ""` (no Internal default: the app waits for the pick); First Draft and `#loopRun` say "pick Internal or Rezi first" when empty; the bar's tab 2 label shows "pick one". Replace the three "Tell the Main Assistant cv_agent: run CV Tool Rezi request" texts (lines ~172, ~241, ~359) with "cv_agent picks it up (cv.tool_status)".

**cv module:** `CompanionHandover(ctx.handover, "cv_tool", host, 8771, args=[--port, --data-dir, --cv-dir, --rules-dir, --profile window_profile("cv_tool"), --agent-work work_dir], ping="/api/ping")`; `export_state` must return both the guard and the companion's export (a dict). **No `opener` in `JobStartAgent`. The gate never opens the app** (decided 2026-11-09: cv_agent launches the UI when the user tells it to; a headless mode may come later, so the items use only the app's API). Instead, `cv.open_tool(job_dir)` starts the app through `CompanionApp`, imports the job, and returns the app's job id to cv_agent. `CvRequest.tool: Literal["Internal","Rezi"] | None`. Items: `cv.open_tool(job_id?)`, `cv.tool_status(job_id)`, `cv.tool_round(...)` (args as `agent_round`), `cv.tool_result(job_id)` (refuses a ready result whose PDF has text under 9 pt). `cv.check_fonts(pdf)`: **measure with pymupdf span sizes** (the app's `font_sizes` way; pypdf's layout `font_size` may not be the printed size). Check pymupdf is in the repo venv first; if not, the module asks the app (`small_text` in the answers) rather than installing.
- Prompt step 3 (First Draft) always ends with a NEED: for the user's review in the CV Tool; the pick, if `tool` is unset, is a NEED: too ("pick Internal or Rezi in the CV Tool's tab 2").

**Rules:** copy into `src/assistant/modules/cv/rules/`: `docs\cv-writing-preferences\SKILL.md` (from `C:\Chang\Jobs\rezi\cv_agent\docs\`, step 4 fixed to the CV Tool's Submit) and from the memory folder `cv-style-no-parentheses-semicolons`, `cv-style-action-to-result`, `cv-min-font-9pt-measured`, `cv-section-order-default`, `rezi-pdf-download-auto`, `rezi-write-sections-scrambles-experience`, `cv-tool-scope`, `cv-tool-rezi-request`, `never-script-cv-folder-copy-first` (all small, ~1–2 KB; read them first, drop anything conflicting with "never download Rezi's PDF"). Facts stay data: `job_skills` lists the three `user-fact*` memory notes (absolute paths, originals stay) and `C:\Chang\Jobs\rezi\cv_tool\data\confirmed_facts.json` (2.6 KB); don't write into that file. `rules_dir` setting (default the module's `rules/`, every `.md` loaded) in `job_folders`/`JobStart`.

Then chunks 2–5 below as planned (`cv_tool.cmd` repoint is outside the repo: the user's yes is implied by "build the full move", but leave the old `server.py` in place).

## Part 2 plan (from session 1). Build cv-uses-cv-tool (read the note in full first)
Use `architecture-first`, `batching`, and `architecture-check` per chunk. Check `docs/api/reusable.md` (`CompanionApp`, `local_guard`, `window`, `load_layered`) and the [companion app checklist](../architecture/reusable-parts.md#companion-app-checklist); follow `html_viewer` as the model.
1. **Move the app:** `C:\Chang\Jobs\rezi\cv_tool\{server.py, cvlib.py, static\, assets\}` → `src/cv_tool/` (`__main__.py`). Copy the code; leave the originals and all data in place. Changes:
   - a fixed port from config;
   - `POST /api/quit`;
   - `local_guard` on every request;
   - `app_kit.window.open_app_window` instead of the hard-coded `msedge` path;
   - `data_dir` = `C:\Chang\Jobs\rezi\cv_tool`;
   - base CV read with the cv module's `pdf_read.py`;
   - the 8.5 pt styles (cvlib lines 401, 406, 408) set to 9 pt;
   - the PDF named `CV_Test_<Company>_final.pdf`;
   - the pick taken from the request's `tool`, else it waits.

   Point `cv_tool.cmd` at the new package only if the user agrees, since it's outside the repo.
2. **The cv module:**
   - `CompanionApp` start and stop, plus a `cv.open_tool` item;
   - `cv.open_tool` (called by cv_agent when the user says to start; never by the gate) feeds the job to the app's API and returns the app's job id;
   - the items `cv.tool_round`, `cv.tool_status` and `cv.tool_result`. `cv.tool_round` returns the rules checklist each round;
   - the 9 pt check (`cv.check_fonts`, using `pdf_read`'s `font_size`);
   - `CvRequest.tool` (optional: `internal` or `rezi`);
   - the `rules_dir` setting (default: the module's `rules/`, every file loaded) and `confirmed_facts.json` in `job_skills`;
   - the new `worker.py` prompt: the 5 CV Tool steps replace the 8. Stop after First Draft for the user's review when the request says so.
3. **The rules folder:** copy `cv-writing-preferences\SKILL.md` (fix its step 4 to the CV Tool's Submit) and the notes `cv-style-*`, `cv-min-font-9pt-measured`, `cv-section-order-default`, `rezi-*`, `cv-tool-scope` and `cv-tool-rezi-request` into `src/assistant/modules/cv/rules/`. Merge the three `user-fact*` notes into a copy of the facts. **Ask the user before writing into `confirmed_facts.json` itself;** it's their data file.
4. **Check** whether a fresh session after a handoff gets the gate's text again (`SessionTaskAgent`, `cv/handoff.py`). Add it back if not.
5. **Tests, docs** (cv `docs/`, `module-library`, `reusable.md` if anything is shared), then rebuild the docs HTML. Then `RELOAD: cv`, and confirm with `list_modules` and `show_menu cv`.

## Part 3: after part 2 is live
- The job agent's task **73aebe5d** is paused, waiting to resend ExampleCorp #1 "when asked again". Send it with `hub.send` if it's still open; it isn't the Main Assistant's child, so `hub.start` it fresh if `hub.send` is refused. The job, from the hand-off record above: the JD as **text**, the base `CV_Test_ExampleCorp.pdf`, the URL, `tool` unset (the user picks in the CV Tool) unless the user says otherwise.
- **Notes for cv_agent:**
  - The job wants one simulation platform, and Chang has Isaac Sim only.
  - Don't claim Isaac Lab, MuJoCo, RL policy training, reward functions or domain randomization.
  - The real sim-to-real link: the G1 teleop validated in Isaac Sim before the physical robot, and the GR00T locomotion policy integration.
  - Lead Skills with Python. No raw graphics APIs.
  - The old folder `work\2026-11-08_ExampleCorp\` (draft_v1.md, handoff.md) and the Rezi resume `00000000-0000-0000-0000-00000000c0de` may be reused or replaced.
  - **Run to First Draft in the CV Tool and stop for the user's review.**
- Watch with `hub.status`; pass every question and approval to the user. Report what's live and what isn't.
