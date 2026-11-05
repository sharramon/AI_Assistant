# HTML viewer as its own app

> **Status: done (2026-10-27).** You directed it (decided in an earlier session, never saved): the viewer is its own app, launchable on its own, launched by the main app, with two-way hooks. Recorded in [decisions](../../architecture/decisions.md#decided). `pytest` and `ruff` pass.

**Asked:** the HTML viewer should not be tied to the main app: a separate app that can launch on its own, is launched by the main app, and passes information both ways (tools, events like `ViewerTabsChanged`, open and highlight requests).

**Why:** it's useful without the assistant, and independent deployment was decided as a goal for parts like it.

**Where it was:** already its own process with a local HTTP API, but its code lived in the main app's package (`src/assistant/modules/html_viewer/`), it imported the window helper from `assistant.infra`, and the docs said independent deployment was not a goal.

## What changed

- **Moved:** the viewer app to its own top-level package `src/html_viewer/` (`viewer.py`, `document.py`, `markdown_source.py`, `highlight.py`, `snip.py`, `page.html`). It imports nothing from `assistant`.
- **Its own window helper:** `src/html_viewer/window.py`, a copy rather than a shared import, which also opens Edge's DevTools port for snip. `temp_ui` keeps `assistant.infra.open_app_window`.
- **Launch on its own:** `python -m html_viewer [files...]`, or `html-viewer` (a script in `pyproject.toml`).
- **Stays in the main app:** the thin module `src/assistant/modules/html_viewer/module.py`. It launches `python -m html_viewer` on the first request, and stops it when the app stops (one you started yourself is left running).

## The hooks

| Direction | How | What |
|-----------|-----|------|
| Main app → viewer | Local HTTP API on `127.0.0.1:8766` | open, highlight, clear, tabs, quit |
| Viewer → main app | Its event stream (`GET /api/events`) | tabs and highlights → `ViewerTabsChanged`; snips → `ViewerClip` |

## Open questions

1. **Its own `pyproject.toml`** so it installs without the assistant? **Recommend later**, when it's deployed somewhere else; today it's a separate package in the same repo, with one dependency (`markdown`).
