# A new grant reaches a running agent without turning it off and on

> **Status: built, waiting on the restart (2026-11-06).** The third session finished `task_agents` (`launched_config`, `_on_grant` per kind, `subject=kind`), the tests (the full suite passes) and the docs. The user approved plan B as written below, in one batch with [the Auto button](per-agent-auto-button.md) and [voice to the stop tab](voice-to-stop-tab.md) (both built, waiting on the restart). The open questions take the recommended answers: (1) an idle open session restarts at once; (2) a revoke still turns the module off; (3) "Allow always" later; (4) `permissions.request` from the Main Assistant is refused with a reason. It needs one app restart; after that, grants apply live.

## Handoff (2026-11-06): build this in a fresh session

**Hard rules from the user:** they're working with sub-agents. Don't restart the app, don't reload any module, don't turn modules on or off. Write the code and run only the tests that run on their own (in-test `App`s, fake programs); list any test that needs the running app or a restart for later.

**Done in the first session:** the Auto button per tab (`temp_ui`, `talker`) and `StopListening.agent_id` (`contracts/voice.py`, `voice_in`, `temp_ui`); 67 tests in the touched files pass, ruff clean, docs updated. The Talker-window item from `agent-talkers.md` ("every question and statement reaches the Talker window in full") was **skipped**: that note has no spec for it.

**Done in the second session (code written, NOT yet tested, ruff not run):**
- `contracts/module.py`: `ModulePermissions.own_agent(agent_id, subject)` (non-abstract, no-op default); `core/permissions/port.py` forwards it to `handler.own_agent`.
- `core/permissions/store.py`: `Grant.added` (items the agent asked for itself, beyond the config list), `with_added`, `with_granted` covering asked + added; saved/loaded as `added = [...]` (only when non-empty).
- `core/permissions/handler.py`: `_agents` registry + `own_agent`; `request(caller, items, reason)` (checks the registry and the `IAgentNames` owner, refuses workspace items, drops already-granted and refused ones, opens a `grant` card with `adds=True`); `_apply` adds the items via `with_added` on Allow; an access card keeps the earlier added items; `grant()` accepts added keys; `grants()` rows have `added`; the active-module message now says "applies from its next session (at once when idle), with no need to turn it off".
- `core/permissions/menu.py`: `permissions.request` (`read`, `write`, `commands`, `python`, `chrome`, `reason`; folders resolved).
- `infra/agent_access.py`: `granted_config` adds granted items beyond the config's list; `watch_grant(ctx, on_grant(subject, granted), subject=None)` (exported from `assistant.infra`).
- `infra/agent_profile.py`: `REQUEST_PROMPT` (shown when `requests` and the door); `requests` field from config `permission_requests`; `command(..., snips=)` adds a `Read` rule and an access line for the snips folder.
- `infra/session_agent.py`: `write_folders` property and setter.
- `infra/profile_agent.py`: `subject=` param (calls `ctx.permissions.own_agent` at start, sets `permission_requests`), `snips()` (`ctx.logs.folder()/snips`, read at each session start), `set_access(config)` (sync rebuild, then an idle open session restarts in a background task `_regrant`, which `stop` cancels).
- `modules/job_search/module.py`: `PermissionChanged` in `listens`, `watch_grant(..., subject=agent_id)` in `init`, `_on_grant` → `set_access(granted_config(...))`, `subject=` passed to `ProfileAgent`.

**Done in the third session:** everything below. Not done: a starting-Auto config key (`start_mode`) the user asked about mid-build; a config can't start an agent in Auto today (decision 8), so it waits on their answer.

**Was still to do (third session, done):**
1. `modules/task_agents/module.py`: add `PermissionChanged` to `listens`; `watch_grant(ctx, self._on_grant)` in `init`; keep `self._kind_of[agent_id] = kind` for autostart agents; move the launched helper's config (lines in `_launch`: `workspace/name`, kind folder read-only, `write_dirs=[]`, `transcript`) into one function `launched_config(name, base)`; `_on_grant(kind, granted)`: `base = granted_config(self._kinds[kind], granted)`, then autostart agents of that kind get `instances(kind, base)[id]`, launched ones get `launched_config(name, base)`, each via `set_access` (catch `AccessDenied`); `_build` passes `subject=kind` to `ProfileAgent`.
2. Tests (in-test Apps and the fake claude only): update `test_permissions_handler.py::test_grant_and_revoke_from_you` ("applies the next time" → "applies from its next session"); update `test_directory.py:92`'s list to include `permissions.request`; add: a grant reaches job_search's next session command (`job.profile.command(...)` has the new read rule, and `agent.info().write_folders` changes); an idle open session restarts; a busy one doesn't; a task_agents kind updates all its helpers; `permissions.request` from a registered agent opens a card and Allow saves `added`, and `granted_config` keeps them; from `main_assistant` (not registered) it's refused; store round trip with `added`; the snips rule is in `command(..., snips=...)`. Then the whole `pytest`, `ruff check`.
3. architecture-check; docs: `architecture/permissions.md`, `api/infra.md` (`set_access`, `watch_grant`, `snips`, `subject`), `api/modules.md` (`own_agent`), `api/control.md` (`permissions.request` on the core menu), `api/reusable.md` (`set_access`, `watch_grant`), `modules/job_search.md`, `modules/task_agents.md`; rebuild with `scripts\build_docs.py`; this note's status and its Pending row → built, waiting on the restart.
4. Final report for the whole batch (see step 6 below).

**Original plan, in this order** (follow `batching`, `architecture-first`, check `docs/api/reusable.md`):
1. Read `infra/profile_agent.py`, `infra/session_agent.py`, `infra/agent_access.py`, `infra/agent_profile.py`, `core/permissions/handler.py`, `menu.py`, `store.py`, `modules/job_search/module.py`, `modules/task_agents/module.py`, and their tests, once each.
2. Live grants: `ProfileAgent.set_access(config)`, a `write_folders` setter on `SessionTaskAgent`, `watch_grant(ctx, module_id, subject, on_grant)` in `agent_access`; `job_search` and `task_agents` (one function for a launched helper's config) use them; the handler's message for an active module.
3. Snips: `AgentProfile.command` adds a read rule for `ctx.logs.folder()/snips` at each session start.
4. `permissions.request` on the core menu (caller → module and subject through the name claim), added items in the saved grant, `request_access` / `granted_config` taking them, the prompt line.
5. Tests as listed under Touches; `pytest`, `ruff`; architecture-check; docs (`permissions.md`, `api/infra.md`, `api/core.md` or `control.md` for the menu item, `reusable.md`, `job_search.md`, `task_agents.md`); rebuild; this note's status and the Pending row → built, waiting on the restart.
6. Final report to the Talker for the whole batch: what was built, tests passed, tests skipped, hand checks after the restart (Auto in the job agent's tab; stop the mic then switch tabs; a grant reaching an idle agent with no off and on; an agent asking with `permissions.request`; an agent reading a snip with no card).

**Asked:** "If I give it a new permission, it has to turn itself off and on. This is not how it should work. Once I give it permission, it should just have permission." (about `job_search_agent`). Then: build the real fix for every agent, so that after the next app restart grants apply on the fly, with no further restarts.

**Why:** today a grant is saved at once, but the running agent never hears of it.

## Why it needs off and on today

1. `job_search` and `task_agents` ask for access **once, when the module starts** (`request_access`). They cut the config to the grant (`granted_config`) and build each `ProfileAgent` from that.
2. `ProfileAgent` builds its `AgentProfile` **once** (folders, commands, Python, Chrome) and hands `write_folders` to `SessionTaskAgent` **once**.
3. The `claude` command line *is* rebuilt at every session start (`ClaudeSession` calls `profile.command(...)` each time, and each task starts a fresh session). But it reads that fixed profile, so the rules and the "Your access" part of the prompt stay as they were.
4. `permissions.grant` saves the wider grant and publishes `PermissionChanged`, but no agent module listens to it. The handler even says *"the change applies the next time it's turned on"* (`core/permissions/handler.py`, `_do_grant`).
5. The config file is reread only on `modules.reload` / `modules.add` (`App._swap`), not on off and on.

## What you do until it's built

- **An item already on its list** (`permissions.grant`): `modules.off` then `modules.on` for the agent's module (this waits until it has no task).
- **A new item not in its config yet:** edit the config, `modules.reload <module>`, then Allow on the card.
- No full app restart is needed in either case.

## The plan (B, every agent)

```
permissions.grant ──► PermissionChanged(module_id, subject, granted)
                           │
        agent module (job_search, task_agents) listens: is it my grant?
                           │  granted_config(its config, granted)
                           ▼
        ProfileAgent.set_access(config) ── new AgentProfile, new write_folders
                           │
        idle open session: restarted once (as for the door) · busy: its next session
```

- **`ProfileAgent.set_access(config)`** (infra, reusable): rebuilds `profile` from the new granted config and hands `SessionTaskAgent` its new `write_folders` (a small setter there). An idle open session restarts once (`restart_session`, the way the door is picked up today). A running turn is never cut: it picks up the change at its next session (the next task or a handoff).
- **`watch_grant(ctx, module_id, subject, on_grant)`** (infra, `agent_access`, reusable): subscribes to `PermissionChanged` and calls `on_grant(granted)` for a non-empty grant of that module and subject. One helper for both modules, so the matching rule lives once.
- **`job_search`** uses `watch_grant` with subject `job_search_agent`, and calls `set_access(granted_config(...))`.
- **`task_agents`**: grants are per kind (subject = kind), so a change applies to every agent of that kind, autostarted and launched. The launched helper's own changes (its sub-folder, the kind folder as read-only, its transcript) move from `_launch` into one function, so a launch and a grant change build the same config.
- **The handler's message** for an active module becomes "applies from its next session; no need to turn it off".
- **Revoke stays as it is:** it turns the module off at once, the safe way to take access back.
- **Not changed:** the Main Assistant (no access list), and a brand-new item that isn't in the config yet (that still needs a config edit, a module reload, and the card).

## Added: an agent asks for a permission itself

You asked that any task agent, or a subagent, can ask for a permission by itself. You get a card, click Allow, and it's granted on the spot with no restart.

**What exists today**

| Path | What it does | The gap |
|---|---|---|
| A tool prompt (`can_use_tool` → `ReportTask` permission → card → `AnswerPermission`) | An agent's tool call outside its rules asks you on a card | **Allow is once only.** The next identical call asks again; nothing is saved |
| `ITaskAgent.request_approval(action, run)` | A module asks you, on the agent's card, before running something for it (e.g. `agents.launch`) | One action, not a grant |
| `permissions.grant` on the door (`core` menu) | An agent may call it; a card opens; Allow saves the grant | **Only items already on its config list** (`only asked items can be granted`). The caller must name the module and subject, which an agent doesn't know. The grant applies only after off and on |
| `ctx.permissions.request_set` | A module asks for its whole access list when it starts | Module-side only; an agent can't call it |
| Subagents | Run inside their parent's `claude` process, under the same rules; their tool prompts come up as the parent's card (to confirm in a test) | Same as the first row: Allow once |

**What's missing, and the plan**

1. **`permissions.request` on the door** (core menu): an agent asks for new items (a folder to read or write, a command, Python, Chrome) with a reason. The handler finds the caller's module and subject from its id (the module that claimed the name, through `IAgentNames`, and the subject the agent module gave for it), so an agent can only ask for itself. You get a card listing the items; Allow, untick some, or Deny. The answer reaches the agent as a note.
2. **Saved grants may hold items beyond the config.** On Allow, the new items join the saved grant (both `asked` and `granted`). `request_access` builds the list from the config **plus** the grant's added items, so the next start doesn't ask again for what you already allowed. `granted_config` takes those added items too.
3. **Live from then on:** the same `PermissionChanged` → `set_access` path above. An idle agent has the access at once; a busy one gets it at its next session (or once the card is answered and its current turn ends).
4. **Prompts:** the agent's "Your access" section tells it to use `permissions.request` when it needs more access, instead of saying it must be restarted.
5. **A subagent** asks through its parent, so the grant goes to the parent agent and every later subagent of that agent has it too.
6. **Your snips, readable by every agent with no card** (asked 2026-11-06 from the rezi tab). Snips and pasted images are saved in this launch's log folder (`logs/<launch>/snips/`), whose name changes every launch, so a fixed config path can't cover it. Instead, `AgentProfile.command` adds a read rule for `ctx.logs.folder()/snips` at every session start, built in like the workspace. It holds only what you snipped, so it needs no card and isn't on the access list. Until then, Allow the one-off card when an agent opens a snip.

**Touches:**
- **Code:** `infra/profile_agent.py`, `infra/session_agent.py`, `infra/agent_access.py`, `infra/agent_profile.py` (the prompt line), `modules/job_search/module.py`, `modules/task_agents/module.py` (both list `PermissionChanged` and tell the handler their agents' subjects), `core/permissions/handler.py`, `menu.py`, `store.py` (the message, `permissions.request`, added items), and `contracts/agents.py` if the subject has to ride on the `IAgentNames` claim.
- **Tests:** a grant reaches the next session's command line, an idle session restarts, a busy one waits, a `task_agents` kind updates all of its helpers.
- **Docs:** `architecture/permissions.md`, `api/infra.md`, `api/reusable.md` (`set_access`, `watch_grant`), `modules/job_search.md`, `modules/task_agents.md`.

**Reload or restart:** infra and core change, so this needs **one app restart**. After it, grants apply live, with no more restarts or off and on.

**Open questions:**
1. Should an idle agent's open session restart at once on a grant, or only at its next task? **Recommended: at once**, so a question you answer right after granting already has the access. (With fresh sessions per task, the difference is small.)
2. Should a revoke also go live (narrow the agent without turning it off)? **Recommended: no**, keep turning it off. Taking access back should be immediate and certain, and a running turn can't be narrowed.
3. Should a tool prompt's card also get an **"Allow always"** button that turns that one call into a saved grant (a `Read` of a folder becomes a read item, a shell command becomes a command item)? **Recommended: later, as a second step.** `permissions.request` covers "the agent asks"; "Allow always" also needs the UI and `AnswerPermission` (a contract) to change.
4. The Main Assistant has no access list, so `permissions.request` from it is refused with a reason. **Recommended: keep it so for now.** Its access is the repo, set in the config.

**Restart with the addition:** still **one app restart**, the same one (core, infra and maybe a contract change). After it, asking, granting and applying all happen live.

## Stopgap done 2026-11-06: Chrome for every task agent

- The job agent already had Chrome (in its config and its saved grant; its sessions connect to Chrome).
- `chrome = true` was added to `[modules.task_agents]`'s defaults, so every kind (`helper`, `rezi`) asks for Chrome. Each kind's list changed, so its next launch shows a card.
- In Manual, each Chrome action still asks you with a card. Auto (the toggle in the agent's tab) stops that.
