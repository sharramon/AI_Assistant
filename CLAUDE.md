# AI Assistant

## Read the docs before searching the code

The architecture overview and the API index are loaded below. Use them to understand the flow before any codebase search:

1. Find the relevant area in the overview or the API index.
2. Read its detail page: `docs/architecture/<area>.md` and `docs/api/<group>.md`.
3. Only then use Grep/Glob: to confirm against the code, or to find what the docs don't cover. If the docs and the code disagree, trust the code and fix the docs.

Before writing a new function, check the API reference for one that already does the job.

What we're working on now is in `docs/next-steps/README.md`.

For agent work (Talker, Main Assistant, Agent Hub, subagents), also read `docs/architecture/agents.md` and `docs/agents/README.md`, including spike findings.

## Workflow

- Making a change that touches more than one function or file: use the `architecture-first` skill.
- After editing anything in `docs/**/*.md`: use the `docs-html` skill (rebuild with `.\.venv\Scripts\python scripts\build_docs.py`). Never edit `docs/html/` by hand.
- Discuss proposed doc or structure changes with the user before editing.

## Architecture overview

@docs/architecture/README.md

## API index

@docs/api/README.md
