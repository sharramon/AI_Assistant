# A skill for the job and cv smoke test

> **Status: proposed (2026-11-13).** Waiting for the user's check. Nothing written yet besides this note.

**Asked:** "Make it into a skill that's always referred to when I ask for a smoke test for the job module and cv module."

**Why:** the last runs didn't follow your order: cv was turned on by hand, and the run went on with old saved grants. A skill makes every run start from the [smoke test page](smoke-test-job-cv.md) and follow it as written.

**Touches:**
- New: `.claude/skills/job-cv-smoke-test/SKILL.md` (a project skill, like `batching` and `architecture-first`).
- After your check: one line in `CLAUDE.md`'s Workflow section, `When the user asks for a smoke test of the job or cv module: use the job-cv-smoke-test skill.`
- No code, no module, no config.

**Approach:** the skill is short and points at the page; the page holds the steps, so they're kept in one place. Its text:

```markdown
---
name: job-cv-smoke-test
description: Always use when the user asks for a smoke test of the job module and the cv module, or says "job smoke test", "cv smoke test", "smoke test the job search", or "smoke test job_search / cv". Runs the written test in docs/next-steps/smoke-test-job-cv.md exactly as written.
---

# Job and cv smoke test

Read the page first: `docs/next-steps/smoke-test-job-cv.md` (HTML: `docs/html-next-steps/smoke-test-job-cv.html`). Follow it as written.

## The user's order, exactly

1. The Main Assistant turns on only `job_search`.
2. `job_search` starts its agent.
3. The agent realizes it needs a CV.
4. `job_search` turns on `cv` at that moment, with the PDF and JD instructions, and subscribes to cv's event.
5. `cv` runs and pings the event.
6. `job_search` receives it and gets the tailored CV PDF.

## Rules

- **Never turn cv on by hand**, not even to unblock a step. cv coming up is what the test checks.
- **Before step 1:** run in Manual mode, both modules inactive, and clear the saved grants (`permissions.grants`, then `permissions.revoke` for cv / cv_agent and job_search / job_search_agent), as on the page.
- **Begin with the first check:** right after `job_search` is turned on, `cv` must still be off. If it's on, that's a fail; report it.
- **Report each step pass or fail**, plainly, with what you saw. A fail is a finding, not something to fix mid-test.
- Run the page's extra checks (E1, E2) at the end, and compare what you see with its known problems list.
- **Ask the user before anything outside the test** (a restart, a reload, a fix, any other module on or off).
```

**Open questions:**
1. The name `job-cv-smoke-test`: fine? Recommended: yes.
2. The CLAUDE.md line above, added once you've checked this note: fine? Recommended: yes.
