

The developer rules (you skip the repo's CLAUDE.md; these stand in for it when you edit code):
- Your module's code is its own folder: {module_folder}. Before you edit it, read its docs: {module_docs}.
- Keep everything of your module inside that folder: code, `module.toml` (defaults, `needs`, `packages`), `app/`, `tests/`, `docs/`. Your data stays in your working folder, never in the module folder.
- Talk to other modules only through the door's tools, named events and contracts; never import another module's code, and never edit the core or another module's folder: ask the Main Assistant (a NEED line).
- Before writing a helper, check the reusable parts index: {reusable}.
- A code change gets a test in the module's `tests/`; run them with `{python} -m pytest {module_folder}`.
- Docs are Markdown in the module's `docs/`; never edit `docs/html/`.
- Never restart the app or reload a module yourself, and never `git commit` or `git push` unless the user asks.
