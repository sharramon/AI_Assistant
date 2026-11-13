# Handoff: multi-agent build, docs and final checks (task d729a7ef)

The design is [multi-agent.md](multi-agent.md); the earlier handoff is [handoff-99c9ff7c.md](handoff-99c9ff7c.md) (its "End" list and "After a restart, check" list still apply). The task rules: tests and ruff after each chunk, don't restart the app, don't git push, and a final report saying what to check after a restart. The user authorized editing `config/default.toml` for this build.

## Done and checked (this session)

- **Chunk 6, the temp UI** (`modules/temp_ui/module.py`, `page.html`):
  - every worker-pane item carries `agent`;
  - an `agents` SSE state item (`focus`, `coordinator`, per agent `busy` / `working` / `held` count), rebuilt from `ListAgents` at start, at each SSE connect, and on `ModuleStateChanged` / `AgentStateChanged`, `TaskUpdated.held` and `FocusChanged`;
  - a held permission or risky card isn't pushed until `FocusChanged.released` brings it, and cards carry `agent`;
  - `POST /focus` `{"agent"}` sends `SetFocus`;
  - the manifest sends `ListAgents` and `SetFocus`, and listens to `FocusChanged`;
  - the page shows one tab per big agent when there are 2 or more: state dot, **!**, the focused tab filled, the Main Assistant's tab in the accent colour. A click posts `/focus`, the feed shows only the focused agent's lines, the pill shows its state, and cards say "{agent} asks permission". Helper usage isn't shown (only the worker and the Talker).
  - Test: `tests/test_temp_ui.py::test_agent_tabs_hold_cards_until_the_focus_moves`.
- **Chunk 7, the job agent:**
  - **New module `modules/job_search/`** (`JobSearchModule`, off at launch). It bundles a `ProfileAgent` with id `job` (`agent_id` in config) and its menu item `job.search(days)`, a **stub**: it answers at once and publishes `AgentNotice(agent_id=caller, source="job.search")`, saying the runner isn't built yet. `JOB_PROMPT` says: one job per session, `HANDOFF:` instead of `handoff.ps1`, never submit or send, confirm before any search.
  - **Shared infra:** a `chrome` option in `claude_command` (`--chrome`) and `AgentProfile` (config key `chrome`).
  - **Config:** `[modules.job_search]` in `config/default.toml`, with workspace `C:/Jobs/CV`, read `C:/Jobs` and JobRadar, `tools = "default"`, `chrome = true`, Manual.
  - Test: `tests/test_job_search.py` (2 tests).
- **Suite:** 444 passed, ruff clean. The only 4 failures are in `test_module_docs.py`, which needs the job_search docs below.

## Next

1. **Docs for job_search** (these fix the 4 failing tests):
   - add `"job_search"` to the agents tab list in `scripts/build_docs.py` (line 64, beside `task_agents`);
   - write `docs/modules/job_search.md`, shaped like `task_agents.md`;
   - add its line to `docs/modules/README.md`.
2. **Other docs:**
   - `docs/modules/talker.md`: the new tags, the one road through `hub.*` via `InvokeTool`, the manifest (sends `InvokeTool`, `AnswerPermission`, `SetPermissionMode`; listens `FocusChanged`, `FocusSuggested`), and its Inner workings diagram.
   - `docs/modules/temp_ui.md`: the tabs, `/focus`, the `agents` item, held cards, and the new sends and listens.
   - `docs/architecture/agents.md`, "Working together" (around line 241): the Talker's part, the temp UI tabs, and the job agent (`job_search`). Also drop the "How does the Main Assistant delegate" open question, which the Hub's menu now answers.
   - `docs/api/reusable.md`:
     - the Used by lines: the Hub's menu adds `temp_ui` (via `SetFocus`); `FocusChanged` adds `talker`, `temp_ui`; `FocusSuggested` adds `talker`; `AgentNotice` adds `job_search`;
     - `ProfileAgent` / `AgentProfile` add `job_search`.
   - `docs/api/infra.md`: the `chrome` option on `claude_command` and `AgentProfile`.
   - The overview's Parts "Modules" row (`docs/architecture/README.md`): add `job_search`, off by default.
   - `docs/next-steps/multi-agent.md`: the status line (chunks 1–7 built; restart needed).
   - `docs/next-steps/job-agent.md`: the status (built as `job_search`, a stub search; open: question 1, the access list, and the real search runner).
   - `docs/next-steps/README.md`: rows 48 and 50.
3. Run the architecture check (skill), then `.\.venv\Scripts\python scripts\build_docs.py`, pytest and ruff. Then write the final report.
4. **Open questions for the final report:**
   - the job agent's access list (job-agent question 1, still unconfirmed; the proposal is shipped);
   - the real `job.search` runner (`sweep.py` with JobRadar's Python, 10 to 15 minutes);
   - whether `--chrome` loads under `--strict-mcp-config` (check after the restart);
   - helper usage in the temp UI header.
5. **After a restart, also check:**
   - the tabs appear once `task_agents` or `job_search` is on;
   - clicking the helper's tab moves the focus and shows its held card;
   - `modules.on job_search` lists `job`, and the job agent's session has the Chrome tools.
