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

Checks one job and gives the text to send to cv_agent with hub.start (the job agent's hand-off)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `company` | string | yes | The job's company |
| `role` | string | yes | The job's title |
| `jd_text` | string | no | The job description as text; or give jd_file |
| `jd_file` | string | no | The job description as a .txt, .md or .html file in cv_dir or output_dir |
| `base_cv` | string | yes | The CV_Test_*.odt you recommend, in cv_dir (read only) |
| `jd_url` | string | no | The posting |
| `degree_first` | boolean | no | Education under Skills (unset: the worker decides from the JD) |
| `target_score` | integer | no | Overrides the config's target |
| `notes` | string | no | Anything else for the worker |

## `cv.read_result`

Reads and checks the CV_RESULT line at the end of a cv_agent task's result

| Argument | Type | Required | What it is |
|---|---|---|---|
| `text` | string | yes | The task's result text |

## `cv.read`

Reads a CV .odt (in the CV folder or the output folder) as its sections, for the worker

| Argument | Type | Required | What it is |
|---|---|---|---|
| `odt` | string | yes | A CV_Test_*.odt in cv_dir or output_dir |

## `cv.build`

Builds the one-page .odt and PDF of a CV in the output folder, fitted and checked

| Argument | Type | Required | What it is |
|---|---|---|---|
| `company` | string | yes | The job's company; names the folder and the files |
| `base_cv` | string | no | A CV_Test_*.odt to build from (read only); or give `sections` |
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
| `edited_odt` | string | no | The edited CV as an .odt (the one cv.build made); or give `edited` |
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
| `result` | object | yes | The job's CvResult: status, stop_reason, pdf_path, odt_path, report_path, rezi_resume, check_copy, target_score, rounds, scores, missing_keywords, keywords_left_out, recommendations, match_ok, compare, one_page, section_order, order_reason, approved_by_user |
| `rounds` | array | no | Each score round: score, added (keywords added), missing (still missing), note; else the result's rounds |
| `compare` | object | no | cv.compare's value from step 6; else the result's compare |
| `notes` | string | no | Anything else for the job agent |
| `target_score` | integer | no | Overrides the config's target |


<!-- tools:end -->

## Notes

Everything above is built: the hand-off (`cv.task`, `cv.read_result`), the nine `rezi.*` items over the Rezi connection (`mcp.py`), and `cv.read`, `cv.build`, `cv.compare` and `cv.report`. The worker `cv_agent` uses them through the door, like any caller. They're tested against a fake Rezi and a fake `claude`; the sign-in, the live tool list and the reads have also run against the real Rezi (chunk 9). How the connection and the guard work: [Architecture](architecture.md#the-rezi-connection-mcppy).

Keyword Targeting, the Rezi Score and the PDF import aren't items: the worker does them in Chrome. A job isn't an item either: it's a task sent to `cv_agent` through the Hub (`hub.start`). `cv.task` gives that task's text, and `cv.read_result` checks its answer.

### The hand-off: `cv.task` and `cv.read_result`

The module stands alone: any caller (later the job agent) reaches the worker in three calls. Nothing else in the app has to change.

1. **`cv.task`** with the job: `company`, `role`, the CV file `base_cv` (an existing `.odt` in `cv_dir`), and the job description as **either** `jd_text` (text) **or** `jd_file` (a `.txt`, `.md` or `.html` file in `cv_dir` or `output_dir`; HTML is read as its visible text). Optional: `jd_url`, `degree_first`, `target_score` (1 to 100) and `notes`, as in `CvRequest` below.
   - It returns `agent_id` (`cv_agent`), `text` and `next`, a reminder of steps 2 and 3. The text is a first line saying what to do, then `CV_REQUEST: <json>` on one line, with the JD text read from the file and `jd_file` naming it.
   - Refused (`invalid_arguments`): both or neither of `jd_text` and `jd_file`, a JD file of another kind, missing, empty or outside those folders, a `base_cv` that isn't an existing `.odt` in `cv_dir`, or a bad field. With the worker off: `not_available`.
2. **`hub.start`** with that `text` and `agent_id`. The worker runs the 8 steps and ends its task with the line `CV_RESULT: <json>`, a `CvResult`.
3. **`cv.read_result`** with the task's result text (from `hub.status`). It returns the new CV and PDF with their metadata:

| Part | What's in it |
|------|--------------|
| `status`, `stop_reason`, `approved_by_user` | `approved` (your yes) or `stopped`, and why |
| `files` | `odt_path`, `pdf_path`, `report_path`, each with `…_exists` (the file is there now) |
| `rezi` | `resume` and `check_copy`: the new Rezi resume and its check copy, name and id each |
| `score` | `target` (the job's, else the config's), `last`, `reached`, and `rounds`: each `{round, score, vs_target, added, missing, note}` |
| `keywords` | `missing`: Rezi's missing keywords at the end; `left_out`: JD terms that aren't on your CVs, so not added |
| `recommendations` | What Rezi or the worker suggests that wasn't done, for example a fact to confirm |
| `page` | `one_page`, `section_order`, `order_reason` |
| `compare` | `cv.compare`'s value from step 6: `match_ok`, `mode`, `checked`, `summary`, `issues` (just `match_ok` if the worker sent none) |

`cv.read_result` refuses (`invalid_arguments`) a text with no line starting `CV_RESULT:`, or one whose line isn't a JSON object or a valid `CvResult`. A result that contradicts itself is not valid: `approved` without your yes, one page, Rezi's match and the PDF; scores that aren't the rounds' scores; or `match_ok` with a compare that found issues.

**Tested end to end through the real Hub** (`tests/test_handoff.py`), with a fake `claude` standing in for the worker. The caller sends `cv.task` with a JD file and the CV's path, then `hub.start` to `cv_agent`. The job arrives intact, and `cv.read_result` on the task's result gives the files, the rounds against the target, the keywords, the recommendations, the one-page check and the compare. The real run with Rezi comes in chunk 9, with your yes.

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

### `cv.read`: an `.odt` as sections

- **Input:** `odt`, a CV `.odt` in `cv_dir` (your CVs) or `output_dir`; any other folder is refused. This is how the worker reads the base CV (step 1) and checks the facts on your other CVs (the truth gate), since its own tools can't read an `.odt`.
- **Returns:** `odt`, `sections` (section → lines, in the `cv.build` form) and `names` (the sections the CV has).
- **Errors:** outside those folders, not an `.odt`, not found, or an unknown heading → `invalid_arguments`.

### `cv.build`: what it does and returns

- **Input:** the base `CV_Test_*.odt` (read only, never changed) or the CV as `sections`. Headings on the CVs map to the eight sections ("Introduction" is Summary, "Additional Experience" joins Experience, "Accomplishments & Publications" is Awards); an unknown heading is refused by name.
- **Output:** `<output_dir>\<date>_<Company>\CV_Test_<Company>.odt` and the `.pdf` next to it, exported with headless LibreOffice. A second build the same day replaces them.
- **The fit:** the roomiest layout that gives one page (10.5 pt and 0.6 in margins, down to 9.5 pt and 0.45 in), then, unless `auto_drop` is false, Publications and then Awards are left out. If it's still over a page, the tightest try comes back with `one_page: false`, and the worker tightens older bullets and builds again.
- **Returns:** `odt_path`, `pdf_path`, `pages`, `one_page`, `problems` (wrong page size, no text, unreadable characters, a heading or the name not found in the PDF's text), `paper`, `layout`, `tries`, `section_order`, `order_reason`, `dropped`, and `text` (the PDF's text, for the compare later).
- **Errors:** bad arguments → `invalid_arguments`; LibreOffice not found → `not_available`; LibreOffice gave no PDF → `failed` (retryable).

### `cv.compare`: step 6, what Rezi read against the edited CV

- **Input:** the edited CV as `edited_odt` (the `.odt` `cv.build` made) or `edited` (sections), and what Rezi read from the imported PDF as `parsed_resume` (`rezi.read_resume`'s `data` for the check copy), `parsed` (sections) or `parsed_text` (one text: Rezi's, or `cv.build`'s `text` as a self-check). One of each.
- **How:** each line is split at `|` and each part checked: found when 90% of its words are there (any order; dashes, quotes, case and punctuation don't count) and every number is.
- **Returns:** `match_ok`, `mode` (`sections` or `text`), `checked` (lines), `summary`, and `issues`, each `{kind, section, line, found_in}`: `missing_section`, `missing`, `moved` (with `found_in`), `extra` (sections only). Every issue is a parse problem: back to step 5.

### `cv.report`: step 8, `report.md`

- **Input:** `company`, `result` (the job's `CvResult`, below), and optionally `role`, `rounds` (each `{score, added, missing, note}`), `compare` (`cv.compare`'s value), `notes`, `target_score` (1 to 100, else the config's).
- **Output:** `report.md` in the folder of `result.pdf_path` (or `odt_path`; with neither, today's job folder), replacing an older one. `rounds` and `compare` default to the result's own, and the target to the result's, else the config's. Sections: Files, Rezi Score (last, target, rounds table), Keywords (still missing, left out), Recommendations, The page (one page, Rezi's match, the compare's issues, section order, your yes), Notes.
- **Returns:** `report_path` and `text` (the report).
- **Refused** (`invalid_arguments`): a result that isn't a valid `CvResult`, a folder outside `output_dir`, scores that aren't the rounds' scores, or `match_ok` with a compare that found issues.

### Request (one per job): `CvRequest` in `data.py`

| Field | Meaning |
|-------|---------|
| `company`, `role` | The job |
| `jd_text` | The job description (from `cv.task`'s `jd_text`, or read from its `jd_file`) |
| `jd_file` | Optional: the file the JD was read from |
| `base_cv` | Path to the `CV_Test_*.odt` to start from, in `cv_dir` (read only; must be an `.odt`) |
| `jd_url` | Optional: the posting |
| `degree_first` | Optional: put Education under Skills. Unset: a first guess from the JD (`order.wants_masters`), which the worker may change |
| `target_score` | Optional, 1 to 100: overrides the config's 90 |
| `notes` | Optional: anything from the caller |

### Result: `CvResult` in `data.py`

| Field | Meaning |
|-------|---------|
| `status`, `stop_reason` | `approved` or `stopped`, and why it stopped (required when stopped) |
| `pdf_path` | The exact PDF that passed Rezi's check |
| `odt_path` | The `.odt` it came from |
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
| `approved_by_user` | Your yes at step 7 |

Scores that aren't the rounds' scores, and `match_ok` with a compare that found issues, are refused. `approved` is refused unless `approved_by_user`, `one_page`, `match_ok` and `pdf_path` are all set.
