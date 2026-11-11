# Handoff 20c1d08e: cv module, PDF in and PDF out (build)

Task: build the plan in `docs/next-steps/cv-pdf-only.md`. The user said "build it". **User change (2026-11-09): keep cv_agent's read access to `C:\Chang\Jobs\CV`. Don't touch `[agent] read_dirs`, and leave that part of the plan out.** Ask before any reload or restart. Ask before editing the job agent's files (`save_jd.py`, the apply-session skill, the ExampleCorp record). Don't touch the uncommitted `infra/session_agent.py` and `handoff_keeper.py` (another agent's). `job_search/module.py`, `tests/test_agents.py` and `tests/test_worker_parts.py` are also modified, not by this task: leave them alone.

## State right now (session 3, 2026-11-09): built and tested, waiting on you

- **Tests:** all updated to PDF fixtures, plus the new `tests/test_pdf_read.py`. 130 cv tests pass, three of them with real LibreOffice; with `test_module_layout.py` and `test_module_docs.py`, 156 pass. Ruff check is clean.
- **Reader fix:** an unplaced line's words are named once in `unplaced`, not twice.
- **Fixture:** `write_pdf(..., extra=)` adds lines, such as an unknown heading for the read check.
- **The ExampleCorp case:** it now reads the reader check's copy in `work\pdf-reader-check\cvs`, never the CV folder, and checks that every word is placed.
- **Docs:** README, architecture and tools are updated, `reusable.md` needs no change (no shared PDF reader), the plan page status and the next-steps row are updated, and the HTML is rebuilt.
- **Not done (waiting on you):** the `cv` reload; your yes on the job agent's 3 files; `CV_Test_SWE.odt` being 0 bytes. Nothing is committed.

## User answers (2026-11-09, after session 3)

- **No for now** to the `cv` reload and to editing the job agent's three files. Wait for the user. Only read-only work, plus the context note below.

## In progress: the Rezi context note (read only, plus one file to write)

**Task:** read `C:\Chang\Jobs\rezi\cv_tool`, `C:\Chang\Jobs\rezi\rezi` and `C:\Chang\Jobs\rezi\rezi_agent` read-only, and run nothing. Then write **only** `C:\Chang\Jobs\rezi\cv_agent\work\rezi_context_note.md` covering:
- how the Rezi flow and its UI really work;
- what each folder holds;
- which tools and scripts belong to which;
- what the old flow did that the cv module doesn't;
- anything that changes the PDF plan.

Then tell the user the key points briefly. **Written (session 4, 2026-11-09).** Tests re-run: 156 pass. Also found: `CV_Test_SWE.odt` was emptied 2026-11-08 02:00:50 (during Hooli); `CV_Test_SWE.pdf` (2026-10-22) exists. Hooli never reached Submit. Still waiting: reload, the job agent's 3 files. (Earlier status below.) All three folders have been read except: Hooli's `job.json` (end state; submitted or not) and the names of the driving scripts in `C:\Chang\Jobs\rezi\cv_agent\scripts` (both still to check, read only).

**Findings so far:**

- **`rezi\` (2026-11-06/07): the cv module's planning folder, not a tool.**
  - `rezi-mcp-findings.md`: the module plan v4, superseded. It planned `rezi.score/keywords/import_pdf` items; the user later chose Chrome in the worker (N1).
  - `cv_module_plan.html`: the approved plan.
  - `handoff-d21df25f.md`: the build log for chunks 1–9, with:
    - the Rezi screen tour (D8);
    - the live tool list (12 tools);
    - the live `read_resume` shape;
    - the Wayne run, cancelled at step 2 after creating resume `41431c88…`.
  - `drafts\`: the first cv docs.
  - `scratch\`: the reader/build tryout scripts (`try_*.py`, `dump_odt.py`).
  - `out\2026-11-07_Wayne\`: the old local `.odt`/PDF build, not the deliverable, plus `out\jd\` (the WayneJD as HTML).
  - `logs\cv_agent.jsonl`: test traffic from the fake `claude` only (Acme jobs), a stray test log.
- **`rezi_agent\notes.md` (2026-11-05): the retired helper's checklist and open questions.** It was written before the module existed. It planned Rezi's "Download PDF" as the deliverable (option A).
- **`cv_tool\`: the standalone CV Tool app the user actually used for Hooli** (README read in full).
  - **Start:** `cv_tool.cmd` runs `pythonw -I server.py`, a server on 127.0.0.1 in its own Edge window (`.edge_profile`).
  - **`cvlib.py`:**
    - reads base CVs as `.odt`/`.docx` only, from `C:\Chang\Jobs\CV`;
    - renders its own HTML template (Source Sans 3, Letter, `render()`);
    - exports the PDF with **headless Chrome print-to-pdf** (`.chrome_print` profile), not LibreOffice;
    - pymupdf for page count, parse checks and highlights;
    - `lint` flags semicolons, parentheses and bullets that wrap (fill > 1.0, target 0.92);
    - an Internal score estimate;
    - the truth check against the `.odt` corpus **plus `data/confirmed_facts.json`** (user-confirmed words and phrases, declined terms).
  - **Its 4 tabs:** Job & CV / CV Tool / First Draft / ATS Loop, then Submit (`result.json`, `outbox\`, `ready.flag`).
  - **How it reaches Rezi:** the app never touches Rezi. "Send JD and CV to Rezi" writes `rezi_requests\<id>.json`, and the user tells cv_agent to run it. cv_agent:
    - writes the text into its own Rezi resume as the full object by ids, never `sections`, and reads it back;
    - scores in Chrome: `/dashboard/resume/<id>/finish-up`, reload once if it shows "Something went wrong", JS-click "Explore My Rezi score", read the text, Esc; then the AI Keyword Targeting card, JS-click both "See all (N)";
    - writes `rezi_requests\results\<name>.json` (score, categories, matched, missing, issues, changes; **no PDF**: the user's rule since Hooli v5).
  - **Hooli:** 7 Rezi rounds ending at 97, with Rezi PDFs `_rezi_draft1`/`r2`–`r4` downloaded before the rule.
- **The step-6 import ("<Company> – check") was never really run** (the Wayne`report.md` says it was skipped at the user's request).

**What changes the PDF plan, to put in the note:**
- (a) **Truth source:** user-confirmed facts live in `cv_tool\data\confirmed_facts.json` and in the memory notes. The cv module's truth gate reads only the CVs, so confirmed facts (system design, requirements analysis, …) and declined ones (AWS, data pipelines, telemetry, unit testing) aren't in the module. Recommend: a read-only input, with the user's yes.
- (b) **Look of the final PDF:** the approved Wayne v10 and Hooli v6 PDFs came from the CV Tool's HTML → Chrome template, not the module's LibreOffice `.odt` build, so the module's PDF will look different. Ask the user which look is the final one.
- (c) **The CV Tool's intake is `.odt`/`.docx`:** it conflicts with PDF-only, but it's outside the module, so leave it.
- (d) **`rezi.write_resume` with `sections` on an update scrambled Experience (Wayne).** The module still offers `sections` with a `resume_id`, via `write_rezi`, which reuses ids in order. Check that the order-based reuse is safe, or make updates use the full object.
- (e) **The memory notes contradict each other:** "use Rezi's export" is older, "never download Rezi's PDF" is newer and wins. The module builds its own PDF, so that's consistent.

**Next:**
1. Read the two remaining items, read only.
2. Write the note at that one path.
3. Give the user the key points briefly.
4. Then wait. No reload, no job agent edits, nothing committed.

## Done (sessions 1 and 2)

- **`pdf_read.py`** (reader): `read_pdf(path) -> PdfCv(content, unplaced, pages)` and `place(lines, plain)`. It uses pypdf's `_layout_mode` internals and raises a RuntimeError if they change.
  - Session 2 fixes:
    - (a) **Centered paragraphs:** the lines' centers match while x0 differs; the fit test uses the whole width `right - left` (`Line.left` = the page's min x0).
    - (b) **First-word width:** a character-weighted estimate (`_weight`: capitals and m/w/& 1.3, narrow i/l/t/punctuation 0.5) × `_WORD_WIDE` 1.1.
    - (c) **Label lines:** a line starting `Label:` (`_LABEL`, e.g. "Skills:", "AI Development:") never joins the line above.
  - **The one-time check against the .odt reader: 33/36 match exactly.** The other 3 aren't reader bugs: the Apple and Walden PDFs are older than their .odt files, and SWE.odt is 0 bytes.
    - Unplaced is 0 on every CV except `CV_Test_Rezi.pdf` (78; Rezi's own layout, so the worker would stop and ask).
    - Scripts and copies: `C:\Chang\Jobs\rezi\cv_agent\work\pdf-reader-check` (`check_all.py`, `lines.py`). Run them with `PYTHONPATH=<repo>\src`.
- **`content.py`:** `CvContent.from_pdf` raises ValueError naming the unplaced text. `from_odt` is removed; `odt.read_odt` is kept for the writer's round-trip tests.
- **`data.py`:** `BASE_CV_NAME` regex. `CvRequest.base_cv` must match `CV_Test_*.pdf`, else "base_cv must be a CV_Test_*.pdf, not <name>". `CvResult.odt_path` is removed, so extra=forbid refuses it.
- **`build.py`:** `build_cv(content, order, pdf_path, export, ...)`. The .odt and the export go in a `TemporaryDirectory`; only the last checked PDF is copied to `pdf_path`. `Built` has no odt_path, and a non-.pdf target raises ValueError.
- **`module.py`:**
  - `cv.task` description: JD as text, base CV as a PDF, the job comes back as a PDF. The `base_cv` and `jd_file` descriptions are updated.
  - `cv.read(pdf)` returns sections, names, pages, `complete` and `unplaced`, plus a `next` (stop and ask with NEED:) when the read is incomplete. A RuntimeError → not_available.
  - `cv.build` has a new `job_dir` arg (`_pdf_target`): it must be a subfolder of work_dir that exists. The PDF goes to `<job_dir>/CV_Test_<Company>.pdf`. If that's the job's base copy (from `job_start.json`, `_job_copies`), the name gets `_tailored`. Without job_dir it uses `output_path` (now `.pdf`).
  - `cv.compare`: `edited_odt` → `edited_pdf` (must be readable).
  - `cv.report`: the folder is the PDF's folder, allowed in output_dir or work_dir. `_REPORT_ARGS` has no odt_path.
  - `_check_pdf` refuses an .odt ("an .odt isn't read; give the CV_Test_*.pdf"). `_content(pdf, sections, ...)` uses `from_pdf`.
  - The docstring is updated, and `json` and `read_pdf` are imported.
- **`handoff.py`:** `result_view.files` has no odt fields; the docstrings are updated.
- **`report.py`:** the `.odt` row is dropped.
- **`worker.py` prompt:** the base CV is a PDF and the JD is text; PDFs only, never an .odt; cv.read's read check (complete false → NEED:); step 5 calls cv.build with company and job_dir, which exports the PDF into the job folder; the CvResult list has no odt_path; the truth gate reads `CV_Test_*.pdf`; the last line says the PDF and report go in the job folder.
- **`module.toml`:** the cv_dir comment says PDFs. **read_dirs is unchanged.**
- **`job_start.py`:** `start_block` adds "cv.build with job_dir=<work_dir> exports the final PDF into this folder". There's no logic change: it copies and hashes any file.
- **New `tests/pdf_fixture.py`:** `write_pdf(content, order, path)` writes a real one-page Helvetica text PDF (no LibreOffice), with `•` bullets and the dates at x=470 for entries. **Not run yet**: first check that `read_pdf(write_pdf(CV, ...))` gives back CV's sections (the test CV strings in test_worker.py display mojibake in PowerShell, but they're fine UTF-8).

## Next

1. **Tests** (run `.\.venv\Scripts\python -m pytest src/assistant/modules/cv tests/test_module_layout.py -q`):
   - **New `tests/test_pdf_read.py`:**
     - `place()` on hand-made `Line`/`Run` lists: left wrap, centered wrap, a `Label:` line not joined, the entry join, small caps (`_small_caps`), a bullet glyph (`_line`), an unknown big heading → unplaced, and `_unread`;
     - the fixture round trip; `CvContent.from_pdf` raising on unplaced;
     - a soffice round trip (OdtWriter → PdfExport → read_pdf), skipped without LibreOffice.
   - **Update these to PDF fixtures (`write_pdf`):**
     - **test_cv.py:** the request needs a `CV_Test_*.pdf` (.odt refused); the CvResult with odt_path is refused.
     - **test_handoff.py:** APPROVED has no odt_path; files has no odt keys; base CVs become .pdf.
     - **test_compare_report.py:** APPROVED has no odt_path; `edited_pdf`.
     - **test_build.py:** `from_odt` → read_odt or from_pdf; the build target becomes `out/CV.pdf` (FakeExport returns the `.pdf` next to the temp odt, so build_cv's copyfile needs a real file there: make FakeExport write bytes); `output_path` → `.pdf`; the cv.build arg refusals include an .odt; the job_dir test (inside work_dir, its base copy not overwritten, outside refused).
     - **test_job_start.py:** `.pdf` base; `cv.read pdf=`; the ExampleCorp test is skipped or pointed at a `.pdf`.
     - **test_worker.py:** `cv.read` with `pdf`; an .odt is refused; the prompt says PDF.
2. **Docs:**
   - update `cv/docs/README.md`, `architecture.md` and `tools.md` (cv.read/cv.build/cv.compare args, no odt_path, pdf_read.py);
   - check `docs/api/reusable.md` (pdf_read is cv-specific, so probably just mention it's not shared);
   - plan page `cv-pdf-only.md`: Status "built (2026-11-09); the access cut is left out at the user's request; the job agent's 3 files wait for your yes";
   - rebuild with the docs-html skill (`.\.venv\Scripts\python scripts\build_docs.py`).
3. **Report, then ask:**
   - (a) reload `cv`?
   - (b) edit the three job agent files to `.pdf`? (Until then, the job agent's cv.task calls with an .odt are refused.)
   - (c) `CV_Test_SWE.odt` is 0 bytes.
