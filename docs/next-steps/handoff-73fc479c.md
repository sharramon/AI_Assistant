# Handoff: the agent-permissions build (task 73fc479c)

The task is to build [agent-permissions.md](agent-permissions.md): all 8 build steps, run in Auto mode. Follow batching, architecture-first, and architecture-check after each big chunk and before the final report. Write tests, then run pytest and ruff, rebuild the HTML (docs-html), and mark the note built in `docs/next-steps/README.md`. Don't git push or restart the app; the restart is asked about after usage-tallies. Agent names is built: the job agent's id is `job_search_agent`, a helper launch needs your yes on a card, and `IAgentNames` exists. The `config/default.toml` edit for the job agent's keys is approved and done. At the end, report the architecture check, test and ruff results, and what needs your eyes after the restart.

## User decisions (session 3), already in the code; the docs still need them

1. **The permissions handler is part of the core, not a module.** It's always on, and no module or agent can turn it off or reload it. `ctx.permissions` is backed by the core handler (`PermissionsPort`), which replaces `AllowAllPermissions`. There's no permissions module and no `IPermissions`. The `permissions.*` grants menu is on the core's menu (id `core`). `data/permissions.toml` stays protected, and an agent's grant or revoke needs your card. The Main Assistant's review goes through `StartTask`, `TaskUpdated` and `CancelTask`. The user wants the docs to say this (the note, `architecture/permissions.md`, the README parts table, `decisions.md`, the API pages) and a report of the check that the core stays small and uses only generic parts.
2. **Grants are saved per kind of agent** (`helper_2` shares `helper`'s; the job agent's subject is `job_search_agent`). Record it in the note as decided (it refines decisions 5 and 10).

## Done (sessions 1–4); code written, the full suite not yet green

- Steps 1–3: the contract `contracts/permissions.py` (now without `IPermissions`), and `core/permissions/` (`rules`, `store`, `handler`, `port`, `menu`). The old `core/permissions.py` and `modules/permissions/` are deleted.
- **Core wiring (session 4):**
  - `core/app.py`: `self.permissions = PermissionsHandler.from_config(...)`; `AnswerPermissionRequest` is handled; `TaskUpdated` is subscribed; `permissions_menu_tools` is under `CORE_ID`; `GetMenu("core")` includes `PermissionsMenu`; `CoreMenu` and `ScopedContext` get a `PermissionsPort`; `permissions.close()` runs in `stop()`.
  - `core/context.py` takes a `permissions=` argument. `core/registry.py` no longer has the `IPermissions` ordering.
- **Step 4** (earlier): `infra/agent_access.py` and the `python` key / `manual_claude_mode` in `agent_profile.py`.
- **Step 5 (session 4):**
  - `job_search`: builds its agent in `start()` after `request_access(subject=job_search_agent, wait=False)`; it has the manifest permission `agent.access`, and is guarded for None.
  - `task_agents`: each autostart kind is asked in `start()`, all cards at once, with one combined `AccessPending`. The helpers are built from the granted kind config with the new `instances(kind, merged)` (`agent_configs` uses it). `_launch` asks `request_access(subject=kind, wait=True)`, and on `AccessDenied` it fails. It has the manifest permission `agent.access`.
- **Step 6 (session 4):**
  - Talker: subscribes `PermissionRequested` / `PermissionChanged`. Cards are keyed `access:<request_id>` in `_cards`, so `<<ALLOW>>` / `<<DENY>>` send `AnswerPermissionRequest` (all or deny). `access_card_text(event)` is a module-level function. The prompt gained the "[Access card]" paragraph.
  - temp UI: `accessCard()` in `page.html` (tick boxes, warnings, "not reviewed", fixed rules), and `POST /access-answer`. `PermissionChanged.request_id` settles the card (`access_closed` item).
- **Step 7 (session 4):** `temp_ui/static/grants.js`, the rough throwaway screen: its own header button, panel and styles, plus one marked `<script>` tag in `page.html`. It uses `GET /grants.js` and `POST /grants` (`list` → `permissions.grants`, `revoke` → `permissions.revoke`, as `temp_ui`).
- **Step 8 (session 4):** `config/default.toml` has `python = ".../Resume/.venv/Scripts/python.exe"` in `[modules.job_search]`, the comment fixed, and a commented `[core.permissions]` block.

## In flight when this session ended

A `debugger` subagent was fixing the test suite: `test_permissions.py`, `test_permissions_handler.py` (core form), a new `tests/conftest.py` (autouse: `GRANTS_FILE` → tmp), `support.pre_grant(...)`, pre-grants in the job_search / agent_names / task_agents tests, the `permissions.*` filter in `test_app.py`, and new behaviour tests. **Its result wasn't seen.** The next session should run pytest first and finish what's left. Also check that `data/permissions.toml` wasn't created by tests.

## Next

**Status (2026-11-05, session 5):**
- **Steps 1–5 below are DONE.** The suite passes: 474 + 1 tests. Ruff is clean, and `data/permissions.toml` is never written by tests.
- **Test setup:** `tests/conftest.py` gives a short card timeout and turns the review off. `support.pre_grant` / `pre_grant_kinds` and `tests/test_access_cards.py` are in place.
- **Docs and HTML:** updated, and agent-permissions is marked built.
- **Architecture check:** OK.
  - The handler holds no logic for any particular module: a new module only declares `agent.access` and lists its access in config.
  - Only the defaults `reviewer = main_assistant` and `you = temp_ui` name agents; both are configurable in `[core.permissions]`.
  - The handler uses only generic core parts. It is 476 + 40 + 49 + 91 + 113 lines.
- **Still wrong:** the bird's-eye diagram shows Permissions as a planned module. Fix it in the fold step (6.4).
- **Next:** 6.2, usage tallies.

**Usage tallies, part A, DONE (session 5):**
- `docs/next-steps/usage-tallies.md` is edited to the user's decisions. The time buckets, the history and `usage.jsonl` are gone (nothing on disk).
- The real sub-agent test ran. Its "Verified (2026-11-05)" section is in the note, and the HTML is rebuilt.
- **What the stream shows:**
  - The sub-agent's own lines don't appear. Only its prompt does, as a `user` line with `parent_tool_use_id` and `agent_id`.
  - Its tokens are in `tool_use_result.usage` on the tool_result line, with `agentId` and `agentType`. There's no cost per sub-agent.
  - The `result`'s `usage` covers the parent only, while `modelUsage` and `total_cost_usd` include the sub-agent.
  - So a sub-agent's row shows tokens, and its ~$ stays in the parent's.
- **Next:** part B, the build, from the note's rewritten build steps: the own `usage` module, the dropdown with nesting, and the Talker as its own row. Then tests, ruff, the architecture check, docs and the HTML rebuild, and mark it built. After that, the rest of step 6.

**Usage tallies, part B, STARTED then stopped (session 5):**
- A build subagent was stopped partway through. It had already changed files on disk: at least `src/assistant/contracts/agents.py` and `src/assistant/modules/talker/module.py`, and maybe a new `src/assistant/modules/usage/`.
- The next session starts by reading `git diff` of those files and `git status` for new files. It keeps what fits the note, and finishes the build:
  - the own `usage` module, with sub-agent tokens from `tool_use_result.usage` (`agentId`, `agentType`) nested under the parent; a sub-agent's ~$ stays in the parent's;
  - the dropdown in the temp UI, in a clearly marked place, with the Talker as its own row;
  - tests (full suite with a 300 s shell cap, about 75 s and 475 tests before), ruff, the architecture check, docs (`docs/modules/usage.md`, the API pages, `reusable.md`) and the HTML rebuild;
  - mark the note built.
- The contracts changed, so the app needs a restart, done by the Talker.
- **A second build subagent was also stopped partway (session 5).** By then it had also changed `src/assistant/modules/temp_ui/module.py`, `temp_ui/page.html` and `config/default.toml`, probably the `[modules.usage]` section.
- The next session should do the build itself, in a fresh context, rather than through a long subagent (they keep being cut off).

**Usage tallies: BUILT (session 5).**
- The code the stopped runs left was complete and passed. Session 5 added the docs: `docs/modules/usage.md`, its tab in `build_docs.py`, `SessionUsage` in `api/agents.md`, `subagent_usage` and `UsageLedger` in `api/infra.md`, `reusable.md`, the `api/README` row, and the module-library regeneration. The note and `next-steps/README` are marked built.
- **Tests:** all 485 pass. Ruff is clean. `test_voice_pieces::test_closing_the_socket...[False]` failed once in the full run, then passed when re-run with its file and the docs tests, so it's timing-flaky and unrelated.
- **Architecture check:** OK. The `usage` module uses only contracts and infra, and the ledger is plain Python in infra. The Talker uses `usage.total` through the menu.
- **The whole list is now built, and the app is READY FOR THE RESTART,** which the Talker does.

**After the restart, test (the next session; fix, ask for a restart again, and re-test until all of it works):**
1. **Post-restart basics:** the door lists modules, `viewer.open` works, `hub.agents` shows `main_assistant` focused, and a normal task runs to done.
2. **Agent names:**
   - `job_search` registers as `job_search_agent`.
   - `IAgentNames.taken()` is right.
   - A clash is refused with a free name.
   - A repeat claim by the same owner is ok.
3. **Helper launch:** `modules.on task_agents`, then `agents.launch` gives the user a card. Allow starts the helper as a child task, and its access card (kind `helper`) shows.
4. **Permissions:**
   - `modules.on job_search` shows the access card in the temp UI, with tick boxes, warnings, and the review or "not reviewed".
   - Allow turns it on, and `data/permissions.toml` gets written.
   - `permissions.grants` lists it.
   - Revoke from the Grants (rough) screen turns it off.
   - A revoke from an agent shows a card.
5. **Usage:** `usage.total` and `usage.agents` (the Talker's row, `main_assistant`'s row). A task that uses a sub-agent shows it nested. The temp UI's total and dropdown.
6. Turn `job_search` and `task_agents` back off afterwards.
7. Then the docs move (6.4) and the bird's-eye diagram fix.
- Read the usage parts of `git diff` and `git status`, then finish, test, run ruff and update the docs as listed above.

1. Run `.\.venv\Scripts\python -m pytest -q` and ruff, and fix what fails (hand loops to `debugger`).
2. Add `tests/test_access_cards.py`:
   - `access_card_text` (talker), including "Not reviewed".
   - temp UI: publish a `PermissionRequested` and see an `access` item on `/events` with `card.items[].trimmable`; `POST /access-answer` reaches the handler; `POST /grants {"action":"list"}` returns rows.
   - Use the `request` / `read_events` / `post` / `ui_port` helpers in `tests/test_temp_ui.py`.
3. Architecture check (core growth ~450 lines in 5 files using only send/publish/find + shared contracts; no module import; the registry special case removed; temp UI grants screen isolated in one file).
4. Docs:
   - `architecture/permissions.md`: core, first piece built, the flow, per-kind grants. A widened grant applies at the next turn-on; a narrowed revoke keeps the fingerprint; a full or workspace revoke removes the grant.
   - README parts row → `src/assistant/core/permissions/`, built.
   - `decisions.md`.
   - API: `core.md` (`PermissionsHandler`, `PermissionsPort`, `PermissionsMenu`; drop `AllowAllPermissions`), `modules.md` (`request_set`), `control.md` (`permissions.*` on the core menu), and messaging (the access types).
   - `reusable.md` (`access_items`, `granted_config`, `request_access`, `manual_claude_mode`, `instances`).
   - The module pages: `job_search`, `task_agents`, `talker`, `temp_ui`.
   - The job-agent note and this note's decisions.
5. `build_docs`, mark the note built in `docs/next-steps/README.md`, then delete this handoff.
6. **Then, as separate steps in the same run, without asking the user whether to carry on** (the user said so on 2026-11-05; hand off to fresh sessions as needed; ask only for a real decision or a risky step; never restart the app; don't push):
   1. **DONE (2026-11-05):** a repeat claim of an agent name by the **same owner** succeeds (`IAgentNames.claim` in `agent_hub`); a different owner is still refused. Add a test in `tests/test_agent_names.py`. Delete `docs/next-steps/handoff-5930027e.md` (the user said yes).
   2. **Usage tallies:**
      - Edit `docs/next-steps/usage-tallies.md` first. Drop the time buckets and the per-time history. Keep only the totals per agent since launch, the dropdown by agent with sub-agents nested, and the Talker as its own row. No spend alerts. The ledger is its own module, with no history after the app closes.
      - Then run one real test with a sub-agent: is its usage in the parent's totals, and do its lines appear in the stream? Record what you verified in the note.
      - Then build the rest with the same architecture-check loop, tests, ruff and doc rebuild, and mark the note built.
   3. At the end, report that everything is ready for the restart (the user is asked about it then), with the architecture-check, test and ruff results.
   4. **Last step, after usage-tallies and the restart tests (approved by the user, docs only, don't ask):**
      - Fold the lasting content of each built note (agent-names, agent-permissions, usage-tallies, and multi-agent and job-agent where built) into the permanent docs, with their diagrams:
        - naming rules and the helper launch flow → `architecture/agents.md` and `api/agents.md`;
        - the permissions design, the card flow and the grants menu → `architecture/permissions.md`;
        - the job agent and the usage design → their module and architecture pages;
        - then update the parts table and the module library.
      - Add the focus and the milestone feed to the bird's-eye diagram, keeping it simple.
      - Leave each note as a short history entry marked built, linking to where its content lives now. Keep `next-steps/README.md` accurate.
      - Rebuild the HTML (docs-html).
   5. **Standing instruction (user, 2026-11-05):**
      - Don't ask about restarts. When the whole list is built, report it's ready, and the Talker restarts the app (not you, not the user).
      - After each restart, test everything the new code touches: the post-restart checks, the permissions card and grants menu, agent names and the duplicate check, helper launch on a card, and the usage ledger and dropdown.
      - If anything fails, fix it, build again, ask for another restart and re-test. Repeat until all of it works.
      - Don't stop until the whole list is built and verified after a restart. Ask only for decisions you truly can't make. Never push.
7. After the restart, the user should look at: the job_search access card (tick boxes, review or "not reviewed"), Allow turning it on, the Grants (rough) screen and its revoke, and the Talker reading a card aloud.
