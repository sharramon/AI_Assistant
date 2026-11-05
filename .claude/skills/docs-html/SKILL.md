---
name: docs-html
description: Use whenever any file under docs/ (Markdown) is created, edited, renamed, or deleted. Regenerates the browsable HTML in docs/html/ so the rendered docs never fall behind the Markdown.
---

# Keep docs/html in sync

The Markdown in `docs/architecture/` and `docs/api/` is the source of truth. `docs/html/` is a generated copy for the user to browse, with Mermaid diagrams rendered. It must always match.

Each page holds only its own content. What all pages share is written once per output: `site.css` (styling), `site.js` (diagrams) and `nav.js` (the tab strip and the sidebar). So a doc edit changes only its own page, and adding or renaming a page changes that page plus `nav.js`. Style or navigation changes go in `scripts/build_docs.py`, never in each page.

The folders built into `docs/html/` are `SECTIONS` in the script: `architecture`, `modules`, `agents`, `api`, `job-project`. Files never move for navigation.

**Navigation has two levels.** The tabs across the top are the areas: **Overview** (the app-wide design), then the module tabs (**Agents**, **voice_in**, **voice_notes**, **html_viewer**, **Stand-ins and terminals**), then the project tabs (`PROJECT_TABS`: one docs folder each about a project outside the app; today **Job project**, `docs/job-project/`, whose sidebar lists that folder's pages). There is no Next steps tab in `docs/html/`. A module tab holds one module or a group of them; every module still has its own page. The strip scrolls sideways when it doesn't fit. The sidebar lists only the active tab's pages, and the page you're on also lists its headings. The active tab is the one the page belongs to:

- **Overview:** the `architecture`, `agents` and `api` pages (`OVERVIEW`), minus pages a module tab claims, with `docs/modules/README.md` right after the module library.
- **A module tab:** set in `MODULE_TABS`, keyed by tab name, in tab order. `modules` lists the module ids it owns (left out, it's just the tab's name, like `voice_in`). Its sidebar is a group named after the tab with each module's `docs/modules/<id>.md`, then `pages` (other pages about it, which belong to this tab, like `architecture/voice.md` for `voice_in`), `related` (name → `page#anchor` elsewhere, links only; the Agents tab lists the agents pages this way, so they stay on Overview too), and always the Architecture overview and the Module library. Module tabs never list change notes; the build stops on any other key.

**`docs/html/` never links into next steps:** not in the tabs, the sidebars, or the page text. Don't write links to `docs/next-steps/` in the Markdown under `architecture/`, `modules/`, `agents/` or `api/`; name the change in plain text if needed. The build turns any such link into plain text, and `tests/test_module_docs.py` fails on one.

**A new module** gets a page in `docs/modules/` (in the template of `docs/modules/README.md`), a link in that README's `## Pages`, a row in the module library, and one entry in `MODULE_TABS`: its id in an existing tab's `modules`, or a new tab (`{}` if it has nothing more). The build stops if a module page is in no tab or in two, or an entry names a missing file; `tests/test_module_docs.py` checks the page, the row and the tab.

`docs/next-steps/` (with its `archive/` of finished notes) is not part of `docs/html/`; it builds to its own output, and its notes use the status values proposed, approved, building, built (waiting on you), done. See the [next-steps-html](../next-steps-html/SKILL.md) skill.

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
