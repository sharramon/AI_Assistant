# Architecture docs audit

Status: **stages 1 and 2 done 2026-11-13; docs built, 997 tests passed; waiting for the user's check by eye and the decisions under "For the user to decide". Final report at the end.** The user approved the audit and the edits in one go, so stage 2 runs without a stop. Docs only: no code change, no reload, no commit.

This note is also the handoff: if a session resets, carry on from "Stage 2 plan" below.

## How it was checked

Each page was read for orientation, then every claim was checked in the code (`src/assistant/core`, `infra`, `contracts`, `modules`, `tests`). The reference pictures and notes come from [module-flow-and-piping.html](module-flow-and-piping.html), with detail from [piping.html](piping.html) and [module-layouts.html](module-layouts.html). Where the docs and the code disagree, the code wins. Line numbers (L…) refer to the page before the edits.

## Rules the edits must keep (tests are code)

- `tests/test_module_docs.py:61-93`: `docs/architecture/README.md` must keep a `## Restructuring` section (only it may link to the next-steps pages at lines 74-77), and a Pages bullet matching `^- Restructuring \(proposal, not started\):`. The one other allowed next-steps link is README's `../../html-next-steps/module-folders.html`. No other architecture, agents, api or module docs page may link into next-steps.
- `tests/test_module_layout.py:67-72`: `short-overview.md` stays under 6000 characters and names no add-on id.

## Cross-page decisions (who holds what)

| Topic | Home page | Others |
|---|---|---|
| Bird's-eye block diagram, summary, Pages, Parts | README.md | — |
| The host, lifecycle, config and layering, inside the core (pic 3), how modules talk (pic 2), D1 to D6 | core.md | link |
| Commands, events, results, timeouts, the CONTROL table, who may send what | communication.md | core.md keeps a short D3/D5 summary |
| Cards flow, modes, review as a listener, access card, risky steps | permissions.md | core.md: two lines and a link |
| Who is who, where each agent works, which CLAUDE.md (pic 5), Hub as coordination only | agents.md | — |
| Agent code layers | agents-code.md | agents.md links, no class table |
| Folders and files | code-map.md | — |
| Module folder layout, three rules (pic 1) and their tests, found/on/reached (pic 4), module_folders (pic 6), modules.add/remove, needs, hot reload | modules.md | core.md: one line and a link |
| Decision record with the why | decisions.md | pages link to it |

The six reference pictures are copied as standalone files (straight copies, no redraw): `img/core-line-rules.svg` (pic 1), `img/modules-talk.svg` (pic 2), `img/core-inside.svg` (pic 3), `img/addon-found-reached.svg` (pic 4), `img/agents-sessions.svg` (pic 5), `img/module-folders-outside.svg` (pic 6). They depend on the reference page's legend and numbered lists, so each page that uses one carries the legend lines it needs and the list for its numbers.

## Code points found (not changed: this is a docs-only job)

- `core/door.py:25` `CORE_LINE` says the core menu is "list, menu, on, off, reload, add"; it also has `docs`, `remove` and `permissions.*`.
- `infra/agent_names.py:3` docstring says "The Agent Hub applies them"; it's `core/callers.py:42`.
- `agent_hub/module.py:3` docstring says "three parts" and lists two; there are five (TaskBoard, Focus, Delivery, MessageGate, Reviewer).
- `job_search/module.py:244` lists `ModuleStateChanged` twice (once through `AGENT_LISTENS`), so the generated module library shows it twice.
- `scripts/build_docs.py` writes the module library's core row; it leaves out `GetMenu`, `StartProvider`, `ShutdownRequested`, `SetPermissionMode`, `AnswerPermissionRequest`, `AddCardNotes`, the core menu and the card events. The text sits between generated markers, so a hand edit would be overwritten.
- The core still names agents in three spots (the restructuring checklist's open should-fix items): `core/callers.py:22-23` reserves `hub`/`talker`, `core/permissions/handler.py:85` maps a `talker:` prefix, and `core/context.py:53-54,187` lets any `ITaskAgent` provider send `ReloadModule`/`AddModule`.

## docs/architecture/README.md (overview)

- **Bird's-eye mermaid (L9-100):** too detailed, and wrong on the core line. It draws Talker, Main and Hub outside the core, and a "Features" box that mixes core modules (usage, task_agents) with add-ons (cv, job_search). The `starts what requires needs` label is garbled. In the code, core modules are those with `group = "core"` in `docs/docs.toml`. → **replace** with `img/core-line-rules.svg` plus a two-line caption.
- **L102 "Built today…":** a dated status paragraph. It says "The Agent Hub is a module, not part of the core", but the Hub is a core module (`agent_hub/docs/docs.toml:3`). → **delete**; keep 2-3 sentences: the core = host + core modules + door and gate + seven ports; the Hub is a core module that only coordinates (`core/app.py:97-137`).
- **"The core idea" + agents-switchboard.svg (L104-108):** duplicates agents.md, and the picture says the door is "hosted by the Hub" (it's the core's, `core/door.py:1-6`). → **delete** from the overview.
- **Summary (L112-118):** fix the garbled "independent deployment is, for parts…" sentence; add that add-ons may live in outside folders (`[core] module_folders`, `core/loader.py:122-166`). → **edit**.
- **"## Currently fixing" (L120-122):** status. → **delete** (it lives in `docs/next-steps/README.md`).
- **"## Restructuring" (L124-136):** step order with dates and "waiting for restart". The test requires the section. → **edit** down to a one-line pointer with the allowed links only.
- **Pages:** all 14 pages listed. The "Restructuring (proposal, not started)" bullet is stale, but its wording is locked by the test → **user decision** (below). The Voice bullet carries status ("the engine comparison is next") → **edit**.
- **Parts table (all File paths exist):**
  - Module directory: the core menu list lacks `modules.docs` (`core/directory.py:61`).
  - Module Registry: doesn't mention outside folders (`loader.add_module_folders`, `loader.py:143`).
  - Shared Infrastructure: "configuration and logging today; persistence and auth/secrets later" is far out of date. Infra holds the agent kit, `ClaudeSession`, `SessionTaskAgent`, the door relay, `agent_access`, `show_pages` and more.
  - Modules: split into core modules and add-ons; note `module_folders`.
  - CV Tool: drop the dates.
  - Agent Hub: add the `Reviewer` (`agent_hub/review.py:49`).
  - Permissions: drop the "Built: …" wording.
  - Voice handler: trim.
  → **edit**.

## docs/architecture/short-overview.md

2816 characters, names no add-on, mostly accurate.

- "Each is one folder, `src/assistant/modules/<id>/`" leaves out outside folders (`[core] module_folders`) and the gitignored `workspace/` → **edit**, one clause.
- "an agent's data folder is named there, outside the repo": it's optional. Unset, the agent works in its module's `workspace/` (`infra/agent_access.py` `data_folder`, `in_module_folder`) → **edit**.
- Add one clause: the door, agent names and modes are the core's (Callers port), not the Hub's → **add**.
- The checking tests: add `tests/test_module_layout.py` → **edit** (optional).

## docs/architecture/code-map.md

- L5 "First drawn 2026-11-08 from the code review": history → **delete**.
- Mermaid id clash: `subgraph Kit["app_kit"]` (L18) and node `Kit["AgentKit"]` (L46) → **rename** the node `AKit`.
- Core box is missing `Callers` (`core/callers.py:26`), `CoreDoor`/`ModuleDoor` (`core/door.py:28,48`), `MenuTable` (`core/tools.py:37`), `ScopedContext` (`core/context.py:58`) and `PermissionsPort`/`PermissionsMenu`. The `directory` node is `CoreMenu` → **edit**.
- Edges:
  - `Hub -- hosts --> Door` is wrong → `App --> CoreDoor` (hosts `DoorServer`, `app.py:133-161`).
  - Add `Router → dispatch_tool → Perm.confirm` (`tools.py:61-110`, `app.py:110-114`).
  - Add `Callers → Perm` (`mode_of`, `app.py:104`).
  - `PA → Callers` (claims, `profile_agent.py:111`).
  - `Perm -- StartTask (review) --> Hub` → `ReviewAccessList → Hub (Reviewer)`, `AddCardNotes → core` (`permissions/handler.py:6,617-621`).
  - `Talker -- hub.* · viewer.* · usage.* --> Hub` → `InvokeTool → Router` via the door.
  → **edit**.
- Contracts box: add `pages.py` (`IPageOpener`), `door.py` (`IModuleDoor`), `ModuleLogs`/`ModulePermissions` → **edit**.
- Infra box: `AgentKit` "provide · reset · grants" (reset left the kit); add `agent_access` and `developer_rules.md` → **edit**.
- Modules box: the Hub node lists `AgentNames` and "door host" (both gone). The real parts are TaskBoard, Focus, Delivery, MessageGate and Reviewer. Split the box into core modules and add-ons; add `module_folders` → **edit**.
- Apps box: add the CV Tool (`cv/app/cv_tool`); each app sits in its module's `app/` (`loader.add_app_folders`) → **edit**.
- "How it reads":
  - The core imports `app_kit` too (`core/app.py:12-13`).
  - The Hub doesn't host the door.
  - The review is `ReviewAccessList` → the Hub's `Reviewer` → `AddCardNotes`.
  → **edit**.
- Known gaps (L122) is a dated list → **replace** with the open gaps only: the Hub split (not approved); the Hub's free-text "permission allowed" in `TaskUpdated.text` (`agent_hub/tasks.py:395-412`); temp_ui is a stand-in.

## docs/architecture/core.md

- **Intro and "Where the core sits" mermaid (L7-45):** shows Orchestrator, Tools, Views, Workers and "capability interfaces later": a pre-rebuild wish-list → **replace** with `img/core-inside.svg` (pic 3) and `img/modules-talk.svg` (pic 2), each with its legend and numbered list.
- **L51 "seven ports … (built 2026-11-13, decisions D1 to D7)":** the ports are right. The six parts D1 to D6 (door, Callers, router, gate, bus, permissions handler) aren't named, and D7 is the boundary tests, not a port → **edit**.
- **Lifecycle box C (L183) and the `app.py` file row (L159):** `App._handlers` (`app.py:106-124`) also handles `AnswerPermissionRequest`, `ListModules`, `GetMenu` and `StartProvider` → **edit**.
- **Shutdown order (L188-190):** `App.stop` (`app.py:171-182`) runs `cancel_all` → `permissions.close()` → modules stop → door stop → handlers unregistered → bus close; the `permissions.close` step is missing → **edit**.
- **"Module folders outside the repo" (L196):** history and plan ("step 2, built …, waiting on an app restart") → **replace** with one lifecycle line and a link to modules.md.
- **L198 `ShutdownRequested` "(decision D5, 2026-11-13), not an event: publishing one does nothing":** → **edit** to "a command; only modules that list it in `sends` (console_io, talker) can send it".
- **L214, L245, L253:** dated items → **delete** the dates; cut `RemoveModule` to one line and a link.
- **L225 "The control panel UI module that uses it comes later":** → **edit**: temp_ui and the agents use the `modules.*` menu.
- **L259 handover banner:** says the Talker, Main Assistant and Hub have no handover. `agent_hub/module.py:140` and `talker/module.py:173` both `export_state`; only main_assistant has none → **replace** with who hands over. Drop "(checked 2026-11-03)".
- **Callers (L275-279):** facts right; "it was the Agent Hub's" and the banner are history → **edit**.
- **Door (L286-292):** "Built", "not the Agent Hub" and "Menus are no longer in the container" are history → **edit** to "Menus are never in the container" (`tools.py:37-41`). **Add:** a door call goes door → router → gate; `DoorServer.call` uses `router.send` with `sent_by` = core (`mcp_door.py:145-158`, `app.py:134`, `router.py:56`).
- **Gate (L296-306):**
  - "arguments checked, and its callers" applies only to items that ask (`tools.py:101-106`); other items are checked in `Menu.call` (`menu.py:155-162`). A module that provides `IToolProvider` itself gets neither.
  - Start on use runs before the callers check (`tools.py:87-92` before `:105`, ≠6).
  - `modules.off` with dependents is sent as core (≠5, `directory.py:80-82`).
  - The gate answers at once (≠2, `tools.py:109`, `handler.py:286`).
  → **edit**.
- **Access-list review (L310-316):** duplicates permissions.md → **cut** to two lines plus ≠3 and a link; keep the why (`_stop_tasks` only cancels, never starts a task).
- **"Communication internals" (L318-372):** Commands, Who may send what and Events duplicate communication.md → **move** them there; keep the container, tools and directory here.
- **"`sends` is strict" / "`publishes` is strict" (L335, L353):** `handles` is strict too (raises, `context.py:157-159`); `listens`, `listens_named` and `publishes_named` are loose with one log line (`context.py:108,224-231`). The checks run in `ScopedContext`; the router only stamps `core` (`router.py:56`) → **edit** (moves to communication.md).
- **L370 "A future `ToolsChanged` event":** speculation → **delete**.
- **Config table:** add `[core] module_folders` and `reload_idle_timeout`. Strip "(module folders item 12)" and "(item 11)" from the layering. Keep the `data/permissions.toml` copy-once as current behaviour (`store.py:31-41`) → **edit**.
- **"Adding, replacing, or removing a module" (L443-459):** duplicates modules.md → **cut** to one line and a link; keep "contracts grow as needed, not in anticipation".
- **Keep:** the lifecycle flowchart (edited), the state diagram and the log sequence. The `classDiagram` (L61-155) is accurate apart from `CommandRouter.hold`; keep it, with `hold` added.
- **Whys to keep:**
  - The permissions handler is in the core, so nothing can turn it off.
  - Shutdown is a command, so it has one known sender.
  - The control-command rules.
  - Menus are core-private, so no module picks its own caller.
  - The gate answers at once (the router's timeout).
  - Contracts aren't reloadable (`isinstance` identity).
  - No file watcher (it would load half-written code).
  - Cleanup doesn't depend on modules behaving.

## docs/architecture/communication.md

- **L3 "Internals are in core.md#communication-internals":** after the move this page holds them → **edit**; link core.md for pics 2 and 3.
- **Runtime flow and sequence mermaids (L7-16, L47-64):** use a made-up Browser module and `browser.open` → **replace** with a link to pic 2 and its real examples (`cv.task`, `DeliverMessage`, `VoiceTranscript`, `cv.job_finished`).
- **Mechanisms table (L24-25):** "Orchestrator lists all `IToolProvider`s" is wrong: menus aren't in the container (`tools.py:37`). `OpenUrl` and `CreateCalendarEvent` don't exist → **edit**, with `IVoice.listen`, `DeliverMessage` and `ActivateModule` as the examples.
- **L34 and L66 "IToolProviders" / "the argument schema each IToolProvider advertises":** → **edit** to the `ToolSpec`s each menu shows through `GetMenu`. Drop "(built 2026-11-12)".
- **L70 "Built 2026-11-13 (decisions D3 and D5 …)":** → **edit** to a plain link to decisions.md.
- **L73:** add that `handles` is strict, that the listen and named-publish declarations are loose and logged, and that the checks run in the module's context → **edit**.
- **L74 "`DeactivateModule` … come only from a you caller or the core":** add ≠5 (the core menu's `modules.off`/`modules.remove` send as `core`, behind the gate's card) and ≠4 (the Talker's card answers count through `relays`, `context.py:51-52`, `default.toml:46`; open decision G17) → **add**.
- Add the CONTROL table here (from core.md).
- **L89 "disabled or suspended":** there is no "suspended" → "the module is off" (`module_off_text`, `tools.py:113`).
- **Command results:** add that `TimedOut` is always retryable (`messages.py:81`) and `Failed` carries `retryable` (`messages.py:76`).
- **L101 "the lifecycle manager cancels all in-flight commands":** it's the App, with `router.cancel_all()` (`app.py:171`) → **edit**.
- From core.md: one handler per command (`ValueError`), the timeout order, and `CommandRouter.hold` (a send waits during a reload, `router.py:28-38,62-68`) → **add**.
- **Events:** facts match `bus.py`. Merge in core.md's event bullets (base-type subscription, `event_handler_timeout`) → **edit**.
- **Chaining (L79):** facts right; drop "are built" → **edit**.
- **Known gap to note:** !2, job_search reads cv's output by file path, past the door. Link modules.md.

## docs/architecture/permissions.md

- **Status block (L5-13), five dated "Built:" notes:** → **replace** with a short "not built yet" list with no dates: single names, permission sources, permissions required at start, the Main Assistant's own access (`port.py:30-36`).
- **History to delete:** L39 ("the stand-in … is gone"), L56 "(built 2026-11-13)" and the fingerprint sentence, L105, L109 "before, the handler started the review task itself", L148, L167 "as before", L199 "no longer", L319, L333, L335 ("before, the Agent Hub"). Keep one line on `copy_old_grants` (`handler.py:203`).
- **Wrong or stale:**
  - L37 and class diagram L241: `permissions.request` is missing (`permissions/menu.py:40-57`).
  - L56: the own-folder write also covers an add-on folder outside the repo (`infra/agent_access.py:10,56-57,129`); the default workspace is `modules/<id>/workspace` (`agent_access.py:65-73`).
  - L112 "It always answers with `AddCardNotes`": if the reviewer can't start, the Hub answers `not_available` and sends no notes (`agent_hub/review.py:66-68`).
  - L170 gate order: start on use first (`tools.py:87-92`), then the `ask` mark; arguments and `callers` are checked before the card only for asking items (`tools.py:101-106`), else in `Menu.call` (`menu.py:155-162`). Add ≠6.
  - L170 "every road passes the gate": code can also ask through `ctx.permissions.confirm` (the Talker's restart, `talker/session.py:398`) → two entry points, one handler.
  - L325, L9: the mode belongs to each worker and Talker pair, kept in Callers (`callers.py:36,71-78`), set per tab (`temp_ui/page.html:235`); L329's Manual row applies to every task agent.
  - L343-345: "Protected `config/`" is the repo's `config/` only (`permissions/rules.py:17-27`); a config folder set by `ASSISTANT_CONFIG_DIR` (`infra/config.py:40-42`) isn't protected (a known gap to confirm). The Modules zone should name outside add-on folders.
  - L352 worktree branch edits in the present tense: probably planned (self-improvement step 4) → check, then mark planned.
  - Class diagram: `ModulePermissions` lacks `own_agent` and `confirm` (`contracts/module.py:154,170`).
- **Missing:**
  - **How a card travels:** the handler publishes `PermissionRequested` on the bus (`handler.py:491`); temp_ui and the Talker listen; the answer `AnswerPermissionRequest` is a command through the router (`app.py:107`); `PermissionChanged` closes the card (`handler.py:441-445`); the agent gets the outcome as an `AgentNotice` command to the Hub, only logged with no Hub (`handler.py:584-589`).
  - **Who may answer a card:** `AnswerPermissionRequest` and `AnswerPermission` are control commands; only `you` (temp_ui) and `relays` (talker) may send them (`core/context.py:48-55,182-187`; `default.toml:45-46`). G17 is open (≠4).
  - **Two card roads:** (a) the handler's cards (access, grant, revoke, message, confirm); (b) an agent's own tool request: `PermissionGate` sends a `ReportKind.PERMISSION` report to the Hub's task board, answered with `AnswerPermission` (`infra/permission_gate.py:30-46`; `agent_hub/tasks.py:366,383`). L318 calls (b) planned; it's built.
  - **Who sets the mode:** `hub.mode` (callers = Talker, Manual only; `agent_hub/module.py:241-248`); Callers keeps no mode for relays (`callers.py:11,83-85`).
  - **`modules.off` without dependents:** no card; sent as core (≠5, `directory.py:77-82`).
  - Microphone never asked (`port.py:34-36`): said at L175 and L199; keep one.
- **Duplicated:** L333 repeats L170-173 → merge into a small table (who or what → card or not). L335's `SetPermissionMode` chain also lives in runtime.md and api/agents.md → one sentence and a link.
- **Pictures:** keep the access-list sequence, but mark P→U as a bus event, U→P as a command, and `AddCardNotes` as a command. **Add** a cards-flow picture cut from pic 3 (gate → handler ⇄ Callers → bus → temp_ui/Talker → router → handler, with ≠1 to ≠4) as `img/permissions-cards.svg`. Keep the class diagram (edited) and the two planned flows, labelled planned.
- **Whys to keep:**
  - L73: a start can't wait on a card.
  - L114: a command pair, so with no Hub the reply is `not_available` at once.
  - L173: the gate returns at once because the router's timeout would cut it.
  - L350: `PROTECTED` sits in the protected zone.
  - L356: the limit.

## docs/architecture/agents.md

- **History to delete:** the L5/L7 status blocks; dated tags at L61, L91, L96, L314, L318 (and its change-note link), L328, L333, L335, L345, L350, L355, L379, L385. Keep the "why" clauses (L258 "a command, not an event, because the Hub's state must not miss it"; "never an interrupt").
- **"The idea" mermaid (L13-53):** agents drawn inside the Hub, the core without door, gate or Callers, and planned Coding/Research/XR agents → **replace** with `img/agents-sessions.svg` (pic 5) and who is who. Keep "logical, not containment" (L57).
- **Add:** which agents are core (talker, main_assistant, agent_hub, task_agents) and which are add-ons (cv, job_search).
- **L91, CLAUDE.md per agent:** "the `task_agents` helpers work in the repo and load its CLAUDE.md" is **wrong**. Helpers work in `<kind workspace>/<name>`, with defaults `../assistant-helper` and `../assistant-rezi`, outside the repo (`task_agents/module.toml`, `module.py:325`), and get no module-folder grant (`own_folder=False`, `module.py:130,243`). → One row per agent:
  - Talker: no built-in tools, only the door's three (`talker/session.py:247-264`).
  - Main Assistant: `workspace="."`, the repo.
  - cv_agent and job_search_agent: `modules/<id>/workspace`, or the config's data folder; repo CLAUDE.md excluded, developer rules loaded.
  - Helpers: outside the repo.
- **L89, L341, job module:** "when the sweep is done, the module sends an AgentNotice" is wrong: the runner is a stub that notifies at once (`job_search/module.py:161,342`). Missing: `job.tailor_cv` turns cv on and sends `cv.task`, cv's named events come back; `job.open_ui` → **edit**.
- **L90 "The Main Assistant has no module of its own":** it has one (`main_assistant`, a `ProfileAgent` with `COORDINATOR_BLOCK`, `main_assistant/module.py:138-140`), but no menu → **edit**.
- **L121 "the core doesn't know that the Hub, agents or Claude exist":** not quite: the three code points above → **soften**, list them as known gaps.
- **L122, Hub row:** → coordination only: task board, focus, held questions, message delivery, plus the access-list review (≠3); it handles `AnswerPermission` for agent cards (`agent_hub/module.py:80-81`).
- **L133-154, Startup tree:** lists `assistant_view` and terminal 2 (off), misses temp_ui, voice_in and usage. The real on-list is `config/modules.toml`: console_io, agent_hub, main_assistant, talker, temp_ui, voice_in, usage. The core opens the door before any module. task_agents, job_search and cv start off → **rewrite**.
- **L226-234, class table:** "MainAssistantModule composed from SessionTaskAgent, ClaudeSession" is really `ProfileAgent` + `AgentKit`; it duplicates agents-code.md → **delete**, link.
- **L219-224, ITaskAgent table:** misses `answer_permission`, `set_permission_mode`, `reset`, `note`, `request_approval` (`contracts/agents.py:200-218`) → one line and a link to the API.
- **L238-260, "Who sends what":**
  - The Talker doesn't send `StartTask`/`SendToTask` commands: it sends `InvokeTool` (hub.* items), `AnswerPermissionRequest`, `ResetRequested` and `ShutdownRequested` (`talker/module.py:113`).
  - "Planned: both agents find module tools through the directory" is built.
  - The terminal-2 View box is stale.
  → **redraw** as a mermaid: Talker → door → gate → hub.*; agents → ReportTask; events to temp_ui.
- **L161-207, sequence diagrams:** label `hub.start`/`hub.send` as going through the door → gate.
- **L364-376, launch sequence:** `agents.launch` goes through the door → gate (≠2).
- **L347, three kinds:** add `cv_agent` (`named_only`; started by `cv.task`, callers job_search_agent and main_assistant; `cv/module.toml`).
- **L337, Limits:** add the exception: a module's own folder under a wider grant.
- **L391, "The Hub encompasses all agents":** contradicts coordination only → "one coordination layer; the Hub holds no agent".
- **Possible duplication:** L289-341 (task state, questions, delivery, message gate) overlaps `agent_hub/docs/architecture.md` and runtime.md → trim to a summary and a link.
- **Notes for this page:**
  - ≠3: the review is a Hub task.
  - ≠4 / G17: the Talker may answer cards.
  - ≠1, ≠5: link permissions.md.
  - !2: job_search reads cv's output by path.
  - !5: `claudeMdExcludes` covers only the repo's files (`infra/agent_profile.py:121-125`), so an agent under an outside module folder may load a parent CLAUDE.md, and the developer rules point at repo paths.
  - Unverified: whether the Talker and the helpers load any CLAUDE.md (it depends on cwd and Claude Code's lookup).

## docs/architecture/agents-code.md

- L5, L18, L20, L24, L25: dates and "gone/now" wording → **delete**.
- L19: add cv to the modules with a worker (`cv/module.py:278`).
- Add `AgentProfile.command`: `repo_claude_md=false` gives `--settings {claudeMdExcludes}` plus `developer_rules.md` (`infra/agent_profile.py:116-136,222-249`; `claude_session.py:69-70`), the code side of pic 5.
- Mermaid 1, L51 `tk_hub["_hub InvokeTool hub.*"]` in TalkerSession: there is no `TalkerSession._hub`; sessions call `TalkerModule.hub` (`talker/module.py:245`) → move or rename.
- Mermaid 2, L152 "planned: to its agent's session": built (`talker/module.py:299-323`) → delete "planned".
- Mermaid 3 matches `core/tools.py:61-110`; optionally mark ≠6 and ≠2.
- Known limits (L275-279, verified `core/directory.py:80-99`): add the three code points above and !5.

## docs/architecture/modules.md

- **L13, the declarations table:**
  - "The core warns when a module handles a command it didn't list": `ctx.handle` raises and the module fails to start (`core/context.py:155-159`).
  - Add `uses`, `needs`, `packages`, `publishes_named`, `listens_named`; the named publishes are loose (`context.py:108,224-231`).
  → **edit**.
- **L42 "`modules.remove` … is refused while another module needs it":** never refused; dependents stay on and the reply names them (`lifecycle.py:197-211`, `app.py:283-319`, `directory.py:95`). L194 already says so → **edit**.
- **L42, core menu:**
  - Missing `modules.docs` (`directory.py:61`) and `permissions.grants/grant/request/revoke` (`permissions/menu.py:28-59`, `app.py:129`).
  - `modules.off` asks only when `with_dependents` is true (`ask_when`, `directory.py:80`).
  - Mention `ask="risky"` with a link to permissions.md.
  → **edit**.
- **L109 "modules never import MCP", example "Resi or Unity":** cv imports the `mcp` client for Rezi (`cv/mcp.py:33,391`) → "never serve MCP; one may be an MCP client", with the `rezi.*` menu as the example. The `list_changed` refresh claim is unverified (no `list_changed` in cv) → drop.
- **Door mermaid (L62-90):** `Notes -- StartListening --> Core` is wrong: voice_notes calls `IVoice.listen` directly (`voice_notes/module.py:9-14,97,137`) → **replace** with a link to pic 2.
- **Chaining mermaid and text (L124-144):** `StartListening`, the "planned: a session destination" edge and "follows its own sessions by the StartListening id" are stale. The call is `IVoice.listen(id, VoiceDestination.CALLER)`, built → **edit** the text, drop the mermaid, link pic 2.
- **L151 "`needs = []` (cv, and job_search since …)":** every `module.toml` has `needs = []` except voice_notes (`["voice_in"]`); the core list leaves out voice_in → **edit**; split the paragraph; config layering moves to a link to core.md; the defaults go in the folder layout section.
- **L183 "the core group stays in the repo":** only tests check it (`tests/test_boundaries.py:180-183,228`); the loader doesn't refuse (!1) → **edit** and add the gap. The `module_folders` detail moves here from core.md.
- **L173, hot swap:** add `assistant.testkit` to the shared code (`loader.py:44`).
- **History to delete:**
  - L5 status block.
  - L16 "Built (2026-11-05) …" (many modules have menus now).
  - L26-48 "Before the refactor", "Step by step" and "What changes", with the three history pictures. L48 "All of it is planned and needs an app restart" is false.
  - L52, L54 status lines ("before, the Agent Hub hosted it").
  - L115, L148, L161, L171, L177 status blocks and dated "(module folders item N)" fragments.
  - L165 "They used to send InvokeTool viewer.open…".
  - L185-208 "Built and planned" table → a short "not built yet" list: packages aren't installed automatically, parallel voice sessions, the data-types table generation.
- **L155** duplicates L150-151 → merge.
- **L111 "Agent Hub (focus, held questions, milestones)"** → "coordination: task board, focus, held questions, message delivery".
- **L54 "In Manual, `use_item` asks with Claude Code's own card":** "for task agents; the Talker has no gate of its own". The Talker part is unverified.
- **Missing (this page holds it):**
  - **Folder layout:**
    - `__init__.py` (one `ModuleProtocol`).
    - `module.toml` (defaults, `needs`, `packages`; every folder has one, `test_module_folders.py:648`).
    - `app/` (companion app, found by folder, `loader.py:38-40,169-187`).
    - `tests/`, and `docs/` (`docs.toml` group).
    - `workspace/` (gitignored, cv and job_search).
    - Optional `ruff.toml` (cv) and `static/` (temp_ui).
    - Tripwire `test_nothing_of_an_add_on_is_outside_its_folder` (`test_module_folders.py:919`).
  - **The three rules (pic 1) and their tests.** test_boundaries numbers them its own way (imports; core settings name no add-on; core needs only core; plus "core starts alone", `test_boundaries.py:1-25,208-240`). Also `test_no_core_code_names_an_add_on` (`test_module_folders.py:804`). Tests catch breaks only when pytest runs.
  - **module_folders:** absolute paths only (`loader.py:122-135`; why: the core may run on a server); each folder is appended to `assistant.modules.__path__` after the repo's (`loader.py:143-166`); an id found twice is a `LoadError` at startup; folders are read at launch (inferred, `loader.py:272`).
  - `modules.add` refuses an already-loaded package and an existing id (`lifecycle.py:177-187`).
  - Start on use for tools as well as contracts (`app.py:233-258`); a call to an off module answers `module_off_text` (`tools.py:113`).
- **Notes for this page:**
  - ≠5: core-menu paragraph.
  - ≠6: start-on-use paragraph.
  - !1: "you" trusted by module id, `callers.py:80`; only `test_boundaries.py:180` catches an outside `temp_ui`.
  - !3: the twice-found check runs only at startup (`loader.py:156`; `modules.add` doesn't check, `lifecycle.py:172-188`).
  - !4: the add card doesn't show the folder (`tools.py:107-109`).
  - !2: workspace section, link the job_search page.
  - !5: link agents.md.
- **Whys to keep:**
  - One door, not plain MCP.
  - Sessions, not copies (one mic).
  - Named events (no restart, each side reloads alone).
  - `needs` vs `requires` (start order vs code contract).
  - Absolute `module_folders` paths.
  - Menus out of the container.
- **Pictures:** use pic 1 (three rules), pic 4 (found, on, reached), pic 6 (module_folders); link pic 2 for chaining.

## docs/architecture/module-library.md

- The generated tables match the code (`tests/test_module_docs.py` passes): 14 modules. The core group is agent_hub, assistant_view, console_io, main_assistant, talker, task_agents, temp_ui, usage, voice_in; the add-ons are cv, echo_orchestrator, html_viewer, job_search, voice_notes.
- The doubled `ModuleStateChanged` in job_search's row and the incomplete core row are code points (above); not editable by hand.
- L9 "(decided 2026-11-12; it replaces the 2026-11-06 rule…)", L5 "(since 2026-11-05)": history → **delete**. L21 "assistant_view (for now)" → drop "(for now)".
- L15, README's Config section "is its `[modules.<id>]` section": settings are `module.toml` defaults, then `config/<id>.toml`, then `<id>.local.toml`, then `local.toml` (`app.py:359-367`) → **edit**.
- Data types table (if hand-written): add `GetMenu`, `ActivateModule`, `DeactivateModule`, `RemoveModule`, `StartProvider`, `AnswerPermissionRequest`, `PermissionRequested`, `PermissionChanged`, `FocusChanged`, `FocusSuggested`, `SetFocus`, `ModuleEvent`, `cv.job_finished`/`cv.job_submitted`; check the `ReviewAccessList`/`AddCardNotes` anchors.

## docs/architecture/communication.md, decisions.md, principles.md disagreements

### decisions.md

- **Edit:**
  - L18: the handler maps a `talker:` prefix to its pair's mode (`handler.py:85,435`); add relays; delete "allow-all stand-in … gone", "special start order … gone", the dates.
  - L17: trim the `data/permissions.toml` copy to one clause.
  - L20: drop the history; keep the rule, `app_kit` and the one import path.
  - L22: describe the module shape as built; drop the plan pointer.
  - L23: "The core hosts it (D1)".
  - L26: on-demand chaining: rule plus a one-line why (`job_search/module.py:376`).
  - L38: the Talker as a relay for card answers is listed as decided, but G17 is open → move it to Open with today's behaviour; keep "never for Auto" as decided (`callers.py:83`).
  - L43 repeats D4 → merge.
  - L27-34: drop the "same day" story; D7 = boundary tests guard the core line, with its why.
  - L52: `IVoice` is decided; only parallel voice sessions stay open.
  - L16, L12: drop the dates.
  - L21: tighten "a restart with reset instructions…".
  - "Deliberately deferred … until two or three very different modules are built": condition met → **user decision**.
- **Add decided entries, each with its why:**
  - Manual off is never refused; `needs` is start order only; a failed needed module doesn't stop its needers.
  - An off module answers `not_available`; the agent asks before `modules.on`; only `start_on_use` providers start by themselves.
  - `modules.remove(settings=keep|purge)`: asks, never refused, purges only `config/<id>.toml` and `.local.toml`, never deletes the folder or edits `modules.toml` (`app.py:283-314`). Supersedes module-folders decision 41's "refuses while needed".
  - `modules.add` asks, in Auto too (it loads new code).
  - Only you set Auto; sessions start in Manual; Manual from anyone.
  - The Hub is coordination only.
  - Router and bus split (commands with a stamped `sent_by`, events only notify).
  - The core line and groups (voice_in stays core).
  - Module folders, layout step 1 (`config/` holds your choices only; `generated/` is rebuildable).
  - The repo CLAUDE.md imports only the short overview; module agents skip it and load the developer rules.
  - Module agents' workspace and the optional data folder.
  - Every module may edit its own folder; task_agents helpers don't.
  - The `module_folders` mechanism.
  - Pages open through `IPageOpener`.
- **Open, to match what's really open:**
  - Keep persistence, the UI handler, self-improvement permissions, parallel voice sessions.
  - Add G17.
  - Add the add-on move itself and step 7.
  - Add a per-add-on CLAUDE.md and a session-only write grant on the add-ons folder.
  - Add the code-versus-data split in workspaces.
  - Add whether `extension-marketplace.md` is superseded.
  - Add the three core-names-an-agent points and the known gaps !1, !3, !4 and the microphone.

### principles.md

- P3: add "menu tools".
- P4: state the core line (what the app can't start without; arrows one way; `tests/test_boundaries.py`).
- P11: "Dependencies are respected" → `needs` is start order, a manual off is never refused.
- P12: drop the date.
- P14 Today: add the Talker's menu.
- P15 Today: the door is the core's; `show_page` only parses the tag and `open_page` goes through `IPageOpener` (`infra/show_pages.py`).
- P17: the "optional would make a cycle … the Hub's door" example is stale (`AGENT_USES`, `infra/agent_kit.py:42`); add the outside `module_folders`; drop the dates.
- P18: the Hub wires `TaskBoard`, `Focus`, `Reviewer`, not `AgentNames` (`agent_hub/module.py:95,108,115`).
- P21: "never name a module" is broken by `callers.py:23` and `handler.py:85` → add a "Today:" line naming them as open.
- L40: drop "added on 2026-11-08 after the code review".
- Numbering 1-22 stays (P13 is referenced from CLAUDE.md).

### docs/agents/self-improvement.md

No contradiction.

## docs/architecture/reusable-parts.md, remote-clients.md

- reusable-parts:
  - L5 dated status → **delete**.
  - L38 "The voice service still sits in `src/`" is false (it's in `voice_in/app/voice_service/`) → **delete**.
  - L32 "(2026-11-13)" → plain statement.
  - Optionally add `agent_access` and `AgentKit`.
- remote-clients:
  - "the orchestrator invokes them through `InvokeTool`" → any agent, through the door.
  - The language-neutral schema and `clients/` don't exist → mark planned.

## docs/api and docs/agents (only where they contradict)

- **api/core.md:**
  - L36 "no longer an event": delete.
  - L64 "(the Agent Hub hosted the do…)": delete.
  - L318 "no longer come this way" → "Pages go through `IPageOpener`".
  - L316: add ≠6.
- **api/messaging.md L115:** "(command; an event until 2026-11-13)" → delete the history.
- **api/tools.md:**
  - L80, L111: delete the history.
  - L101: link decisions.md, not the checklist.
  - L96: the argument and callers check is for asking items; others are checked in `Menu.call`; ≠6.
- **api/control.md:**
  - L3: list `AnswerPermission` and `AnswerPermissionRequest` (relay-only, `context.py:51-52`). The `ReloadModule`/`AddModule` check only tests for `ITaskAgent` (`context.py:187`); the Allow is the agent's own `PermissionGate` card (`session_agent.py:790`). Through the menu the sender is core (≠5).
  - L57 `permissions.request` "always your card": in Auto it's granted at once (`handler.py:387-389`); an agent with no access list is refused (`handler.py:366-368`).
  - L56, L58 grant/revoke from an agent in Auto run at once (`handler.py:354,408`).
  - L64 revoke: the `message:`-only case keeps the module on (`handler.py:681-682`).
  - Delete the dates (L60, L62, L98, L115, L170, L174).
- **api/README.md:**
  - L57 `AnswerPermissionRequest`: only you or a relay may send it.
  - L78: the gate order (≠6).
  - L120: mark `AnswerPermission` as a control command.
  - L113 auto = "no prompts": confirm cards and `RELOAD:`/`ADD_MODULE:` cards still show in Auto (`handler.py:279`, `permission_gate.py:219`).
  - L163 AgentKit "reset": no longer in the kit.
  - L17: add `module_roots`, `in_module_folder`, `developer_rules`.
  - L50, L127, L133 "(an event until 2026-11-13)": delete.
- **api/infra.md:**
  - L302, L489, L410: dated history → delete.
- **api/testkit.md:**
  - L23, L43 "(module folders item 11)": delete.
- **api/reusable.md:**
  - L108: history, delete.
  - L22: the Event Bus sits under Contracts → move it to Core host.
- **api/agents.md:**
  - L383 "Used by: talker and main_assistant through the door" → every agent with the door.
- **agents/README.md:**
  - L28 "Talker: no tools" → no built-in tools, only the door's three.
  - L39 "not enforced until the permissions handler is built": it's built.
  - L44 "one Main Assistant and one active task": several agents (`max_extra_agents=3`).
  - L9-13: add module agents and helpers.
  - L40: a missing line break.
- **agents/runtime.md:**
  - L484 "the planned pairs": built.

## Pictures

| Picture | Plan |
|---|---|
| `core-line-rules.svg` (pic 1) | README (block diagram) and modules.md (three rules) |
| `modules-talk.svg` (pic 2) | core.md; linked from communication.md and modules.md |
| `core-inside.svg` (pic 3) | core.md |
| `addon-found-reached.svg` (pic 4) | modules.md |
| `agents-sessions.svg` (pic 5) | agents.md |
| `module-folders-outside.svg` (pic 6) | modules.md |
| `permissions-cards.svg` (add) | permissions.md: a cut of pic 3, card arrows only |
| `agents-switchboard.svg` | stale ("door hosted by the Hub", "next big agent (later)"); off README and agents.md, replaced by pic 5 and pic 2 |
| `agents-below-hub.svg` | stale (same error, "next agent's module (later)"); off agents.md, replaced by pic 2 |
| `agents-modes.svg` | labels match the code; keep on agents.md |
| `agents-code-layout.svg` | stale (Hub's `_Door`/`_Names`, AgentNotice as an event, no Callers, gate or cv); off agents-code.md, whose three mermaids (corrected) carry the layers |
| `module-directory-1-before.svg`, `-2-steps.svg`, `-3-changes.svg` | history (before/after); off modules.md, replaced by pic 4 |
| Mermaids | replace: README bird's-eye, core.md "Where the core sits", communication.md both, modules.md door and chaining, agents.md "The idea" and "Who sends what" (redraw); fix: code-map (edges, id clash), agents-code (1, 2), permissions sequence (arrow kinds), core.md classDiagram (`hold`) |

The stale SVG files stay on disk. `docs/next-steps/agent-talkers.md:125-128,175` embeds the four agents-* files, and `module-system.md` / `module-shape-refactor.md` link the module-directory ones; those are change notes. `agents-switchboard.svg` also has uncommitted changes. Deleting them is the user's call (below).

## Good to know and Known gaps for the architecture docs

As current-state notes, each on its home page:

- ≠1: risky core-menu items card even in Auto (`directory.py:80-99`): permissions, core.
- ≠2: the gate doesn't wait; on Allow the handler runs the step (`tools.py:109`, `handler.py:285,554`): core, permissions.
- ≠3: the review is a Hub task; notes come back as `AddCardNotes` (`review.py:66,96`): permissions, agents.
- ≠4 / G17: the Talker relays card answers (`context.py:51-52`, `default.toml:46`); whether they count as yours is open: permissions, communication, agents, decisions (Open).
- ≠5: `modules.off` without dependents gets no card and is sent as core (`directory.py:77-82`): permissions, communication, modules.
- ≠6: start on use runs before the callers check (`tools.py:87-92` vs `:105`): core, permissions, modules.
- Door calls go door → router → gate (`mcp_door.py:145-158`): core.
- Listening is loose; publishing and handling are strict (`context.py:108,157-159,224-231`): communication.
- !1: "you" is trusted by module id (`callers.py:80`): permissions, modules.
- !2: job_search reads cv's output by path (`job_paths.json` `cv_output`): modules, agents, communication.
- !3: the twice-found check runs only at startup (`loader.py:156`): modules, core.
- !4: the `modules.add` card doesn't show the folder (`tools.py:107-109`): modules, permissions.
- !5: `claudeMdExcludes` covers only the repo's files (`agent_profile.py:121-125`): agents, agents-code.
- The microphone is never asked (`port.py:34-36`): permissions.
- A config folder outside the repo isn't in the protected zone (`rules.py:21-27`): permissions (to confirm).
- The core still names agents in three spots: agents-code, principles (P21), decisions (Open).

## For the user to decide

1. The overview's Pages bullet must start "Restructuring (proposal, not started):" (test-locked, `tests/test_module_docs.py:88`), but the restructuring is built. Change the test and the wording?
2. Delete the stale SVG files (the agents-* three and module-directory-* three) even though change notes still show them?
3. decisions.md "Deliberately deferred … until two or three very different modules are built": the condition is met. Rewrite or drop it?
4. A config folder outside the repo (`ASSISTANT_CONFIG_DIR`) isn't protected: record it as a known gap (done) or fix it in code? **Answered 2026-11-13: fixed in code, protected like `config/` (writes refused, reads allowed); [outside-config-protected](outside-config-protected.md), built, waiting for the restart.**
5. The code points listed above (docstrings, `CORE_LINE`, the doubled event, the generated core row): fix in a code task? **Answered 2026-11-13: fixed in code, the core row generated from `App.offers()` with a tripwire test; [audit-code-fixes](audit-code-fixes.md), built, waiting for the restart.**

## Stage 2 plan

Six editors, one group of files each, so no file has two editors; one Write per file. Afterwards: one docs build, the tests, the architecture check, the final report below.

| Editor | Files |
|---|---|
| A | core.md, communication.md, api/core.md, api/messaging.md, api/tools.md |
| B | permissions.md, api/control.md, new img/permissions-cards.svg |
| C | agents.md, agents-code.md, agents/README.md, agents/runtime.md, api/agents.md |
| D | modules.md, module-library.md, api/modules.md |
| E | README.md, short-overview.md, code-map.md, reusable-parts.md, remote-clients.md, api/README.md, api/infra.md, api/testkit.md, api/reusable.md |
| F | decisions.md, principles.md |

## Final report (stage 2)

### Per page

- **README.md (overview):**
  - Bird's-eye only: `img/core-line-rules.svg` with the three rules, a five-point summary, the Pages list and the Parts table.
  - Parts: Modules split into core and add-ons; infra, Registry (outside folders), the core menu (`modules.docs`) and Hub (`Reviewer`) fixed.
  - Removed: "Currently fixing", the status paragraph, the switchboard image.
  - `## Restructuring` cut to one line.
  - Left: the test-locked bullet wording.
- **short-overview.md:** adds outside module folders, `workspace/`, the optional data folder, "the door, names and modes are the core's (Callers)", and `test_module_layout.py`. 3100 characters, names no add-on.
- **core.md:**
  - Pic 2 and pic 3, each with its legend and list (T/C/E; 1-13, P7, ≠1-≠6), and a D1-D6 parts table.
  - Fixed: the handler list, the shutdown order (`permissions.close`), who hands over (only main_assistant doesn't), the gate order (≠6), door → router → gate.
  - Config gains `module_folders`, `reload_idle_timeout` and `restart_exit_code`.
  - Gaps !1, !3, !4 and the microphone.
  - Commands, events and CONTROL moved to communication.md. The review, `module_folders`, remove and "adding a module" are cut to links. The whys are kept.
- **communication.md:**
  - The made-up Browser mermaids are replaced by real examples and links to core.md's pictures.
  - Holds the CONTROL table, strict vs loose declarations, `hold`, retryable results, ≠4, ≠5 and !2.
- **permissions.md:**
  - Undated "Built / Not built yet" box.
  - "How a card travels" with the new `img/permissions-cards.svg` (a cut of pic 3), and "Two card roads".
  - Modes per agent pair (Manual from anyone, Auto only from you); the sequence diagram marks commands vs bus events.
  - Zones: the repo's `config/` only; outside add-on folders added.
  - Good to know ≠1-≠6, Known gaps; G17 under Open questions. Worktree branch edits marked planned (no code makes a worktree).
  - Left: the "(built)" headings, because other pages and change notes link `#access-lists-built` and `#permission-mode-built`.
- **agents.md:**
  - "Who is who" with pic 5 (legend, notes 1-4); a core/add-on agents table; a "where each works / which CLAUDE.md" table (helpers work outside the repo).
  - The Hub as coordination only; job and cv notes fixed (the job runner is a stub; `job.tailor_cv`).
  - Startup tree rewritten; "Who sends what" as a new mermaid; sequences use `hub.*` through door → gate.
  - Class table removed; switchboard and below-hub pictures removed; Good to know and known gaps section.
  - Renamed anchor: "The Agent Hub: the switchboard" → "coordination only" (nothing linked it).
- **agents-code.md:** the SVG is replaced by a layers table; adds `AgentProfile.command`'s CLAUDE.md part; mermaid fixes (the `hub` box, "planned" removed); the gate quirks; three known limits plus !5.
- **modules.md (full rewrite):**
  - Sections: the module folder, the three rules (pic 1) with their tests, find and open a menu (pic 4 with the A/P table), the core's menu, module folders outside the repo (pic 6, !1-!5), turning on and off, dependencies, a "Not built yet" list.
  - Fixed: `handles` is strict, remove is never refused, `modules.off` asks only with dependents, `needs`, cv as an MCP client, `IVoice.listen`.
  - Removed: the before/after section, its three pictures and both mermaids.
- **module-library.md:**
  - Hand-written parts only: dates removed, the Config description fixed, a note on what the generated tables leave out, 17 more data types.
  - The generated text is untouched.
- **decisions.md:**
  - Decided is grouped (Platform, Core line, Modules, Agents, Permissions), each entry with a why and a link; every missing rebuild decision added.
  - Open matches what's really open: G17, the add-on move, a per-add-on CLAUDE.md, code vs data, extension-marketplace, the core naming agents, the known gaps.
  - "Deliberately deferred" left as it was. Step 7 not listed (nothing defines it).
- **principles.md:** numbering 1-22 kept; P3, P4, P11, P12, P14, P15, P17, P18 and P21 fixed (P21 gets a "Today:" line for the two exceptions).
- **code-map.md:** mermaid redrawn: the id clash fixed, the core's real classes, the door hosted by the core, the review as `ReviewAccessList` → `AddCardNotes`, modules split into core and add-ons, the CV Tool. "How it reads" fixed; Known gaps lists only what's open.
- **reusable-parts.md, remote-clients.md:** status and false lines removed; remote clients marked planned.
- **docs/api:**
  - README: four permissions fixes, AgentKit, the infra list, dates, the Event Bus under Core host.
  - core, messaging, tools: history removed, ≠6, door → router → gate, the context checks. messaging.md wrongly said the core refuses to turn voice_in off; fixed.
  - control: the card answers, sent as core, Auto, no access list, `message:` revoke, the `ListModules` order.
  - modules: four fixes.
  - agents: Used by.
  - infra, testkit, reusable: history removed.
- **docs/agents:** README (roles, the Talker's tools, the handler clause, limits); runtime.md (history wording at the audited spots).
- **Pictures:** six reference pictures copied into `img/` plus the new `permissions-cards.svg`. No longer used by any architecture, agents or api page: `agents-switchboard.svg`, `agents-below-hub.svg`, `agents-code-layout.svg`, `module-directory-1-before.svg`, `-2-steps.svg`, `-3-changes.svg`. They're kept on disk because change notes still show them (decision 2).

### Deliberately left

- Many dated "built …" tags in `docs/agents/runtime.md`, `docs/api/infra.md` and the API "Used by" lines (the audit scoped those pages to contradictions only).
- messaging.md's planned voice items.
- The generated module-library text.
- No code touched (the code points are listed above).

### Checks

- `.\.venv\Scripts\python scripts\build_docs.py`: passed (74 pages to docs/html, 132 to docs/html-next-steps).
- `.\.venv\Scripts\python -m pytest`: **997 passed**, 2 deselected, 4 warnings (unclosed-pipe ResourceWarnings in two subprocess tests, not docs-related). This includes the doc tests: no next-steps links, the short overview's size, module docs.
- The anchors the editors flagged exist: `core.md#lifecycle`, `#configuration`, `#reloading-a-modules-code`, `permissions.md#risky-steps-ask-even-in-auto`, `modules.md#dependencies`.
- No dates, "no longer", "used to" or "hosted by the Hub" left in `docs/architecture/*.md` (two hits are real data: a log folder name and the `StartListening` command).
- Anchor sweep (follow-up session): 935 anchored links in docs/architecture, docs/agents, docs/api and module docs pointing into architecture; no broken file or anchor. All 7 `img/*.svg` files the architecture pages use exist; the 6 stale ones are unreferenced.
- Ruff not run: no Python touched.

### Not verified

- **No picture was looked at rendered**: the seven SVG files and the redrawn mermaids (code-map, agents "Who sends what").
- `permissions-cards.svg` is a fresh cut with labels placed by estimate.
- Not every intra-doc anchor was swept (only the flagged ones).
- Which CLAUDE.md the Talker and the helpers load: unsettled in code; the agents page says so.
- "The Talker has no gate of its own" (pic 4, P1): taken from the reference, not checked in code.

### Architecture check (docs part, at the end)

- **Modularity:** the pages now state the core line as the code has it (core = host + core modules + door/gate + ports; add-ons talk only through tools, events and contracts); the three places where the core still names agents are listed as open, not hidden.
- **Reuse:** no helper moved; `docs/api/reusable.md` only lost history wording and moved the Event Bus row to Core host. The pictures are reused from the reference page, not redrawn.
- **Fit with the main app:** each topic has one home page (table above); communication.md holds the message rules and core.md the pictures.
- **Diagrams:** replaced: README, core, communication, modules, agents. Fixed: code-map, agents-code, permissions sequence. Added: permissions-cards.

### Files edited more than once

- This note (Write, then the status line and this report).
- tools.md (a heading put back for five inbound links).
- modules.md (a voice wording fix).
- agents.md (the `cv.job_submitted` name).
- runtime.md, api/agents.md, api/infra.md and api/reusable.md: one Edit per spot, by design.

### Pages to check by eye

- `docs/html/architecture/index.html` (overview)
- `docs/html/architecture/core.html`
- `docs/html/architecture/permissions.html` (new cards picture)
- `docs/html/architecture/agents.html`
- `docs/html/architecture/modules.html`
- `docs/html/architecture/code-map.html` (redrawn mermaid)
- `docs/html/architecture/decisions.html`

### Next (a fresh session, only if wanted)

Nothing required. Optional: sweep every `*.md#anchor` link in docs/architecture, docs/agents and docs/api against the headings; then act on the user's answers to "For the user to decide" 1-5.

## Cleanup

The user's answers (2026-11-13): 1 yes, 2 yes (and delete out-of-date notes), 3 drop. 4 and 5 are code tasks for later.

**What the cancelled run left:** nothing from this cleanup. No file deleted, no Cleanup section, the overview's Restructuring bullet, the test and the decisions.md line all unchanged. Every other change under `docs/` and `tests/` in `git status` comes from the audit stages before it.

**What the test guarded:** `tests/test_module_docs.py::test_main_docs_never_link_into_next_steps` keeps the permanent docs (architecture, agents, api, module pages) from linking into the change notes, which come and go. The one exception the user allowed is the overview's `## Restructuring` section and its one Pages bullet, and only to a fixed set of notes. The exact wording "(proposal, not started)" only found that bullet. The new wording "(built …)" does the same job, so the test still finds the one bullet and still refuses any other next-steps link.

**Pictures to delete** (`docs/architecture/img/`; the build regenerates `docs/html`, so their copies go too):

- `agents-below-hub.svg`: stale (draws the door and names in the Hub); no page uses it.
- `agents-code-layout.svg`: stale (the Hub's `_Door`/`_Names`, no Callers or gate); no page uses it.
- `module-directory-1-before.svg`, `module-directory-2-steps.svg`, `module-directory-3-changes.svg`: before/after history of the module-system build; no page uses them.
- **Kept:** `agents-switchboard.svg`. The repo's root `README.md` still shows it, so it's still in use (your call: swap the root README's picture for `core-line-rules.svg`, then delete it).

None of the notes embeds these pictures. They name them only as text, so no picture link breaks.

**Notes to delete** (`docs/next-steps/`, with their built copies):

- `job-cv-result-via-tools.md`: its own status line says it was replaced by job-cv-finish-event.
- `hub-folder-check-parent.md`: cancelled, never built; replaced by agent-talk-and-questions.
- `handoff-b31b8901.md`: done; superseded by handoff-2389decf.
- `handoff-8c52a851.md`: "done, committed, nothing left to carry on".
- `handoff-4dca192a.md`: built; its current state lives in job-cv-finish-event, and the rest is history.
- `handoff-9bc35422.md`: finished; the restart and hand checks it leaves are in agent-talk-and-questions.
- `handoff-da696d15.md`: the mid-build state of job-cv-start-order, which is now built and reloaded; that note holds the current state.
- `handoff-0873d2c8.md`: the overnight module-folders run, finished (the checklist is 20 of 20, committed); its rules were for that run only.

**Kept as judgement calls (for you):**

- `module-shape-refactor.md`: superseded, but module-system.md still calls its "Diagrams to update" table the full list of doc changes.
- `handoff-73fc479c.md`: its build is done, but door-at-session-start.md's hand check still points at its item 3.
- `handoff-5eff4e83.md`: stale (in progress on 2026-11-12), but named-module-events.md links it.
- `handoff-20c1d08e.md`: the cv-pdf-only build, waiting on you (it alone notes `CV_Test_SWE.odt` at 0 bytes).
- `handoff-d81801ee.md`: done, waiting for your review of piping.html.
- `handoff-dce225ad.md`: holds your decisions that replace manual-off-never-refused's part 2.
- `handoff-e519644c.md`: cv_agent's own note.
- `rezi-module.md`, `two-agent-states.md`: replaced or folded into other notes, but their Pending rows aren't closed.
- Every note whose Pending row still says "waiting on you", plus the ones the task named to keep.

**Links fixed:** the three Pending rows for deleted notes in `docs/next-steps/README.md`; agent-talk-and-questions.md (line 3) and handoff-5eff4e83.md (line 45) now name the deleted notes as plain text.

**Item 3:** the `## Deliberately deferred` section of decisions.md is dropped (its one line was the whole section), and the overview's Pages line now says "decided and open". No decision was waiting on that line: the section held nothing else, and nothing in the Open list points to it.

**Second batch (2026-11-13, the judgement calls, approved by you):**

- `module-shape-refactor.md`: superseded by module-system (built); its docs table was out of date. Mentions in module-system, job-agent and voice-notes are plain text.
- `handoff-73fc479c.md`: the agent-permissions build log, done. Its helper-launch hand check is now one standalone, still-open line in door-at-session-start.md (not marked passed).
- `handoff-5eff4e83.md`: the smoke test, all stages passed; named-module-events names it as plain text.
- `handoff-20c1d08e.md`: the cv-pdf-only build, live. Its one fact kept here: the base CV folder's CV_Test_SWE.odt has been 0 bytes since 2026-11-08 (the PDF copy is fine; outside the repo, left untouched, your call).
- `handoff-d81801ee.md`: the piping.html arrows, done; the pictures moved into module-flow-and-piping.html.
- `handoff-dce225ad.md`: its decisions (1 to 5) are all in manual-off-never-refused.md and the code (`_note_missing_needs`, the "isn't on" answer in `core/tools.py`).
- `handoff-e519644c.md`: cv_agent's page-settings note, built (`page_settings` in cv).
- `rezi-module.md`: replaced by the cv module; its Pending row is closed, and module-folders-launch-check names it as plain text. `task_agents/module.toml` (the rezi helper's comment and prompt) still names the path; that's module code, left for a code task.
- `two-agent-states.md`: built via agent-talk-and-questions step 3; its Pending row is closed and the links there are plain text.
- `agents-switchboard.svg` (both copies): stale; the root README now shows `agents-sessions.svg`. agent-talkers and restructuring-checklist name it only as plain text (history).
