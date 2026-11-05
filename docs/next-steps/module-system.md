# Module system: one interface, a directory, menus everywhere

> **Status: building (2026-11-05).** Approved 2026-11-05: you sent the whole refactor to run unattended in Auto. Progress per chunk and the choices made on the way: [Progress and decision log](#progress-and-decision-log). **Supersedes** the [module shape note](module-shape-refactor.md) (approved 2026-11-04, never built). Its design stays on the [Modules](../architecture/modules.md) page, and its "Diagrams to update" table is still the full list of doc changes. This note adds the one interface, puts every module in the build order, and brings in the agents.

**Asked:** rework all tools, modules and the architecture around modules, so everything is hot-swappable. Every module is a wrapper with inputs and outputs (a menu), the main system knows which modules exist, and the Talker and Main Assistant can find modules and call them. One reusable module interface (`ModuleProtocol`) that every module implements, and every existing module recoded with it in mind.

**Why:** today the wrapper exists but the menu doesn't. Only `html_viewer` has a menu, written as a separate `IToolProvider` class. Manifests have no description. The Talker is hardcoded to the viewer's tools. The Main Assistant can't call any tool. Modules are listed by hand in `__main__.py`.

## What exists and what's missing

| Piece | Today | Missing |
|---|---|---|
| Interface | `Module` (`contracts/module.py`): an abstract class with no state. It has `manifest`, `init` (required), and `start` / `stop` / `busy` / `export_state`, which do nothing unless a module overrides them | The name `ModuleProtocol`, and a `menu` |
| Manifest | id, provides, requires, optional, permissions | `description`, `handles` (commands), `publishes` / `listens` (events) |
| Menu | `IToolProvider` + `ToolSpec` + `InvokeTool` → `dispatch_tool`. Only the viewer has one, written as its own class | A `Menu` part declared on the module, readable without starting it, with the arguments checked against each item's schema |
| Hot swap | `ReloadModule`, `AddModule`, `ModuleStateChanged` (built 2026-11-03) | Companion apps (voice, viewer) restart with the module. Today a reload keeps the old service code |
| Directory | `ListModules` → `ModuleInfo` (id, state, contracts) | One line per module (`ModuleInfo.description`), a `GetMenu(module_id)` command, and the core's own menu (module control as menu items) |
| Found by folder | `MODULES` list hand-written in `__main__.py:21-43` | The core scans `src/assistant/modules/`, reusing `core/loader.py` |
| Boundaries | `ctx.handle` accepts any command class | Only commands in `assistant.contracts` that are listed in `handles`. A `ctx.logs` port replaces the `LogSink`s in config |
| Voice contract | `voice_in` handles `StartListening` / `StopListening`; one listener at a time | An `IVoice` contract with sessions and a destination; `voice_notes` requires it |
| Agents using it | Talker: SHOW tags → `viewer.*`. Main Assistant: no tool path; the viewer watches its tags | Both use list → menu → call (decision 2) |

## The target shape

**`ModuleProtocol` is a thin protocol (decided 2026-11-05).** A protocol is an interface a class satisfies by having the right members; it is not a `Contract` (a capability looked up through the container), so it has no `I` prefix. It's today's `Module` renamed, with one new optional attribute; modules subclass it to get the do-nothing defaults. It does no work itself, and everything with behaviour is a part the module owns ([principle 12](../architecture/principles.md)).

| Member | Required? | What the module puts there |
|---|---|---|
| `manifest` (class attribute) | yes | Who it is (id, one-line `description`), what it needs (`requires`, `optional`, permissions) and its inputs and outputs (`handles`, `publishes`, `listens`, `provides`) |
| `menu` (class attribute) | no, default none | A `Menu`: the actions an assistant or another module may call |
| `init(ctx)` | yes | Keep `ctx`, subscribe, handle commands, build its parts |
| `start()` / `stop()` | no | Start and stop its work; `stop` frees everything |
| `busy()` / `export_state()` | no | "Don't reload me now", and what to hand to its new copy |

**What a module owns:** its `manifest` and `menu` (plain data on the class, the same for every copy), its `ctx` (given to each copy at `init`), and its own parts (`CompanionApp`, a `Menu`, later `ctx.logs`).

**What a `Menu` holds:** one item per action, each with a name, a one-line description, a JSON Schema for its inputs (a `ToolSpec`), and the module method that runs it. The core reads it without starting the module, for the directory and the generated module library. When the module is on, the core links the items to that copy. It checks the arguments against the schema (`invalid_arguments` if they're wrong) before calling the method. The module never calls `ctx.provide(IToolProvider, ...)`; `IToolProvider` stays as the core's adapter for `InvokeTool`.

**Before and after: `html_viewer`.** Today it carries a 45-line `_ViewerTools(IToolProvider)` class with a hand-written argument check for each tool:

```python
# Before
class HtmlViewerModule(Module):
    manifest = Manifest(id="html_viewer", provides=(IToolProvider,))
    async def init(self, ctx):
        ...
        ctx.provide(IToolProvider, _ViewerTools(self))     # + class _ViewerTools: tools() and invoke()

# After
menu = Menu()

class HtmlViewerModule(ModuleProtocol):
    manifest = Manifest(
        id="html_viewer",
        description="View, edit, highlight and snip HTML pages",
        publishes=(ViewerTabsChanged, ViewerClip), listens=(AgentActivity,),
    )
    menu = menu

    async def init(self, ctx): ...                          # no provide line

    @menu.item("viewer.open", "Open an HTML file in the viewer",
               {"path": {"type": "string"}, "front": {"type": "boolean"}}, required=["path"])
    async def open(self, path: str, front: bool = False) -> Result:
        return await self.show(path, front)
```

- **Inputs and outputs** are the menu plus `handles` (commands in) and `publishes` / `listens` (events). The core checks `handles`. The [module library](../architecture/module-library.md) table is generated from them.
- **The directory** is the core's: `ListModules` (one line each) → `GetMenu(id)` → `InvokeTool`. The core's own menu offers `modules.list / on / off / reload / add`, and the risky ones ask you.
- **Hot swap** stays as built. `ModuleProtocol`, `Menu` and the manifest live in `contracts` and are never reloaded. A module's methods are, so a reloaded module's menu runs its new code.

## Build order (each chunk ships on its own; riskiest last)

| # | Chunk | Modules recoded | Restart? | Tests |
|---|---|---|---|---|
| 1 | Rename `Module` → `ModuleProtocol`. New manifest fields (`description`, `handles`, `publishes`, `listens`). `ctx.handle` warns on an unlisted command, then refuses after chunk 9 | All 10 (rename and fields, no behaviour change) | Yes | Manifest validation; the handles check; `test_module_docs` |
| 2 | `Menu` part (items, schema check, read without starting, linked to the running copy by the core). Generate the module library table from the manifests and menus | `html_viewer` (its `_ViewerTools` goes), `echo_orchestrator` | Yes | Item → `ToolSpec`; bad arguments → `invalid_arguments`; viewer tools unchanged; a reload runs the new method; generated library matches |
| 3 | Directory: `ModuleInfo.description`, `GetMenu`, the core's menu (`modules.*`) with your approval for the risky ones | none | Yes | List / menu / call; approval asked for off-with-dependents |
| 4 | Find by folder; the `MODULES` list goes; folder name = manifest id | `assistant_view`, `console_io` (folder checks) | Yes | Scan a temp folder with a fake module; a bad folder is skipped and logged |
| 5 | `ctx.logs` port | `temp_ui`, `html_viewer` | Yes | Sinks reached through `ctx.logs`; nothing in config |
| 6 | Voice contract `IVoice`: sessions, destination | `voice_in`, `voice_notes`, `temp_ui` (mic button) | Yes for the contract, then `RELOAD` | Two sessions with the fake engine; each gets only its own text |
| 7 | Companion apps follow the module: off quits, on starts, "reload with restart" | `voice_in`, `html_viewer` | Yes (`app_kit`) | `CompanionApp` quits an adopted app; reload brings up new service code |
| 8 | The MCP door (decision 2): a small MCP server in the app with three fixed tools (list modules, show a menu, use an item), passed to each `claude` session; its calls go through the permission card. The Main Assistant uses it; the viewer stops watching its SHOW tags | `main_assistant`, `html_viewer`, `agent_hub` | Yes (`infra`) | Call the endpoint directly: a call reaches `InvokeTool` and returns its result; permission asked; one real-`claude` test |
| 9 | Talker drops the hardcoded viewer mapping and uses list → menu → call. Commands become strict | `talker` | Yes | Talker tests via the generic path; SHOW still opens pages |

Each chunk ends with the `architecture-check` skill, the docs rows it triggers (the old note's table: items 2/5 → chunk 1, 6 → 3, 4 → 4, 3 → 5, 8 → 6, 1 → 3 and 7, 7 → 8 and 9), and a docs rebuild. Chunks 8 and 9 come last because they change the agents that run this work. A slip there breaks the assistant itself, so each one is done in a Claude Code session, not from inside the app.

**Restarts:** every chunk touches the core or contracts, so the app is restarted once per chunk, which you do. After chunk 2, a change to a single module is just a `RELOAD`.

## Docs and diagrams

- **Everywhere:** `Module` becomes `ModuleProtocol` in the docs (API, architecture, module pages). Principle 12's naming rule now explains protocols (done 2026-11-05).
- **Modules page:** the status line points here. The menu row says "a `Menu` part on the module". "Built and planned" ticks off per chunk.
- **Module library:** the table between its markers is generated (chunk 2), and its hand-written note goes.
- **API:** `ModuleProtocol` and `Menu` (each with a reusable-index line, used by every module). `Manifest` gets its fields, Control gets `GetMenu` and the core's menu, Tools lists `modules.*`, Messaging gets `IVoice`.
- **Overview chart:** already draws the target. Each piece drops its planned style as its chunk lands. Parts table rows as in the old note.
- **SVGs** `module-directory-2-steps` / `-3-changes`: mark steps built (sources in `docs/architecture/img/`).
- **Principles 14 to 17:** shorten each "Today:" line as its chunk lands.

## Connection to the job agent

Not now (decision 4). Agents will use or live inside modules, so the [job agent](job-agent.md) is built after this rework, as a new module on `ModuleProtocol`. Its gaps become module-shaped:

| Job-agent gap | As a module |
|---|---|
| Agent registry | The directory, filtered to modules that provide `ITaskAgent`. No separate list |
| Naming an agent | The agent's module id (`job_agent`, `main_assistant`) is its name. `StartTask.agent_id` takes it |
| Talking to it directly | Its menu: for example `job.status`, `job.ask`, `job.next`, wrapping `GetTaskStatus` / `SendToTask` for that agent |
| Agent cap | A limit on how many `ITaskAgent` modules are on or working at once, checked by the core when one is turned on (chunk 3's approval path) |
| Folder and access code | Moves to shared infra, with a config section per agent module (already in that note) |

## Decisions

1. **The interface: decided 2026-11-05.** It's kept thin (no behaviour), and modules implement it. The menu is a `Menu` part the module owns, not protocol behaviour. Its name is decision 3.
2. **How the agents reach the menus: decided 2026-11-05, A (one door).** Why, in plain words, with the picture: [modules](../architecture/modules.md#why-one-door-and-not-an-mcp-server-per-module). The agents call tools through MCP, as one adapter at their edge only (the rule below). The options were:
   - **A. One door (recommended).** One MCP server in front of the core with three fixed tools: list modules, show a menu, use an item. The agents' tool list never changes when a module is swapped, on, or off, and the server only reads the directory. If the HTTP link from `claude` to the app fails, a small stdio relay that `claude` starts passes the calls on.
   - **B. A door per module.** Each module's menu items show up as their own MCP tools. The agent sees them directly, but its tool list changes with every swap. The experiment shows `list_changed` handles that, at the cost of a notice per change and a longer tool list.

   Both cost the same: a small server and port in the app, its calls through our permission card, and one real-`claude` test (the fake `claude` doesn't speak MCP). The untested piece, an HTTP server inside our app, is checked as a spike alongside chunk 1. The `TOOL:` reply line is kept only as the fallback if that spike fails.
3. **The name: decided 2026-11-05, `ModuleProtocol`.** Principle 12's rule stays: the `I` prefix only for `Contract` subclasses. The rule now has a plain-words note on what a protocol is, with `ModuleProtocol` as the example.
4. **Order: decided 2026-11-05.** The module rework comes first. No work on the job agent now: agents will use or live inside modules, so it waits until the rework is done.

**The MCP rule (agreed in discussion):** MCP is one adapter at the agents' edge, on top of the wrapper. Modules are never MCP servers and never import MCP. Traffic between modules, and from the UI to a module, stays commands, events and contracts. The wrapper gives what MCP doesn't: events and commands between modules (principle 16), contracts and `requires` (principles 2, 3, 17), hot swap in one process (principle 11), per-module permissions, the directory (principle 15), and callers that aren't agents, like UI buttons. MCP adds only standard mid-reply calls from Claude sessions.

## Progress and decision log

| # | State | Commit | Restart needed |
|---|---|---|---|
| 1 | built: `ModuleProtocol`, the manifest fields, the `handles` warning, all 10 manifests filled | see `git log` ("Module system, chunk 1") | yes (contracts, core) |
| 2 | built: `Menu` part (`contracts/menu.py`), the core's `MenuTools` adapter linked after `init`; `html_viewer` (its `_ViewerTools` gone) and `echo_orchestrator` (`echo.say`) on it; the module library's table generated by `scripts/build_docs.py` | see `git log` ("Module system, chunk 2") | yes (contracts, core) |
| 3 | built: `ModuleInfo.description`, `GetMenu` (read from the class, on or off), the core's own menu `modules.list / menu / on / off / reload / add` (`core/directory.py`, id `core`), the risky items asking the permissions first | see `git log` ("Module system, chunk 3") | yes (contracts, core) |
| 4 | built: `find_modules()` in `core/loader.py` scans `src/assistant/modules/` (id = folder name, a bad folder skipped and logged); `__main__.py`'s `MODULES` list is gone; `AddModule` refuses a folder named differently from its id | see `git log` ("Module system, chunk 4") | yes (core, `__main__`) |
| 5 | built: `ModuleLogs` contract, `ctx.logs` (`folder()`, `sink(name)`) backed by `core/logs.py` `SessionLogs`; `App(..., logs=)`; `wire_modules` gone, nothing log-related in config; `talker`, `main_assistant` (transcripts), `temp_ui` (Logs button), `html_viewer` (snips) use it | see `git log` ("Module system, chunk 5") | yes (contracts, core, `__main__`) |
| 6 | built: `IVoice` + `VoiceDestination` (`contracts/voice.py`); `voice_in` provides it (`_Voice` part, same sessions as the commands, `finish` ends only its own id); `voice_notes` requires it, no longer sends commands; the temp UI keeps the commands | see `git log` ("Module system, chunk 6") | yes (new contract) |
| 7 | built: `CompanionApp.code_changed()` (`source_stamp`) and `stop(adopted=True)` in `app_kit`; `voice_in` and `html_viewer` hand their app over on a reload unless its code changed, else quit it so the new copy launches the new code; `html_viewer` gained the handover | see `git log` ("Module system, chunk 7") | yes (`app_kit`) |
| 8 | built: the one MCP door. `infra/mcp_door.py` (a stdio relay `claude` starts, and the app-side `DoorServer`), the `IModuleDoor` contract provided by `agent_hub` (port and token handed over on reload), `main_assistant` passes it as `--mcp-config` to each new session (read-only tools allowed, `use_item` asks in Manual) | see `git log` ("Module system, chunk 8") | yes (contracts, infra) |
| 9 | not started | | |

**Decisions taken while building** (the most conservative choice each time, for you to check):

- **D1 (chunk 1): a `sends` field too.** The plan listed `handles`, `publishes`, `listens`. The module library also has a "Calls" column, so `Manifest.sends` (commands out) was added; with it the whole library table can be generated in chunk 2.
- **D2 (chunk 1): no `Module` alias.** `Module` is renamed outright, with no old name kept. The app needs a restart for chunk 1 anyway, and a second name would hide unconverted code.
- **D3 (chunk 1): the manifest checks itself.** The id must be a Python identifier (folder names are, and chunk 4 needs id = folder), the description one line, `handles` / `sends` only `Command` types and `publishes` / `listens` only `Event` types. Wrong ones raise when the module's file is imported.
- **D4 (chunk 2): our own small schema check, no `jsonschema`.** Installing a package needs your OK, so `Menu.check` covers what menus use: required, unknown arguments, `type`, `enum`, `minLength` (trimmed, so `"  "` is empty, as the viewer checked before). Swap in `jsonschema` later if menus need more.
- **D5 (chunk 2): the menu's items are the module's own methods.** The viewer's existing `show` / `highlight` / `tabs` are decorated directly; no wrapper methods. A plain return value becomes `Result.ok`.
- **D6 (chunk 2): `IToolProvider` stays public.** Modules use `Menu`; `IToolProvider` stays for providers whose tools change at runtime (the gateway, later) and the core's `MenuTools`. The echo stand-in's `/tools` still lists every provider, so it now lists its own `echo.say` too.
- **D7 (chunk 2): the library's "On" column is the default config.** Generated from `config/default.toml` `modules.enabled`, not your `.local` override, so the docs don't change with your machine. Its "Contracts" column is new (provides / requires / optional); the hand-written "Handles: `InvokeTool` (its tools)" became the "Menu" column.
- **D8 (chunk 3): the core's approval goes through a permissions object, today the allow-all stand-in.** There's no handler that can ask you yet, so `modules.off` with dependents and `modules.add` call `permissions.request(...)` on `AllowAllPermissions("core")`, which allows and logs. When the permissions handler lands (or the MCP door in chunk 8 puts agent calls through the permission card), they ask you. `modules.reload` doesn't ask: reloads are routine (`RELOAD:` lines).
- **D9 (chunk 3): the core's menu has the id `core`, reserved.** `Manifest(id="core")` now raises. `ListModules` stays modules only; `GetMenu("core")` and `modules.menu` give the core's items, and the door (chunk 8) will add a `core` line to its list.
- **D10 (chunk 4): a bad folder is skipped, not fatal.** One broken module folder doesn't stop the app: it's logged as a warning and the rest load. If that module is in `modules.enabled`, startup still fails, with the existing "Enabled modules not found". Folders starting with `_` are ignored. `AddModule` checks id = folder only for packages directly under `assistant.modules`, so tests and other roots can still add packages of any name.
- **D11 (chunk 4): `App(available, ...)` keeps its parameter.** `__main__` passes `find_modules()`; tests keep passing their own classes. Every module folder is still imported at launch, as the old static imports did.
- **D12 (chunk 5): `ctx.logs` covers the Talker and Main Assistant too.** The plan named `temp_ui` and `html_viewer`, but "nothing in config" also meant the transcript sinks `wire_modules` put into `talker` and `main_assistant`'s sections, so both now ask `ctx.logs.sink(name)`. Config keeps only the file name. Without a `LogSession` (tests), `sink` gives a plain `Path` under `logging.dir`, which `ClaudeSession` already accepts; an absolute name stays absolute.
- **D13 (chunk 6): one mic, sessions owned by their caller, not parallel.** The voice service takes one listener, so `IVoice` keeps "the second press wins". What's new is that each caller opens its session under its own id and `finish(id)` never ends anyone else's (before, `StopListening` stopped whatever was open). Parallel sessions would need a service change, left for later (open in [decisions](../architecture/decisions.md)).
- **D14 (chunk 6): the caller makes the session id.** `listen(session_id, destination)` takes the id rather than returning one, so the caller can follow `VoiceState` / `VoiceTranscript` from the very first event (they can arrive before `listen` returns).
- **D15 (chunk 6): the temp UI keeps `StartListening` / `StopListening`.** The commands stay as the UI button's form, backed by the same session code, so the throwaway temp UI isn't reworked. It doesn't list `IVoice`; its mic says "voice input is off" when no handler is there, as before.
- **D16 (chunk 7): "reload with restart" is automatic, no new command field.** A reload compares the companion app's source with what it was when the module started using it (`CompanionApp.code_changed()`: newest `.py` mtime and file count). Changed: no handover, and the old copy quits the app; unchanged: handed over. No `ReloadModule(restart_apps=...)` flag, so nothing in the contracts changed.
- **D17 (chunk 7): turning a module off still quits only an app it launched.** A viewer or voice service you started yourself stays open on `DeactivateModule`; only a reload with changed code quits an adopted one (`stop(adopted=True)`), because otherwise the old code would keep running.
- **D18 (chunk 8): the stdio relay, not an MCP server inside the app.** The early check: no MCP library is installed (installing one needs your OK), and the streamable-HTTP MCP flavour can't be checked against the real `claude` without a paid call. So I took the fallback the note names: a tiny stdio relay `claude` starts itself (the experiment verified stdio servers with Claude Code 2.1.318), passing calls to a plain local HTTP endpoint in the app. Hand-written JSON-RPC, standard library only. The real-`claude` test is written (`tests/test_mcp_door.py`, `claude` marker) but **not run**: it costs a call. Run it after the restart: `.\.venv\Scripts\python -m pytest -m claude tests/test_mcp_door.py`.
- **D19 (chunk 8): `main_assistant` doesn't list `IModuleDoor` as `optional`.** The Hub lists `ITaskAgent` as `optional`, so the two would be a circular dependency. It looks the door up at each session start instead, so the first session after launch may start before the door is up; every later task's fresh session has it.
- **D20 (chunk 8): the viewer keeps watching the Main Assistant's SHOW tags.** The worker's standing prompt (the one this run uses) relies on SHOW tags to open pages, so dropping that now would break page showing until the prompt changes. The door is added alongside; drop the tag watching once the real-`claude` test passes and the prompt says to use `viewer.open`.
- **D21 (chunk 8): in Auto, `use_item` runs without a card.** That's `bypassPermissions`, like every other tool in Auto. The core menu's risky items (`modules.off` with dependents, `modules.add`) still go through the permissions stand-in, which allows and logs (D8).
- **D22 (chunk 8): the door's port is free by default.** `door_port = 0` (no config change), handed to the new copy with the token on a Hub reload, so tests never collide with the running app.
- **Known flake 2:** `tests/test_html_viewer.py::test_refuses_what_it_cant_do` once hit a socket abort in a full run and passed alone (the viewer app's server, untouched here).

**Before the build (2026-11-05):** this note, decisions 1 to 4, the MCP rule, chunk 8 as the MCP door, and three temporary picture pages in `docs/temp/` (not in the docs build): `tool-paths.html`, `tool-mcp-wrapper.html`, and `one-door-vs-many.html`.

**Experiment (2026-11-05, Claude Code 2.1.318; a throwaway stdio server, deleted afterwards):**

| Test | Result |
|---|---|
| Tool added or removed, with the `list_changed` notice | The running session follows it on its next turn. Verified |
| Tool added, no notice | Never seen. Verified |
| Tool removed, no notice | Still listed; a call gets a clean error. Verified |
| Server exits mid-session | Still shown as connected; the next call restarts it by itself and works. Verified |
| `mcp_reconnect` control request | A fresh server, the current tools. Verified |
| `mcp_set_servers` mid-session | The new server's tools are listed. Verified (listed, not called) |
| New session | Sees the current set. Verified |
| HTTP server inside our app; a new tool not on the allow list | Not tested |

**Next:** chunk 9, the Talker: drop its hardcoded viewer mapping (SHOW tags → `viewer.*`) for list → menu → call, and make commands strict (`ctx.handle` refuses a command not in `handles`; check every manifest first). The Talker is a `claude` session too, so it can take the same `IModuleDoor` (`mcp_config()`) as the worker; keep SHOW working as the note says. Then the end-of-refactor checks and the restart test checklist (see the handoff section). Restart: chunks 4 to 8 are waiting for one.

## Handoff: how the unattended run continues

The user is away. Run every remaining chunk in Auto without asking for plan approval. **One chunk per session:** build it, run the tests and ruff, the `architecture-check` skill, update the docs it touches (diagrams, module library, API pages, the reusable index, module pages), rebuild (`scripts\build_docs.py`), commit locally ("Module system, chunk N: …", like `git log`), update the progress table above, then end with `HANDOFF: docs/next-steps/module-system.md`.

- **Rules:** never `git push`; never touch `C:\Chang\Jobs`; never restart or close the app (the Talker does). Code that needs a restart: finish code, tests and docs, and note it. A risky step or a design question the note doesn't answer: take the most conservative choice and log it as the next **D** entry above instead of stopping. Keep the README row's status current (the five words).
- **Known flake:** `tests/test_voice_pieces.py::test_closing_the_socket_cancels_the_running_piece_and_frees_the_slot[True]` sometimes fails in a full run and passes alone (voice service timing, not this refactor).
- **After chunk 9:** (1) check the module philosophy (principles, modules and communication pages) against every module, with a table saying whether each agrees, and fix any that don't; (2) check the module diagrams against the code; (3) check every module works with the new tests. Then prepare the live test for after a restart, without restarting: a short checklist and, where useful, a script. It covers hot swapping every module with `ReloadModule` and `Activate` / `DeactivateModule`, and modules using each other, especially `voice_notes` getting the recorder through the voice contract and events.
- **Final report:** the commits (hash, message, files), the chunks done, the module-by-module philosophy table, the tests and ruff results, the D decisions, exactly what is ready for the restart test, and plainly anything not finished.
