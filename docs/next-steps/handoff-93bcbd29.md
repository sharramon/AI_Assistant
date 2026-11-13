# Handoff: job UI output folder, privacy paths, cv packages, voice_in note, CLAUDE.md options

**Status: done (2026-11-13), committed.** Nothing left to carry on.

- **Output folder:** cv writes new PDFs to `src/assistant/modules/cv/workspace/out` (`output_dir` unset). The job project's `job_paths.json` (gitignored) has `"cv_output": "../../cv/workspace/out"`; `job_paths.py` resolves a relative path from the workspace and reads an optional `job_paths.local.json` beside it that overrides any key. The old output folder's files were copied there (the old folder left in place). Docs: `job_search/docs/job-project.md`.
- **Privacy:** real paths in tracked files replaced with placeholders (`C:/Jobs`, `C:/Projects`, `Users/you`); the real values are in the gitignored `config/local.toml`. `.gitignore` names the module workspaces, `out/`, `job_paths*.json` and `applied/`. **Left on purpose:** `.claude/settings.json` (hook paths; a settings file, needs your yes). Git history still has the old paths (no rewrite).
- **cv packages:** pypdf and mcp were installed by hand and never declared. cv's `packages` now lists pymupdf, pypdf, mcp and httpx2; `cv/tests/test_packages.py` checks every import.
- **voice_in:** stays core; the launch-check note and the checklist corrected.
- **CLAUDE.md options:** [agent-claude-md-options.md](agent-claude-md-options.md) (nothing changed).
- **Needs an app restart** for cv's `module.toml` and `config/local.toml` to take effect.
