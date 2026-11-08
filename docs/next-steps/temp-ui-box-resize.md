# Temp UI: drag the typing box taller or shorter

> **Status: built, waiting on the batched restart or a `RELOAD: temp_ui` (2026-11-08).** Task 4 of the queue; nothing was reloaded or restarted. Then refresh the window and do the hand checks below.

**Asked:** let the user change the height of the Talker pane's typing box by click and drag.

**Decided (the user):** one size for every tab (not per tab), and it stays where you dragged it (sending a message doesn't reset it).

**Touches:** `src/assistant/modules/temp_ui/page.html` only (CSS, one element, page JS); `docs/modules/temp_ui.md` (one line). No server, contract or config change. The temp UI is a throwaway stand-in ([decisions](../architecture/decisions.md#open-decisions)), so no new design.

**Approach:**
- A thin **drag handle** (`#grip`, a bar with a small grip mark, `ns-resize` cursor) on the top edge of the input area, above the mic's live line, the snips and the box. It also draws the line the input area had on top.
- Dragging it up makes the box taller, down shorter (pointer events with capture, so it works when the pointer leaves the bar).
- **Limits:** at least 40 px (the old height); at most 60 % of the window, and never so tall that the Talker's chat goes under 120 px. The chat area keeps filling the rest (it was already `flex: 1`). The limit is re-applied when the window is resized.
- **One size, kept:** stored in the page's `localStorage` (`temp_ui.boxHeight`), so it holds across tabs, sends and a window refresh. Nothing resets it. Double-click the handle to go back to 40 px.
- The Send, mic and clear buttons stay 40 px tall at the box's bottom edge instead of stretching with it.
- No helper reused or added: nothing in `docs/api/reusable.md` covers page layout, and this is temp-UI code.

**Built (2026-11-08):** in `page.html`: the `#grip` element and its CSS, the textarea's `max-height: 160px` replaced by the drag limits, `form` aligned to the bottom with 40 px buttons, and the drag code next to the form's code (`boxLimit`, `setBox`).

**Your checks (after the restart or `RELOAD: temp_ui`; refresh the window first):**
1. Drag the bar above the typing box up: the box grows, the chat above shrinks and still scrolls. Drag down: it shrinks back, never below one line.
2. Drag it as high as it goes: it stops with some chat still showing (at most about 60 % of the window).
3. Type and send a message: the box keeps its dragged height.
4. Switch to another agent's tab and back: the same height in every tab.
5. Refresh the window: the height is still the one you dragged to. Double-click the bar: back to one line.
6. With the mic on and a snip waiting, the live line and the thumbnail still sit between the bar and the box; Send, mic and ✕ stay normal-sized at the bottom.
