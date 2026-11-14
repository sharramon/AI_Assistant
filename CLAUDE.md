# AI Assistant

## Read the docs before searching the code

The short overview is loaded below. Use the docs to understand the flow before any codebase search:

1. Find the relevant area in the short overview, the [architecture overview](docs/architecture/README.md) or the [API index](docs/api/README.md) (the core only). A module's own API and tools are on its docs page, `src/assistant/modules/<id>/docs/`.
2. Read its detail page: `docs/architecture/<area>.md` and `docs/api/<group>.md`, or the module's own docs.
3. Only then use Grep/Glob: to confirm against the code, or to find what the docs don't cover. If the docs and the code disagree, trust the code and fix the docs.

Before writing a new function, check the [reusable parts index](docs/api/reusable.md) and the API reference for one that already does the job. After building a reusable part, add it to the index with its Used by line ("Build it once", principle 13).

What we're working on now is in `docs/next-steps/README.md`.

For agent work (Talker, Main Assistant, Agent Hub, subagents), also read `docs/architecture/agents.md` and `docs/agents/README.md`, including spike findings.

## Workflow

- Any multi-step task: follow the `batching` skill.
- Making a change that touches more than one function or file: use the `architecture-first` skill.
- During and at the end of a multi-chunk build: use the `architecture-check` skill after each big chunk and before the final report.
- After editing anything in `docs/**/*.md`: use the `docs-html` skill (rebuild with `.\.venv\Scripts\python scripts\build_docs.py`). Never edit `docs/html/` by hand.
- Discuss proposed doc or structure changes with the user before editing.

## Short overview

@docs/architecture/short-overview.md
