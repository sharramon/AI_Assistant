# Handoff: multi-agent build, chunks 6–7 (task 99c9ff7c)

The design is [multi-agent.md](multi-agent.md). The task, from the user: continue the build in order, chunks 6 → 7, tests and ruff after each, a short progress line after each, don't stop between chunks unless blocked. At the end: docs, reusable parts index, architecture check, docs rebuild, and a final report saying what to check after a restart. Don't restart the app, don't git push. The user may edit `config/default.toml` for this build only as the task needs (the cap setting is done).

## Done and checked

- **Chunks 1–3, and the cap** (earlier sessions): contracts, door caller, Hub focus / held / menu / feed, `AgentProfile`, `MilestoneFeed`, `status_lines`, `ProfileAgent`, the `task_agents` module, `[modules.agent_hub] max_extra_agents = 3` (the coordinator isn't counted). Docs for these were updated and rebuilt.
- **Chunk 4, the Talker** (`modules/talker/module.py`, this session):
  - **Decision (architecture-first):** the Talker keeps its tags as a shorthand, like SHOW for `viewer.open`. Every Hub tag now runs through the Hub's menu with `InvokeTool` (`_hub(name, **args)`; the core fills in the caller `talker`), so there is one road to the Hub and no MCP round-trips. Permission answers stay on `AnswerPermission`, per task. Its manifest now sends only `InvokeTool`, `AnswerPermission` and `SetPermissionMode`, and listens to `FocusChanged` and `FocusSuggested` too.
  - **The tags:**
    - WORK → `hub.start` with agent_id = the coordinator.
    - ASK / PAUSE → `hub.send` to the coordinator's task.
    - LOOK [agent] → `hub.status`.
    - CANCEL [agent] → `hub.cancel`.
    - New: AGENTS → `hub.agents` (names and marks only).
    - New: FOCUS: agent → `hub.focus`.
    - New: PASS → `hub.send`, no task id, with the user's own text word for word (only on the user's own input).
    - ALLOW / DENY [agent] → a card picked per task. A bare one with more than one card open gets a status asking which (`MANY_CARDS`).
  - **The rest:**
    - It keeps an open-tasks table (`_open`, built from `TaskUpdated`), plus `_focus` and `_cards`.
    - Updates from helpers are named (`[Task update: reply from job]`); the coordinator's carry no name, so the one-assistant voice stays.
    - Held questions and milestones are never said, and a helper out of focus never speaks. The coordinator's done / reply / failed updates are always said; only its questions are held.
    - `FocusChanged.released` is said as `[Focus] … [Task update: need/permission from X] …`. A focus move with nothing released becomes a note on the next message.
    - While a helper has the focus, every message is prefixed `[Focus] the user is talking to X directly (pass their words on)`.
    - `FocusSuggested` becomes `[Suggestion] … Ask them yes or no; if yes, FOCUS: X`.
    - The prompt has the new tags and an "Other agents" paragraph.
  - Tests: new `tests/test_talker_agents.py` (3 tests).
- **Chunk 5, the Main Assistant:** delegation lines in `COORDINATOR_BLOCK` (`infra/agent_profile.py`), so every coordinator gets them: `hub.agents`, `hub.start` (child task, self-contained text), `hub.status` / `hub.send` / `hub.cancel` for its own children, and `hub.suggest_focus` (only the user moves the focus). Test: `test_task_agents.py::test_only_the_coordinator_is_told_to_delegate_and_suggest`. The menu mechanics were already tested in chunk 1.
- **Full suite:** 442 passed, ruff clean. The only failure is `test_module_docs::test_the_library_table_is_generated…`, which clears when the docs are rebuilt (the manifests changed).

## Next

1. **Chunk 6, the temp UI** (throwaway, keep small). Files: `modules/temp_ui/module.py` (around 470 lines; `_on_task` at about line 316, `_push` / `_push_state`, `_stream` at about line 445, `_serve` routes at about line 358) and `page.html` (the worker pane at about lines 165–172, `permissionCard` at about 213, `add()` at about 398). The plan as worked out:
   - **Server:**
     - Put `agent` (the event's `agent_id`) on every worker-pane item: `_on_activity`, `_on_state`, `_on_task`.
     - Add an `agents` state item `{"kind": "agents", "focus": id, "agents": [{"id", "busy", "working", "held"}]}`. Rebuild it from `ListAgents` on start, on each SSE connect, on `ModuleStateChanged` and on `AgentStateChanged`. Set `held` from `TaskUpdated.held` (cleared on a final state and on `FocusChanged`).
     - Subscribe to `FocusChanged`. For each released task whose question starts with `Permission: `, push its permission card.
     - Push a permission card only when `not event.held`, and put the agent's name on it (`agent` field; the title is "{agent} asks permission").
     - Add `POST /focus` `{"agent"}` → `SetFocus`.
     - Manifest: add `SetFocus` and `ListAgents` to sends and `FocusChanged` to listens. `ListAgents` is handled by the Hub.
   - **Page:** a small side panel or tab strip above the worker feed, one tab per big agent: its name, a **!** when held, and the focused one marked. The `main_assistant` tab gets its own colour. A click posts `/focus` and shows only that agent's lines (filter by `item.agent`; items without `agent` show everywhere). The worker state pill follows the selected tab.
   - **Tests:** extend `tests/test_temp_ui.py`: a held card isn't pushed until the focus moves, `/focus` sends `SetFocus`, and items carry `agent`.
2. **Chunk 7, the job agent:** read `docs/job-project/README.md` and `docs/next-steps/job-agent.md`. Per the decision, build a `job_search` module that bundles its `ProfileAgent` (folder `C:\Chang\Jobs\CV`, Chrome tools, Manual), with a stub `job.search` callback through `AgentNotice` if the notes don't settle the real one. List the unclear points as open questions.
3. **End:**
   - Docs: `docs/modules/talker.md` (the new tags, the one road through the menu, the manifest, its Inner workings diagram), `docs/modules/temp_ui.md`, `architecture/agents.md` ("Working together": the Talker part), `api/reusable.md` (the Used by lines for the Hub's menu and `FocusChanged` / `FocusSuggested`: the Talker and the temp UI), and in `multi-agent.md` the status line and the decision on the Talker's tags (copy it from above). Also the bird's-eye diagram's focus / feed, if the overview allows.
   - Run the architecture check (skill), then `.\.venv\Scripts\python scripts\build_docs.py`, pytest and ruff, then write the final report.
   - **After a restart, check:**
     - `hub.agents` lists `main_assistant` as focused.
     - The Main Assistant's and the Talker's doors work.
     - A normal WORK task runs to done.
     - After `modules.on task_agents`, a task for `helper` runs beside the Main Assistant, and its `STATUS:` reaches the Main Assistant.
     - The helper's question shows a **!** until it's focused, then the Talker says it, named.
     - PASS sends your words word for word.
     - A bare "yes" with two cards open is refused.
