---
name: next-steps-html
description: Use whenever a file under docs/next-steps/ (Markdown) is created, edited, renamed, archived, or deleted, or when a next-steps proposal is approved and moves into the permanent docs. Next steps build to their own HTML output, docs/html-next-steps/, never into docs/html/.
---

# Keep next steps out of the main docs

`docs/next-steps/` holds proposals and change notes. They change often and many get thrown away, so they'd clutter the main docs. They build to their own output, `docs/html-next-steps/`, with its own index (the next-steps `README.md`). `docs/html/` holds only the permanent docs (`architecture/`, `modules/`, `agents/`, `api/`); nothing in it links into next steps: no Next steps tab, no change notes in the sidebars, no links in the page text. The next-steps output is opened directly (`docs/html-next-steps/index.html`); its own tab strip ends with a **Next steps** tab and keeps the tabs back to the main docs. Both outputs share files the same way: each page holds only its content, and `site.css`, `site.js` and `nav.js` (the tabs and the sidebar) are written once per output (see [docs-html](../docs-html/SKILL.md)).

**Finished notes live in `docs/next-steps/archive/`**, a section of the next-steps output (`ARCHIVE` in `scripts/build_docs.py`) with its own index, `archive/README.md`. The Next steps sidebar lists the active notes and one **Archive** link; archived notes aren't listed there.

## Status values

Every note's status line (`> **Status: <value> (<date>).**`) and its row in the **Pending changes** table use one of:

- **proposed:** written, waiting for the user's check.
- **approved:** the user checked it; not being built yet (also when the session can't build it itself).
- **building:** being built.
- **built (waiting on you):** built, with a restart or the user's check left. Say what's left.
- **done:** built and checked, nothing waiting on the user.

A handoff note follows its build: it's finished when its build is.

## Rule

After **any** change to a Markdown file under `docs/next-steps/`, in the same piece of work, before reporting back:

1. If you added a note, link it from the **Pending changes** table in `docs/next-steps/README.md`. That table lists only active notes.
2. If a note is now **done** with nothing waiting on the user, archive it (below).
3. Rebuild:
   ```powershell
   .\.venv\Scripts\python scripts\build_docs.py
   ```
   One command builds both outputs, archive included.
4. Confirm the output says `Wrote N pages to docs/html-next-steps/` with the expected count. If the build fails, fix it before moving on.
5. Tell the user the HTML was rebuilt. Point them to `docs/html-next-steps/index.html`, not `docs/html/`.

## Archiving a note

1. Move it to `docs/next-steps/archive/<note>.md`. No stub at the old path.
2. Move its row from the Pending changes table to the table in `archive/README.md` (title, date, one line on what it did).
3. Rewrite every link to it: other notes (`archive/<note>.md` from the top folder, `<note>.md` from inside the archive), the note's own relative links (one folder deeper), skills, `CLAUDE.md`, code comments and tests that name its path. `tests/test_module_docs.py` fails on a broken link between notes.

## When a proposal is approved

When a design in a next-steps note becomes part of the app (for example an architecture section), it leaves next steps:

1. Move the content into the right permanent page under `docs/architecture/`, `docs/agents/`, or `docs/api/`. Discuss where it goes with the user first.
2. Leave the note as a short record (status, date, where it went); once it's done, archive it.
3. Rebuild both outputs with the command above, and follow the [docs-html](../docs-html/SKILL.md) skill for the permanent pages.

## Never

- Build next steps into `docs/html/`, or add `next-steps` to the main sections in `scripts/build_docs.py`.
- Link from the permanent docs (`architecture/`, `modules/`, `agents/`, `api/`) to a note, archived or not, even in the Markdown. Name it in plain text. The build turns such links into plain text, and `tests/test_module_docs.py` fails on one.
- Point the user at a note through `docs/html/`. Give the `docs/html-next-steps/` path.
- List archived notes in the Next steps sidebar or the Pending changes table.
- Edit files in `docs/html-next-steps/` or `docs/html/` by hand. The build deletes and regenerates both folders.
