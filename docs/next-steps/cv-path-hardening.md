# cv path: only cv.task / cv.read_result for the job agent, and a return address that survives a relaunch

> **Status: approved (2026-11-09).** The user approved the note as written and all four recommendations: (1) only the job agent and the Main Assistant may call `cv.task`; (2) no check with the user before the Main Assistant's `hub.start` to cv_agent; (3) archive CV Tool jobs `2026-11-09_ExampleCorp` and `_2` and the work folder `2026-11-08_ExampleCorp`, delete `CV/.claude/state/job-task.txt`; (4) a Claude Code session in AI_Assistant builds it. Written by job_search_agent; copied here by the Main Assistant. **Built:** part 1 (item 1, the archive) and part 2 (item 2, the cleanup, the round cap), 2026-11-09; the loads wait on the user. See [Build status](#build-status).

**Asked (the full question):** "Harden the path from the job search agent to the cv module so the job agent cannot call cv.open_tool, cv.tool_*, cv.build, rezi.write_resume or hub.start for cv_agent itself. Only the job agent's cv.task and cv.read_result, then the Main Assistant's hub.start, should be possible. Propose the simplest enforcement that cannot be bypassed, say whether each part can be done inside a module (reloaded in place) or needs a core change and an app restart, and say who can do each part." Item 2: "Find the cause of the lost task id when cv_agent was relaunched … where the task id and the parent/child link are kept, why a module reload or relaunch drops them, and how a result can reach the right parent afterwards. No zombie IDs left over: list stale task, agent or CV Tool job ids, say which are safe to clean, and propose how stale ones get cleaned automatically."

**Why:** today nothing but item descriptions keeps the job agent off the cv worker's tools, so it can break the one-job sequence. And the finished CV reached the job agent only because the Talker carried it by hand.

## Item 1: hardening (priority)

**Reuse, nothing new:** the `Menu` part's `callers=(...)` list (`contracts/menu.py:108-138`, in the reusable parts index). The core checks it on every call, and the caller can't be faked: `ScopedContext.send` sets it, and the module door proves an agent's id with its session token (`docs/api/tools.md`, "Who sets caller"). `hub.answer`, `hub.mode` and `hub.focus` already use it.

| # | Change | Where | Load | Who |
|---|---|---|---|---|
| 1a | `callers=("cv_agent",)` on every cv item except `cv.task`, `cv.read_result` and `rezi.status`: `cv.open_tool`, all `cv.tool_*`, `cv.check_fonts`, `cv.build`, `cv.read`, `cv.compare`, `cv.report`, all `rezi.*` writes and reads | `modules/cv/module.py` | `cv` reload | a Claude Code session in AI_Assistant (I can't write `src/`) |
| 1b | `callers=("job_search_agent", "main_assistant")` on `cv.task` and `cv.read_result` | same | same reload | same |
| 1c | `hub.start` refuses `cv_agent` unless the caller is in a config list, `[modules.agent_hub] start_only_by = { cv_agent = ["main_assistant"] }`; the free-agent pick (no `agent_id`) skips restricted agents. No agent name in code (principle 21) | `modules/agent_hub/module.py:185`, `tasks.py:168` | `agent_hub` reload, only with no task open (its `busy()` waits), or the batched restart | same |
| 1d | A cv-flow block in the Main Assistant's prompt: on the job agent's request (1e), `hub.start(agent_id="cv_agent", text)`, then pass the result on | `modules/main_assistant` | `main_assistant` reload | same |
| 1e | `cv.task` also sends the coordinator an `AgentNotice` ("job_search_agent asks for a CV: …" with the text), so the job agent needs no `hub.start` and no message route to the Main Assistant | `modules/cv/module.py` (already publishes `AgentNotice`) | `cv` reload | same |
| opt | The round cap (5) checked in the CV Tool's code, not only in cv_agent's prompt | `modules/cv/tool.py` | `cv` reload | same |

**No core change and no app restart are needed.** The `Task` contract has no "started by" field, so the gate (`job_start.py:184`) can't see who sent a task. 1c closes that hole at the only door that starts tasks, so adding `started_by` to the contract (a core change plus restart) isn't needed. The Talker's own tab (`hub.send`, the user typing) stays open: that's you.

**After the build, each of these must be refused:** the job agent calling `cv.open_tool`, `cv.tool_round`, `cv.build`, `rezi.write_resume`, or `hub.start` to `cv_agent` (tests next to `tests/test_handoff.py`).

## Item 2: the lost task id

**Where the id and the link are kept:** only in the Hub's memory, `TaskBoard._tasks` (`agent_hub/tasks.py:109`). Each record holds `parent_task_id` and `holder`, the agent object that took the task. Copies outside the Hub: `CV_Module/.claude/state/cv_agent-task.txt` (the latest id, written at each assign, only for the edit hook) and the gate's `_ready` set (memory).

**Why it was lost:**
1. The `cv` reload provides a new agent object under the same id. `_close_replaced` (`tasks.py:120-129`) then ends the old task as **failed** ("was reloaded"). That's all dca1005e's "failed" was.
2. The relaunched cv_agent session never had the old id. The work went on from its tab: the Talker's `hub.send` with no task starts a new task **with no parent** (`agent_hub/module.py:204`), so 5c8ea130 has `parent_task_id = None`.
3. Even with a parent set, **nothing delivers a child's end to its parent agent.** `_finish` only feeds the coordinator (`tasks.py:333`), so the parent has to poll `hub.status`. And the parent, e3241acc, had already ended, because the job agent's own session changed. A return address made of task ids dies when either side changes session.

**Fix (inside the cv module, `cv` reload):** address the result **by agent id, on disk**. `cv.task` gets its caller (add the `caller` argument), so it writes `reply_to: job_search_agent` (and the coordinator) into the `CV_REQUEST`. The gate saves that in `job_start.json`. When `cv.tool_result` comes back ready (your Submit), the cv module sends `AgentNotice(agent_id=reply_to, text=<PDF path + CV_RESULT>)`, and the Hub passes it on with `note()` (`agent_hub/module.py:253`). This doesn't depend on any task id, cv_agent's memory or a reload. If the job agent isn't running, the Hub logs the dropped notice; `result.json` stays in the job's folder, and the next apply session reads it.

## Leftover ids now (nothing deleted)

| Id / item | What | State | Clean? |
|---|---|---|---|
| e3241acc | job agent, ExampleCorp CV hand-off (parent of dca1005e) | done | nothing to do: Hub memory, gone at restart |
| dca1005e | cv_agent, ended by the `cv` reload | failed | same |
| 5c8ea130 | cv_agent, the relaunched ExampleCorp job (no parent) | done | same |
| 7c17fdda, 1ca586e3 | cv_agent: jobs-folder check, humanizer rule | done | same |
| 983e7622 | job agent, ExampleCorp logging | done | same |
| 2b4f1cb1 | this task | running | no |
| `CV/.claude/state/job-task.txt` = c799bbda | left from the old agent id `job` (renamed 11-05) | stale | **safe to delete** |
| `CV_Module/.claude/state/cv_agent-task.txt` = 1ca586e3 | last cv task | overwritten at the next assign | leave |
| CV Tool job `2026-11-09_ExampleCorp` | first start, 2 drafts, not submitted | abandoned | **safe to archive** |
| CV Tool job `2026-11-09_ExampleCorp_2` | second start, 2 drafts, not submitted | abandoned | **safe to archive** |
| CV Tool job `2026-11-09_ExampleCorp_3` | v1-v14, submitted (`result.json`, `ready.flag`) | the real one | keep |
| CV Tool job `_4` | named in task 7c17fdda | no longer on disk | nothing |
| work `2026-11-09_ExampleCorp_StaffEngineerWidgetDesign` | the job folder; two set-ups (`job_start.json`, `job_start_2.json`): the first for dca1005e, the second after the relaunch | done | keep (the extra `.py` probes could go) |
| work `2026-11-08_ExampleCorp` | pre-module draft (.odt, handoff) | old | safe to archive |
| Rezi resume 0000c0de | the ExampleCorp resume | used | keep |

No open task is stuck: every agent shows a correct open task or none.

**Automatic cleanup (proposed):**
- Hub (`agent_hub`, reload or the batched restart): clear `holder` when a task ends (today a failed record keeps the old agent object alive), and keep only the last 20 finished records.
- cv (`cv` reload): when a job reaches Submit, older unsubmitted CV Tool jobs for the same work folder move to `cv_tool/jobs/_archive/`. The gate writes one `job_start.json` per job and reuses it on a second set-up, instead of `_2`.
- Task files: the profile agent writes `<agent_id>-task.txt` and removes any `*-task.txt` for ids that are no longer configured (infra, restart). Optional; only one file is stale today.

## Build hand-off (for the Claude Code session in AI_Assistant)

Done by job_search_agent: `CV/.claude/state/job-task.txt` (c799bbda) deleted on the user's yes. Everything below is outside its write access.

1. Copy this note into `AI_Assistant/docs/next-steps/cv-path-hardening.md`, add its row to Pending changes, run `build_docs.py`.
2. Build 1a-1e, the optional round cap, the item 2 fix (`reply_to` in `cv.task` → `job_start.json` → `AgentNotice` on Submit), and the automatic cleanup. Add the refusal tests next to `tests/test_handoff.py` and run the tests.
3. Archive (move, don't delete) into `CV_Module/cv_tool/jobs/_archive/`: `2026-11-09_ExampleCorp`, `2026-11-09_ExampleCorp_2`. Move `CV_Module/work/2026-11-08_ExampleCorp` to `CV_Module/work/_archive/`. Keep `_3` and the `..._StaffEngineerWidgetDesign` work folder.
4. Do not reload or restart anything. Report back. The user is asked before the `cv`, `main_assistant` and `agent_hub` reloads (`agent_hub` only with no task open). Any app restart is the user's.

## Open questions (answered 2026-11-09: all four recommendations approved)
1. **Who else may call `cv.task`?** Recommend the job agent and the Main Assistant only.
2. **Should the Main Assistant ask you before each `hub.start` to cv_agent?** Recommend no: the cv worker already waits for your "start".
3. **Archive or delete the two abandoned CV Tool jobs and the stale task file?** Recommend archive the jobs and delete the one task file, on your yes.
4. **Who builds it?** I can't write `src/` or the app's docs. Recommend a Claude Code session in `AI_Assistant` builds 1a-1e and item 2 in one pass. Then `cv` and `main_assistant` reloads, and the `agent_hub` reload once no task is open (I'll ask before any of them). You do any app restart.

## Build status

### Part 1: built 2026-11-09 (Main Assistant)

- **1a, 1b:** cv's menu is a `CallerMenu` (`modules/cv/module.py`): on every call it asks the module's `may_call(name, caller)` before the core's own checks. `cv.task` and `cv.read_result`: only `[hand_off] callers` (`job_search_agent`, `main_assistant`); `rezi.status`: anyone; every other item: only the worker (`agent.agent_id`). The ids come from cv's `module.toml` `[hand_off]`, not the code (principle 21), so the item-level `callers=(...)` of `Menu` wasn't used: it takes fixed ids. **Later:** if a second module needs caller lists from config, move this into `Menu` (a core change, restart).
- **1c:** `[modules.agent_hub] start_only_by = { cv_agent = ["main_assistant"] }` in `config/default.toml`. `hub.start` naming a listed agent is refused to other callers; **the Talker always may** (it speaks for you: its tab's `hub.start` and `hub.send` start tasks for the agent you're talking to). A free-agent pick (no `agent_id`) skips listed agents (`TaskBoard(restricted=...)`).
- **1e, with one change:** a note never wakes an agent (`ITaskAgent.note`: "never starts work"), so a notice alone would sit until the Main Assistant's next turn. `cv.task` therefore **starts a task on the coordinator** (`StartTask`, `[hand_off] coordinator`) with the request and the exact text; only when the coordinator is busy or off does it send the `AgentNotice`. Its result says which (`asked`: `task <id>` or `notice`) and tells the job agent it may not call `hub.start`. When the coordinator itself calls `cv.task`, it just gets the text.
- **1d:** one generic line in the coordinator's prompt (`COORDINATOR_BLOCK`): a task or notice from a module may ask it to start an agent; do it with `hub.start` and the exact text, without asking the user. No cv names in it: the request carries them.
- **Tests:** `modules/cv/tests/test_callers.py`: the job agent is refused `cv.open_tool`, `cv.tool_round`, `cv.tool_status`, `cv.check_fonts`, `cv.build`, `cv.read`, `rezi.write_resume`, `rezi.list_resumes`, `rezi.sign_in` and `hub.start` for `cv_agent`; a free pick skips `cv_agent`; the Talker may start it; `cv.task` asks the coordinator. The cv tests now call the worker's items as `cv_agent` and `hub.start` as `main_assistant`.
- **Archived (moved, nothing deleted):** `CV_Module/cv_tool/jobs/_archive/2026-11-09_ExampleCorp` and `_2`; `CV_Module/work/_archive/2026-11-08_ExampleCorp`. `_3` and the `..._StaffEngineerWidgetDesign` folder stay.
- **Loads needed (ask the user first):** `cv` reload, `main_assistant` reload, `agent_hub` reload (only with no task open) or an app restart; the `config/default.toml` line is read when `agent_hub` starts. Until `agent_hub` reloads, `hub.start` to `cv_agent` is still open.
- **Not mine, still failing:** `modules/cv/tests/test_cv_tool.py::test_every_style_on_the_page_is_9_pt_or_more` (the CV Tool's `MIN_PT` is now 10, the test expects 9).

### Part 2: built 2026-11-09 (Claude Code session)

- **Item 2, the return address:** `CvRequest.reply_to` = `cv.task`'s caller; the gate saves it in `job_start.json`. The first `cv.tool_result` that sees a Submit tells that agent (`reply.py`, `_tell_asker`), **with one change from the plan:** like part 1's 1e, a task of its own (`StartTask`, so it wakes), and an `AgentNotice` only when it's busy or off (`_wake`, shared with `_ask_coordinator`). The text: the PDF, the score, where `result.json` is (not a `CV_RESULT` line: `result.json` isn't a `CvResult`; cv_agent's own line still comes at its task's end). `job_start.json` records `replied` per Submit, so it's told once. The CV Tool's `/api/job/result` now also gives the job's `work_dir`. The coordinator's ask says the CV reaches the asker by itself.
- **Cleanup:** Hub: an ended record's `holder` is cleared, and only the last 20 finished records stay (held ones and an open task's parent stay too). cv: one `job_start.json` per job (replaced at a second set-up, first `started` kept). CV Tool: at Submit, older unsubmitted jobs of the same work folder move to `jobs\_archive\` (`cvlib.archive_older`).
- **Round cap in code:** `CvTool` refuses a score round and `cv.tool_internal_round` past `max_rounds` (5); a print without a score and `cv.check_fonts` still work.
- **Not built (optional):** the profile agent removing stale `*-task.txt` files (an infra change needing a restart; none is stale now).
- **Tests:** `test_tool.py` (told once per Submit, by id; the cap), `test_cv_tool.py` (the archive), `test_job_start.py` (one record), `agent_hub/tests/test_stale_task.py` (holder cleared, records pruned). Full suite: all pass but the known `test_every_style_on_the_page_is_9_pt_or_more` (`MIN_PT` 10 vs the test's 9; not from this change).
- **Finished (third session, 2026-11-09):** docs HTML rebuilt; full suite 748 passed (the known `MIN_PT` test deselected), ruff clean. Architecture check: every check lives in its module (cv's `CallerMenu`, the Hub's `start_only_by`), ids come from config, no core or contract change, docs match.
- **Loads:** the user's app restart (2026-11-09) loads `cv`, `main_assistant` and `agent_hub` together. Nothing else is left to build.
- **Hand checks after the restart:** (1) the job agent calling `cv.open_tool`, `cv.build` or `hub.start` for `cv_agent` is refused; (2) its `cv.task` starts a task on the Main Assistant, which starts `cv_agent` with the exact text; (3) after Submit in the CV Tool, the job agent is told once (PDF, score, `result.json`); (4) a 6th score round is refused. Separately: fix `test_every_style_on_the_page_is_9_pt_or_more` (expects 9 pt, `MIN_PT` is 10).
