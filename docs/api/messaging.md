# Messaging

Commands, events, and results. All items: `from assistant.contracts import ...`. Back to the [API index](README.md).

All messages are frozen pydantic models, so they're immutable and serialize to JSON (`model_dump_json()`), which lets them cross to remote clients later.

## `Message`

`class Message(BaseModel)`

Base for commands and events.

**Fields**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `id` | `str` | new uuid hex | Unique per message |
| `correlation_id` | `str \| None` | `None` | Links related messages: a reply to its request, progress to its job |
| `timestamp` | `datetime` | now (UTC) | When it was created |

**Defined in:** `src/assistant/contracts/messages.py`

## `Command`

`class Command(Message)`

Base for requests that exactly one handler carries out. Subclass it and add fields. Send with [`ModuleContext.send`](modules.md#modulecontextsend); handle with [`ModuleContext.handle`](modules.md#modulecontexthandle).

**Example**

    class OpenUrl(Command):
        url: str

**Defined in:** `src/assistant/contracts/messages.py`

## `Event`

`class Event(Message)`

Base for notifications that any number of modules may receive. Subclass it and add fields. Publish with [`ModuleContext.publish`](modules.md#modulecontextpublish).

**Defined in:** `src/assistant/contracts/messages.py`

## `Result`

`class Result(BaseModel)`

Outcome of a command. Every command returns exactly one. Build with the class methods below.

**Fields**
| Name | Type | Description |
|------|------|-------------|
| `status` | `Status` | Which outcome |
| `value` | `Any` | Payload when `ok` |
| `error` | `str \| None` | What went wrong otherwise |
| `retryable` | `bool` | Whether retrying might help |
| `is_ok` | `bool` (property) | `status is Status.OK` |

**Constructors**
| Method | Status | `retryable` | Use when |
|--------|--------|-------------|----------|
| `Result.ok(value=None)` | `ok` | `False` | It worked |
| `Result.invalid_arguments(error)` | `invalid_arguments` | `False` | Input was wrong; the caller can fix and retry |
| `Result.not_available(error)` | `not_available` | `False` | No handler, or the capability is off |
| `Result.failed(error, retryable=False)` | `failed` | as given | The handler ran and hit an error |
| `Result.timed_out(error)` | `timed_out` | `True` | Took too long (produced by the router) |
| `Result.cancelled(error="Cancelled")` | `cancelled` | `False` | Cancelled (produced by the router) |

Handlers normally return only `ok`, `invalid_arguments`, `not_available`, or `failed`. The router produces `timed_out` and `cancelled`, and turns handler exceptions into `failed`.

**Defined in:** `src/assistant/contracts/messages.py`

## `Status`

`class Status(StrEnum)`: `OK`, `INVALID_ARGUMENTS`, `NOT_AVAILABLE`, `FAILED`, `TIMED_OUT`, `CANCELLED`. Values are the lowercase names (`"ok"`, ...). Suggested agent reactions are in the [architecture overview](../architecture/README.md#command-results).

**Defined in:** `src/assistant/contracts/messages.py`

## `InputReceived`

`InputReceived(text: str, source: str, conversation_id: str | None = None)` (event)

User input from any source.

**Fields**
| Name | Type | Description |
|------|------|-------------|
| `text` | `str` | What the user said or typed |
| `source` | `str` | Id of the module (or client) it came from |
| `conversation_id` | `str \| None` | Groups inputs into a conversation, if the source tracks one |

**Defined in:** `src/assistant/contracts/messages.py`

## `ResponseReady`

`ResponseReady(text: str, conversation_id: str | None = None, correlation_id=...)` (event)

A reply to present. Set `correlation_id` to the `id` of the `InputReceived` it answers, so the source can tell which replies are its own.

**Defined in:** `src/assistant/contracts/messages.py`

## `ShutdownRequested`

`ShutdownRequested(reason: str = "")` (event)

Asks the host to shut down cleanly. Any module may publish it.

**Defined in:** `src/assistant/contracts/messages.py`
