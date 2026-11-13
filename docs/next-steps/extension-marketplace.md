# Extensions like a marketplace: what's built, what's missing

> **Status: proposed, all answers in (2026-11-07).** Research and a proposal only; no code changed, nothing reloaded. Your answers are in [Decisions](#decisions-2026-11-07); the design below follows them. Waiting on your check before anything is built.

**Design principle: design for future potential markets, not for the markets themselves today.** Keep the hooks a market would need: manifest fields, declared permissions, process isolation, hot load and unload, version compatibility. Build no store features, no signing and no sandbox now.

**Asked:** the project should have the same architecture as an extension marketplace. Extensions can be completely unloaded and brand-new ones loaded, written by other people, so the core can't know what exists. Extensions, and the new interfaces they bring, must be hot swappable. No store now: development is done with a store in mind.

**Short answer:** half of it is built. The **module half** is built: a manifest, a menu, contracts, a directory, add, turn off and reload while running, access cards, one door, finding modules by folder. That makes it a plug-in system *for code in this repo*. The **marketplace half** isn't built: installing from outside the repo, a manifest you can read before running any code, strangers' code kept out of the app's process, new contracts while running, versions, and an uninstall that leaves nothing behind. `job_search` and `cv` follow the module pattern, but `cv`'s own Python reaches the network, your folders and LibreOffice from inside the app, with nothing declared or asked.

Related: [self-contained modules](module-self-contained.md) (layout, umbrellas), [permissions](../architecture/permissions.md), [modules](../architecture/modules.md), [core](../architecture/core.md#runtime-module-control).

## Decisions (2026-11-07)

1. **Strangers' code never runs in the app's process.** How it's enforced: [Trust](#trust-how-strangers-code-is-kept-out-of-the-apps-process).
2. **A separate process now, an operating-system sandbox later:** yes. Until the sandbox, install only from people you trust.
3. **Where extensions live:** `%LOCALAPPDATA%\assistant\extensions\<id>\`, their data in `%LOCALAPPDATA%\assistant\data\<id>\`, outside the repo: yes.
4. **Python packages: one environment per extension that runs in its own process.** In plain words: each such extension gets its own private folder of the Python packages it needs, so two extensions that need different versions of a package can't break each other or the app. Modules inside the app keep the app's environment.
5. **Uninstall** always deletes its grants, code and data folder, and asks on the card about files it wrote elsewhere (your CVs stay unless you say): yes.
6. **`cv` is the pilot extension:** the first one used to prove the setup works, end to end, before any other module is moved to it. Nothing in `cv` changes until the extension host is built.
7. **Changed: new interfaces (contracts) load and swap while the app runs, with no restart.** Extensions are hot swappable, contracts included. This **overrides** the current rule that "a new module that needs a new contract needs a restart" ([core](../architecture/core.md#runtime-module-control), [modules](../architecture/modules.md#hot-swap)) for contracts brought by extensions. Design: [Contracts at runtime](#contracts-at-runtime-no-restart). The architecture pages change when this is built, not before.
8. **No store and no signing now; built with a store in mind.** The manifest carries `id`, `version`, `author`, `core_api` and a `checksum` slot from the start, so a store can be added later without a redesign.
9. **Names can't clash by accident.** Every extension command, event and contract name starts with the publisher and the extension id, then the interface name (`acme.cv.tailor.start`). A clash is refused at install and the second extension isn't loaded. Deliberate overlaps (several modules filling the same role, such as two voice modules) go through [umbrellas and their defaults](module-self-contained.md#umbrellas-modules-that-do-the-same-job-the-users-design-not-built-yet), never through shared names.
10. **A repo module may use an interface only an extension provides as optional, never required.** The core starts with no extensions at all. Example: the mic button asks for the `voice` role as optional and shows as unavailable when nothing fills it; the repo's own `voice_in` stays the default provider.

## 1. What's built, against marketplace needs

| Marketplace need | Today | Evidence |
|---|---|---|
| Core doesn't know what exists | **Mostly.** Modules are found by folder; `__main__` names none. The core still names a few (reviewer `main_assistant`, "you" = `temp_ui`, reserved agent ids, the SHOW tag → `viewer.open`, `TALKER = "talker"`); umbrellas would fix that, designed only | `core/loader.py:152`, `core/permissions/handler.py:55,119`, [self-contained note](module-self-contained.md#step-1-the-audit-what-lives-outside-each-modules-folder) |
| Load a brand-new extension while running | **Built, but only from inside the source tree.** `AddModule` imports `assistant.modules.<id>`; the folder must sit in `src/assistant/modules/` (`MODULES_PACKAGE`, `check_folder`) | `core/loader.py:28,143`, `core/lifecycle.py:174` |
| Unload it completely | **Turned off, not removed.** `DeactivateModule` stops it and `ctx.close()` removes its subscriptions, command handlers and contracts. There's no remove: the class stays in the lifecycle's list and `sys.modules`, it stays in the directory as "inactive", and its folder, config section, grants and files stay. Deleting the folder takes a restart | `core/context.py:111`, no `RemoveModule` in the core (searched) |
| What an unload leaves behind | **Depends on the module behaving.** Its own asyncio tasks and threads aren't tracked by the core ("old code left running", muted by the closed context). Companion apps quit only if the module launched them. `claude` sessions stop through `ProfileAgent.stop`, which releases the agent id. Grants stay in `data/permissions.toml` (removed only by a revoke). Tokens, output files and logs stay | [core: reloading](../architecture/core.md#reloading-a-modules-code), `core/permissions/handler.py:486` |
| A manifest that declares everything | **Partly.** It declares contracts, commands, events, and permission names. No version, author, core version, Python dependencies, network hosts, folders or accounts. Folders, commands and Chrome come from the **config** access list, and only for an agent worker | `contracts/module.py:36-60` |
| Read the manifest before running code | **No.** The manifest is a Python class attribute, so reading it imports (runs) the module's code. `build_docs.py` does the same | `core/loader.py:165` |
| Permissions checked | **For agent workers, yes; for module code, no.** Access lists go on one card, saved per kind of agent, and `claude` enforces them in its own process. Single names (`microphone`, `network`) are allowed and logged. A module's Python runs in the app's process as you and can do anything: [the limit](../architecture/permissions.md#the-limit) | [permissions](../architecture/permissions.md) |
| One door for agents, with a proven caller | **Built.** Three fixed tools; the caller is proved by its token; works for any module's menu | `infra/mcp_door.py`, [modules](../architecture/modules.md#how-the-agents-reach-the-menus-one-door) |
| Same menu and tools page for every extension | **Built for moved modules.** `Menu` with checked arguments; the tools page is generated from the menu; three standard pages required. Every module has moved (2026-11-12), the eight once kept central too | `app_kit/module_docs.py`, [standard layout](module-self-contained.md#the-standard-docs-layout-decided-2026-11-06) |
| An extension brings its own interfaces | **No.** Contracts are Python classes in `assistant.contracts`; a module needing a new one fails with "needs a restart". Whether a module may handle a command type of its own is *not confirmed* | [core](../architecture/core.md#reloading-a-modules-code) |
| Dependencies between extensions | **Built, by contract,** with the core starting the provider first and refusing to stop a needed one | [modules](../architecture/modules.md#dependencies) |
| Package, download, install, update, signing, registry, version checks | **None.** One Python distribution holds everything; Python dependencies are extras in `pyproject.toml` (e.g. `voice`) | [self-contained note](module-self-contained.md), decision 6 |

**Where it runs:** every module runs in the app's one Python process (a modular monolith, [decisions](../architecture/decisions.md#decided)). Separate processes today are the `claude` sessions (each agent), the companion apps (`html_viewer`, `voice_service`), and whatever a module starts itself (LibreOffice, a browser).

## 2. `job_search` and `cv` against this

| | `job_search` | `cv` |
|---|---|---|
| **Follows the pattern** | Yes: manifest (provides `ITaskAgent`, `permissions=("agent.access",)`), menu `job.search` (a stub), imports only `contracts` and `infra`. Not moved yet: page in `docs/modules/`, config in `default.toml:97-111`, test in `tests/` | Yes, and moved: `module.toml`, the three docs pages, own `tests/`. Imports `contracts`, `infra` and its own files (absolutely, as `assistant.modules.cv.*`, which ties it to that place in the tree) |
| **Inside the app's process** | The module, its menu, the `job.search` stub task | The module and its whole menu: `rezi.*` (an MCP **client** to `https://api.rezi.ai/mcp`, a browser sign-in with a callback server on `127.0.0.1:33418`, a 30-day token in `%LOCALAPPDATA%\assistant\cv\`), `cv.read` / `cv.build` / `cv.compare` / `cv.report` (reads your CVs, writes the output folder), the ODT writer |
| **Separate processes** | The `job_search_agent` `claude` session (with Claude in Chrome), stopped in `stop()` | The `cv_agent` `claude` session (Chrome, "only app.rezi.ai" by prompt, not enforced); LibreOffice `soffice` through a blocking `subprocess.run` (120 s timeout) that `stop()` doesn't track; the system browser for the sign-in |
| **Reaches outside its folder** | `C:\Jobs\CV` (workspace), `C:\Jobs`, `C:\Projects\Resume`, JobRadar's Python, Chrome, the job project's `CLAUDE.md` and skills. All on its access card | On the worker's card: workspace `C:\Jobs\rezi\cv_agent`, read folders, Chrome. **Not declared or asked anywhere:** the module's own network calls to Rezi and the callback port, the token file, reading the CV folder, writing `C:\Jobs\rezi\rezi\out`, running `soffice.exe`, a LibreOffice profile in `%TEMP%\assistant-cv-soffice`, writing resumes into your Rezi account |
| **Names from the core / other modules** | The Hub through `ProfileAgent` (`IAgentNames`, `IModuleDoor`); `AgentNotice` to its caller. Named by `talker/prompt.py:145` and `temp_ui/agent_tabs.py:8` | `hub.start` and `cv_agent` in `cv.task`'s answer; `viewer.open` in the worker's prompt; `REPO = parents[4]` (`module.py:69`) assumes it sits in the repo; `tests/test_worker.py:22` imports `assistant.modules.agent_hub` |
| **Left behind on unload** | Grant `job_search → job_search_agent`; the handler's `_agents` entry; the transcript in `logs/`; `.claude/state/<id>-task.txt`; the job project's files | The same, plus the Rezi token, the LibreOffice profile, output CVs and reports, and the Rezi resumes it made (tracked only until a restart) |

**Both:** stopping kills the `claude` process (`claude_session.py:299-312`) but not its process tree; whether its children (the Chrome bridge, MCP clients) die with it is *not confirmed*. The permissions handler's `_agents[agent_id]` entry is added by `own_agent` and never removed (`core/permissions/handler.py:181`). **`cv` on import** changes the global `sys.path` and adds DLL folders (`mcp.py:58`), which affects the whole app: exactly what a stranger's in-process code could do unseen.

So both are well-behaved modules. As extensions they'd fall short in one way each: `job_search` isn't self-contained yet, and `cv` does real work in the app's process that nothing declares or checks.

## 3. The gaps for a marketplace

1. **Package format.** Nothing yet. Needed: one zip holding the folder, the static manifest, docs, tests and a dependency list.
2. **A manifest that declares everything, readable without running code** ([below](#the-manifest-extensiontoml)).
3. **Trust and isolation.** Today all module code runs in the app's process as you. Strangers' code must not ([decision 1](#decisions-2026-11-07)).
4. **Contracts at runtime.** Today a new contract needs a restart; extensions must bring their own while the app runs ([decision 7](#decisions-2026-11-07)).
5. **Version compatibility.** No core API version, no check at load.
6. **Install, update, uninstall.** Install means copying into `src/` and `AddModule`. No uninstall; no per-extension data folder, so the core can't know where an extension wrote.
7. **Tracked work.** The core can't end a module's tasks, threads or child processes; it relies on `stop()`. A process per extension fixes this for extensions (kill the process tree).
8. **Same standard for everyone.** The menu, the generated tools page and the three pages are built; needed is to make them a load-time rule for extensions, and links to the app's docs only through `[related]`.
9. **Umbrellas and defaults.** Designed in the [self-contained note](module-self-contained.md#umbrellas-modules-that-do-the-same-job-the-users-design-not-built-yet), not built. A marketplace needs them so the core's own needs (SHOW, the reviewer, "you") go to a default instead of a named module.
10. **Shared parts across the process line.** `ProfileAgent`, `request_access` and `CompanionApp` are imported Python today. An extension in its own process needs them through the host.
11. **Store and signing:** later ([decision 8](#decisions-2026-11-07)); only the manifest fields now.

**Not confirmed:** whether a module may define and handle its own command or event types without a restart today; whether the Rezi client closes cleanly on stop; whether `claude`'s child processes die with it; which Windows sandbox would work on Windows 11 Home.

## The design

### Two kinds of module

| | **Built-in module** | **Extension** |
|---|---|---|
| Where | `src/assistant/modules/<id>/` (the repo) | `%LOCALAPPDATA%\assistant\extensions\<id>\` |
| Runs | In the app's process, as today | Always in its own process, the **extension host** |
| Python packages | The app's environment | Its own environment ([decision 4](#decisions-2026-11-07)) |
| Reached through | Commands, events, contracts, its menu | The same, relayed by the host; agents reach its menu through the module door |
| Unload | `stop()`, then `ctx.close()` | `stop()`, then the core kills the host's process tree |

### Trust: how strangers' code is kept out of the app's process

- **The loader imports only from the repo's own module folder.** `find_modules` and `AddModule` already look only under `assistant.modules` (`MODULES_PACKAGE`). That stays a hard rule: no configurable root, no extra path.
- **The extensions folder is never imported.** It's never on `sys.path`. Anything found there is always launched as a separate process (`python -I` in the extension's own environment, running the host), and the app reaches it only through the host's socket and the module door.
- **An extension can't mark itself trusted.** A `trusted` key (or anything like it) in `extension.toml` is refused at install. The trust flag is set only by the core, kept in its own state in the protected zone (`data/extensions.toml`, beside `data/permissions.toml`), and changed only by your answer on a card. Moving an extension into the repo's module folder is a code change you review, not a flag.
- **The host has no core objects.** It gets a token, like an agent at the door, so every call it makes carries a proven caller, and the permission card names the extension.
- **What a process alone doesn't stop:** the extension's code can still read your files and use the network as you. That needs the OS sandbox ([decision 2](#decisions-2026-11-07)); until then, install only from people you trust.

### Contracts at runtime (no restart)

**Why a new contract needs a restart today:** a contract is a Python class in `assistant.contracts`, and every module holds that class. Swapping it would break `isinstance` checks and contract identity, so contracts can't be reloaded.

**The change:** contracts brought by extensions become **data the core holds**, not Python classes every module imports.

- **A contract is a declaration**, shipped in the extension's folder (`contracts/<name>.toml`): its name, a version (`cv.tailor@1`), and its operations, commands and events, each with a JSON Schema, the same shape as a menu item. The core's built-in contracts (`IVoice`, `ITaskAgent`, the core's commands) stay Python classes in `assistant.contracts`; changing those is still a core change.
- **The core keeps a contract registry**, added to and removed from while running: `register(declaration, owner)` when the extension loads, `remove(owner)` when it unloads. A second declaration of the same name and major version must match the first, or it's refused.
- **Calls go by name, checked by schema.** The router and the bus key extension commands and events by name (`cv.tailor.start`), not by Python type, and check arguments against the schema, as menus already do. A built-in module that uses an extension's contract gets a caller object (`ctx.contract("cv.tailor@1")`) that sends by name, so no Python class crosses over.
- **Names:** `<publisher>.<extension id>.<interface>` for contracts, and the same prefix for their commands and events ([decision 9](#decisions-2026-11-07)). The install checks every name against the registry; a clash refuses the install and nothing of the second extension loads.
- **`requires` by name and major version.** An extension's manifest lists `requires = ["acme.cv.tailor@1"]`; the core resolves it at activation, as today, from the registry. A repo module may list an extension's contract only under `optional` ([decision 10](#decisions-2026-11-07)), so the app starts and runs with no extensions installed; the load check refuses a repo module that requires one.
- **When the provider unloads:** modules that require it are stopped first (the card names them, like `with_dependents` today) and go to a new state, **waiting**, with the reason ("waiting for cv.tailor@1"). They aren't failed or forgotten. When any provider of that contract is back, they start again on their own.
- **When the provider reloads (a hot swap):** calls to it are held, as `CommandRouter.hold` does today, and its dependents keep running. If the new copy changes the contract within the same major version (new optional fields), dependents carry on. If it changes the major version, dependents that require the old one go to waiting.
- **When the declaration is removed:** only when no provider declares it any more; a held call then fails with `not_available`.

So the rule becomes: **changes to the core and its built-in contracts need a restart; an extension and the contracts it brings don't.**

### The manifest: `extension.toml`

Read before any code runs; shown on the install card; the core holds the extension to it.

```toml
id = "cv"
version = "1.0.0"
author = "..."
core_api = ">=1,<2"        # the core's API versions it works with
checksum = ""              # empty now; a store fills it (sha256 of the package) and the core checks it
description = "..."
umbrella = ""              # later
provides = ["cv.tailor@1"] # contracts, declared in contracts/
requires = []
python = "requirements.txt"

[needs]
read = ["C:/Jobs/CV"]
write = ["C:/Jobs/rezi/rezi/out"]
network = ["api.rezi.ai"]
listen = ["127.0.0.1:33418"]
accounts = ["rezi"]
commands = ["C:/Program Files/LibreOffice/program/soffice.exe"]
chrome = true
agent = "cv_agent"         # its worker, with its access list as today
```

No `trusted` key: [trust](#trust-how-strangers-code-is-kept-out-of-the-apps-process) is the core's.

## 4. Recommended path, in small steps

Tests and ruff after each. "Restart" = a core, contracts, infra or `app_kit` change; these are one-time costs of building the setup. Once it's built, extensions and their contracts load, swap and unload without a restart.

| # | Step | Restart? |
|---|---|---|
| 1 | **`extension.toml`** read without importing; checked against the menu at load. Written for `cv` first (no `cv` code changes) | Restart |
| 2 | **Core API version** (`CORE_API` in contracts) and the `core_api` check; `checksum` kept and checked when filled | Restart (with 1) |
| 3 | **`ctx.data_dir`** (`%LOCALAPPDATA%\assistant\data\<id>\`) and **remove**: `modules.remove` on the core's menu (a card): turn off, drop it, remove its grants and the handler's `_agents` entry, delete its data folder, ask about other files | Restart |
| 4 | **Contract registry** for declared contracts, calls by name with schema checks, `requires` by name and major version, the **waiting** state and the restart of waiting modules | Restart |
| 5 | **Extension host**: `python -I -m assistant.ext_host <folder>` in the extension's own environment, over a local socket (menu calls, events, commands, declared contracts), with its own door token; unload kills the process tree. The trust flag in `data/extensions.toml` | Restart |
| 6 | **Pilot `cv`** as the first extension: a copy installed from the extensions folder, run in the host, proven end to end (sign-in, build, the worker, unload, reload, remove). The repo copy stays until the pilot passes | No restart (that's the point) |
| 7 | **Install and update from a zip**: `extensions.install / update` on the core's menu, the card showing `[needs]` | Restart (with 5) |
| 8 | **Umbrellas** as designed, so the core names no module | Restart |
| 9 | **Later:** the OS sandbox; a store and signing | — |

Steps 1 to 5 and 7 could share one restart if built together. `job_search` moving into its own folder (self-contained step 3) needs only a reload; it becomes an extension after the `cv` pilot passes.

## Open questions

None left: all ten are answered ([Decisions](#decisions-2026-11-07)). Where the publisher name comes from (the manifest's `author` for now, a store account later) is settled when step 1 is built.
