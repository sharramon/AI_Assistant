---
name: docs-html
description: Use whenever any file under docs/ (Markdown) is created, edited, renamed, or deleted. Regenerates the browsable HTML in docs/html/ so the rendered docs never fall behind the Markdown.
---

# Keep docs/html in sync

The Markdown in `docs/architecture/` and `docs/api/` is the source of truth. `docs/html/` is a generated copy for the user to browse, with Mermaid diagrams rendered. It must always match.

Each page holds only its own content. What all pages share is written once per output: `site.css` (styling), `site.js` (diagrams) and `nav.js` (the tab strip and the sidebar). So a doc edit changes only its own page, and adding or renaming a page changes that page plus `nav.js`. Style or navigation changes go in `scripts/build_docs.py`, never in each page.

The central folders built into `docs/html/` are `SECTIONS` in the script: `architecture`, `agents`, `api` (the app-wide pages only). Every module keeps its docs in its own folder, `src/assistant/modules/<id>/docs/`, found by folder and built into `docs/html/modules/<id>/`. Files never move for navigation.

**Navigation has two levels.** The tabs across the top are the areas: **Overview** (the app-wide design), then the module tabs, the core group's first (**Core modules**: agent_hub, talker, main_assistant, task_agents, usage, temp_ui, console_io, assistant_view, voice_in), then the add-ons' (**Add-ons**: cv, job_search, html_viewer, voice_notes, echo_orchestrator), with a separator before each group. There is no Next steps tab in `docs/html/`. The strip scrolls sideways when it doesn't fit. The sidebar lists only the active tab's pages, and the page you're on also lists its headings. The active tab is the one the page belongs to:

- **Overview:** the `architecture`, `agents` and `api` pages (`OVERVIEW`).
- **A module tab:** set by each module's `docs/docs.toml`: `group` (required: `core` or `add-on`; where it sits in the docs, never where its files live), `tab` (default: its id; modules naming the same tab share it, like **Agents**, and a tab never mixes groups), `pages` (its other pages, in order) and `related` (name → `page#anchor` in the central docs, links only). Its sidebar has one group per module (Overview, Architecture, Tools, then its other pages), then Related, then App-wide (the Architecture overview and the Module library). The build stops on an unknown key, a missing group, page or link, or a module package with no `docs/` folder.

**`docs/html/` never links into next steps:** not in the tabs, the sidebars, or the page text. Don't write links to `docs/next-steps/` in the central Markdown or a module's docs; name the change in plain text if needed. The build turns any such link into plain text, and `tests/test_module_docs.py` fails on one (its one allowed exception: the overview's link to `module-folders.html`).

**A new module** gets its own `docs/` folder with the three standard pages (`README.md` and `architecture.md` in the template of the "Module pages" section of `docs/architecture/module-library.md`; `tools.md` is generated from its menu by the build) and a `docs.toml` with its `group`. The build adds its row to the module library under its group; `tests/test_module_docs.py` checks the folder, the row and the tab.

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
