---
name: docs-html
description: Use whenever any file under docs/ (Markdown) is created, edited, renamed, or deleted. Regenerates the browsable HTML in docs/html/ so the rendered docs never fall behind the Markdown.
---

# Keep docs/html in sync

The Markdown in `docs/architecture/` and `docs/api/` is the source of truth. `docs/html/` is a generated copy for the user to browse, with Mermaid diagrams rendered. It must always match.

Each page holds only its own content. What all pages share is written once per output: `site.css` (styling), `site.js` (diagrams) and `nav.js` (the sidebar). So a doc edit changes only its own page, and adding or renaming a page changes that page plus `nav.js`. Style or sidebar changes go in `scripts/build_docs.py`, never in each page.

`docs/next-steps/` is not part of `docs/html/`; it builds to its own output. See the [next-steps-html](../next-steps-html/SKILL.md) skill.

## Rule

After **any** change to a Markdown file under `docs/`, in the same piece of work, before reporting back:

1. If you added a page, link it from its section's `README.md`. The navigation order follows those links, and unlinked pages are listed last.
2. Rebuild:
   ```powershell
   .\.venv\Scripts\python scripts\build_docs.py
   ```
3. Confirm the output says `Wrote N pages to docs/html/` with the expected count. If the build fails, fix it before moving on.
4. Tell the user the HTML was rebuilt, and say which pages changed. Write each page's **full absolute path** (like `C:\Chang\Git_projects\AI_Assistant\docs\html\api\tools.html`), never a bare file name: the chat turns the path into an Open in viewer button, and a bare name fails with "No such file".

## Batching

Follow the [batching](../batching/SKILL.md) skill: one edit per page, and build once at the end.

## Never

- Edit files in `docs/html/` by hand. The build deletes and regenerates that folder.
- Report docs work as done without rebuilding.
- Rebuild only some of the pages. The script always rebuilds all of them, so navigation stays consistent.
