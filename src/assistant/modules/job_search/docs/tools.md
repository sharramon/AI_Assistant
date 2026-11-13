# job_search: tools

<!-- tools:start (generated from the module's menu by scripts/build_docs.py; don't edit) -->

Its menu, as the main AI sees it (`modules.menu`). Every item is called with `modules.use_item`.

## `job.open_ui`

Opens the job UI (Tracker, Job stack, Live search, Keywords) in its own window on the Tracker page, every time: starts its local server first if it isn't answering, and closes the job UI window already open, so there's only one

No arguments.

## `job.search`

Start a job search; answers at once, and the result reaches you as a note at your next turn (the runner is a stub for now)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `days` | integer | no |  |

## `job.tailor_cv`

Hands one job's CV to cv (only the job agent): answers at once; the job module turns cv on (cv_agent's access card is asked then), sends it the base PDF and the JD, and tells you the outcome as a message. cv's end and the user's Submit come later as messages too

| Argument | Type | Required | What it is |
|---|---|---|---|
| `company` | string | yes | The job's company |
| `role` | string | yes | The job's title |
| `base_cv` | string | yes | The chosen base CV, a .pdf (its path) |
| `jd_text` | string | no | The job description as text; or give jd_file |
| `jd_file` | string | no | The job description as a file cv may read |
| `jd_url` | string | no | The posting |
| `degree_first` | boolean | no | Education under Skills (unset: cv's worker decides) |
| `target_score` | integer | no | The ATS score to reach |
| `notes` | string | no | Anything else for cv's worker |


<!-- tools:end -->
