# Decisions

What's decided, what's still open, and what's deliberately deferred. Back to the [overview](README.md).

## Decided

- **Core and PC-side modules:** Python.
- **Quest 3 client:** separate Unity (C#) app, connecting through the gateway module.
- **Deployment:** runs on a PC for now, a server later.
- **Agents:** an [Agent Hub](agents.md) module coordinates a Talker, a Main Assistant, and subagents. The core doesn't know agents exist.

- **Runtime module control:** modules can be turned on and off while the app runs, through a core control interface; a control panel UI module and the Talker use it. A module's code can be reloaded, and a brand-new module added, while the app runs (decided 2026-11-03). Only changes to the core, contracts or shared helpers, and a new module that needs a new contract or port type, need a restart. See [core](core.md#reloading-a-modules-code).
- **Views:** for now a throwaway [temp UI](../agents/runtime.md#temp-ui) (a local web page in its own window: Main Assistant left, Talker right) plus terminal 1. The UI configurations you'll actually want get their own design conversation. Terminal 2 (`assistant_view`) still exists but is off by default.
- **Agent runtime:** `claude -p` sessions on the subscription (terms checked; built, see [agent runtime](../agents/runtime.md)).
- **Agent Hub contracts:** [`ITaskAgent`](../api/agents.md) and the Hub's commands and events (built).
- **Independent apps where it pays off** (decided in an earlier session, recorded 2026-10-27): a part may be its own app, deployed and run on its own, when it's useful without the assistant. It doesn't import the assistant; the main app launches it and talks to it through two-way hooks (its local HTTP API one way, its event stream the other), via a thin module. The modules inside the main app stay a modular monolith in one process. First one: the [HTML viewer](html-viewer.md) (`src/html_viewer`, run with `python -m html_viewer`); its thin module is `html_viewer`.
- **Permissions are per module:** one [permissions handler](permissions.md) module; every module asks through `ctx.permissions`, and the core fills in who is asking. Not the whole app holding everything. Grants are saved in `data/permissions.toml`; with no handler running, everything is allowed and logged (designed, not built; the stand-in that allows and logs is planned now, the handler later).
- **Build it once** (2026-11-02): behavior two parts need is one reusable part, listed in the [index](../api/reusable.md) with who uses it ([principle 13](principles.md), [Reusable parts](reusable-parts.md)). What the main app and the independent apps share goes in a new package, `app_kit` (standard library only, never imports `assistant`); each part has one import path, so the window functions aren't re-exported from `assistant.infra`. This replaces the HTML viewer's own copy of the window code ([viewer decision 8](html-viewer.md#decided)). The `ctx.permissions` stand-in is built now, ahead of the handler. `app_kit` and `agent_tags` are built (2026-11-02); the stand-in is planned.
- **Worker context and edit batching** (2026-11-03): every step resends the whole conversation, and the worker's context kept growing large while its code edits were poorly batched (the same file edited again and again), so every step cost more. The rule: the worker is reminded at 150k (`context_reminder`) and hands off to a fresh session by itself. Batching is a standing line in the worker's prompt plus a hook note on the second edit to a file, once per file, covering `Edit`, `Write`, `MultiEdit` and `NotebookEdit`, for the worker only. Neither interrupts it: an interrupt costs a full step and balloons the context. Grouping edits never means skipping the architecture-check, the tests or ruff. A restart with reset instructions goes with them. How it runs: [runtime](../agents/runtime.md#fresh-sessions-and-handoffs).
- **Module shape** (2026-11-04): every module is a wrapper (manifest, lifecycle, context) with a menu of tools; the Talker and the Main Assistant find modules through a one-line directory, then open only the menu they need; the core finds modules by folder; modules chain through declared events and shared services with sessions and destinations ([modules](modules.md), [principles 14 to 17](principles.md)). Dependencies stay by contract only: `voice_in` gets a voice contract, and voice notes requires that contract, not `voice_in`'s id. The overview now draws the core with its ports. Mostly planned; the build plan is the module-shape change note, with voice notes built first.

## Open decisions

- **Persistence technology**
- **UI handler:** a separate part that owns the user-facing UIs (chat window, Quest, glasses) instead of each UI being its own ad hoc module. Its shape isn't decided; the temp UI is a throwaway stand-in until it is.
- **Self-improvement permissions:** how the Main Assistant gets access to its own code ([plan](../agents/self-improvement.md)); will go through the [permissions handler](permissions.md)
- **How general event types are:** one general event (for example a text stream carrying its source and destination) reused by voice, notes and transcription, or a new type per use. Fewer types mean fewer restarts; too few make events vague ([modules](modules.md#chaining-modules)).
- **How the Main Assistant calls tools:** tags in its reply that the app turns into the directory asks and `InvokeTool`, or one generic tag. Decide before both assistants switch over ([modules](modules.md#find-a-module-then-open-its-menu)).
- **The voice contract's shape:** its name and methods, and how a session's destination is given, decided with the voice-notes build.

## Deliberately deferred

Don't add more architectural machinery until two or three very different modules (e.g. a text input, a browser tool, and a view) are built and we've checked that each can be replaced independently. Let those real modules show which abstractions are actually missing.
