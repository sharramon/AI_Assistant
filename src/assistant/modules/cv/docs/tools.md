# cv: tools

The `cv` module's menu. What it is: [Overview](README.md). How the items fit together: [Architecture](architecture.md).

<!-- tools:start (generated from the module's menu by scripts/build_docs.py; don't edit) -->

Its menu, as the main AI sees it (`modules.menu`). Every item is called with `modules.use_item`.

## `rezi.sign_in`

Signs in to Rezi in the browser (OAuth) and keeps the 30-day token; lists Rezi's tools

| Argument | Type | Required | What it is |
|---|---|---|---|
| `force` | boolean | no | Sign in again even with a valid token (default false) |
| `timeout` | integer | no | Seconds to wait for the browser (default 300) |

## `rezi.status`

Signed in to Rezi or not, the token's days left, the resumes made here (never connects)

No arguments.

## `rezi.list_resumes`

Your Rezi resumes, most recently changed first

No arguments.

## `rezi.read_resume`

One Rezi resume's content, also as the CV's sections

| Argument | Type | Required | What it is |
|---|---|---|---|
| `resume_id` | string | yes | The resume's id (from rezi.list_resumes) |
| `extra` | object | no | More arguments for Rezi's tool, passed as they are (if its live schema needs them: see rezi.sign_in's `check`) |

## `rezi.get_resume_format`

The sections and fields Rezi's resume format has, for a write

No arguments.

## `rezi.write_resume`

Makes a new Rezi resume, or updates one this module made; every other is refused

| Argument | Type | Required | What it is |
|---|---|---|---|
| `sections` | object | no | The CV as sections (cv.read's), written into Rezi's format here; or give resume |
| `name` | string | no | With sections: the resume's name, e.g. "<Company> – <Role>" |
| `job_title` | string | no | With sections: the job's title (Rezi's jobTitle) |
| `job_company` | string | no | With sections: the job's company (Rezi's jobCompany) |
| `jd_text` | string | no | With sections: the job description (Rezi's jobDescription) |
| `resume` | object | no | Or the whole resume object in Rezi's format (name, jobTitle, jobCompany, jobDescription, data: see rezi.get_resume_format); no id in here |
| `resume_id` | string | no | Only to update a resume this module made; leave out to make a new one |
| `verify` | boolean | no | Read the resume back after the write (default true) |

## `rezi.generate_keywords`

Rezi's keywords for the job description saved on a resume this module made

| Argument | Type | Required | What it is |
|---|---|---|---|
| `resume_id` | string | yes | A resume made here, written with the JD (jd_text) |

## `rezi.search_jobs`

Searches Rezi's job listings by role and location

| Argument | Type | Required | What it is |
|---|---|---|---|
| `role` | string | yes | The job title to search for |
| `location` | string | no | Where |
| `extra` | object | no | More arguments for Rezi's tool, passed as they are (if its live schema needs them: see rezi.sign_in's `check`) |

## `rezi.get_job_details`

One job's full details from rezi.search_jobs

| Argument | Type | Required | What it is |
|---|---|---|---|
| `job_id` | string | yes | A job's id from rezi.search_jobs |
| `extra` | object | no | More arguments for Rezi's tool, passed as they are (if its live schema needs them: see rezi.sign_in's `check`) |

## `cv.task`

Checks one job (the JD as text, the base CV as any .pdf) and starts cv_agent on it as your child task; its end and the user's Submit go out as cv's events (cv.job_finished, cv.job_submitted), which your module turns into messages for you (the job agent's hand-off)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `company` | string | yes | The job's company |
| `role` | string | yes | The job's title |
| `jd_text` | string | no | The job description as text; or give jd_file |
| `jd_file` | string | no | The job description as a .txt, .md or .html file in cv_dir, output_dir or work_dir (read into jd_text) |
| `base_cv` | string | yes | The base CV: any .pdf file, its path used as given (read only; it must exist; a non-.pdf such as an .odt is refused) |
| `jd_url` | string | no | The posting |
| `degree_first` | boolean | no | Education under Skills (unset: the worker decides from the JD) |
| `target_score` | integer | no | Overrides the config's target |
| `notes` | string | no | Anything else for the worker |
| `tool` | string | no | The CV Tool's pick (unset: the user picks Internal or Rezi in its tab 2) |

## `cv.read_result`

Reads and checks the CV_RESULT line at the end of a cv_agent task's result: give task_id (cv reads the ended task's whole result) or the result's text, one of them

| Argument | Type | Required | What it is |
|---|---|---|---|
| `task_id` | string | no | The cv_agent task's id (your child task) |
| `text` | string | no | The task's result text |

## `cv.open_tool`

Opens a job the job start set up (its folder) in the CV Tool, starting the app if needed; gives the app's job_id. Call it only when the user tells you to start

| Argument | Type | Required | What it is |
|---|---|---|---|
| `job_dir` | string | yes | The job's folder (CV_JOB's work_dir) |

## `cv.tool_status`

One CV Tool job: the pick (Internal or Rezi, empty: not picked yet), the CV's content and text, a pending Rezi request, the loop (score, issues, rounds) and Submit's state

| Argument | Type | Required | What it is |
|---|---|---|---|
| `job_id` | string | yes | The CV Tool's job id (cv.open_tool's) |

## `cv.tool_round`

Sends one round to the CV Tool: the edited content (prints the local PDF) and/or the score read for it; gives the PDF, its text under 10 pt, the loop and the rules checklist

| Argument | Type | Required | What it is |
|---|---|---|---|
| `job_id` | string | yes | The CV Tool's job id (cv.open_tool's) |
| `content` | object | no | The whole CV in the app's shape (cv.tool_status's content, edited): name, contact, summary, skills [[label, text]], experience [{title, company, dates, bullets}], education [{degree, detail}], awards, publications, education_first. Prints a new local PDF |
| `export` | boolean | no | Print a new local PDF (default: true when content is given) |
| `score` | integer | no | The ATS score read for this PDF |
| `categories` | object | no | The score's categories, name -> score |
| `matched` | array | no | Matched keywords |
| `missing` | array | no | Missing keywords |
| `issues` | array | no | The scorer's biggest issues |
| `changes` | string | no | What changed in this round |
| `note` | string | no | A note for the round |
| `request_id` | string | no | The pending Rezi request this round answers (cv.tool_status) |
| `tool` | string | no | Who scored it (default the job's pick) |

## `cv.tool_draft`

The Internal First Draft, with no agent: the proposals (Skills reordered by JD rank, backed JD terms to add, terms that need the user's yes); with apply, the reorder and the named backed terms are put in and an Internal round scores it

| Argument | Type | Required | What it is |
|---|---|---|---|
| `job_id` | string | yes | The CV Tool's job id (cv.open_tool's) |
| `apply` | boolean | no | Put the proposals in and score (default false: proposals only) |
| `reorder` | boolean | no | With apply: reorder the Skills items (default true) |
| `add` | array | no | With apply: backed terms from the proposals' add list to put in (a term not on the CVs is refused: it needs the user's yes in the app) |

## `cv.tool_internal_round`

One Internal ATS Loop round, with no agent: prints the current CV, scores it with the Internal estimate and gives the loop with the matched and missing keywords

| Argument | Type | Required | What it is |
|---|---|---|---|
| `job_id` | string | yes | The CV Tool's job id (cv.open_tool's) |

## `cv.check_fonts`

The CV Tool job's current PDF: any text under 10 pt (measured from the PDF; a warning)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `job_id` | string | yes | The CV Tool's job id (cv.open_tool's) |

## `cv.tool_result`

The user's Submit in the CV Tool: result.json once they submitted (ready), never refused; small_text (text under 10 pt) is a warning only. The module already passed the Submit on (cv.job_submitted) when the user submitted

| Argument | Type | Required | What it is |
|---|---|---|---|
| `job_id` | string | yes | The CV Tool's job id (cv.open_tool's) |

## `cv.read`

Reads a CV PDF (the base CV's copy in the job's folder, a draft or another of your CVs) as its sections, with the read check: every word placed, or the unplaced text to ask you about

| Argument | Type | Required | What it is |
|---|---|---|---|
| `pdf` | string | yes | The path of any existing .pdf, used as given (a non-.pdf, an .odt too, is refused) |

## `cv.build`

Builds and exports the one-page PDF of a CV into the job's folder (job_dir), fitted and checked; no .odt comes out

| Argument | Type | Required | What it is |
|---|---|---|---|
| `company` | string | yes | The job's company; names the folder and the files |
| `base_cv` | string | no | Any .pdf to build from (read only; an .odt is refused); or give `sections` |
| `job_dir` | string | no | The job's folder (CV_JOB's work_dir): the final PDF is exported there as <cv_prefix><Company>.pdf. Unset: <output_dir>/<date>_<Company>/ |
| `sections` | object | no | The CV as section -> list of lines (contact, summary, skills, experience, projects, education, awards, publications); `• ` starts a bullet, `left \| dates` an entry line; the first contact line is the name |
| `jd_text` | string | no | The job description: a master's in it puts Education under Skills |
| `degree_first` | boolean | no | Education under Skills (overrides the guess from jd_text) |
| `drop` | integer | no | Sections of the drop list (Publications, then Awards) left out from the start |
| `auto_drop` | boolean | no | Leave out more of the drop list if it's still over a page (default true) |
| `paper` | string | no | Overrides the config's paper |

## `cv.compare`

Compares what Rezi read from the PDF with the edited CV: same content or the issues

| Argument | Type | Required | What it is |
|---|---|---|---|
| `edited_pdf` | string | no | The edited CV as a PDF (the one cv.build made); or give `edited` |
| `edited` | object | no | The edited CV as section -> list of lines, as for cv.build |
| `parsed` | object | no | What Rezi read from the imported PDF, as section -> list of lines, as for cv.build; or give `parsed_text` |
| `parsed_text` | string | no | What was read as one text (cv.build's `text`, or copied from Rezi): checks only for missing lines |
| `parsed_resume` | object | no | What was read as Rezi's resume JSON (rezi.read_resume's `data` for the check copy), read into sections here |

## `cv.report`

Writes report.md next to the job's PDF: result, score rounds, keywords left out, the compare

| Argument | Type | Required | What it is |
|---|---|---|---|
| `company` | string | yes | The job's company |
| `role` | string | no | The job's title |
| `result` | object | yes | The job's CvResult: status, stop_reason, pdf_path, report_path, rezi_resume, check_copy, target_score, rounds, scores, missing_keywords, keywords_left_out, recommendations, match_ok, compare, one_page, section_order, order_reason, approved_by_user |
| `rounds` | array | no | Each score round: score, added (keywords added), missing (still missing), note; else the result's rounds |
| `compare` | object | no | cv.compare's value from step 6; else the result's compare |
| `notes` | string | no | Anything else for the job agent |
| `target_score` | integer | no | Overrides the config's target |


<!-- tools:end -->

## Notes

Everything above is built: the hand-off (`cv.task`, `cv.read_result`), the nine `rezi.*` items over the Rezi connection (`mcp.py`), and `cv.read`, `cv.build`, `cv.compare` and `cv.report`. The worker `cv_agent` uses them through the door, like any caller. They're tested against a fake Rezi and a fake `claude`; the sign-in, the live tool list and the reads have also run against the real Rezi (chunk 9). How the connection and the guard work: [Architecture](architecture.md#the-rezi-connection-mcppy).

**The interface is PDF in, PDF out** (since 2026-11-09): the job description comes in as text (`jd_text`, or a `.txt`, `.md` or `.html` file), the base CV as any `.pdf`, and the tailored CV goes out as a one-page PDF in the job's folder. Every `cv.*` item refuses an `.odt`. The module still writes an `.odt` on the way to the PDF, but only in a temporary folder that's removed after the build.

Keyword Targeting, the Rezi Score and the PDF import aren't items: the worker does them in Chrome. A job isn't an item either: it's a task on `cv_agent` that `cv.task` starts through the Hub (`StartTask`, as the caller's child task), and `cv.read_result` checks its answer.

### The hand-off: `cv.task` and `cv.read_result`

The module stands alone: a caller in `hand_off.callers` (the job agent, the Main Assistant) hands a job to the worker with one call, and the result comes back to it as a message at your Submit. Nothing else in the app has to change.

1. **`cv.task`** with the job: `company`, `role`, the CV file `base_cv` (the path of any existing `.pdf`, used as given: no name or folder rule since 2026-11-13), and the job description as **either** `jd_text` (text) **or** `jd_file` (a `.txt`, `.md` or `.html` file in `cv_dir`, `output_dir` or `work_dir`; HTML is read as its visible text). Optional: `jd_url`, `degree_first`, `target_score` (1 to 100) and `notes`, as in `CvRequest` below.
   - It starts `cv_agent` on the job itself (`StartTask`, with the caller's newest open task as parent, so the caller may `hub.send` to it as its child) and returns `agent_id` (`cv_agent`), `task_id`, `text` and `next` (nothing more to call: end your turn; when the task ends cv publishes `cv.job_finished` and your module wakes you; the whole result: `cv.read_result task_id=…`). The `StartTask` has `tell_parent=False`, so the Hub sends no second message about the end. At the user's Submit cv publishes `cv.job_submitted`, and your module wakes you again with the PDF and the score. The text is a first line saying what to do, then `CV_REQUEST: <json>` on one line, with the JD text read from the file and `jd_file` naming it, and the caller as `reply_to`.
   - Refused (`invalid_arguments`): both or neither of `jd_text` and `jd_file`, a JD file of another kind, missing, empty or outside those folders, a `base_cv` that isn't a `.pdf` ("base_cv must be a .pdf file, not <name>", an `.odt` too) or isn't there ("base_cv not found: <path>"), or a bad field. With the worker off: `not_available`. With `cv_agent` busy on another job: the Hub's refusal, naming that job and who it's for ("it's on the CV for <role> at <company> (task <id>, for <asker>)"), and "Nothing was queued; try again when it's free".
2. **The work.** The worker runs the CV Tool's steps and ends its task before your Submit with the line `CV_RESULT: <json>`, a `CvResult` with status `ready` (or `stopped`). At your Submit in the CV Tool, the module sends the result to the caller (`reply_to`) with [`DeliverMessage`](../../../../../docs/api/agents.md#delivermessage): into its open task, or a new task, never into a turn ([Architecture](architecture.md#the-hand-off-handoffpy)).
3. **`cv.read_result`** with the task's id, `task_id` (cv fetches the ended task's whole result itself), or its result text, `text`: one of them. A `task_id` it can't find, or not a `cv_agent` task, is refused (`invalid_arguments`); a task with no result yet is `not_available`. It returns the new CV and PDF with their metadata:

| Part | What's in it |
|------|--------------|
| `status`, `stop_reason`, `approved_by_user` | `ready` (everything but your Submit, which reaches the caller as the cv module's message), `approved` (older results: your yes) or `stopped`, and why |
| `files` | `pdf_path` and `report_path`, each with `…_exists` (the file is there now); no `.odt` comes out |
| `rezi` | `resume` and `check_copy`: the new Rezi resume and its check copy, name and id each |
| `score` | `target` (the job's, else the config's), `last`, `reached`, and `rounds`: each `{round, score, vs_target, added, missing, note}` |
| `keywords` | `missing`: Rezi's missing keywords at the end; `left_out`: JD terms that aren't on your CVs, so not added |
| `recommendations` | What Rezi or the worker suggests that wasn't done, for example a fact to confirm |
| `page` | `one_page`, `section_order`, `order_reason` |
| `compare` | `cv.compare`'s value from step 6: `match_ok`, `mode`, `checked`, `summary`, `issues` (just `match_ok` if the worker sent none) |

`cv.read_result` refuses (`invalid_arguments`) a text with no line starting `CV_RESULT:`, or one whose line isn't a JSON object or a valid `CvResult`. A result that contradicts itself is not valid: `ready` without one page and the PDF, or with `approved_by_user`; `approved` without your yes, one page and the PDF; scores that aren't the rounds' scores; or `match_ok` with a compare that found issues.

**Tested end to end through the real Hub** (`tests/test_handoff.py`), with a fake `claude` standing in for the worker. The caller sends `cv.task` with a JD file and the CV's path, which starts `cv_agent` (no coordinator in between). The job arrives intact, and `cv.read_result` on the task's result gives the files, the rounds against the target, the keywords, the recommendations, the one-page check and the compare. The real run with Rezi comes in chunk 9, with your yes.

### The `rezi.*` items

- **Errors, for every item:** not signed in, or the token ran out → `not_available` (use `rezi.sign_in`); a write the guard refuses → `invalid_arguments`; Rezi's error → `failed`; no answer → `failed` (retryable).
- **Answers:** Rezi's answer comes back as `data` when it's data, else as `text`.
- **`extra`:** `rezi.read_resume`, `rezi.search_jobs` and `rezi.get_job_details` pass any `extra` arguments through, for whatever the live tool needs beyond the ones named.
- **`rezi.sign_in`:** opens the browser for Rezi's sign-in (OAuth with PKCE) and keeps the 30-day token. With a valid token no browser opens, unless `force`. `timeout` is 30 to 900 seconds (default 300). It then lists Rezi's live tools, returning `tools`, `schemas` (the live arguments of the tools the items use) and `check`: `{ok, missing, new, arguments}` against the seven tools and arguments the items use. If the tool list fails after the sign-in, the sign-in still counts (`tools_error`). A sign-in that waits on the browser goes on in the background: after 20 seconds the item answers `signing_in` with `sign_in: {state: waiting}`, and `rezi.status` reports how it ends. A second call waits on the same sign-in; no second browser opens.
- **`rezi.status`:** signed in or not, the token's days left, `created` (the resumes made here) and `sign_in` (none, waiting, done or failed). It never connects.
- **`rezi.list_resumes`:** Rezi's list, plus `created`. It always asks for up to 200 resumes, so the guard sees them all.
- **`rezi.read_resume`:** the resume, `created_here`, and `sections` (the CV's eight sections) with `skipped` (keys it couldn't place). If it can't read any section: `sections: null` and `sections_error`.
- **`rezi.get_resume_format`:** the format Rezi expects for `rezi.write_resume`.
- **`rezi.write_resume`:**
  - Give either `sections` (`cv.read`'s form, with `name`, `job_title`, `job_company` and `jd_text`), which the module writes into Rezi's format, or a whole `resume` object. With `sections` it also returns `left_out`: lines Rezi's format has no place for (the contact headline).
  - With no `resume_id`, it makes a new resume. Its id comes from Rezi's answer, or else the one new id in the resume list, and the guard remembers it.
  - With a `resume_id`, it updates that resume only if this module made it. Every other resume is refused, and so is an id hidden in the fields.
  - It returns `created`, `resume_id`, `answer`, a `warning` when the new id wasn't found or was an existing resume, and `read_back` (unless `verify` is false), which is `rezi.read_resume`'s answer, with `sections`.
  - Writes run one at a time.
- **`rezi.generate_keywords`** (`resume_id`): Rezi's keywords for the job description saved on the resume. Only for a resume this module made, since Rezi may save on it.
- **Rezi's real format** (seen live): a resume is `{name, jobTitle, jobCompany, jobDescription, data}`. In `data`, `contact` and `summary` are plain, and each list section (`experience`, `education`, `skills`, …) is keyed by an id, with `index` for the order and `hide`. The module reads it exactly: in `index` order, hidden entries skipped, military, research, involvement and teaching read as experience, certifications as awards, coursework as education. An update reuses the resume's ids in order and hides the extra old entries.
- **Never used:** Rezi's `auto_apply_job`, `duplicate_resume` and the cover-letter tools.
- **`rezi.search_jobs`** (`role`, optional `location`) and **`rezi.get_job_details`** (`job_id`): Rezi's job listings.

### `cv.read`: a CV PDF as sections, with the read check

- **Input:** `pdf`, the path of any existing `.pdf`, used as given (since 2026-11-13; before, only a `CV_Test_*.pdf` in `work_dir`, `cv_dir` or `output_dir`). A non-`.pdf`, an `.odt` too, and a missing file are refused. This is how the worker reads the base CV's copy (step 1) and checks the facts on your other CVs (the truth gate).
- **How** (`pdf_read.py`): pypdf's layout reader gives each piece of text with its place and size. Pieces on one baseline make a line (a wide gap is the entry's ` | ` before the dates), a bullet glyph makes a `• ` line, small caps are lower-cased, and a wrapped line joins the one above. The headings map to the eight sections as before ("Introduction" is Summary, "Additional Experience" joins Experience, "Accomplishments & Publications" is Awards).
- **The read check:** every word of the PDF's plain text must be in what was read. A big heading it doesn't know, the text under it, and any word not placed are listed in `unplaced`.
- **Returns:** `pdf`, `sections` (section → lines, in the `cv.build` form), `names`, `pages`, `complete` and `unplaced`. When `complete` is false it adds `next`: stop and ask you with NEED:, naming the unplaced text.
- **Errors:** outside those folders, an `.odt` ("an .odt isn't read; give the CV_Test_*.pdf"), not a `.pdf`, not found, or not a readable PDF → `invalid_arguments`; pypdf's layout reader changed → `not_available`.

### `cv.build`: what it does and returns

- **Input:** the base CV as any `.pdf` (read only, never changed; refused unless every word is placed) or the CV as `sections`, and `job_dir`, the job's folder (CV_JOB's `work_dir`).
- **Output:** the PDF only, exported with headless LibreOffice. With `job_dir` (a folder inside `work_dir` that exists): `<job_dir>\CV_Test_<Company>.pdf`, or `…_tailored.pdf` when that name is the job's copy of its base CV (from `job_start.json`), so the copy is never overwritten. Without `job_dir`: `<output_dir>\<date>_<Company>\CV_Test_<Company>.pdf`. The `.odt` and LibreOffice's export are made in a temporary folder outside the agent's folders and removed; only the checked PDF is copied out. A second build the same day replaces the PDF.
- **The fit:** the roomiest layout that gives one page (10.5 pt and 0.6 in margins, down to 9.5 pt and 0.45 in), then, unless `auto_drop` is false, Publications and then Awards are left out. If it's still over a page, the tightest try comes back with `one_page: false`, and the worker tightens older bullets and builds again.
- **Returns:** `pdf_path`, `pages`, `one_page`, `problems` (wrong page size, no text, unreadable characters, a heading or the name not found in the PDF's text), `paper`, `layout`, `tries`, `section_order`, `order_reason`, `dropped`, and `text` (the PDF's text, for the compare later).
- **Errors:** bad arguments (an `.odt`, a `job_dir` outside `work_dir` or missing, text the read check can't place) → `invalid_arguments`; LibreOffice not found → `not_available`; LibreOffice gave no PDF → `failed` (retryable).

### `cv.compare`: step 6, what Rezi read against the edited CV

- **Input:** the edited CV as `edited_pdf` (the PDF `cv.build` made, in `work_dir`, `output_dir` or `cv_dir`) or `edited` (sections), and what Rezi read from the imported PDF as `parsed_resume` (`rezi.read_resume`'s `data` for the check copy), `parsed` (sections) or `parsed_text` (one text: Rezi's, or `cv.build`'s `text` as a self-check). One of each.
- **How:** each line is split at `|` and each part checked: found when 90% of its words are there (any order; dashes, quotes, case and punctuation don't count) and every number is.
- **Returns:** `match_ok`, `mode` (`sections` or `text`), `checked` (lines), `summary`, and `issues`, each `{kind, section, line, found_in}`: `missing_section`, `missing`, `moved` (with `found_in`), `extra` (sections only). Every issue is a parse problem: back to step 5.

### `cv.report`: step 8, `report.md`

- **Input:** `company`, `result` (the job's `CvResult`, below), and optionally `role`, `rounds` (each `{score, added, missing, note}`), `compare` (`cv.compare`'s value), `notes`, `target_score` (1 to 100, else the config's).
- **Output:** `report.md` in the folder of `result.pdf_path` (the job's folder in `work_dir`, or a folder in `output_dir`; without a `pdf_path`, today's folder in `output_dir`), replacing an older one. `rounds` and `compare` default to the result's own, and the target to the result's, else the config's. Sections: Files, Rezi Score (last, target, rounds table), Keywords (still missing, left out), Recommendations, The page (one page, Rezi's match, the compare's issues, section order, your yes), Notes.
- **Returns:** `report_path` and `text` (the report).
- **Refused** (`invalid_arguments`): a result that isn't a valid `CvResult` (one with the old `odt_path` too), a folder outside `output_dir` and `work_dir`, scores that aren't the rounds' scores, or `match_ok` with a compare that found issues.

### The CV Tool: `cv.open_tool`, `cv.tool_status`, `cv.tool_round`, `cv.check_fonts`, `cv.tool_result`

The module's link to its UI half, the CV Tool app (`src/cv_tool`, `python -m cv_tool` on `127.0.0.1:8771`). Each item starts the app if it isn't running (`CompanionApp.ensure_running`, no window) and uses only its JSON API. Built and tested, live with the `cv` reload.

| Item | Calls | Returns |
|---|---|---|
| `cv.open_tool(job_dir)` | Reads the job's `job_start.json`, the JD and the base CV's copy (`read_pdf` → the app's content shape); `POST /api/job/import`, then `POST /api/window` | `job_id`, `tool` (the request's pick, or `""`: the user picks in tab 2), `window` (opened or raised), `unplaced` (text the reader couldn't place: ask), `left_out` (sections the app has no place for, e.g. projects) |
| `cv.tool_status(job_id)` | `GET /api/job/status` | `tool`, `content` (the app's shape), `text`, a pending `rezi_request`, `loop` (score, issues, rounds), `ready` (submitted) |
| `cv.tool_round(job_id, …)` | `POST /api/round` | `pdf` (the new local PDF), `small_text` (text under 10 pt), `state`, `rules` (the checklist: each rule file and its first rule) |
| `cv.check_fonts(job_id)` | `POST /api/round` with nothing in it | the current `pdf` and its `small_text` |
| `cv.tool_draft(job_id, apply?, reorder?, add?)` | `POST /api/draft/internal`; with `apply`, `POST /api/draft/internal/apply` | The Internal First Draft with no agent: the proposals (`reorder`, `add`: backed terms, `ask`: terms that need your yes, `declined`, `matched`); with `apply`, the Skills reorder and the named backed terms put in, then an Internal round (`state`). A term not on your CVs is refused here: it needs your yes in the app |
| `cv.tool_internal_round(job_id)` | `POST /api/loop/internal` | One Internal round with no agent: the PDF printed, the Internal score, and the loop with the matched and missing keywords (`state.keywords`, from that round) |
| `cv.tool_result(job_id)` | `GET /api/job/result` | `{ready: false}` until your Submit; then `result` (`result.json`: `pdf_path` `CV_Test_<Company>_final.pdf`, the rounds, the keywords) |

- **`cv.tool_round`'s arguments:** `content` (the whole CV in the app's shape: `name`, `contact`, `summary`, `skills` `[[label, text]]`, `experience` `[{title, company, dates, bullets}]`, `education` `[{degree, detail}]`, `awards`, `publications`, `education_first`) prints a new local PDF (`export`, default true with content). With the Internal pick and no score given, the app scores it. The score fields are `score`, `categories`, `matched`, `missing`, `issues`, `changes` and `note`, plus `request_id` when they answer a pending Rezi request. They're saved as a round. Rezi's PDF is never taken.
- **The Internal path needs no agent:** `cv.open_tool`, `cv.tool_draft` (with `apply`), `cv.tool_internal_round`, `cv.check_fonts` and `cv.tool_result` run a whole Internal job through the module; rewording bullets and the Summary is still an editor's work (yours in the app, or cv_agent's with `cv.tool_round`).
- **The truth check** (the app's "not on your CVs" flags) reads every `CV_Test_*` `.pdf`, `.odt` and `.docx` in your CV folder, plus the confirmed facts' `words` and each word of their `phrases`; a hyphenated term like "sim-to-real" is backed when every part is. It never reads the facts' `notes` or a job's notes: those also say what not to claim. (Fixed 2026-11-09: before, it read only `.odt` CVs and `words`, so "modular" and "sim-to-real" were flagged.)
- **9 pt, a warning:** whenever `small_text` isn't empty, the answer's `next` says to shorten the wording or ask, never shrink the font. A Submit is never refused: `cv.tool_result` returns a submitted PDF with text under 9 pt with its `small_text` as a warning.
- **Refused:** `job_dir` outside the work folder, or with no readable `job_start.json` → `invalid_arguments`. The app answering an error → `failed` ("the CV Tool says …"). The app not starting or not answering → `not_available`.

### Request (one per job): `CvRequest` in `data.py`

| Field | Meaning |
|-------|---------|
| `company`, `role` | The job |
| `jd_text` | The job description (from `cv.task`'s `jd_text`, or read from its `jd_file`) |
| `jd_file` | Optional: the file the JD was read from |
| `base_cv` | Path to any `.pdf` to start from, used as given, in any folder and with any name (read only; a non-`.pdf`, an `.odt` too, is refused; `cv.task` and the job start also refuse a missing or 0-byte file) |
| `jd_url` | Optional: the posting |
| `degree_first` | Optional: put Education under Skills. Unset: a first guess from the JD (`order.wants_masters`), which the worker may change |
| `target_score` | Optional, 1 to 100: overrides the config's 90 |
| `notes` | Optional: anything from the caller |
| `tool` | Optional: the CV Tool's pick, `Internal` or `Rezi`. Unset: you pick it in the CV Tool's tab 2 |

### Result: `CvResult` in `data.py`

| Field | Meaning |
|-------|---------|
| `status`, `stop_reason` | `ready` (cv_agent's end: everything but your Submit), `approved` (older results) or `stopped`, and why it stopped (required when stopped) |
| `pdf_path` | With `ready`, the last local PDF from `cv.tool_round` (your Submit copies it to `CV_Test_<Company>_final.pdf`, named in the cv module's message); on the old path, the one `cv.build` exported (there's no `odt_path`: a result with one is refused) |
| `report_path` | `cv.report`'s `report.md` |
| `rezi_resume`, `check_copy` | The new Rezi resume and its check copy: name and id each |
| `target_score` | The score aimed at (1 to 100); unset: the config's |
| `rounds` | Each score round: `score`, `added` (true keywords added), `missing` (still missing), `note` |
| `scores` | The Rezi Score after each round (0 to 100), filled from `rounds` when left out; `score` is the last one |
| `missing_keywords` | Rezi's missing keywords at the end (unset: the last round's `missing`) |
| `keywords_left_out` | Terms you don't have, so not added |
| `recommendations` | Suggestions not acted on |
| `match_ok`, `compare` | Rezi read the same content; `cv.compare`'s value from step 6 |
| `one_page` | It's one page |
| `section_order`, `order_reason` | The order used, and why |
| `approved_by_user` | Your yes on the old path (step 7); false with `ready`, since your Submit comes after |

Scores that aren't the rounds' scores, and `match_ok` with a compare that found issues, are refused. `ready` is refused unless `one_page` and `pdf_path` are set, and with `approved_by_user`. `approved` is refused unless `approved_by_user`, `one_page` and `pdf_path` are all set. Rezi's match (`match_ok`) is no longer needed: the CV Tool's own page is the final PDF, with no Rezi import check.
