# Reusable parts

Behavior that two parts need is built once and shared ([principle 13](principles.md)). This page says where reusable parts live and why; the list of them is the [reusable parts index](../api/reusable.md). Back to the [overview](README.md).

> **Status: decided 2026-11-02.** `app_kit` and `agent_tags` are built (2026-11-02), and `ctx.permissions` is built (it forwards to the core's permissions handler). Everything in the index exists unless it says *planned*.

## The rule

- **One part, many users.** Written once, tested on its own, listed in the [index](../api/reusable.md), and marked **Reusable · Used by: …** on its API entry. A part with one user stands out there.
- **When it counts:** a second user exists or is in an approved change note, or it implements a decided pattern (task agents, companion apps). Not "might be useful one day" ([principle 10](principles.md)).
- **What qualifies:** the same behavior, not just similar, knowing nothing about any one module. Module specifics are parameters.
- **Built by composition** ([principle 12](principles.md)): objects and functions you compose, never a base class with code in it.

## Where they live: three places, by who may import them

| Place | Holds | Imports | Used by |
|-------|-------|---------|---------|
| `assistant.contracts` | Interfaces, commands, events: reusable by definition | nothing | core, modules |
| `assistant.infra` | Helpers for the main app's modules: `ClaudeSession`, `SessionTaskAgent`, `LogSession`, config, and `agent_tags` | contracts, `app_kit` | core, modules |
| `src/app_kit/` | Helpers shared by the main app **and** the independent apps: the Edge window, layered config, `CompanionApp`, the local-only guard (`local_guard`) | standard library only | `html_viewer`, `voice_service`, `temp_ui`, thin modules, other apps |

`app_kit` exists because the [independent apps](decisions.md#decided) can't import `assistant`. That rule used to force copies (the viewer had its own window code). `app_kit` is a small package in the same repo, ships with each app that uses it, and never imports `assistant`. Each part has one import path: the window functions come only from `app_kit`, not re-exported from `assistant.infra`.

## Left out on purpose

- **HTTP servers:** the temp UI (raw asyncio), the viewer (stdlib), and voice (FastAPI) each serve differently. The temp UI is throwaway and the viewer works. **New companion apps use FastAPI**; nothing gets migrated.
- **Agent prompts:** the SHOW instructions appear in both agent prompts. Modules can't share text without importing each other; this goes away once agents call tools directly. Turning a SHOW tag into the viewer's tool call is shared ([`show_page`](../api/infra.md#show_page)).
- **SSE writing and the in-app page server** (viewer app, temp UI, voice notes): `voice_notes` copies the temp UI's page server. Left until the UI handler is designed, since the temp UI is a stand-in; the long-lived user is the viewer app.
- **Viewer events** stay in `contracts/messages.py`.

## Companion app checklist

Every independent app the main app launches (the [HTML viewer](html-viewer.md), the [voice service](voice.md)) keeps the same shape, so [`CompanionApp`](../api/app_kit.md#companionapp) can launch and call any of them:

1. Its own package under `src/`, run with `python -m <app>`; never imports `assistant`.
2. Listens on `127.0.0.1` only, refuses another host, and refuses browser requests from another origin (WebSocket `Origin`, JSON-only POSTs). One shared check does it: [`app_kit.local_guard`](../api/app_kit.md#local_guard).
3. A ping endpoint answering `{"app": "<name>", ...}`.
4. A JSON `POST` quit endpoint.
5. Config with [`app_kit.load_layered`](../api/app_kit.md#load_layered): its TOML file plus a `.local` override.
6. A thin module in the main app built on `CompanionApp`: launch if nothing answers the ping, call the API, read the event stream, quit on stop only if it launched it. On a reload, hand the `CompanionApp` over in `export_state`, unless `code_changed()`: then quit it with `stop(adopted=True)` so the new copy runs the new code.

## Adding a reusable part

1. Check the [index](../api/reusable.md) first; extend a part that nearly does the job.
2. Put it in the right place (table above), with its own tests.
3. Add one line to the index and an API entry starting with **Reusable · Used by: …**. Update the Used by line whenever a user is added or removed.
