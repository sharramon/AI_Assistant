# Core host (internal)

The stable host in `assistant.core`. Modules never use these directly; they go through [`ModuleContext`](modules.md#modulecontext). Listed here so nothing gets rebuilt elsewhere. Back to the [API index](README.md). Design and behavior: [core architecture](../architecture/core.md).

## `App`

`App(available: Sequence[type[Module]], config: dict[str, Any])`

Wires the core together and runs the enabled modules. Construction validates the module selection.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `available` | `Sequence[type[Module]]` | yes | Every module the app can run (`MODULES` in `__main__.py`) |
| `config` | `dict` | yes | From [`load_config`](infra.md#load_config) |

**Raises:** [`StartupError`](#startuperror) if the enabled modules can't run together.

**Attributes:** `router: CommandRouter`, `bus: EventBus`, `container: Container`.

| Method | Description |
|--------|-------------|
| `async run()` | `start()`, wait for shutdown (or task cancellation), then `stop()` |
| `async start()` | Register the `InvokeTool` handler, subscribe to `ShutdownRequested`, init and start modules. May raise `StartupError` |
| `async stop()` | Cancel in-flight commands, stop modules in reverse order, close the bus |
| `request_shutdown()` | Make `run()` proceed to `stop()` |

**Defined in:** `src/assistant/core/app.py`

## `StartupError`

`class StartupError(Exception)`

The configured modules can't run together: raised by [`resolve_modules`](#resolve_modules) or by [`LifecycleManager.start`](#lifecyclemanager) when a required provider fails.

**Defined in:** `src/assistant/core/registry.py`

## `resolve_modules`

`resolve_modules(available: Sequence[type[Module]], enabled: Sequence[str]) -> list[type[Module]]`

Select the `enabled` modules and return them in start order: providers before the modules that require or optionally use them, otherwise in `enabled` order.

**Raises:** `StartupError` for unknown or duplicate ids, non-shared contracts in a manifest, a missing required contract, more than one provider of a single-provider contract, or a circular dependency.

**Defined in:** `src/assistant/core/registry.py`

## `LifecycleManager`

`LifecycleManager(modules: list[type[Module]], make_context: Callable[[Manifest], ScopedContext], stop_timeout: float = 5.0)`

| Method | Description |
|--------|-------------|
| `async start()` | Instantiate and `init` each module, then `start` each, in order. A failing module is closed and skipped; raises `StartupError` if another module requires a contract only it provides |
| `async stop()` | `stop` each active module in reverse order (with `stop_timeout`), then close its context |

**Defined in:** `src/assistant/core/lifecycle.py`

## `ScopedContext`

`ScopedContext(manifest, router, bus, container, config, log)`

The [`ModuleContext`](modules.md#modulecontext) implementation. Records every subscription, handler, and provided contract made through it.

| Method | Description |
|--------|-------------|
| `close()` | Remove everything this module registered |

**Defined in:** `src/assistant/core/context.py`

## `CommandRouter`

`CommandRouter(default_timeout: float = 30.0, timeouts: dict[str, float] | None = None)`

`timeouts` maps command class names to per-type timeouts.

| Method | Description |
|--------|-------------|
| `register(command_type, handler)` | Set the single handler. Raises `ValueError` if one exists |
| `unregister(command_type, handler)` | Remove it, only if it's still the registered handler |
| `async send(command, timeout=None) -> Result` | Run the handler as a task; map every outcome to a `Result` (see [internals](../architecture/core.md#communication-internals)) |
| `cancel(correlation_id) -> int` | Cancel in-flight commands whose `id` or `correlation_id` matches |
| `cancel_all() -> int` | Cancel every in-flight command |

**Defined in:** `src/assistant/core/router.py`

## `EventBus`

`EventBus(queue_size: int = 100, handler_timeout: float | None = 10.0)`

| Method | Description |
|--------|-------------|
| `subscribe(event_type, handler, owner="core") -> Subscription` | Start a worker delivering matching events (subclasses included) from a bounded queue |
| `unsubscribe(sub)` | Stop delivery; queued events are dropped |
| `publish(event)` | Enqueue for each matching subscriber; never blocks. Drops and logs when a queue is full |
| `async close()` | Cancel and await all workers |

`Subscription` has `event_type`, `owner`, `task`, and `offer(event) -> bool`.

**Defined in:** `src/assistant/core/bus.py`

## `Container`

`Container()`

| Method | Description |
|--------|-------------|
| `provide(contract, impl, owner)` | Register a provider. `TypeError` if `contract` isn't shared or `impl` doesn't implement it; `ValueError` if a single-provider contract already has one |
| `remove_owner(owner)` | Remove everything `owner` provided |
| `get_all(contract) -> list` | All providers, possibly empty |
| `get_one(contract)` | First provider or `None` |

**Defined in:** `src/assistant/core/container.py`

## `is_shared_contract`

`is_shared_contract(t: object) -> bool`

True for `Contract` subclasses defined under `assistant.contracts` (excluding `Contract` itself).

**Defined in:** `src/assistant/core/container.py`

## `dispatch_tool`

`async dispatch_tool(container: Container, command: InvokeTool) -> Result`

The `InvokeTool` handler. Looks up providers at call time; returns `not_available` for an unknown tool, `failed` for a name offered twice, else the provider's result.

**Defined in:** `src/assistant/core/tools.py`
