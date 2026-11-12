# Temp UI: send a snip on its own, show it on the sent message, log every snip step

> **Status: built (waiting on you) (2026-11-05).** Approved as written: `(snip)` for a snip sent alone, the same thumbnail size in the sent bubble. Built; the full suite passes (488 passed, 0 failed, checked after the build) and `ruff` is clean. Left: the app restart, then the by-hand checks in the test plan.
>
> **Checks by hand (after the restart):** (a) snip sent with no text: **passed** (2026-11-05). The Talker got `(snip)` with the image and the image stayed on the sent message. (b), (c) and (d) are still to do.
>
> **As built:** the last 30 sent snips stay served by `GET /snip/<id>` so the bubbles keep their images. Besides × drops, a snip pushed out by the limit of 3 is logged too, in both modules. The Talker logs the snip count for every message, 0 included.

**Asked:** "When I press send with only the image it does send, and in my input in the chat the image remains there, you know, as a separate image in the chat box. I just need some confirmation that the image sent as I send it to you." Also: find out where a snip got lost.

**Why:** the diagnosis (2026-11-05) found:
- **Send with only a snip does nothing.** Both ends stop on empty text on purpose: the page's send handler (`temp_ui/page.html:652`, `if (!value) return;`) and `/say` (`temp_ui/module.py:509`). The page posts only `{text}`; the Talker adds the image from its own list of pending snips (`talker/module.py:528-530`, attached at `:560-567`).
- **Nothing confirms a snip went out.** On every message the temp UI clears the thumbnails (`temp_ui/module.py:240-242`), and the "you" bubble shows only the text.
- **One snip was lost with no trace.** In the 16:09 launch, snip `6b47364b` went out with the next message; snip `087352c6` (16:36:11) never went out with any later one. No dropped events, errors, resets or reloads in the log, and the debugger couldn't reproduce it. Only a sent message or the × on a thumbnail empties the Talker's list, and neither is logged.

**Touches:** `temp_ui` (`page.html`, `module.py`) and the `talker` module only. No contract, core or config change. Docs: [temp_ui](../../src/assistant/modules/temp_ui/docs/README.md) (a short **Snips** paragraph: send with a snip alone, thumbnails move into the sent bubble), [talker](../../src/assistant/modules/talker/docs/README.md) (pending snips, the placeholder text, the log lines), the snips line in the [runtime page](../agents/runtime.md#temp-ui). Tests: `tests/test_temp_ui.py` and the Talker's tests.

**Approach:**
1. **Send with only a snip.** The page lets send through when the box is empty but thumbnails are showing. `/say` publishes `InputReceived` when there is text *or* a waiting snip; with no text it uses the placeholder `(snip)`, so the Talker's turn has some text. The Talker attaches the image as today.
2. **Show the snip on the sent message.** When a message goes out (typed or spoken), the temp UI puts the waiting thumbnails into that "you" bubble as a separate image row under the text, instead of only clearing them. The bubble shows what the temp UI held; the Talker's log line (step 3) shows what was really attached.
3. **Log every snip step, at info level** (in the launch's log):
   - Talker: a snip received (id, file); a snip dropped and from where (`sent` with message *id*, or `x` from the thumbnail); how many it attached to a message (count and ids, `0` included when the temp UI showed some).
   - temp_ui: a snip shown, a × click (`/drop-snip`), and how many thumbnails moved into a sent bubble.
   If a snip goes missing again, the log shows which step lost it.

**Test plan:**
- Automated: `/say` with empty text and a waiting snip publishes `(snip)`; with empty text and no snip publishes nothing; the sent item carries the thumbnails; the Talker logs receive, attach and drop. Then `pytest` and `ruff`.
- By hand, after the app restart: (a) snip, send with no text: the bubble shows the image and the Talker describes it; (b) snip plus typed text, and snip plus a spoken message; (c) snip, then × on its thumbnail, then send text: no image goes out; (d) read the log: one line per step for each of these.

**Restart:** the code could be reloaded module by module, but you asked for an **app restart** after the change; it will be offered when the build is done.

**Open questions:**
1. **Placeholder text** for a snip sent alone: `(snip)`? **Recommend** `(snip)`; the Talker sees the image either way.
2. **Image size in the bubble:** same small thumbnail as above the input, or larger? **Recommend** the same thumbnail size, click to open it full size in the viewer later if wanted.
