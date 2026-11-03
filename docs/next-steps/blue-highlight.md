# Blue highlight in the HTML viewer

> **Status: done (2026-10-28).**

**Asked:** "Or just make the highlight color blue or red right?" The viewer's yellow highlight on white letters doesn't work in the dark theme (snip `logs/2026-10-28_01-32-08_trying-the-html-viewer-highlight/snips/snip_e39a39ee.png`, from `docs/html/architecture/index.html`).

**Why:** the highlight is pale yellow (`#ffe26a`) and keeps the page's text color (`color: inherit`). On a dark page the text is near-white, so white on yellow is about 1.2:1 and nearly unreadable.

**Touches:** `src/html_viewer/page.html`, the `MARK_STYLE` rule `mark.hv-mark` (line 191). Nothing else; highlights are drawn in the browser only.

**Approach:**
- Change `mark.hv-mark` from `background: #ffe26a; color: inherit; … box-shadow: 0 0 0 2px #ffe26a;` to `background: #2f5fa8; color: #fff; … box-shadow: 0 0 0 2px #2f5fa8;`.
- Set the text to white instead of inheriting it, so it reads on both themes and inside links (link colors would otherwise be blue on blue).
- Contrast, worked out from the colors:

  | | Contrast | Needed |
  |---|---|---|
  | White text on `#2f5fa8` | 6.3:1 | 4.5:1 (WCAG AA) |
  | Highlight against a dark page (`~#18191d`) | 2.8:1 | stands out |
  | Highlight against a light page (`#fff`) | 6.3:1 | stands out |

- Blue, not red: red reads as an error.
- Check by hand: highlight a sentence in `docs/html/architecture/index.html` in the dark theme and in the light theme, including a link and inline code.

**Decided:**
- Shade: `#2f5fa8`, chosen by the user from a side-by-side preview against the darker `#1f4e8c` (8.3:1, but stands out less on a dark page).
