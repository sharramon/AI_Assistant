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
