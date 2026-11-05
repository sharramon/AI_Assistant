# Principles

The rules every design and implementation decision follows. If a change conflicts with one, raise it before proceeding. Back to the [overview](README.md).

**The core controls communication; modules control functionality.**

1. **Modularity and ease of experimentation come first**, ahead of architectural sophistication for its own sake.
2. **Stable contracts, disposable implementations.** Modules depend on interfaces, never on concrete implementations.
3. **Loose coupling.** Modules never import each other's internals. Use contract interfaces for direct interactions, commands for explicit actions, and events for notifications. DI only ever resolves shared contract interfaces, never a module's concrete type.
4. **Minimal core.** No experimental or module-specific logic in the host.
5. **Replaceable AI orchestration.** The model, agent framework, and orchestration logic are a module like any other.
6. **Module-owned state.** Each module manages its own state and exposes only what its contracts require.
7. **Independent lifecycles.** Modules can be initialized, started, suspended, and stopped independently.
8. **Graceful removal.** Removing an optional module must not break unrelated modules or require widespread changes.
9. **Technology independence.** Modules may later run out of process in other languages, so messages crossing module boundaries are plain, serializable data.
10. **Avoid premature complexity.** No distributed infrastructure, elaborate plugin systems, or speculative abstractions without an actual requirement. The one plugin mechanism is the module shape itself: modules found by folder, listed in the directory, and used through their menus ([modules](modules.md)).
11. **Runtime module control.** Every eligible module can be activated and deactivated independently through a central control interface while the app runs. The core owns lifecycle transitions; each module owns its resources and loads expensive ones only when needed. Dependencies are respected. A module's code is hot-swapped in place, and if the new code fails the old code runs again. A module's code changes, and adding a new module, never need a restart; only changes to the core, contracts or shared helpers do, including a new contract or port type. Runtime configuration changes never need a rebuild.
12. **Interfaces by inheritance, functionality by composition.** Classes inherit only interfaces (`ModuleProtocol`, `Contract` subclasses) to establish contracts, and are assembled from composed parts to get behavior. No deep inheritance hierarchies: no intermediate base classes that carry implementation. Shared behavior is a shared part, not a shared parent. A module can provide a contract through a composed object: `ctx.provide(ITaskAgent, self._agent)`.
    - **Naming:** `I` prefix if and only if the class subclasses `Contract` (`IToolProvider`, `ITaskAgent`). `ModuleContext`, `Contract`, and concrete classes get no prefix. A **protocol** gets none either: it's an interface a class satisfies by having the right methods. A contract is different: a capability one module offers and others look up through the container. Example: `ModuleProtocol` (built 2026-11-05), which every module satisfies.
    - **Mechanism:** contracts are `ABC`s, not `Protocol`s, because the core checks providers with `isinstance`.
13. **Build it once.** When two parts need the same behavior, it becomes one **reusable part**: written once, tested on its own, listed in the [reusable parts index](../api/reusable.md) with a **Used by** line, and used by both. A second copy is a bug.
    - **When it counts:** a second user exists or is in an approved change note, or the part implements a decided pattern (task agents, companion apps). "Might be useful one day" doesn't count (principle 10).
    - **What qualifies:** the behavior is the same, not just similar, and it knows nothing about any one module; a module's specifics come in as parameters.
    - **How:** by composition (principle 12): an object or function you compose, never a base class with code in it. Check the index before writing a helper. Where reusable parts live: [Reusable parts](reusable-parts.md).
14. **A module is a wrapper with a menu.** Every module is the same wrapper the core manages (a manifest with a one-line description, a lifecycle, a context) holding a menu of named tools, each with a description and its inputs: MCP-like, but ours only ([modules](modules.md#a-module-is-a-wrapper-with-a-menu)). Refines 3 and 12.
    - **Today:** the wrapper and `IToolProvider` menus are built; the one-line description is planned.
15. **Directory, then menu.** The Talker and the Main Assistant find capabilities the same way, one line per module first, then only that module's menu, then `InvokeTool`; no agent has another module's tools written into it ([modules](modules.md#find-a-module-then-open-its-menu)).
    - **Today:** planned. The Talker is hardcoded to the viewer's tools and the Main Assistant can't call tools; both are known gaps.
16. **Chain, don't glue.** A module uses another only through what that one declares (its events, commands, or menu), and a shared service serves several users through sessions with a destination each, never through copies of itself ([modules](modules.md#chaining-modules)). Refines 3; it's 13's "build it once" for running services.
    - **Today:** events between modules are built; voice sessions are planned (the voice service takes one listener at a time).
17. **Declared dependencies, found by folder.** A module is its folder: the core finds it there and first starts whatever provides the contracts its manifest `requires`; a module depends on contracts, never on another module's id, and never starts another module itself ([modules](modules.md#dependencies)). Extends 11's "dependencies are respected".
    - **Today:** `requires` by contract is built; finding modules by folder is planned (modules are still listed in `__main__.py`).
