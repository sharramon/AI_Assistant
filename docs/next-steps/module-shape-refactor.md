# Module shape: directory, menus, and clean boundaries

> **Status: approved (2026-11-04).** The design is in the architecture docs; the build is pending, voice notes first. The design is on the [Modules](../architecture/modules.md) page, with principles 14 to 17 and a decision. Nothing is built; no API, source or config file has changed. Chosen: the overview draws the core with its ports; dependencies stay by contract only, so voice gets its own contract (item 8). Added 2026-11-04: module control for you and the assistants (item 1).

**Asked:** update the plans to match the module-directory picture (`scratch/module-directory.html`): a module is a wrapper with a menu inside, the assistants find modules through a one-line directory and open only the menu they need. Also make voice usable by more than one module, and try a voice-notes module first in that shape. The other scratch pages it draws on: `scratch/module-wrapper.html`, `scratch/tools-and-mcp.html`, `scratch/port-boundary.html`.

**Why, in short:** today the Talker is hardcoded to the viewer's `viewer.open` / `viewer.highlight`, the Main Assistant can't call module tools at all, there is no module description anywhere, and adding a module means editing the entry point by hand. Neither assistant can turn a module on or off.

## The changes

### 1. Modules turned on, off, reloaded and unloaded by you or an assistant

Modules can be turned on, off, reloaded and fully unloaded by you or by an assistant, like Unity extensions.

| | |
|---|---|
| What changes | The module-control commands (`ListModules`, `ActivateModule`, `DeactivateModule`, `ReloadModule`, `AddModule`) become tools of the core, offered to both the Talker and the Main Assistant through the same directory and menu asks as every module (item 6). Risky ones need your approval, through the [permissions handler](permissions-handler.md) (or the Agent Hub's permission card until it exists): for example turning off a module that others require, or one in use (a recording in progress). A module that launches a companion app (the voice service, the HTML viewer) quits it when switched off and starts it again when switched on, whether or not this copy launched it. Two new options: **restart the service** (quit the companion app; it comes back with its new code on next use) and **reload with restart** (reload the module and restart its app, instead of handing the running app over). Later: unload a module from memory when it hasn't been used for a long time. |
| Why | Today the core has the commands and the temp UI can send them, but the assistants can't. A plain reload hands the running service over and keeps the old code: on 2026-11-04 the voice service's fix (`voice_service/session.py`) needed the service quit by hand through its `POST /quit`, and the mic clicked once, to run. Today `stop` quits the companion app only if this copy launched it. |
| Size | Medium (core tools and approval); small for the companion-app restart option |
| Restart | Yes (core and contracts); the thin modules (`voice_in`, `html_viewer`) can then be reloaded |
| Touches | `contracts/control.py` (restart option on `ReloadModule`, or a `RestartService` command), `core/lifecycle.py`, `core/tools.py` (control commands as core tools), `app_kit/companion.py` (`CompanionApp`: quit what it adopted), `voice_in/module.py`, `html_viewer/module.py`, `talker/module.py` and `main_assistant/module.py` (prompts), the [Control API](../api/control.md), tests |
| Open | Which control actions count as risky, and the idle time before unloading. |

### 2. Core checks every command

| | |
|---|---|
| What changes | `ctx.handle` accepts a command only if its class lives in `assistant.contracts` and the manifest lists it in a new `handles` field. |
| Why | Today a module can register any command class, even its own private one, with no check. The boundary should be the shared contracts. |
| Size | Small |
| Restart | Yes (core and contracts) |
| Touches | `core/context.py`, `contracts/module.py` (`Manifest.handles`), each module's manifest, tests |

### 3. A `ctx.logs` port

| | |
|---|---|
| What changes | Modules ask `ctx.logs` for their chat log file or the snips folder. The entry point stops naming `temp_ui` and `html_viewer` and stops putting live `LogSink` objects into config (`__main__.py:112-113`). |
| Why | Config should be plain data, and the entry point shouldn't know which modules want logs. |
| Size | Medium |
| Restart | Yes |
| Touches | `contracts/module.py` (`ModuleContext`), `core/context.py`, `__main__.py`, `temp_ui`, `html_viewer`, the modules with a `transcript` setting, tests |

### 4. Find modules by folder

| | |
|---|---|
| What changes | The core imports modules by name from the enabled list and scans `src/assistant/modules/` for the available ones, reusing `core/loader.py`. A module's folder name must match its manifest id. The static imports and `MODULES` list at `__main__.py:21-43` go away. |
| Why | A new module is then just a new folder: no hand edit of the entry point. |
| Size | Medium |
| Restart | Yes |
| Touches | `core/app.py`, `core/loader.py`, `core/registry.py`, `__main__.py`, tests |

### 5. Description and announcements in the manifest

| | |
|---|---|
| What changes | Two new manifest fields: one `description` line, and a list of the events the module announces. |
| Why | The directory (item 6) needs the one line. The events list lets a module see what it can listen to without reading another module's code. |
| Size | Small |
| Restart | Yes |
| Touches | `contracts/module.py`, every module's manifest, the [Modules API](../api/modules.md#manifest) |
| Also (open, 2026-11-04) | To generate the [module library](../architecture/module-library.md#generated-later) from the manifests, two more things: the events the module **listens to** (today only `ctx.subscribe` calls), and its **`ToolSpec`s readable without starting it** (today `tools()` on a running instance). Then the library table between its markers is rewritten by a script before the docs build. |

### 6. Directory, then menu

| | |
|---|---|
| What changes | Two asks. "List modules with one-liners": extend `ListModules` / `ModuleInfo` with the description, or add a command. "Give me this module's menu": returns that module's `ToolSpec`s. Calling an item stays `InvokeTool`. The core's own menu holds the module-control tools (item 1). |
| Why | An assistant sees one line per module, then opens only the menu it needs, instead of every tool always in view. |
| Size | Medium |
| Restart | Yes |
| Touches | `contracts/control.py`, `contracts/tools.py`, `core/tools.py`, `core/lifecycle.py`, tests |

### 7. Both assistants use the generic asks

| | |
|---|---|
| What changes | The Talker and the Main Assistant use the asks from item 6 plus `InvokeTool`, in place of the hardcoded SHOW-tag mapping (`talker/module.py:471-478`). The worker gets a way to call module tools; today it can't, and the viewer watches its SHOW tags instead. |
| Why | Any new module's tools become usable by both, without code in the Talker. |
| Size | Large |
| Restart | Yes |
| Touches | `talker/module.py` (prompt and tag handling), `main_assistant/module.py` (prompt), `infra/agent_tags.py`, `html_viewer/module.py` (stops watching the worker's tags), tests |
| Open | How the worker invokes tools: tags in its reply that the app reads, or one generic tag. To be decided (see [open questions](#open-questions)). |

### 8. Voice sessions

| | |
|---|---|
| What changes | First check whether `voice_in` can serve more than one consumer (phase 1 left out "several listeners at once", so probably not). Then add a session id and a destination on `StartListening`, so the Talker window and another module (a voice-notes app) each get their own text. A new **voice contract** in `contracts/voice.py`, provided by `voice_in`; modules that need voice declare `requires=(<voice contract>,)` so it starts with them. `requires` stays by contract only, never a module id (decided 2026-11-04). |
| Why | One shared mic and engine; two copies of the module would fight over the mic. |
| Size | Small for the destination; medium if several sessions at once |
| Restart | Yes for the `StartListening` field (contracts); `voice_in` itself can be reloaded |
| Touches | `contracts/voice.py`, `voice_in/module.py`, maybe `temp_ui`, the [Voice](../architecture/voice.md) page, tests |

### 9. Small cleanups from the earlier review

| | |
|---|---|
| What changes | A typed handover for reloads, the cosmetic `infra` import, and a reminder that permissions are still the allow-all stand-in (the real handler is the [permissions handler](permissions-handler.md) note). |
| Why | Loose ends found while reviewing the boundaries. |
| Size | Small |
| Restart | Yes for the handover type; the import is cosmetic |
| Touches | `core/lifecycle.py`, `contracts/`, the reloadable modules, `infra/__init__.py` |

## Suggested order

1. **Voice notes first.** Build a voice-notes module in the target shape: its own manifest requiring the new voice contract (item 8), listens to `VoiceTranscript` / `VoiceState`, imports no other module, has its own record button. The only refactor piece it takes is the minimal voice destination change from item 8.
2. **Module control next (item 1).** The companion-app parts first (quit on off, start on on, restart the service, reload with restart), then the control commands as core tools for both assistants, with your approval for the risky ones. Until item 6 lands they are offered as plain tools; afterwards they sit in the core's menu.
3. **Then the refactor:** items 2 and 5 (manifest fields and the check), then 4 (find by folder), 3 (`ctx.logs`), 6 (directory and menu), 7 (both assistants), and 9 alongside.

The notes work shows what the refactor really needs: which events it listens to, what it needs from the manifest, and where a module still has to reach outside its own folder.

## Diagrams to update as we refactor

The main architecture and API pages stay as they are for now: apart from what was added on 2026-11-04 (marked planned), they describe the code that exists, which is what an agent needs to read before changing it. The user wants the main flowcharts updated **item by item, as each refactor step lands**, not all at once ahead of the code. This list says what each page shows today, what it should show afterwards, and which item above makes the change due. The design itself is on the [Modules](../architecture/modules.md) page; it isn't repeated here.

**One page is already ahead of the code:** the overview chart in [`architecture/README.md`](../architecture/README.md) was redrawn on 2026-11-04 and already shows the target shape (the core with five ports, modules as wrappers with menus, the directory, list · menu · call, voice notes requiring the voice contract). Several of those things don't exist yet. As each item lands, the matching piece of the chart drops its planned style; nothing new needs drawing, except item 1's arrows.

| Page · diagram | Today | After the refactor | Triggered by |
|---|---|---|---|
| [Overview](../architecture/README.md) · bird's-eye chart | **Ahead of the code.** Draws the Directory port, "1 list · 2 menu" arrows from both agents, the Main Assistant's "3 call", Lifecycle's "find by folder: planned", and Voice notes with a voice contract; all styled planned or dashed. Only the Control panel sends "on · off · reload" to Lifecycle | Same picture, with each piece drawn as built: Directory and the list/menu arrows (items 5, 6), both agents' call arrows through `InvokeTool` (7), find by folder (4), Voice notes and its contract (8 and the voice-notes build). The Commands port checks `handles` (2). Both agents can also turn modules on, off and reload them, through the core's menu, with your approval (1) | 1, 4, 5, 6, 7, 8 |
| Overview · "Built today" paragraph under the chart | Lists the directory, find by folder, the voice contract and voice notes as planned | Moves each into "built" as it lands; says the assistants can turn modules on and off (1) | 1, 4, 6, 8, voice notes |
| Overview · Parts table | Module Registry "planned: finds modules by folder"; Module directory at _TBD_; Modules row lists today's modules; Voice handler "planned: voice contract and sessions"; Voice notes _TBD_; Shared Infrastructure has no `ctx.logs`; Lifecycle Manager turns modules on and off for the core only | Registry finds by folder (4); directory row gets its real location and command names (6); Contracts row mentions `handles`, the description and events fields and the voice contract (2, 5, 8); the log handler row says modules reach logs through `ctx.logs` (3); voice rows lose "planned" (8); Lifecycle Manager and Control panel rows say the assistants use it too, and companion apps restart (1) | 1, 2, 3, 4, 5, 6, 8 |
| [Principles](../architecture/principles.md) · rules 10, 11 | 10 already says the plugin mechanism is "found by folder, listed in the directory, used through menus"; 11 says a new module needs no restart | Check both still read true once modules are found by folder and listed in the directory; 11's "no restart" for a new module is only fully true after 4, and a companion app's new code only runs without a restart after 1 | 1, 4, 6 |
| Principles · rules 14 to 17 and their "Today:" lines | 14: description planned. 15: planned, Talker hardcoded to the viewer, Main Assistant can't call tools. 16: voice sessions planned. 17: finding by folder planned | Each "Today:" line is shortened, then removed when its rule is fully true: 14 after 5; 15 after 6 and 7; 16 after 8; 17 after 4 | 4, 5, 6, 7, 8 |
| [Reusable parts](../architecture/reusable-parts.md) · "Where they live" | Three places by who may import them; no mention of ports or menus as shared parts | Add `ctx.logs` as a port every module uses (3), the directory/menu asks as the one way agents find tools (6), and the voice contract as the shared voice service's interface (8) | 3, 6, 8 |
| [Reusable parts index](../api/reusable.md) | No entries for `ctx.logs`, the directory asks, the voice contract; `CompanionApp` quits only what it launched | One line each with its **Used by** line, added in the same step that builds it; `CompanionApp`'s line gains the restart (1) | 1, 3, 6, 8 |
| [Core](../architecture/core.md) · "Where the core sits" and "Structure" charts | Core parts without a directory; modules come from the `MODULES` list in `__main__.py` | Registry scans `src/assistant/modules/`; the directory sits in the core; `ctx.logs` appears among the context's ports; the router checks `handles` | 2, 3, 4, 6 |
| Core · "Lifecycle" and "Runtime module control" charts | Start from a hand-written module list; `AddModule` takes a package; module control comes from the core's callers and the temp UI only; a reload hands a companion app over | Start from the enabled list resolved by folder; adding a module is a new folder; typed reload handover (9); both assistants send the control commands as core tools, risky ones after your approval, and "reload with restart" / "restart the service" restart a companion app (1) | 1, 4, 9 |
| Core · "Logging" chart and "Adding, replacing, or removing a module" | The entry point hands `LogSink`s to `temp_ui` and `html_viewer` through config; adding a module means editing `__main__.py` | Modules ask `ctx.logs`; adding a module needs no entry-point edit | 3, 4 |
| [Communication](../architecture/communication.md) · "How modules reach each other" chart and "Chaining modules" | Commands registered with no check; Talker reaches the viewer through hardcoded SHOW tags; chaining section marked planned | Commands only from `assistant.contracts` and listed in `handles`; agents go directory → menu → `InvokeTool`; voice sessions with a destination drawn as built | 2, 6, 7, 8 |
| [Agents](../architecture/agents.md) · "The idea" chart and Responsibilities | Talker maps SHOW tags to `viewer.*`; the Main Assistant has no tool path and the viewer watches its tags; neither agent can turn modules on or off | Both agents use the directory, menus and `InvokeTool`; the viewer stops watching the worker's tags; both can turn modules on, off and reload them, asking you for risky ones (1). The open question on how the worker calls tools is answered first | 1, 6, 7 |
| [Permissions](../architecture/permissions.md) | No module-control actions | Risky module-control actions (turning off a module others require, or one in use) ask you | 1 |
| [Voice](../architecture/voice.md) · "The voice handler: three parts" and the `voice_in` module chart | One session at a time, no destination, no voice contract; a reload keeps the running service | Sessions with a destination; `voice_in` provides the voice contract; voice notes and the temp UI drawn as two users of it (8). Off quits the service, on starts it, and reload with restart brings up new service code (1) | 1, 8 |
| [HTML viewer](../architecture/html-viewer.md) | The thin module quits the viewer at stop only if it launched it | Off quits the viewer, on starts it, reload with restart (1) | 1 |
| [Control API](../api/control.md) · `ModuleInfo`, `ListModules`, `ReloadModule` | `ModuleInfo` has id, state, provides, requires; no description. The commands are sent by the core's callers and the temp UI | Gains the description (or a new directory command is documented here), plus the "menu" ask (5, 6); the commands are also core tools for the assistants, and `ReloadModule` gains a restart option or a restart command is added (1) | 1, 5, 6 |
| [Modules API](../api/modules.md) · `Manifest`, `ModuleContext` | `Manifest`: id, provides, requires, uses, permissions. `ModuleContext` has no `logs` | `Manifest` gains `handles`, `description` and the announced events; `ModuleContext` gains `logs` | 2, 3, 5 |
| [Tools API](../api/tools.md) and [Messaging API](../api/messaging.md) | `InvokeTool` used only by the Talker; tools offered today are the viewer's; `StartListening` has `send_as_input` only | The module-control tools are listed among the tools offered (1); new menu command if item 6 adds one; `StartListening` gains a destination; the voice contract is listed | 1, 6, 8 |
| [App kit API](../api/app_kit.md) · `CompanionApp` | Quits the app at stop only if it launched it | Can quit an app it adopted, and restart it (1) | 1 |
| [API index](../api/README.md) | Tables match today's code | New rows for each new command, field and contract, in the step that adds it | 1, 2, 3, 5, 6, 8 |
| SVGs in `docs/html/architecture/img/` (`module-directory-1-before`, `-2-steps`, `-3-changes`) | Hand-drawn; their sources are `docs/architecture/img/*.svg`, copied by `build_docs.py`. "1-before" is the November 2026 snapshot, "2-steps" and "3-changes" show the plan | "1-before" stays as history. Edit the sources under `docs/architecture/img/`, never the copies in `docs/html/`: mark steps built in "2-steps" and "3-changes" as items 4 to 7 land | 4, 5, 6, 7 |

**How to apply:** each item's build step updates the rows above that name it, before its final report (the `architecture-check` skill), then rebuilds the docs.

## Open questions

1. **How many event types to keep generic?** For example one text-stream event carrying its source and destination, reused by voice, notes and transcription, versus a new event per use. Fewer types means fewer restarts; too few makes events vague.
2. **How does the worker invoke tools?** Tags in its reply that the app reads and turns into `InvokeTool`, or one generic tag for "call this item of this module". Decide before item 7.
3. **Which module-control actions are risky, and when is a module unloaded?** Which ones ask you (turning off a module others require, or one in use; maybe any `AddModule`), and how long unused before unloading from memory. Decide before item 1's assistant part.
