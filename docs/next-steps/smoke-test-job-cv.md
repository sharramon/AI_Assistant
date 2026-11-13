# Smoke test: job_search brings up cv when it needs a CV

> **Status: proposed (2026-11-13).** A written test only: nothing was run. The fix it checks is built ([job-cv start order](job-cv-start-order.md): job_search's `needs = []`, `job.tailor_cv` turns cv on at the CV step). Run it by hand after a reload of `job_search` and `cv` (or an app restart). Follows the [`app-update`](../../.claude/skills/app-update/SKILL.md) process.

## The flow this test checks

1. The Main Assistant turns on the job module (`job_search`), and only that module.
2. The job module starts the job search agent.
3. The job agent realizes it needs a CV.
4. The job module turns on the cv module **at that moment, not before**. It hands cv the PDF and the job description (JD) instructions, and subscribes to cv's event.
5. The cv module runs and pings that event when it's finished.
6. The job module receives the event and gets the tailored CV PDF.

## Before you start

- **Mode:** Manual, so the access cards show.
- **Clean start:** `modules.list` shows `job_search` and `cv` both **inactive**. If either shows `failed`, see known problem (b): restart the app instead of trusting `modules.off`.
- **Clear the saved grants**, so both cards show again (known problem (c)):
  1. `permissions.grants` lists what's saved.
  2. `permissions.revoke` with `module_id` `cv`, `subject` `cv_agent` (no `items`: all).
  3. `permissions.revoke` with `module_id` `job_search`, `subject` `job_search_agent`.
  4. `permissions.grants` again: neither is listed. (They're stored in `config/permissions.toml`.)

## Steps

| # | What to do | What you should see | Pass | Fail |
|---|------------|---------------------|------|------|
| 0 | Ask the Main Assistant to turn on `job_search` with `modules.on`. Nothing else. | One card: **job_search_agent's access card**. | The call names only `job_search`. | Any call that names `cv`. |
| **1** | **First check**, right after step 0: `modules.list`. | `cv` is **inactive**. | `cv` is still off. | `cv` is on (`starting` or `active`). In the last run cv came up first by itself and job_search stayed held behind its card, never active. |
| 2 | Click **Allow** on job_search_agent's card. `modules.list`. | `job_search` **active**, `cv` still **inactive**. | Both as shown. | `job_search` not active, or `cv` on. |
| 3 | Open the job UI and give the job agent a job to apply for. | The job agent starts and sees its job state. | The agent is running on the job. | No agent, or it can't see the job. |
| 4 | Let the job agent reach the CV step. | It calls `job.tailor_cv`, and the **job module** turns cv on: **cv_agent's access card** shows. | `cv` turns on only now, and the card shows. | `cv` was already on, no card shows, the agent calls `cv.task` or `modules.on cv` itself, or it asks you to turn cv on. |
| 5 | Click **Allow** on cv_agent's card. | cv gets the base PDF and the JD instructions, and runs. | `cv` **active**, its agent working on this job. | `cv` fails, or runs without the PDF or JD. |
| 6 | Wait for cv to finish. | cv pings its event (`cv.job_finished`). | The event fires once, for this job. | No event, or the job agent never hears it. |
| 7 | Look at the job agent. | It got the event and has the tailored CV PDF. | The PDF path points at the new, tailored file. | No PDF, or it uses the untailored base PDF without asking you. |

## Extra checks (from the earlier smoke test)

| # | What to do | Pass | Fail |
|---|------------|------|------|
| E1 | Find cv's output folder. | It's `src/assistant/modules/cv/workspace/out`, and the tailored PDF is there. | Another folder, or not found. |
| E2 | Open the job UI with `job.open_ui`. | A fresh app window opens. | Error, or it opens as a tab. |

## Known problems from the last run

- **(a) cv came on at job_search start.** Fixed (built 2026-11-13, [job-cv start order](job-cv-start-order.md)): job_search's `needs` is `[]`, and the job module turns cv on at the CV step.
- **(b) `modules.off` on a failed job_search** returned ok but left it showing `failed`, not `inactive`. Not fixed: the cause is in the core (`LifecycleManager._deactivate`), a separate change with its own note and an app restart.
- **Extra check for the fallback:** at step 5, click **Deny** instead. The job agent should get the module's message and ask you whether to use the base PDF untailored.
- **(c) cv_agent's old saved grant** meant its card didn't show again. Clear the saved grants before the test (above).
- **(d)** The earlier smoke test also asked for cv's output folder and `job.open_ui`: kept as E1 and E2.
