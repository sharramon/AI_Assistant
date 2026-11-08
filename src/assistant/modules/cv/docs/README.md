# cv: tailor a CV for one job with Rezi, one clean page, your yes

## Purpose

Takes a CV (`CV_Test_*.odt`) and a job description (JD). Rezi edits and scores a new copy for that JD. The module's worker reformats it to one clean page (US Letter by default), has Rezi check that page, and returns the PDF you approved, with the scores, keywords and checks that led to it. One module with its worker inside; it stands alone, and other modules (the job agent) connect to it later through `cv.task`.

**Status (2026-11-07):** built and tested, chunks 1 to 8. That covers the menu (`rezi.*`, `cv.*`), the Rezi connection with its resume guard, the one-page build and checks, the worker `cv_agent`, and the in-and-out contract below. Everything is tested against a fake Rezi and a fake `claude`. Chunk 9, the real run, is under way: the real Rezi sign-in, live tool list and reads work, and the module now reads and writes Rezi's real resume format. Off by default; turning it on asks for the worker's access on one card.

How it works inside: [Architecture](architecture.md). Its menu, and what a job sends in and gets back: [Tools](tools.md).

## In and out

- **In** (`cv.task`): the job's company and role, the job description as text or as a `.txt`, `.md` or `.html` file, and the CV file (`CV_Test_*.odt` in `C:\Chang\Jobs\CV`). Optional: the posting's URL, Education first, a target score, notes.
- **Out** (`cv.read_result` on the task's result): the new `.odt`, the PDF and `report.md`, and with them the Rezi Score after each round against the target, the keywords still missing and those left out because you don't have them, recommendations, the one-page check, and the compare of what Rezi read. Also the new Rezi resume and its check copy, and whether you approved it.

The calls and every field: [Tools](tools.md#the-hand-off-cvtask-and-cvread_result).

## The 8 steps

1. **Receive** the base CV and the JD from the caller, sent through the Hub (`cv.task`, then `hub.start` to `cv_agent`). Pick the section order.
2. **Edit in Rezi:** a new resume from the base CV, Keyword Targeting with the JD, keep only true edits, save.
3. **You read** the edited CV. Changes go back to step 2.
4. **Rezi Score** and missing keywords: 90 or more (aim 100), at most 5 rounds. Below target goes back to step 2, adding only terms you really have.
5. **One clean page:** the worker builds the `.odt` and the PDF.
6. **Rezi checks the page:** it imports the PDF, the worker compares what Rezi read with the edited resume, and Rezi scores it again. A layout problem goes back to step 5, a content problem to step 2.
7. **Is this the one?** Your yes, or the step to go back to.
8. **Return** the PDF, the `.odt` and the report to the caller: the task ends with a `CV_RESULT` line, which the caller reads with `cv.read_result`.

The loops are drawn on the [Architecture](architecture.md#conceptual-flow-the-8-steps) page.

## Who does what

| Who | Does |
|-----|------|
| **Rezi** (MCP + web app) | Holds a new resume for each job (the base is never changed). Keyword Targeting with the JD gives the missing keywords; the Rezi Score rates the CV. Imports the one-page PDF, shows what it read, scores it again. Rezi's AI writer isn't used for now. |
| **The worker** (`cv_agent`) | Drives Rezi: the `rezi.*` items for data, Chrome for Keyword Targeting, the Score and the PDF import. Is the truth gate: keeps only wording backed by facts already on your CVs, adds no skill, title, tool or number you don't have, no keyword stuffing. Formats the one page itself (`cv.build`). Reads what Rezi says is wrong and loops back. Asks you at steps 3 and 7, giving the PDF's path (the viewer shows HTML only), and returns the result. Never uploads or submits anything outside Rezi. |
| **You** | Check the content after the edit (step 3). Give the final yes on the PDF (step 7). |

## Wrapper

| Field | Value |
|-------|-------|
| id | `cv` |
| provides | `ITaskAgent`: its worker `cv_agent`, so the Hub lists it and starts its tasks |
| requires / optional | nothing; its worker claims its agent id `cv_agent` from the Hub, the way `job_search`'s agent does (`ProfileAgent`) |
| permissions | `agent.access`: the worker's access list on one card when cv turns on (its workspace, read `C:\Chang\Jobs\CV` and the output folder, Chrome only for app.rezi.ai). cv turns on when you allow. A later grant reaches the worker live |

## Config

Defaults in `module.toml` in this module's folder; `[modules.cv]` in the app's config only overrides them.

| Key | Default | Meaning |
|-----|---------|---------|
| `section_order` | Contact, Summary, Skills, Experience, Projects, Education, Awards, Publications | The usual order |
| `degree_first_order` | Education right under Skills | Used when the JD requires or prefers a master's |
| `drop_first` | `publications`, `awards` | What goes first when the page is too long |
| `target_score` | 90 | The Rezi Score to reach (aim 100) |
| `max_rounds` | 5 | Score rounds before it stops and reports |
| `paper` | `letter` | US Letter; `a4` later |
| `output_dir` | `C:\Chang\Jobs\rezi\rezi\out` | Where each job's folder goes |
| `cv_dir` | `C:\Chang\Jobs\CV` | Your CVs: `cv.read` reads `.odt` files only here and in `output_dir` |
| `soffice` | `C:\Program Files\LibreOffice\program\soffice.exe` | LibreOffice, for the PDF export |
| `rezi_url` | `https://api.rezi.ai/mcp` | Rezi's MCP server (`https://` only; `http://` only on this machine) |
| `token_file` | `""`: `%LOCALAPPDATA%\assistant\cv\rezi_token.json` | Where the 30-day Rezi token is kept; refused inside the repo |
| `callback_port` | 33418 | The sign-in comes back to `http://127.0.0.1:<port>/callback` |

The worker's table, `[agent]`, takes the same keys as `job_search`'s agent. They are its access list:

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | `false`: the menu only, with no worker and no card |
| `agent_id` | `cv_agent` | Its id in the Hub |
| `workspace` | `C:\Chang\Jobs\rezi\cv_agent` | Its working folder (the only one it writes) |
| `read_dirs` | `C:\Chang\Jobs\CV` | Folders it reads; the output folder is added |
| `tools`, `chrome` | `default`, `true` | Its tools; Claude in Chrome, only for app.rezi.ai |
| `permission_mode` | `acceptEdits` | Sessions start in Manual |
| `transcript` | `cv_agent.jsonl` | Its session's log |

## Code and tests

Everything is in this module's folder, `src/assistant/modules/cv/`:

- Built: `module.py` (the wrapper, its config check, the worker's wiring, the `rezi.*` items, `cv.task`, `cv.read_result`, `cv.read`, `cv.build`, `cv.compare`, `cv.report`), `module.toml` (the defaults), `worker.py` (the worker's prompt and its `[agent]` check), `handoff.py` (the `CV_REQUEST` and `CV_RESULT` lines, `read_jd_file`, `result_view`), `content.py` (`CvContent`, the eight sections), `rezi.py` (`ReziTools`: the `rezi.*` items' work, `check_tools`, the error mapping), `guard.py` (`ResumeGuard`), `rezi_json.py` (`read_rezi`: Rezi's resume JSON as sections; `write_rezi`: sections into Rezi's real format), `order.py` (`SectionOrder`, `wants_masters`), `data.py` (`CvRequest`, `CvResult`, `Round`, `ResumeRef`), `odt.py` (`read_odt`, `OdtWriter`, `LAYOUTS`), `pdf.py` (`PdfExport`, `PageCheck`), `build.py` (`build_cv`: write, export, check, fit to one page), `compare.py` (`FieldCompare`, `Comparison`), `report.py` (`ReportWriter`), `mcp.py` (the Rezi connection: `McpClient`, `TokenStore`, `LoopbackCallback`)
- Planned: the real run end to end (chunk 9, with your yes); after it passes, as a separate step, retiring the separate Rezi helper. Other modules (the job agent) connect through `cv.task` later; cv doesn't change them
- Needs: LibreOffice (`soffice`) for the PDF, the `pypdf` package for the page check, and the `mcp` package for Rezi
- `docs/`: this page, [Architecture](architecture.md), [Tools](tools.md) and `docs.toml`. These are the module's docs; the old plan page `cv_module_workflow.html` in `C:\Chang\Jobs\CV\Recruiters\docs` is left as it was
- `tests/`: its own tests, run with `pytest src/assistant/modules/cv/tests`. `fake_rezi.py` is a fake Rezi: the `mcp` package's own server with an in-memory OAuth sign-in and Rezi's tools in its real format, reached without the network. `test_cv.py` covers the config, order and data; `test_build.py` the one page (one test uses real LibreOffice); `test_compare_report.py` the compare and the report; `test_rezi_mcp.py` the connection; `test_rezi_items.py` the `rezi.*` items and the guard; `test_worker.py` the worker and `cv.read`; `test_handoff.py` the contract, end to end through the Hub with a fake `claude`
