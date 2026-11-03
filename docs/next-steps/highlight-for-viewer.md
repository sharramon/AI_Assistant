# Highlight for viewer

> **Status: done (2026-10-27).** Approved with the recommended answers: keep old highlights until cleared, no labels, page text only. Built as planned; `pytest` and `ruff` pass, and it was checked in a real Edge window (mark drawn, scrolled to, Clear and Clear all, editing a highlighted paragraph). One change: the scroll target is part of the tab's state (`focus`), not an event, so a viewer window that opens only for the highlight still scrolls to it. As built: [HTML viewer](../architecture/html-viewer.md#as-built-v1).

**Asked:** "highlight for viewer": the AI opens the relevant HTML file in the viewer and highlights the part of the page it's talking about. You clear a highlight by clicking it and choosing **Clear**. It's the **Point at a section** item under Later in the [HTML viewer](../architecture/html-viewer.md#scope) scope.

**Why:** "see the third paragraph under Parts" makes you hunt. A highlight shows you right away.

**Touches:**
- `html_viewer`: a `viewer.highlight` tool in `module.py`; highlight state per tab and `POST /api/highlight`, `/api/clear` in `viewer.py`; drawing, scrolling and the Clear popup in `page.html`.
- The `<<SHOW: ...>>` tag (Main Assistant and Talker) gets an optional target.
- `talker` and `main_assistant` prompts; the Talker's open-tabs tally lists highlights.
- Docs: [HTML viewer](../architecture/html-viewer.md), [Tools offered today](../api/tools.md#tools-offered-today).

## Approach

**How the AI picks and marks the part:**
- A new tool next to `viewer.open` and `viewer.tabs`: **`viewer.highlight(path, text, heading?)`**. `text` is a short quote of the page's words (a sentence or phrase); `heading` narrows the search to one section when the words appear more than once. It opens the file if it isn't open, switches to its tab, scrolls to the text and marks it.
- Agents can't call app tools yet, so they use the tag they already use: `<<SHOW: path | "quoted text" | heading>>` on its own line. The `html_viewer` module reads it, as it does `<<SHOW: path>>` today.
- **Not found** (the words aren't on the page): the file still opens, nothing is marked, and the result says so. **Several matches**, even within the heading: the first one is marked, and the result says how many there were.
- The mark is a yellow background over the matched words. Several highlights can be on a page at once.

**What survives:**
- Highlights live in the **viewer program's state for the tab, never in the file**. They're drawn over the page, so saving never writes them, and the edit tool removes them from the HTML it sends.
- **Window closed and reopened, switching tabs, the page redrawn:** they're drawn again.
- **File reloaded** (changed on disk, or a rebuild) **or the highlighted text edited:** the viewer looks for the quoted text again. If it's still there, the highlight stays; if not, it's dropped quietly, and the Talker's tally no longer lists it.
- **Tab closed or app restarted:** gone.

**How Clear works:**
- **Click** a highlight: a small popup by it offers **Clear** and **Clear all**. Clicking elsewhere closes the popup.
- **Double-click** still edits the text as before; the popup steps aside.
- Clearing removes the highlight from the tab's state, so it doesn't come back on reload. The Talker sees it gone in its tally.

## Open questions

1. **Keep old highlights when the AI adds a new one?** **Recommend** keeping them until you clear them, since you asked for clearing by hand. Option: each new AI reply clears its own earlier ones.
2. **A label on the highlight** (a few words from the AI, shown on hover)? **Recommend** leaving it out for now: the AI's reply already says why.
3. **Highlight inside diagrams (Mermaid nodes)?** **Recommend** page text only for now; diagram nodes later.
