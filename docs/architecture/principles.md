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
10. **Avoid premature complexity.** No distributed infrastructure, elaborate plugin systems, or speculative abstractions without an actual requirement.
11. **Runtime module control.** Every eligible module can be activated and deactivated independently through a central control interface while the app runs. The core owns lifecycle transitions; each module owns its resources and loads expensive ones only when needed. Dependencies are respected. Code changes may need a restart; runtime configuration changes never need a rebuild.
12. **Interfaces by inheritance, functionality by composition.** Classes inherit only interfaces (`Module`, `Contract` subclasses) to establish contracts, and are assembled from composed parts to get behavior. No deep inheritance hierarchies: no intermediate base classes that carry implementation. Shared behavior is a shared part, not a shared parent. A module can provide a contract through a composed object: `ctx.provide(ITaskAgent, self._agent)`.
    - **Naming:** `I` prefix if and only if the class subclasses `Contract` (`IToolProvider`, `ITaskAgent`). `Module`, `ModuleContext`, `Contract`, and concrete classes get no prefix.
    - **Mechanism:** contracts are `ABC`s, not `Protocol`s, because the core checks providers with `isinstance`.
