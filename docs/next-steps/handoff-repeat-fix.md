# Handoff question stops repeating

> **Status: built (waiting on you) (2026-11-08).** Approved as written (any answer is a go-ahead). Built and tested; the `job_search` reload (prompt) and an app restart (`infra`) are left, each after you say so.

**Asked:** the job agent keeps asking "I've handed this task off 3 times … Should I carry on?", even after a yes, and its finished tasks wait on that question until cancelled. Build fix 1 (the job prompt) and fix 2 (a yes gives a fresh allowance); skip the per-agent config.

**Why:**
- The job agent's prompt (`JOB_PROMPT` in `src/assistant/modules/job_search/module.py`) tells it to end every finished job with `HANDOFF: <note>`. `SessionTaskAgent._finish_turn` reads that line as "continue in a fresh session", so a finished task is never reported done: it keeps going in a fresh session, or, past the limit, waits on the question.
- Once `HandoffKeeper` reaches `max_handoffs` (3), every later `HANDOFF:` line asks again. A yes resumes the session but never resets the count.

**Touches:** `src/assistant/modules/job_search/module.py` (prompt), `src/assistant/infra/handoff_keeper.py`, `src/assistant/infra/session_agent.py`, their tests, `docs/api/infra.md` (HandoffKeeper, SessionTaskAgent), and the job_search module page if it describes the prompt.

**Approach:**
1. **Job prompt:** at the end of a job, write the next-session note and next_prompt.txt, then end with a normal final report and no `HANDOFF:`. Use `HANDOFF:` only to continue the *same* job in a fresh session (context large, or asked to reset).
2. **A yes gives a fresh allowance:** when the handoff question is asked, `SessionTaskAgent` remembers the note it asked about. The next message to the task is your answer. It starts a fresh allowance (`HandoffKeeper.reset()`) and continues that handoff in a fresh session reading the note, so the yes isn't spent on the old, full session. The answer's text goes along to the fresh session, so a "no, stop" or other instruction still reaches the agent. Cancelling still ends the task. The question then comes back at most once per 3 more handoffs.
3. Tests: a yes after the question resets the count and starts the fresh session, with no repeat question at the next `HANDOFF:`; a final report without `HANDOFF:` ends as done (already covered; check it is).

**After building:** fix 1 needs a `job_search` reload; fix 2 changes `src/assistant/infra`, so it needs an app restart. Both only after you say so.

**Open questions:**
- Should *any* answer to the handoff question count as a go-ahead (recommended: yes, with the answer's text passed to the fresh session; to stop, you cancel the task), or only a clear yes?
