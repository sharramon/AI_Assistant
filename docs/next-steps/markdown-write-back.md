# Viewer edits write back to the Markdown

> **Status: done (2026-10-27).** Approved as written, with Q1 (match by text) and Q2 (no rebuild from the viewer). Built as planned; `pytest` and `ruff` pass. One addition: a change at the very start or end of a block goes at the block's edge, outside any markup. `markdown` is now a runtime dependency (the viewer renders blocks with it). A dry run on the architecture overview page mapped 66 of 77 text blocks; the 11 others are repeated table cells ("core", "API"), which it refuses as planned. Not yet tried by hand in the real window. As built: [HTML viewer](../architecture/html-viewer.md#as-built-v1).

**Asked:** "I thought I asked you to make it so that the text edits will overwrite the markdown." Saving a text edit in a built docs page should change its source Markdown too, so a docs rebuild keeps it. You did ask before: it's recorded as a **Later** item, "Write-back to Markdown for built pages", in the [base HTML viewer](base-html-viewer.md#scope) note and in the [HTML viewer](../architecture/html-viewer.md#scope) scope. It was left out of v1.

**Why:** today saving a page in `docs/html` or `docs/html-next-steps` only changes the HTML and warns "The next docs rebuild will overwrite this edit." The edit is lost at the next rebuild.

**Touches:**
- `src/assistant/modules/html_viewer/`: the save path in `viewer.py`, plus a new `markdown_source.py` (find the source file, map a block, rewrite its lines).
- `page.html`: the new save message.
- `tests/test_html_viewer.py`: write-back tests against small Markdown files.
- Docs: [HTML viewer](../architecture/html-viewer.md) (scope, decided, as built).
- No change to `scripts/build_docs.py`.

## Approach

**Finding the source file.** Every built page already says where it came from (`<!-- Generated from docs/... -->`). The viewer reads that.

**Mapping an edited paragraph to its Markdown.** This happens when you save, not when you edit, so undo needs nothing special:

1. For each element whose text changed since the last save, take its **old plain text** (what was saved before) and its **new plain text**.
2. Split the Markdown into blocks (heading, paragraph, list item, table cell) with their line numbers, skipping code fences. Render each block with the same Markdown settings the build uses and keep its plain text.
3. **The block whose plain text equals the old text** is the source. If exactly one block matches, it's used.
4. Within that block, only the part that changed is replaced: drop the text both versions start and end with, and look for the old middle part in the block's Markdown. If it's found exactly once, replace it with the new middle part. Bold, links, `code` and the `#`, `- ` or `|` around it stay as they are.

Example: you change "turns modules on and off" to "turns modules on or off" inside a paragraph with a link and bold text. Only `and` → `or` is written into that line of the `.md`; the rest of the line isn't touched.

**When the mapping is ambiguous or impossible**, the Markdown is never guessed at:
- no block matches (text that isn't from the Markdown, such as the nav or footer), or **two or more blocks match** (the same sentence twice on a page);
- the changed part isn't found exactly once in the block, for example an edit that crosses a bold or a link boundary.

Those edits aren't written to the Markdown. Edits that do map are still written.

**What the warning becomes.** Saving writes both files: the Markdown first, then the HTML, so the page matches until the next rebuild.
- All edits written back: no warning. A short note says "Saved; also written to `docs/architecture/README.md`."
- Some couldn't be written back: a warning before saving that lists them ("2 edits can't be written to the Markdown: the next rebuild will overwrite them"), with **Save anyway** or **Cancel**, the same as today.
- No source found (the comment is missing, or the `.md` was moved): today's warning, unchanged.

## Open questions

1. **Match by text when saving, or tag blocks with line numbers in the build** (the earlier plan)? Tags need a change to `build_docs.py` and extra attributes in every built page, and they go stale as soon as the Markdown is edited by hand. **Recommend matching by text**: no build change, it works on pages already built, and it refuses when unsure.
2. **Rebuild after saving?** After a write-back the HTML is right in the viewer but may differ slightly from what the build would make, and CI checks that the two match. **Recommend not rebuilding from the viewer**: the `docs-html` skill rebuilds before any commit anyway. The save note can say a rebuild is still needed.
