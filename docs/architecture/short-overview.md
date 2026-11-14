# Short overview

The project in one page, for every session that works in the repo (the repo's `CLAUDE.md` loads only this page). The whole picture is the [architecture overview](README.md); the public interface is the [API reference](../api/README.md).

## What it is

A modular personal AI assistant, built as a long-term experimental platform: a small, stable **core** hosts a changing set of independent **modules** (inputs, outputs, views, tools, background workers, and the AI agents themselves) that can be added, replaced or discarded with little change elsewhere. It's a modular monolith with ports and adapters: the modules run in one process, and a module's code is reloaded in place without a restart ([core](core.md)).

## The core line

- **The core** is what the app can't start without: the host (`src/assistant/core/`), the core modules (each module's `docs/docs.toml` says `group = "core"`), the one module door with its one gate (`dispatch_tool`), and seven ports (lifecycle, commands, events, contracts, directory, permissions, callers).
- **Add-ons** are every other module. Each is one folder, `src/assistant/modules/<id>/` or in an outside folder named in `[core] module_folders`: its code, `module.toml` (defaults, `needs`, `packages`), `app/` (a companion app, if any), `tests/`, `docs/`, and an agent's `workspace/` (gitignored).
- **Modules talk only through tools, events and contracts** (`assistant.contracts`), never by importing each other's code. Shared helpers are `assistant.infra` and `app_kit`; tests use `assistant.testkit`.
- **Arrows point one way:** an add-on may need the core or another add-on; the core never names an add-on. `tests/test_boundaries.py`, `tests/test_module_folders.py` and `tests/test_module_layout.py` check it.
- **Your choices** are in `config/` (`config/<id>.toml` for one module, gitignored). An agent works in its module's `workspace/`, unless its config names a data folder outside the repo.

## The agents

The Talker talks with you; the Main Assistant does the work and coordinates; helpers and module agents do jobs. The Agent Hub (a core module) does coordination only: the focus, tasks and messages. The door, the agent names and each agent's permission mode are the core's (its Callers port). Agents reach every module through one MCP door with three tools (list modules, show a menu, use an item), so one line per module is all they load until they need a menu ([agents](agents.md), [modules](modules.md)). A module's own agent skips this file and loads the short developer rules instead.

## Where to read next

- A part of the core: its page under `docs/architecture/` (the [Pages list](README.md#pages)), then its group in the [API reference](../api/README.md), which covers the core only.
- A module: its own `docs/` folder, `src/assistant/modules/<id>/docs/README.md` (its tools page is built from its menu). The [module library](module-library.md) lists every module and links its page.
- Before writing a helper: the [reusable parts index](../api/reusable.md).
- What we're working on now: `docs/next-steps/README.md`.
