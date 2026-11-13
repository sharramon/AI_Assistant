# The base CV's copy in a job folder is named `base_…`

> **Status: built and tested (2026-11-13): 821 tests pass, ruff clean. Waiting on you:** a cv reload, or the app restart the Hub fix needs anyway, loads it. Not committed.

**Asked:** "Yes, give clearer name" (2026-11-13). The job agent's fake-job check found `CV_<name>.pdf` in a job folder and took it for a CV that cv_agent had made. It was the base CV's copy ([problem C](job-cv-finish-event.md#problem-c-the-stray-pdf-fixed-2026-11-13-the-copy-is-named-base_)).
**Why:** the copy had the base CV's own name, which looks just like a tailored CV.
**Touches:** cv only: `job_start.py`, `module.py` (`cv.read`'s argument text, `_pdf_target`'s docstring), `tests/test_job_start.py`, cv's `README.md` and `architecture.md`.
**Approach:**
- `JobStart.prepare` copies the base CV as `BASE_COPY_PREFIX + name` (`BASE_COPY_PREFIX = "base_"`), e.g. `base_CV_Test_ExampleCorp.pdf`. Never overwriting still holds (`base_CV_Test_ExampleCorp_2.pdf` for a changed copy).
- The worker's start block says the `base_` prefix marks the untouched base.
- `cv.build` with `job_dir` now writes `CV_Test_<Company>.pdf` with no clash, because the copy has a different name. The `_tailored` guard stays for job folders made before this change.
- Nothing checks the copy's name against `cv_prefix`: `cv.read` and `cv.build` take any PDF in the work folder, and the CV Tool gets the copy's path and content from the module.

**Open questions:** none.

## Tests

2026-11-13, full suite in the foreground: **821 passed, 2 deselected, 0 failed**. `tests/test_job_start.py` is included. `ruff check`: all checks passed. Details and the 4 unrelated warnings: [job-cv-finish-event: tests (2026-11-13)](job-cv-finish-event.md#tests-2026-11-13). That run covers this change and the two earlier fixes.
