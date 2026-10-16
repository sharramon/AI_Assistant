---
name: docs-html
description: Use whenever any file under docs/ (Markdown) is created, edited, renamed, or deleted. Regenerates the browsable HTML in docs/html/ so the rendered docs never fall behind the Markdown.
---

# Keep docs/html in sync

The Markdown in `docs/architecture/` and `docs/api/` is the source of truth. `docs/html/` is a generated copy for the user to browse, with Mermaid diagrams rendered. It must always match.

## Rule

After **any** change to a Markdown file under `docs/`, in the same piece of work, before reporting back:

1. If you added a page, link it from its section's `README.md`. The navigation order follows those links, and unlinked pages are listed last.
2. Rebuild:
   ```powershell
   .\.venv\Scripts\python scripts\build_docs.py
   ```
3. Confirm the output says `Wrote N pages` with the expected count. If the build fails, fix it before moving on.
4. Tell the user the HTML was rebuilt, and say which pages changed.

## Never

- Edit files in `docs/html/` by hand. The build deletes and regenerates that folder.
- Report docs work as done without rebuilding.
- Rebuild only some of the pages. The script always rebuilds all of them, so navigation stays consistent.
