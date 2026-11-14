# cv result fixes: an empty tool pick, and a clearer "no valid CV_RESULT"

**Status:** built (waiting on you), 2026-11-14. Approved and built: all four fixes, with the tests below (cv 168 passed; full suite 1004 passed; ruff clean). Left: the `cv` reload (asked first) and the hand checks at the end. Built as planned, with one wording change: the messages say "CV_RESULT line", without the marker's colon. The module's tools page (`cv/docs/tools.md`) describes the new refusals and summaries.

## What happened

In the job and cv smoke test (fake job NonexistentTestCo / Smoke Test Engineer, cv task `6d360b37`), the job agent heard "No valid CV_RESULT line in its last message" in `cv.job_finished`, and `cv.read_result task_id=6d360b37` failed with:

```
1 validation error for CvResult
tool
  Input should be 'Internal' or 'Rezi' [type=literal_error, input_value='', input_type=str]
```

The job folder held only the base CV copy, the JD and `job_start.json`. That part is right: the request's notes told cv_agent to stop at once, with no CV Tool, so no CV was meant to come out.

## The cause: one bug, not two

cv_agent **did** end with a CV_RESULT line (`logs/2026-11-13_23-52-50_run-the-check/cv_agent.jsonl`, its only reply):

```
CV_RESULT: {"status": "stopped", "stop_reason": "Smoke test (fake job): ...", "tool": "", "target_score": null, "rounds": [], ..., "one_page": false, "section_order": ["summary", "skills", "experience", "education", "awards", "publications"], ...}
```

The line is well formed, and everything in it is valid except `"tool": ""`. The two symptoms come from that one field:

1. **`CvResult.tool`** (`data.py`) accepts only `"Internal"`, `"Rezi"` or null. An empty string is refused. The fallback in `handoff.read_result` (use the request's pick when the line names none) didn't help, because this request named no pick.
2. **"No valid CV_RESULT line"** comes from `handoff.job_finished`. It catches the same `ValueError` and reports it as if the line were missing. So the job agent was told the line wasn't there, when it was there and only one field was wrong.

**Why cv_agent wrote `""`:** its instructions (`worker.py`) describe the line for a `ready` result: "tool (the pick: Internal or Rezi)". For a stopped job they only say "ends the same way". Nothing was picked, so it wrote an empty pick. The CV Tool does the same: its own job file and `cv.tool_status` use `""` for "not picked yet" (`cvlib.py`). This is the same kind of bug as the 13th's `rezi_resume: ""`, which was fixed for that one field only.

## The fixes (recommended)

1. **Read an empty pick as no pick (`data.py`).** A `mode="before"` validator on `tool`, like `_no_resume`: `""` or whitespace becomes None. A `ready` Internal result still needs nothing from Rezi. A Rezi pick still needs its `rezi_resume`. The request's pick still fills in a missing one.
2. **A clear refusal for a wrong pick.** Any other value (`"rezi"`, `"Both"`) is refused with one plain line: `tool must be "Internal" or "Rezi", or left out when nothing was picked (got "Both")`. Today it's pydantic's three-line dump. For the other fields, `read_result` turns a `ValidationError` into one short line per field (`field: message`).
3. **Say which failure it was (`handoff.job_finished` / `finish_summary`).** If there's no line: "No CV_RESULT line in its last message." If there's a line that isn't valid: "Its CV_RESULT line isn't valid: \<the reason\>. cv.read_result task_id=… shows it." The job agent then knows the line is there and what to report.
4. **cv_agent's instructions (`worker.py`).** One added sentence: "Leave tool out when nothing was picked (a job stopped before step 2); never write an empty string." The code fix (1) makes this a nice-to-have. It keeps the lines tidy without relying on the agent.

The answer to "end check or instructions?" is both, with the code doing the work. Fixes 1 to 3 make the reader tolerant and clear, so a slip like this can't hide a result again. Fix 4 makes the slip less likely.

**Not changed:** `ToolPick` stays `Internal | Rezi`, and the CV Tool's `""` convention stays.

## Tests (automated)

In `src/assistant/modules/cv/tests/test_handoff.py`:
- the smoke test's exact line reads as `stopped` with `tool` None;
- `"tool": ""` with the request's pick `Rezi` takes `Rezi`;
- `"tool": "Both"` is refused with the one-line message;
- `job_finished`'s summary says "No CV_RESULT line" for a text without one, and "isn't valid: …" for the smoke test's line with a bad field.

In `test_worker.py`: the prompt has the "leave tool out" sentence. Then the full `pytest` and `ruff`.

## Loading it, and your hand checks

- **Load:** a `cv` module reload (`RELOAD: cv`). No core, contract or infra code changes, so no app restart is needed. cv_agent's instructions are read when its session starts, so the reload must restart cv_agent's session (cv_agent is idle now). I'll ask before the reload.
- **Hand checks:**
  1. Run the job and cv smoke test again (the same fake job, cv told to stop at once). `cv.job_finished`'s summary should read `CV_RESULT status stopped (...)`, and the job agent's `cv.read_result task_id=…` should return the view with `"tool": null`.
  2. Check cv_agent's CV_RESULT line in `cv_agent.jsonl`: it should leave `tool` out (fix 4).
  3. Afterwards, the fake NonexistentTestCo work folder in `modules/cv/workspace/work/` can be deleted, on your go.

A real job (#9 at GM) isn't needed for these checks. Its results always carry a real pick.
