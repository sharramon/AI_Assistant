# Modules

Writing a module. All items: `from assistant.contracts import ...`. Back to the [API index](README.md).

## `Module`

`class Module(ABC)`

Base class for every module. Set the `manifest` class attribute and implement `init`.

The core calls `init` for every module in dependency order, then `start` for each, and on shutdown `stop` in reverse order. `stop` is called for every module whose `init` succeeded, even if `start` never ran. If `init` or `start` raises, the module is skipped (see [lifecycle](../architecture/core.md#lifecycle)).

**Attributes**
| Name | Type | Description |
|------|------|-------------|
| `manifest` | `ClassVar[Manifest]` | Required. Identifies the module and its dependencies |

### `Module.init`

`async init(self, ctx: ModuleContext) -> None`

Abstract. Subscribe to events, register command handlers, and provide contracts here. Keep `ctx` if the module needs it later. Don't start background work yet.

### `Module.start`

`async start(self) -> None`

Begin active work: listening for input, background loops. Default does nothing.

### `Module.stop`

`async stop(self) -> None`

Stop work and release resources. Default does nothing. Has `core.module_stop_timeout` seconds. Subscriptions, handlers, and provided contracts are removed by the core afterwards, so there's no need to undo them here.

**Example**

    class EchoOrchestrator(Module):
        manifest = Manifest(id="echo_orchestrator", optional=(ToolProvider,))

        async def init(self, ctx: ModuleContext) -> None:
            self._ctx = ctx
            ctx.subscribe(InputReceived, self._on_input)

        async def _on_input(self, event: InputReceived) -> None:
            self._ctx.publish(ResponseReady(text=f"Echo: {event.text}", correlation_id=event.id))

**Defined in:** `src/assistant/contracts/module.py`
**See also:** [`Manifest`](#manifest), [`ModuleContext`](#modulecontext), [adding a module](../architecture/core.md#adding-replacing-or-removing-a-module)

## `Manifest`

`Manifest(id: str, provides: tuple = (), requires: tuple = (), optional: tuple = ())`

Frozen dataclass describing a module. Dependencies are on contracts, never on other modules.

**Fields**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `str` | yes | Unique id, used in `modules.enabled` and as the config section name |
| `provides` | `tuple[type[Contract], ...]` | no | Contracts this module provides via `ctx.provide` |
| `requires` | `tuple[type[Contract], ...]` | no | Contracts that must be provided by an enabled module, or startup fails |
| `optional` | `tuple[type[Contract], ...]` | no | Contracts used if present; only affects start order |

Every type listed must be a [`Contract`](#contract) from `assistant.contracts`, or startup fails.

**Defined in:** `src/assistant/contracts/module.py`

## `ModuleContext`

`class ModuleContext(ABC)`

A module's only access to the rest of the app, passed to `init`. Everything registered through it is removed automatically when the module stops.

**Attributes**
| Name | Type | Description |
|------|------|-------------|
| `module_id` | `str` | This module's id |
| `config` | `dict[str, Any]` | The `[modules.<id>]` config section, or `{}` |
| `log` | `logging.Logger` | Logger named `assistant.modules.<id>` |

### `ModuleContext.subscribe`

`subscribe(event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None`

Receive every published event that is an instance of `event_type` (subclasses included). The handler runs on this subscription's own worker, one event at a time, in order. It is cancelled after `core.event_handler_timeout`; exceptions are logged.

### `ModuleContext.publish`

`publish(event: Event) -> None`

Publish an event. Returns immediately and never waits on subscribers. Events are dropped for a subscriber whose queue is full.

### `ModuleContext.handle`

`handle(command_type: type[K], handler: Callable[[K], Awaitable[Result]]) -> None`

Become the single handler for `command_type`. The handler must return a [`Result`](messaging.md#result).

**Raises:** `ValueError` if the command type already has a handler.

### `ModuleContext.send`

`async send(command: Command, timeout: float | None = None) -> Result`

Send a command to its handler and wait for the result. Never raises for handler problems; see [`Result`](messaging.md#result) for the outcomes.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `command` | `Command` | yes | The command to send |
| `timeout` | `float \| None` | no | Seconds. Defaults to `core.command_timeouts.<Class>`, then `core.command_timeout` |

**Example**

    result = await ctx.send(InvokeTool(name="add", args={"a": 1, "b": 2}))
    if result.is_ok:
        print(result.value)

### `ModuleContext.cancel`

`cancel(correlation_id: str) -> int`

Cancel in-flight commands whose `id` or `correlation_id` matches. Returns how many were cancelled. Their senders get `Status.CANCELLED`.

### `ModuleContext.provide`

`provide(contract: type[C], impl: C) -> None`

Offer `impl` as a provider of `contract`.

**Raises:** `ValueError` if `contract` isn't in `manifest.provides`, or if it is a single-provider contract that already has a provider. `TypeError` if `impl` doesn't implement `contract`.

### `ModuleContext.get_all`

`get_all(contract: type[C]) -> list[C]`

All current providers of `contract`, possibly empty. Call it when needed rather than caching, since providers can change.

### `ModuleContext.get_one`

`get_one(contract: type[C]) -> C | None`

The provider of a single-provider contract, or `None`.

**Defined in:** `src/assistant/contracts/module.py` (interface), `src/assistant/core/context.py` (implementation)

## `Contract`

`class Contract(ABC)`

Base for capability interfaces that modules provide and resolve. Subclasses must be defined under `assistant.contracts`; the core rejects any other type.

**Attributes**
| Name | Type | Description |
|------|------|-------------|
| `multiple` | `ClassVar[bool]` | Whether several modules may provide it at once. Default `False` |

**Defined in:** `src/assistant/contracts/module.py`
**See also:** [`ToolProvider`](tools.md#toolprovider)
