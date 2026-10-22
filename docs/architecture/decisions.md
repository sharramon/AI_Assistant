# Decisions

What's decided, what's still open, and what's deliberately deferred. Back to the [overview](README.md).

## Decided

- **Core and PC-side modules:** Python.
- **Quest 3 client:** separate Unity (C#) app, connecting through the gateway module.
- **Deployment:** runs on a PC for now, a server later.
- **Agents:** an [Agent Hub](agents.md) module coordinates a Talker, a Main Assistant, and subagents. The core doesn't know agents exist.

- **Runtime module control:** modules can be turned on and off while the app runs, through a core control interface; a control panel UI module and the Talker use it. Code changes still need a restart. See [core](core.md#runtime-module-control).
- **Views:** two terminals for now (talk, and a view-only window on the Main Assistant). The chat window comes later as nicer UX for the same thing.

## Open decisions

- **Persistence technology**
- **Agent runtime:** `claude -p` sessions on the subscription (provisional, pending a terms check and the [spike](../agents/spike.md))
- **Agent Hub contracts:** designed after the spike

## Deliberately deferred

Don't add more architectural machinery until two or three very different modules (e.g. a text input, a browser tool, and a view) are built and we've checked that each can be replaced independently. Let those real modules show which abstractions are actually missing.
