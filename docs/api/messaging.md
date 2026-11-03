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

`class Status(StrEnum)`: `OK`, `INVALID_ARGUMENTS`, `NOT_AVAILABLE`, `FAILED`, `TIMED_OUT`, `CANCELLED`. Values are the lowercase names (`"ok"`, ...). Suggested agent reactions are in the [communication architecture](../architecture/communication.md#command-results).

**Defined in:** `src/assistant/contracts/messages.py`

## `InputReceived`

**Reusable** · Used by: `console_io`, `temp_ui`, `voice_in` (planned) publish; `talker`, `echo_orchestrator` subscribe

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

**Reusable** · Used by: `talker`, `echo_orchestrator` publish; `console_io`, `temp_ui` subscribe

`ResponseReady(text: str, conversation_id: str | None = None, correlation_id=...)` (event)

A reply to present. Set `correlation_id` to the `id` of the `InputReceived` it answers, so the source can tell which replies are its own. Leave it `None` when the assistant speaks first (e.g. "the task is done"); `console_io` prints those too.

**Defined in:** `src/assistant/contracts/messages.py`

## `ShutdownRequested`

`ShutdownRequested(reason: str = "")` (event)

Asks the host to shut down cleanly. Any module may publish it.

**Defined in:** `src/assistant/contracts/messages.py`

## `SessionTheme`

`SessionTheme(text: str)` (event)

A few words about what this app session is about, from your first question. The Talker publishes it once; `__main__` passes it to [`LogSession.set_theme`](infra.md#logsession), which creates the session's log folder with it in the name. Until then nothing is written to disk. If the first turn fails, the Talker still publishes it, with the message itself.

**Defined in:** `src/assistant/contracts/messages.py`

## `ViewerTabsChanged`

`ViewerTabsChanged(tabs: tuple[str, ...] = (), active: str | None = None, highlights: tuple[tuple[str, str], ...] = ())` (event)

The [HTML viewer](../architecture/html-viewer.md)'s open tabs or highlights changed: a tab opened, closed, or was switched to, or a highlight was added, cleared, or dropped. `tabs` are the open files' full paths in tab order; `active` is the one showing; `highlights` are `(path, quoted text)` pairs. The `html_viewer` module publishes it; the Talker keeps the latest and hears it, as a `[Viewer] open: ...; highlighted: ...` line, with your next message.

**Defined in:** `src/assistant/contracts/messages.py`

## `ViewerClip`

`ViewerClip(id: str, image_path: str, file: str, heading: str | None = None)` (event)

You snipped part of a page in the [HTML viewer](../architecture/html-viewer.md). `image_path` is the PNG, kept in the launch's log folder (`snips/`); `file` is the page; `heading` the nearest heading above the box. The `html_viewer` module publishes it. The Talker keeps up to 3 and sends them as images with your next message; the temp UI shows them as thumbnails until then.

**Defined in:** `src/assistant/contracts/messages.py`

## `ViewerClipDropped`

`ViewerClipDropped(id: str)` (event)

You dropped a snip before sending it (the × on its thumbnail). The Talker forgets it. Published by `temp_ui`.

**Defined in:** `src/assistant/contracts/messages.py`

## Voice

Voice input ([design](../architecture/voice.md#the-voice_in-module)). Any UI sends the commands; `voice_in` handles them and publishes the events. `VoiceState` and `VoiceTranscript` carry `correlation_id` = the session id (the `StartListening` command's id), so a UI can drop a stale session's updates. Built 2026-11-03; `voice_in` itself is planned.

### `StartListening`

**Reusable** · Used by: `temp_ui` (planned) sends; `voice_in` (planned) handles

`StartListening(send_as_input: bool = True)` (command)

Turn the mic on. With `send_as_input=False` (dictating into a text box, say) the text goes only to `VoiceTranscript` subscribers, never to the Talker. **Result:** `ok` once the service says `started`, value `{"session_id"}`; already listening: `ok` with the same session. `not_available` (retryable) if the service couldn't start or the mic or engine failed; `failed` for `busy` or a denied `microphone` permission.

### `StopListening`

**Reusable** · Used by: `temp_ui` (planned) sends; `voice_in` (planned) handles

`StopListening()` (command)

Turn the mic off. **Result:** `ok` after the final arrives, value `{"text", "latency_ms"}`; nothing listening: `ok` with `None`.

### `ListeningState`

**Reusable** · Used by: `VoiceState`

`StrEnum`: `idle` (mic off), `starting` (clicked; the service may be launching, the mic opening), `listening` (mic open, text coming), `failed` (went wrong; the event's `reason` and `detail` say what).

### `VoiceState`

**Reusable** · Used by: `voice_in` (planned) publishes; `temp_ui` (planned) subscribes

`VoiceState(state: ListeningState, reason: str | None = None, detail: str | None = None)` (event)

The mic's state changed. `reason` is the service's error code, `"service_stopped"`, or `"silence"` on an idle after a silence stop; `detail` is a short sentence for the button.

### `VoiceTranscript`

**Reusable** · Used by: `voice_in` (planned) publishes; `temp_ui` (planned) and any module that wants voice text subscribe

`VoiceTranscript(session_id: str, text: str, final: bool = False)` (event)

The live text: each partial (`final=False`), then once the final text (`final=True`; empty clears the line). This is the public stream of voice text; `InputReceived(source="voice")` is only the Talker's way in.

**Defined in:** `src/assistant/contracts/voice.py`

### The voice service protocol

**Reusable** · Used by: `voice_service` server (planned), `voice_in` client (planned)

`from voice_service.protocol import ...` (not `assistant.contracts`: the service never imports the assistant). The [`/ws/listen` protocol](../architecture/voice.md#the-protocol) as frozen pydantic models, one JSON object per text frame, so the service and its Python clients share one definition. `voice_service/__init__.py` is empty, so importing it doesn't pull in FastAPI or sherpa-onnx.

| Item | Kind | Summary |
|------|------|---------|
| `Start`, `Stop` | app → service | `{"type": "start"}`, `{"type": "stop"}` |
| `Started` | service → app | The mic is open |
| `Partial(text)` | service → app | The text so far |
| `Final(text, latency_ms, complete=True, ended_by="stop")` | service → app | The finished text; `ended_by` is `"stop"` or `"silence"` |
| `Error(reason: ErrorCode, detail="")` | service → app | A fixed code and a sentence for the log |
| `ErrorCode` | `StrEnum` | `busy`, `mic_unavailable`, `mic_lost`, `engine_failed`, `bad_message` |
| `parse_client_message(raw)` | function | A frame from the app: `Start \| Stop`. Raises `ProtocolError` |
| `parse_service_message(raw)` | function | A frame from the service: `Started \| Partial \| Final \| Error`. Raises `ProtocolError` |
| `dump(message)` | function | A message as one JSON text frame |
| `ProtocolError` | exception (`ValueError`) | Not JSON, not an object, unknown `type`, a missing or bad field, or the wrong direction; the service answers `bad_message` |

**Defined in:** `src/voice_service/protocol.py`
