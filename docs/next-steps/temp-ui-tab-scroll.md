# Temp UI: switching tabs lands at the bottom, unless you'd scrolled up

> **Status: built (waiting on you) (2026-11-06).** Approved with both recommendations; follow-up: a scrolled-up pane keeps its *line* in view, not its pixel offset. `RELOAD: temp_ui`, then the hand checks below.

**Asked:** "Why does clicking away and into a task agent always have its worker window scrolled to somewhere in the middle, and not to the bottom where the most recent tasks are shown?"

**Why (the cause):** both panes are one shared list for all tabs; a tab switch only hides the other agents' lines (`showAgents` in `src/assistant/modules/temp_ui/page.html`, the `el.hidden = !shown(el)` loop). The worker pane is never scrolled after that, so it keeps the previous tab's `scrollTop`, which in the new tab's (different height) content lands somewhere in the middle. The Talker pane is always forced to the bottom, and that runs on *every* `agents` item (module, agent, task and focus changes), not only on a switch, so a Talker you'd scrolled up in jumps down whenever any agent changes state.

**Even from the very bottom (the user's detail):** it happens even when you were at the very bottom before clicking away. The cause is the same: the pane's `scrollTop` is a pixel offset, and nothing scrolls it again after the switch. It stays at the old tab's bottom offset, the browser clamps it to the new tab's lines, and that offset is the middle of a longer tab. So the fix remembers per tab whether you were *at the bottom* (not just the offset), and scrolls to the true bottom only once the new tab's lines are shown and laid out: right after re-filtering, then again in the next two animation frames. While those run, the page's own scroll events don't count as yours. Lines and images that arrive later (a replay on reconnect, a snip thumbnail loading) scroll it down again while the pane is following the bottom.

**Touches:** `src/assistant/modules/temp_ui/page.html` only (page JS); `docs/modules/temp_ui.md` (one line). No server, contract or config change; a `RELOAD: temp_ui` is enough.

**Approach:**
- Keep a small per-tab memory for each pane: `{ pinned, top }`, where `pinned` means "was at the bottom" (the page's existing `atBottom`, 40 px slack).
- In `showAgents`, before re-filtering: note the old tab, and save each pane's `pinned` / `scrollTop` under it.
- After re-filtering:
  - **Tab changed:** for each pane, if the new tab has a saved entry with `pinned = false` (you'd scrolled up there on purpose), restore its `top`; otherwise (first visit, or you were at the bottom) scroll to the bottom.
  - **Same tab** (an `agents` refresh with no switch): scroll to the bottom only if that pane was at the bottom before; leave it alone otherwise. This replaces the unconditional Talker scroll.
- New lines keep following as today (`add`: follow only when at the bottom).
- No new helper: `atBottom` is already in the page; nothing in `docs/api/reusable.md` covers page scrolling, and this is throwaway temp-UI code, so it isn't added to the index.

**Decided (2026-11-06, the user, both recommendations):**
1. A tab you'd scrolled up in keeps your position even when new lines arrive there while you're away; scroll to the bottom yourself to follow again.
2. Closing a tab forgets its saved positions, so a reopened tab with the same name starts at the bottom.

**Built (2026-11-06):** in `page.html`: `scrollMemory` (per tab, per pane: `pinned`, `top`), `stuck` (the shown tab's panes following the bottom, kept up to date by your scroll events), `saveScroll` before the re-filter in `showAgents`, `restoreScroll` after it (now, then two frames later), a capture `load` listener for late images, and `add` follows when `stuck` or at the bottom. The unconditional Talker scroll is gone.

**Follow-up (2026-11-06, the user):** "If I was at the bottom, stay at the bottom. If I was looking at something in the middle, keep that line in view." The first build saved only a pixel `scrollTop` for a pane you'd scrolled up in, so the same line came back only if nothing above it changed size. Now, for a pane not at the bottom, `saveScroll` keeps the **anchor**: one block (a message, card or activity row, a child of the pane), and how far its top sat from the pane's top. `restoreScroll` scrolls so that same block sits at the same place again, now and in the next two frames, whatever the pane's height or the lines added meanwhile. If that block is gone (the panes were rebuilt on a reconnect), it falls back to the old pixel offset. The at-the-bottom rule is unchanged: true bottom after layout.

**Which block (the user asked for the one in view, 2026-11-06):** the shown block **nearest the middle of the view** (`middleLine`: the one spanning the middle line, else the closest one). Not the top visible one, because that's often only half showing: the tail of something you've already read, scrolled mostly off the top. The block in the middle is the one you're most likely reading. It goes back at the same height in the view, so it stays in frame even if the window grew.

**Your checks (after `RELOAD: temp_ui`; refresh the window first):**
1. In a busy tab, scroll the worker pane to the very bottom, click another tab, wait for new lines in the first one, click back: it's at the bottom, newest line showing.
2. The same with the Talker pane.
3. Scroll up in a tab's worker pane so a line you can recognise sits in the middle of the pane, switch away and back: that same line is in the middle again, even if lines came in meanwhile. Try it once after resizing the window while away, too.
3b. The same with the Talker pane: the message you were reading (in the middle) is back in the same place.
4. Scrolled up in the Talker pane, wait for another agent to change state (a tab's dot changes): the Talker pane doesn't jump.
5. At the bottom of the Talker pane, send a snip: once its thumbnail loads, the pane is still at the bottom.
6. Scroll up in a helper's tab, close it with ×, open one with the same name: it starts at the bottom.
