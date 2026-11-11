# Flash the app's taskbar icon when an agent needs you

> **Status (2026-11-10): built and tested as written** (the user checked it; failures of every agent flash too, a cancel doesn't). Flash only when the app window isn't in focus, and keep flashing until you click it. Code: `flash_window` and `_find_window` in `src/app_kit/window.py`; `_notice`, `_flash`, `FLASH_KINDS` in `src/assistant/modules/temp_ui/module.py`. Tests: `tests/test_taskbar_flash.py` (ends and questions of every agent, a failed helper task, no flash on progress / replies / a cancel). Documented in `docs/modules/temp_ui.md` and `window` in `docs/api/app_kit.md`. Takes effect at the one app restart after all pending fixes.

## The problem

When an agent finishes a task while you're in another window, nothing tells you. You find out only when you look at the app again.

## When it flashes

Only while the app window (the temp UI's Edge window) is **not** in front. It keeps flashing until you bring the window forward (Windows stops it then by itself).

| Event | Flash? |
|---|---|
| Any agent's task is done or failed: the Main Assistant, a helper, the job agent (`TaskUpdated`, kind `done` / `failed`) | yes |
| An agent asks you something: a `NEED:` question, a risky step, a permission request (`TaskUpdated`, kind `need` / `permission`), also when it's held behind a tab's **!** | yes |
| A permissions-handler card (`PermissionRequested`: an access list, a grant) | yes |
| A task you cancelled, progress, milestones, replies | no |

## Where it goes

- **`app_kit/window.py`**: a new `flash_window(pid, title)` next to `raise_window`, with the window search they both need moved into one private `_find_window(pid, title)`. It calls `FlashWindowEx` with `FLASHW_ALL | FLASHW_TIMERNOFG` (flash the caption and the taskbar button until the window comes to the front), and does nothing when the window is already in front or not on Windows. Reusable: the HTML viewer and the CV Tool could use it later.
- **`temp_ui`**: it owns the app window (it started the Edge process), so it calls `flash_window(edge pid, "Assistant")` from its existing `_on_task` and `_on_access_card` handlers, in a thread. No new events, nothing in the core or the Agent Hub: the Hub's `TaskUpdated` already covers every agent's tasks, helpers included. When the real UI handler replaces the temp UI, it calls the same helper.
- Tests: `temp_ui` flashes on done / failed / need / permission / a card, and not on progress or a cancel (the flash call is swappable, like the viewer's raise). Docs: `docs/api/app_kit.md` (`window`), the reusable index's Used by line, `docs/modules/temp_ui.md`.

It needs one app restart (the code is in `app_kit` and a running module), taken with the other pending fixes.
