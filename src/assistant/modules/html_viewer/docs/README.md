# html_viewer: the HTML viewer and its app

## Purpose

View, edit, highlight and snip HTML files in tabs. `html_viewer` is the thin module; the **viewer app** (`app/html_viewer/` in this module's folder) is its own program that doesn't import the assistant. Off at launch, **on when used**: with `start_on_use = true`, the first page opened (a SHOW tag, the temp UI's Open in viewer button, any `viewer.*` call) turns it on through the core, even if you turned it off ([start on use](../../../../../docs/api/core.md#dispatch_tool)). `modules.on` / `modules.off` still work. Full design: [HTML viewer](viewer-app.md).

## Wrapper

| Field | Value |
|-------|-------|
| id | `html_viewer` |
| provides / requires / optional | provides [`IPageOpener`](../../../../../docs/api/modules.md#ipageopener) (the page-opener slot); requires and optional: none |
| needs | none (`needs = []` in its `module.toml`) |
| packages | none beyond the app's own (the viewer uses the standard library and `markdown`) |
| menu | a [`Menu`](../../../../../docs/api/modules.md#menu): `viewer.open`, `viewer.highlight`, `viewer.tabs` |
| events | its named events `html_viewer.tabs_changed` and `html_viewer.clip` ([events](architecture.md#events)) |
| permissions | none declared |

## Config

Its defaults are in its own `module.toml`: `host`, `port` (8766), `window`, `generated` (folders built from Markdown), `start_timeout`, `start_on_use` (true: opening a page turns the module on). A `[modules.html_viewer]` section in the app's config only overrides them, key by key.

## Running the viewer app by hand

The module launches it (`python -m html_viewer`, with its `app/` folder first on `PYTHONPATH`). To run it alone, from the repo folder:

```powershell
$env:PYTHONPATH = "src\assistant\modules\html_viewer\app"; .\.venv\Scripts\python -m html_viewer [files...]
```

There is no `html-viewer` script any more: the app lives in its module's folder, which an install doesn't put on the path. An optional `html_viewer.toml` beside the app (and its gitignored `.local.toml`) sets its defaults; none is committed.

## Code and tests

- Module: `src/assistant/modules/html_viewer/module.py`, defaults in `module.toml`
- App: `src/assistant/modules/html_viewer/app/html_viewer/`
- Tests: `tests/test_html_viewer.py` in this module's folder (the app and the module, on the [test kit](../../../../../docs/api/testkit.md)); the Talker hearing its events in `talker/tests/test_talker_snips.py`, the temp UI hearing them in `temp_ui/tests/test_temp_ui_snips.py` (each with the names it declares); centrally, `tests/test_start_on_use.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), [the viewer app](viewer-app.md), and `docs.toml` (its docs tab and group)
