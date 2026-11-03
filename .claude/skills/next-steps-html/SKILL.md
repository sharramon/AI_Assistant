---
name: next-steps-html
description: Use whenever a file under docs/next-steps/ (Markdown) is created, edited, renamed, or deleted, or when a next-steps proposal is approved and moves into the permanent docs. Next steps build to their own HTML output, docs/html-next-steps/, never into docs/html/.
---

# Keep next steps out of the main docs

`docs/next-steps/` holds proposals and change notes. They change often and many get thrown away, so they'd clutter the main docs. They build to their own output, `docs/html-next-steps/`, with its own index (the next-steps `README.md`). `docs/html/` holds only the permanent docs (`architecture/`, `agents/`, `api/`) and never links into next steps. Both outputs share files the same way: each page holds only its content, and `site.css`, `site.js` and `nav.js` (the sidebar) are written once per output (see [docs-html](../docs-html/SKILL.md)).

## Rule

After **any** change to a Markdown file under `docs/next-steps/`, in the same piece of work, before reporting back:

1. If you added a note, link it from the **Pending changes** table in `docs/next-steps/README.md`. That page is the index.
2. Rebuild:
   ```powershell
   .\.venv\Scripts\python scripts\build_docs.py
   ```
   One command builds both outputs.
3. Confirm the output says `Wrote N pages to docs/html-next-steps/` with the expected count. If the build fails, fix it before moving on.
4. Tell the user the HTML was rebuilt. Point them to `docs/html-next-steps/index.html`, not `docs/html/`.

## When a proposal is approved

When a design in a next-steps note becomes part of the app (for example an architecture section), it leaves next steps:

1. Move the content into the right permanent page under `docs/architecture/`, `docs/agents/`, or `docs/api/`. Discuss where it goes with the user first.
2. Leave the note in `docs/next-steps/` as a short record (status, date, a link to where it went), or remove it if the user prefers.
3. Rebuild both outputs with the command above, and follow the [docs-html](../docs-html/SKILL.md) skill for the permanent pages.

## Never

- Build next steps into `docs/html/`, or add `next-steps` to the main sections in `scripts/build_docs.py`.
- Link from the permanent docs to next steps in the HTML. The build turns such Markdown links into plain text in `docs/html/`.
- Edit files in `docs/html-next-steps/` or `docs/html/` by hand. The build deletes and regenerates both folders.
