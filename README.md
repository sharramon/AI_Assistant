# AI Assistant

A highly modular personal AI assistant, and a long-term experimental platform. A small, stable core hosts an ever-changing set of independent modules (voice in, an HTML viewer, notes, tools, and the AI agents themselves) that can be turned on, off, swapped or reloaded while the app runs.

## The core idea: agents and modules

**Messages go through the Agent Hub; tools go through the module door.**

- You talk to a **Talker**, which passes your words to the agent with the **focus**: the **Main Assistant** (the coordinator) or a specialist like the **job agent**.
- Agents that aren't focused keep working. Their questions and permission cards wait behind a **!** on their tab until you switch to them.
- Every agent sends one-line `STATUS:` milestones to the Main Assistant, which reads them at its next turn without being interrupted.
- No agent calls a tool directly. Every agent uses a module's menu items through one **module door** (over MCP): list the modules, open one's menu, use an item. The core checks who may call it and runs it.
- A big agent is in charge of its own module: the job agent comes with `job_search`, its menu and its background worker.

[![The Agent Hub as a switchboard: messages through the Hub, tools through the module door](docs/architecture/img/agents-switchboard.svg)](docs/architecture/img/agents-switchboard.svg)

## How it's built

A **modular monolith** using ports and adapters, dependency injection and events. Every module is a wrapper (manifest, start / stop / reload, context) with a menu of what it can do, and it reaches the rest of the app only through the core's ports: commands, events, contracts and the module directory. Parts that are useful on their own (the HTML viewer, the voice service) are their own apps, launched by a thin module.

## Docs

- [Architecture overview](docs/architecture/README.md)
- [Agents: big agents and their modules](docs/architecture/agents.md#big-agents-and-their-modules)
- [Module library](docs/architecture/module-library.md)
- [API reference](docs/api/README.md)

The browsable HTML is built with `python scripts/build_docs.py` into `docs/html/`.

## Running

```powershell
.\.venv\Scripts\python -m assistant
```

Configuration is in `config/default.toml`, with personal overrides in `config/local.toml` (not committed).
