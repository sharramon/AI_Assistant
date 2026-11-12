# html_viewer: the HTML viewer and its app

## Purpose

View, edit, highlight and snip HTML files in tabs. `html_viewer` is the thin module; the **viewer app** (`src/html_viewer`) is its own program that doesn't import the assistant. Off at launch, **on when used**: with `start_on_use = true`, the first page opened (a SHOW tag, the temp UI's Open in viewer button, any `viewer.*` call) turns it on through the core, even if you turned it off ([start on use](../../../../../docs/api/core.md#dispatch_tool)). `modules.on` / `modules.off` still work. Full design: [HTML viewer](viewer-app.md).

## Wrapper

| Field | Value |
|-------|-------|
| id | `html_viewer` |
| provides / requires / optional | none |
| menu | a [`Menu`](../../../../../docs/api/modules.md#menu): `viewer.open`, `viewer.highlight`, `viewer.tabs` |
| permissions | none declared |

## Config

`[modules.html_viewer]`: `host`, `port` (8766), `window`, `generated` (folders built from Markdown), `start_timeout`, `start_on_use` (true: opening a page turns the module on).

## Code and tests

- Module: `src/assistant/modules/html_viewer/module.py`
- App: `src/html_viewer/`
- Tests: `tests/test_html_viewer.py`, `tests/test_start_on_use.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), [the viewer app](viewer-app.md), and `docs.toml` (its docs tab and group)
