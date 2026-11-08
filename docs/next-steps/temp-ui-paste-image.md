# Temp UI: paste an image into the chat box

> **Status: built (waiting on you) (2026-11-05).** Approved with all three recommendations (reuse `ViewerClip`, `[Pasted] image`, Talker only). Built in `temp_ui` and `talker`; the full suite and `ruff` pass; loaded with `RELOAD`, no restart. Left: the checks by hand in the test plan.
>
> **As built:** a clipboard that also holds text stays a text paste (so copying from a page doesn't turn into an image). The page converts any image to PNG; the server takes PNG only. A refused paste shows why in the box's placeholder for a few seconds. The string `(pasted)` lives in both modules for now; at the next restart, widen `ViewerClip`'s docstring and consider a shared constant in `contracts`.

**Asked:** "Make images pastable into the main talking module as well", so you can paste a screenshot of the temp UI and the assistant can see what's wrong (the horizontal bar over the top buttons, still to look at after this is built).

**Why:** today the only way to show the assistant an image is a snip from the HTML viewer. A screenshot of the temp UI itself (or anything else) can't get in.

**Touches:** `temp_ui` only (`page.html`, `module.py`), plus maybe one line in `talker` (question 2). No contract, core or config change, so it loads with `RELOAD: temp_ui` (and `talker`), no restart. Docs: [temp_ui](../modules/temp_ui.md) (its **Snips** paragraph), [talker](../modules/talker.md) if question 2 is yes, the snips line in the [runtime page](../agents/runtime.md#temp-ui). Tests: `tests/test_temp_ui.py`.

**Approach:** a pasted image becomes a snip, so everything after the paste is the existing snip path ([snip-send](temp-ui-snip-send.md)).
1. **Page:** a `paste` listener on the chat box. If the clipboard holds an image, the page posts it (`POST /paste-image`, the PNG bytes) and the text paste is left alone. No thumbnail is drawn on the page side: it arrives over the event stream like a viewer snip.
2. **Saved:** `temp_ui` writes it to `<launch log folder>/snips/paste-<id>.png`, the same folder the viewer's snips go in (`ctx.logs.folder()`), refuses anything over 10 MB or not an image, and publishes the existing `ViewerClip` (`id`, `image_path`, `file="(pasted)"`, no heading).
3. **Everything else is reused as is:** the Talker's pending snips (limit 3, oldest dropped and logged), the thumbnail with its × (`POST /drop-snip`, `ViewerClipDropped`), `GET /snip/<id>`, send with no text as `(snip)`, the thumbnails moving into your sent bubble, and the 30 kept sent snips.
4. **Logged at info level:** temp_ui logs the paste (id, size, file) or why it was refused; the receive, ×, attach and drop lines are the existing ones.

Checked [reusable.md](../api/reusable.md): nothing new to add; this reuses `ViewerClip`, `ViewerClipDropped` and `ctx.logs`.

**Helper agent tabs:** there is one chat box; a tab only moves the focus. With a helper in focus, the Talker still gets the image, but it passes your *text* to the helper word for word (`hub.send` carries text only), so **the helper doesn't see the image**. See question 3.

**Test plan:** automated: `/paste-image` with a PNG saves the file and publishes `ViewerClip`; non-image and oversized bodies are refused and logged; then the existing snip tests. By hand, after the reload: paste a screenshot, send with no text (bubble shows it, the Talker describes it); paste plus text; paste then ×.

**Open questions:**
1. **Reusing `ViewerClip` for a paste** (its docstring says "from the HTML viewer"). **Recommend** reuse it now, and widen the docstring to "a snip or a pasted image" at the next restart. A new event type would need a restart now.
2. **How the Talker names it:** today it would say `[Viewer] snip from (pasted)`. **Recommend** a one-line Talker change: `[Pasted] image (image attached; file: …)` when `file` is `(pasted)`.
3. **Helpers:** **recommend** Talker only for now. Later, if wanted: when a helper has the focus, the passed text gets the image's file path added, so the helper can open it with Read.
