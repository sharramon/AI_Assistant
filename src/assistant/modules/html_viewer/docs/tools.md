# html_viewer: tools

<!-- tools:start (generated from the module's menu by scripts/build_docs.py; don't edit) -->

Its menu, as the main AI sees it (`modules.menu`). Every item is called with `modules.use_item`.

## `viewer.open`

Open an HTML file in the HTML viewer (switches to its tab if it's open); front: also bring the viewer window to the front (for the user's clicks)

| Argument | Type | Required | What it is |
|---|---|---|---|
| `path` | string | yes |  |
| `front` | boolean | no |  |

## `viewer.highlight`

Open an HTML file in the viewer and highlight a short quote of its text, optionally only in the section under a heading; scrolls to it

| Argument | Type | Required | What it is |
|---|---|---|---|
| `path` | string | yes |  |
| `text` | string | yes |  |
| `heading` | string | no |  |
| `front` | boolean | no |  |

## `viewer.tabs`

The files open in the HTML viewer, and their highlights

No arguments.


<!-- tools:end -->
