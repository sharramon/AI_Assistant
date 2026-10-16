# Decisions

What's decided, what's still open, and what's deliberately deferred. Back to the [overview](README.md).

## Decided

- **Core and PC-side modules:** Python.
- **Quest 3 client:** separate Unity (C#) app, connecting through the gateway module.
- **Deployment:** runs on a PC for now, a server later.

## Open decisions

- **Persistence technology**
- **Initial orchestrator** (model and agent framework)

## Deliberately deferred

Don't add more architectural machinery until two or three very different modules (e.g. a text input, a browser tool, and a view) are built and we've checked that each can be replaced independently. Let those real modules show which abstractions are actually missing.
