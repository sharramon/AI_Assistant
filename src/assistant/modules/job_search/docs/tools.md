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


<!-- tools:end -->
