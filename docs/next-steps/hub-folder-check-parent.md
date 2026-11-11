# The Hub's folder check skips the starting task

> **Status: cancelled (2026-11-09), never built.** Replaced by [agent-talk-and-questions](agent-talk-and-questions.md): the Main Assistant is out of the cv hand-off, and the real clash was cv_agent's repo write grants.

**Asked:** "Change `_folder_clash` in `agent_hub/tasks.py` so the requesting (parent) task doesn't count" (option (a), after job_search_agent's Globex Robotics CV request could not be started on cv_agent).

**Why:** `hub.start` refuses an agent when another open task's agent writes one of its folders. The Main Assistant's own task, the one calling `hub.start`, counts as such a task. The Main Assistant and cv_agent both write `C:\Chang\Git_projects\AI_Assistant`, so the Main Assistant can never start cv_agent from a task: the refusal was "cv_agent would write …, which main_assistant's open task 4df48918 writes".

**Touches:** `src/assistant/modules/agent_hub/tasks.py` (`_folder_clash` and its call in `start`), a test in `src/assistant/modules/agent_hub/tests/`, `docs/architecture/agents.md` / `docs/modules/agent_hub.md` where the folder rule is described. Needs a reload of `agent_hub` (asked first), no app restart.

**Approach:**
- `_folder_clash` gets the new task's `parent_task_id` and skips that open task. The parent hands work on and waits for its child, so the two don't write side by side in practice; any other open task still blocks as before.
- Only the direct parent is skipped, not its other children or the parent's parent.
- Test: a parent task whose agent writes folder X starts a child on another agent writing X (allowed); a task without that parent still is refused.

**Open questions:**
- Should the parent's whole chain (grandparents) be skipped too? Recommended: no, only the direct parent; widen it later if a real case needs it.
