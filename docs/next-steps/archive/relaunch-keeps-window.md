# Relaunch opens one fresh window

> **Status: done (2026-10-26), fixed after trying it.** In the real app the old window stayed open: Edge refuses `window.close()` in an app window it didn't open from script. Now the app window runs on its own Edge profile (`--user-data-dir`), so it is its own Edge process, and the app closes it: at startup (any window left from the last launch) and when it stops. Checked by hand: opening, closing, and reopening a window on that profile, in under a second each; your normal Edge is untouched.

**Asked:** "Every time we relaunch, the old window's chat gets reset to a blank AND a new window gets launched." Wanted: a relaunch ends the current session, closes the old window, and starts a fresh session in exactly one new window with a blank chat.

**Why:** after a relaunch you have a blank old window plus a new one, and every relaunch adds another.

**Cause** (found in the code):

1. **Blank old window:** the chat history only exists in the app's memory, so a relaunch loses it. The old window's `EventSource` keeps retrying, reaches the new app, and on reconnect `page.html` clears both panes, expecting the server to replay its history. The new app has nothing to replay.
2. **Second window:** `TempUIModule.start()` always opens an Edge window. The relaunch doesn't close the old one: Edge isn't a child of the app, so `relaunch.ps1` never stops it.

**Touches:** `src/assistant/modules/temp_ui/` (`module.py`, `page.html`), the [temp UI docs](../../agents/runtime.md#temp-ui).

**Approach:** the old window closes itself; the new app opens the one new window, as it does now.

- Each app launch gets a random id, sent as the first item on `/events`. The page remembers the id it first got.
- On reconnect, same id (a short network drop): clear and replay, as now. **Different id** (the app was relaunched): the page closes its own window (`window.close()`).
- The new app opens its window on start as today, so exactly one window remains, with a blank chat.
- ~~Killing Edge from the script isn't an option: the app window shares Edge's process with your normal browser.~~ With its own profile it doesn't share it, so the app closes it (see the status).
- If the browser refuses `window.close()` (e.g. `window = "browser"`, a normal tab), the page shows "This session ended; the app opened a new window" instead of a blank chat.
