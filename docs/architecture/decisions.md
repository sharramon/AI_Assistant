# Decisions

What's decided, what's still open, and what's deliberately deferred. Back to the [overview](README.md).

## Decided

- **Core and PC-side modules:** Python.
- **Quest 3 client:** separate Unity (C#) app, connecting through the gateway module.
- **Deployment:** runs on a PC for now, a server later.
- **Agents:** an [Agent Hub](agents.md) module coordinates a Talker, a Main Assistant, and subagents. The core doesn't know agents exist.

- **Runtime module control:** modules can be turned on and off while the app runs, through a core control interface; a control panel UI module and the Talker use it. Code changes still need a restart. See [core](core.md#runtime-module-control).
- **Views:** for now a throwaway [temp UI](../agents/runtime.md#temp-ui) (a local web page in its own window: Main Assistant left, Talker right) plus terminal 1. The UI configurations you'll actually want get their own design conversation. Terminal 2 (`assistant_view`) still exists but is off by default.
- **Agent runtime:** `claude -p` sessions on the subscription (terms checked; built, see [agent runtime](../agents/runtime.md)).
- **Agent Hub contracts:** [`ITaskAgent`](../api/agents.md) and the Hub's commands and events (built).
- **Independent apps where it pays off** (decided in an earlier session, recorded 2026-10-27): a part may be its own app, deployed and run on its own, when it's useful without the assistant. It doesn't import the assistant; the main app launches it and talks to it through two-way hooks (its local HTTP API one way, its event stream the other), via a thin module. The modules inside the main app stay a modular monolith in one process. First one: the [HTML viewer](html-viewer.md) (`src/html_viewer`, run with `python -m html_viewer`); its thin module is `html_viewer`.
- **Permissions are per module:** one [permissions handler](permissions.md) module; every module asks through `ctx.permissions`, and the core fills in who is asking. Not the whole app holding everything. Grants are saved in `data/permissions.toml`; with no handler running, everything is allowed and logged (designed, not built; the stand-in that allows and logs is planned now, the handler later).
- **Build it once** (2026-11-02): behavior two parts need is one reusable part, listed in the [index](../api/reusable.md) with who uses it ([principle 13](principles.md), [Reusable parts](reusable-parts.md)). What the main app and the independent apps share goes in a new package, `app_kit` (standard library only, never imports `assistant`); each part has one import path, so the window functions aren't re-exported from `assistant.infra`. This replaces the HTML viewer's own copy of the window code ([viewer decision 8](html-viewer.md#decided)). The `ctx.permissions` stand-in is built now, ahead of the handler. `app_kit` and `agent_tags` are built (2026-11-02); the stand-in is planned.

## Open decisions

- **Persistence technology**
- **UI handler:** a separate part that owns the user-facing UIs (chat window, Quest, glasses) instead of each UI being its own ad hoc module. Its shape isn't decided; the temp UI is a throwaway stand-in until it is.
- **Self-improvement permissions:** how the Main Assistant gets access to its own code ([plan](../agents/self-improvement.md)); will go through the [permissions handler](permissions.md)

## Deliberately deferred

Don't add more architectural machinery until two or three very different modules (e.g. a text input, a browser tool, and a view) are built and we've checked that each can be replaced independently. Let those real modules show which abstractions are actually missing.
