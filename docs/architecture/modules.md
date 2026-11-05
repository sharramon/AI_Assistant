# Modules

How a module is shaped, how the assistants find what it can do, and how modules work together. The core's side is in [core](core.md); the messages are in [communication](communication.md). Each module's own page, and every module's interface side by side: the [module library](module-library.md). Back to the [overview](README.md).

> **Status: decided 2026-11-04, being built.** Built: the wrapper (`ModuleProtocol`, the manifest with its one-line description and inputs and outputs, lifecycle, context), the `Menu` part (the HTML viewer's and the echo stand-in's), the generated module library, `requires` by contract, reloading a module while the app runs, the directory (`ListModules`, `GetMenu`, the core's `modules.*` menu), finding modules by folder, the `ctx.logs` port, and the voice contract (`IVoice`) with sessions each owned by their caller. Planned: both assistants using the directory. Each item: [Built and planned](#built-and-planned). The build plan is the module system change note (`docs/next-steps/module-system.md`), which supersedes the module-shape note. The agents reach the menus through [one MCP door](#how-the-agents-reach-the-menus-one-door) (decided 2026-11-05).

## A module is a wrapper with a menu

Every module has the same **wrapper**, owned by the core, and inside it a **menu** of what it can do.

| Part | What it is | Built? |
|------|------------|--------|
| **Manifest** | Its id, a one-line `description`, the contracts it `provides`, `requires`, and optionally uses, the commands it `handles` and `sends`, the events it `publishes` and `listens` to, its permissions | Built (description, commands and events 2026-11-05). The core warns when a module handles a command it didn't list |
| **Lifecycle** | `ModuleProtocol`: `init`, `start`, `stop`, `busy`, `export_state`; the core starts, stops, and reloads it | Built |
| **Context** | `ctx`, its only access to the app: commands, events, contracts, config, log, permissions | Built, with `ctx.logs` (2026-11-05) |
| **Menu** | A [`Menu`](../api/modules.md#menu) part on the module: named items, each with a one-line description and its inputs (`ToolSpec`), readable without starting the module. The core links it to the running copy, checks the arguments, and routes `InvokeTool` to it | Built (2026-11-05): the HTML viewer (`open`, `highlight`, `tabs`) and the echo stand-in (`echo.say`) |

- **The wrapper is ours only.** Every module has the same one, so the core can start, stop, swap, and list any module without knowing what it does.
- **The menu is MCP-like:** a list of tools a model can read and call, with a description and an argument schema each. It isn't MCP itself. The agents reach every menu through [one MCP door](#how-the-agents-reach-the-menus-one-door) in front of the core; modules never speak MCP.
- **A menu can be empty.** `voice_in` offers commands (`StartListening`, `StopListening`) and events, not tools.

## Find a module, then open its menu

Both the Talker and the Main Assistant find what to use the same way: first a **directory** with one line per module, then the **menu** of the one module they need, then a call. They never see every tool at once, and no agent has another module's tools written into it.

Colors in the pictures: solid lines are built today, dashed orange is planned. Blue is a module's wrapper (ours only), yellow its menu (MCP-like), purple the core, faded grey the old way.

### Before the refactor (November 2026)

[![Before the refactor: the Talker hardcoded to the viewer, the Main Assistant unable to call tools](img/module-directory-1-before.svg)](img/module-directory-1-before.svg)

One shortcut to one module. The Talker turns its SHOW tags into the viewer's `viewer.open` / `viewer.highlight`; the Main Assistant can't call module tools at all, so the viewer watches its SHOW tags instead. The core keeps a flat list of tools, with no directory and no one-line descriptions.

### Step by step (the asks built; the agents using them planned)

[![Step by step: list modules, open one menu, call one item](img/module-directory-2-steps.svg)](img/module-directory-2-steps.svg)

1. **List modules** (built): `ListModules`, the directory, one line each, from each manifest's description.
2. **Give me its menu** (built): `GetMenu(id)`, that module's `ToolSpec`s only, read from its class, so it works while the module is off.
3. **Call an item** (built): `InvokeTool(name, args)`, routed to the module that offers it (the module must be on).

The core has a menu of its own under the id `core`: `modules.list`, `modules.menu`, `modules.on`, `modules.off`, `modules.reload`, `modules.add`. So anything that can call a menu item can also find modules and turn them on, off, or reload them. The risky items (turning off with dependents, adding new code) ask the permissions first. The agents will send all three asks through [one MCP door](#how-the-agents-reach-the-menus-one-door) (decided 2026-11-05; planned).

### What changes

[![What changes: a one-line description, two new asks, both assistants using them](img/module-directory-3-changes.svg)](img/module-directory-3-changes.svg)

Each manifest gets a one-line description, the core gets the two asks, and both assistants use them instead of hardcoded tags. All of it is planned and needs an app restart (it touches the core and contracts).

### How the agents reach the menus: one door

> **Status: decided 2026-11-05, planned** (chunk 8 of the module system change note, `docs/next-steps/module-system.md`).

The agents are `claude` sessions, and MCP is how a `claude` session calls tools in the middle of a reply. So the app serves **one MCP server, the door**, in front of the core. It has three fixed tools that map onto the three steps above: **list modules**, **show a menu**, **use an item**. Everything behind it is our own wrapper: the core's directory, `InvokeTool`, and the permission check.

```mermaid
flowchart TB
    Talker["<b>Talker</b>"]
    Main["<b>Main Assistant</b>"]
    Door["<b>One MCP door</b><br/>3 fixed tools: list modules · show a menu · use an item"]
    subgraph App["Our app: commands, events, contracts"]
        Core["<b>Core</b><br/>directory · InvokeTool · permission check"]
        Viewer["<b>HTML viewer</b><br/>menu"]
        Voice["<b>voice_in</b>"]
        Notes["<b>Voice notes</b>"]
        Unity["<b>Unity module</b><br/>menu · an MCP client inside"]
        Btn["<b>Mic button</b><br/>UI"]
    end
    UnityMcp["Unity's own MCP server"]

    Talker --> Door
    Main --> Door
    Door --> Core
    Core --> Viewer
    Core --> Voice
    Core --> Unity
    Notes -- "StartListening" --> Core
    Btn -- "StartListening" --> Core
    Unity -. "MCP" .-> UnityMcp

    classDef planned fill:#efeaf7,stroke:#6b4fa0,color:#1d1d1b
    classDef later fill:#f2f1ee,stroke:#8a877c,stroke-dasharray:5 4,color:#5f5e58
    class Door planned
    class Unity,UnityMcp later
```

Purple: planned. Dashed grey: an example for later. Agents, other modules and UI buttons all reach a module the same way, through the core.

| | **One door** (chosen) | **A door per module** |
|---|---|---|
| Directory: one line per module, then one menu | Kept | The agent sees every tool at once |
| Permissions: one check, your "Allow?" card | Kept, for every caller | Only the agent's own allow-list; buttons and modules unchecked |
| Module to module (voice notes → voice) | Kept | No path between doors, or glue per pair |
| Hot swap (hand over state, wait while busy) | Kept; the agent's three tools never change | Each door just stops and starts; the agent's tool list changes |
| The agent calls mid-reply | Yes | Yes |

### Why one door and not an MCP server per module

- **Modules talk through the core.** To each other and to the UI, modules use commands, events and contracts. That's how voice notes uses `voice_in`, and how the mic button reaches it.
- **Per-module servers would go around the core.** Each would face only the agent. It would skip the permission check, the module directory, the links between modules (`requires`, events), and hot swap in one process (handing over state, waiting while busy).
- **Swapping would depend on every server behaving.** Our experiment (2026-11-05, Claude Code 2.1.318): a running session follows tool changes only when the server announces them (`list_changed`). A tool added without a notice is never seen, and a removed one stays listed until a call fails. A crashed server restarts on the next call. With one door, the three tools never change, so none of that matters.
- **MCP stays a door at the agents' edge.** Modules are never MCP servers and never import MCP. The door only reads the directory and passes calls to the core.
- **An outside tool that already speaks MCP, such as Unity, becomes a module.** The module is an MCP client of that tool and offers its own menu, so the agents reach it through the same door, with the same permissions. A dedicated agent can sit on top of it if it's worth one.

## Chaining modules

> **Status:** events between modules are built (`voice_in` publishes `VoiceTranscript` and `VoiceState`; voice notes listens to them), and so is the voice contract `IVoice` (2026-11-05): `voice_in` provides it, voice notes requires it, and each caller opens and ends only its own session. One mic, so one session at a time; the second press wins.

Modules are combined through what they declare, with no glue code between pairs:

- **Listen to events.** A module uses another's output by subscribing to the events it announces. A voice-notes module listens to `VoiceTranscript`; it never imports `voice_in`.
- **Call commands or menu items.** For an action with a result, through the core (`StartListening`, `InvokeTool`).
- **Share a service through sessions.** A shared service runs once and serves several users. Each user starts a **session** and says where the result goes (its **destination**); the service keeps them apart by session id. Two copies of `voice_in` would fight over the one mic and load the speech engine twice.
- **Keep message shapes general.** Reuse a general event (for example a text stream carrying its source and destination) before adding a new type per use: a new type is a contract change and needs a restart. How general is [open](decisions.md#open-decisions).

```mermaid
flowchart LR
    Btn["<b>Mic button</b><br/>temp UI"]
    Rec["<b>Record button</b><br/>voice notes"]
    Video["<b>Video file</b><br/>transcription app"]
    Voice["<b>voice_in</b><br/>provides IVoice"]
    Talker["<b>Talker</b>"]
    Notes["<b>Voice notes</b><br/>requires IVoice"]

    Btn -- "StartListening<br/>send to the Talker" --> Voice
    Voice -- "final text" --> Talker
    Rec -- "StartListening<br/>not to the Talker" --> Voice
    Voice -- "VoiceTranscript<br/>its sessions only" --> Notes
    Rec -. "planned: a session<br/>destination: notes" .-> Voice
    Video -. "file source<br/>(the service has one)" .-> Voice

    classDef planned fill:#efeaf7,stroke:#6b4fa0,color:#1d1d1b
    class Video planned
```

Solid: built (the mic button's flow, and voice notes v1, which follows its own sessions by the `StartListening` id; see [voice_notes](../modules/voice_notes.md)). Purple, dashed: planned. Today the voice service takes one listener at a time (a second `start` gets `busy`) and `StartListening` only chooses whether the Talker gets the text (`send_as_input`). The video case feeds a file instead of the mic; the service already has a file source and `transcribe_file` ([voice](voice.md#a-shared-service)).

## Dependencies

> **Status:** built, by contract, including the voice contract (2026-11-05).

- **A manifest requires contracts, never module ids** ([principle 2](principles.md)). The core starts the provider first: in dependency order at startup, and at runtime `ActivateModule` activates the sole provider first. It refuses to turn a provider off while an active module requires it ([runtime module control](core.md#runtime-module-control)).
- **`optional`** contracts are used if some module provides them, and the module copes without them.
- **No module starts another itself.** Turning on voice notes turns on voice, like a package listing its dependency, but the core does it.
- **Voice:** `voice_in` provides the voice contract [`IVoice`](../api/messaging.md#ivoice), and voice notes requires it: turning voice notes on turns `voice_in` on first, and `voice_in` can't be turned off while voice notes is on. Any other module that provides `IVoice` can replace `voice_in`.

## Hot swap

> **Status:** built (2026-11-03).

A module's code is swapped while the app runs: `ReloadModule` stops it, imports its package fresh, and starts a new instance; if the new code fails, the old code runs again. `AddModule` loads a brand-new module. Changes to the core, contracts, `infra`, `app_kit`, or `__main__`, and a new contract, still need a restart. Details: [reloading a module's code](core.md#reloading-a-modules-code).

## Found by folder

> **Status: built (2026-11-05).** `find_modules()` in `core/loader.py`; `__main__.py` names no module.

- **A module is its folder:** `src/assistant/modules/<id>/`, with the folder name equal to the manifest id. Its `__init__.py` exports exactly one `ModuleProtocol` class.
- **The core scans the folder** at launch to know which modules are available; `modules.enabled` still says which start. It reuses the reload's loader (`core/loader.py`). Folders starting with `_` are ignored.
- **A bad folder is skipped and logged** (it fails to import, exports no module class or two, or its id isn't the folder's name); the other modules still load. If it was in `modules.enabled`, startup then fails with "Enabled modules not found".
- **Adding a module is adding a folder,** then `AddModule("assistant.modules.<id>")` while the app runs (which refuses a folder named differently from its id), or a restart.

## Built and planned

| Item | State |
|------|-------|
| Wrapper: manifest (id, contracts, permissions), lifecycle, context | Built |
| Menus: a `Menu` part on the module, linked by the core, called with `InvokeTool` | Built (2026-11-05; the HTML viewer, the echo stand-in) |
| `requires` / `optional` by contract, dependency order, refusal to stop a needed provider | Built |
| Reload and add while running | Built (2026-11-03) |
| Events from one module heard by another (`VoiceTranscript`, `VoiceState`) | Built |
| `ModuleProtocol`: the one interface, `Module` renamed | Built (2026-11-05) |
| Manifest description, commands (`handles`, `sends`) and events (`publishes`, `listens`) | Built (2026-11-05); the core warns on an unlisted handled command, refusing it is planned |
| `ctx.logs` port | Built (2026-11-05) |
| Directory and menu asks (`ListModules` with descriptions, `GetMenu`, the core's `modules.*` menu) | Built (2026-11-05) |
| Both assistants using them through one MCP door | Planned (door decided 2026-11-05) |
| Finding modules by folder | Built (2026-11-05) |
| Voice contract; voice sessions with a destination | Built (2026-11-05): `IVoice`, one mic, each caller owns its session; parallel sessions would need the voice service to take several listeners |
| Voice-notes module | Built (v1 2026-11-04; requires `IVoice` 2026-11-05) |
| A page per module and the [module library](module-library.md) | Built; the library's table is generated from the manifests and menus (2026-11-05), the module pages are hand-written |
