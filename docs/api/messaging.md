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

**Reusable** · Used by: `console_io`, `temp_ui`, `voice_in` (`source="voice"`) publish; `talker`, `echo_orchestrator` subscribe

`InputReceived(text: str, source: str, conversation_id: str | None = None, agent_id: str | None = None)` (event)

User input from any source.

**Fields**
| Name | Type | Description |
|------|------|-------------|
| `text` | `str` | What the user said or typed |
| `source` | `str` | Id of the module (or client) it came from. `"voice"` (from `voice_in`) reaches the Talker's session as `[Spoken] <text>`, so it reads the text as possibly misheard |
| `conversation_id` | `str \| None` | Groups inputs into a conversation, if the source tracks one |
| `agent_id` | `str \| None` | The agent tab it was typed in (the temp UI's chat box sets it). `None` (voice, terminal 1): the focused tab. Added 2026-11-05 (agent talkers) |

**Defined in:** `src/assistant/contracts/messages.py`

## `ResponseReady`

**Reusable** · Used by: `talker`, `echo_orchestrator` publish; `console_io`, `temp_ui` subscribe

`ResponseReady(text: str, conversation_id: str | None = None, agent_id: str | None = None, correlation_id=...)` (event)

A reply to present. Set `correlation_id` to the `id` of the `InputReceived` it answers, so the source can tell which replies are its own. Leave it `None` when the assistant speaks first (e.g. "the task is done"); `console_io` prints those too. `agent_id`: the agent tab whose chat it belongs in (the Talker sets it); `None` means the focused tab.

**Defined in:** `src/assistant/contracts/messages.py`

## `ShutdownRequested`

`ShutdownRequested(reason: str = "", restart: bool = False)` (event)

Asks the host to shut down cleanly. Any module may publish it. With `restart`, `App.restart_requested` is set, the app exits with `core.restart_exit_code` (75), and the launcher (`python -m assistant`) starts it again. Published with `restart` by the Talker's `<<RESTART>>` ([Restart](../agents/runtime.md#the-talker-on-its-own)).

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

**Shared limits** (in `assistant.contracts`, one owner, principle 19): `MAX_SNIPS = 3`, the snips sent with one message (the Talker keeps, the temp UI shows at most this many); `PASTED_FILE = "(pasted)"`, a pasted image's `file`. Used by `talker`, `temp_ui`.

You snipped part of a page in the [HTML viewer](../architecture/html-viewer.md). `image_path` is the PNG, kept in the launch's log folder (`snips/`); `file` is the page; `heading` the nearest heading above the box. The `html_viewer` module publishes it; so does `temp_ui` for an image pasted into its chat box (`file=PASTED_FILE`, `"(pasted)"`, no heading; the Talker labels it `[Pasted] image`). The type's docstring still says "from the HTML viewer": widen it at the next restart. The Talker keeps up to `MAX_SNIPS` (3) and sends them as images with your next message; the temp UI shows them as thumbnails until then.

**Defined in:** `src/assistant/contracts/messages.py`

## `ViewerClipDropped`

`ViewerClipDropped(id: str)` (event)

You dropped a snip before sending it (the × on its thumbnail). The Talker forgets it. Published by `temp_ui`.

**Defined in:** `src/assistant/contracts/messages.py`

## Access and permissions

Access lists and the messages of the core's [permissions handler](../architecture/permissions.md#access-lists-built) (its first piece). A task-agent module asks for its whole list with [`ctx.permissions.request_set`](modules.md#modulecontextpermissions); the handler answers from a saved grant, or asks you on one card: `PermissionRequested` → `AnswerPermissionRequest` → `PermissionChanged`. Built 2026-11-05.

**Reusable** · Used by: `job_search`, `task_agents` (lists, through [`request_access`](infra.md#agent_access)); the core's handler (sends the cards); `talker`, `temp_ui` (show and answer them)

### `AccessKind`

`class AccessKind(StrEnum)`: `workspace` (its working folder, read and write; always kept when the list is allowed), `read` (a folder), `write` (a folder), `python` (a Python, with any arguments), `command` (a shell command, with any arguments), `chrome` (the Claude in Chrome tools).

### `AccessItem`

`AccessItem(kind: AccessKind, target: str = "")` (frozen)

One line of an access list. `target`: the resolved folder, the Python's path or the command; empty for Chrome.

| Member | Does |
|--------|------|
| `key` | `kind:target` (or `chrome`): names the item in answers and saved grants |
| `from_key(key)` | The item a key names. `ValueError` for an unknown kind |
| `trimmable` | Whether the card gives it a tick box (not the workspace) |
| `label` | The line on the card: "read C:\Chang\Jobs", "run … (any arguments)", "use Chrome" |

### `AccessNote`

`AccessNote(text: str, items: tuple[str, ...] = (), source: "rule" | "review" | "refused" = "rule")` (frozen)

A line on the card about some items (their keys): a fixed rule warning, the Main Assistant's review note, or an item taken off the list.

### `AccessDenied`, `AccessPending`

Exceptions from `request_set`. `AccessDenied`: you denied the list, didn't answer in time, or the workspace was refused. `AccessPending`: the list waits on a card (`wait=False`); a module's `start` lets it through, so the start ends at once with this reason, and the handler turns the module on after your Allow.

### `PermissionRequested`

`PermissionRequested(request_id, module_id, subject="", action="access", reason="", items=(), notes=(), reviewed=None, rules=(), caller="")` (event)

A card for you. `action`: `access` (a module's list), or `grant` / `revoke` (an agent's call, `caller`, waiting for your yes). `items`: the lines offered. `notes`: refused items, rule warnings, then the review's notes. `reviewed`: `True` or `False` for an access list (`False` shows "not reviewed"), `None` for no review step. `rules`: the fixed rules. Published by the handler; `temp_ui` shows it with tick boxes, the Talker says it.

### `AnswerPermissionRequest`

`AnswerPermissionRequest(request_id: str, allow: bool, keep: tuple[str, ...] | None = None)` (command)

Your answer to a card. `keep`: the keys of the ticked items (`None`: all of them); ignored on Deny. Handled by the core. `invalid_arguments` if the card isn't open or a key isn't on it.

### `PermissionChanged`

`PermissionChanged(module_id, subject="", granted=(), request_id="", text="")` (event)

A grant was saved, denied, widened or revoked. `request_id`: the card it closes, if any (UIs drop it). `granted`: what the module or subject holds now. `text`: what happened, for you.

**Defined in:** `src/assistant/contracts/permissions.py` · **Tests:** `tests/test_permissions_handler.py`, `tests/test_access_cards.py`

## Voice

Voice input ([design](../architecture/voice.md#the-voice_in-module)). A module that needs the mic requires the voice contract [`IVoice`](#ivoice); a UI button may send the commands instead. `voice_in` provides the one and handles the other, with the same sessions, and publishes the events. `VoiceState` and `VoiceTranscript` carry `correlation_id` = the session id (the `StartListening` command's id, or the id given to `IVoice.listen`), so each caller follows only its own session. Built 2026-11-03; `IVoice` built 2026-11-05.

### `IVoice`

**Reusable** · Used by: `voice_in` provides; `voice_notes` requires · built 2026-11-05

`class IVoice(Contract)`, single provider, in `assistant.contracts`.

| Method | Does |
|--------|------|
| `async listen(session_id, destination=VoiceDestination.CALLER) -> Result` | Open a session under an id the caller made (`uuid4().hex`), so it can follow its events from the first one. Value `{"session_id"}`. The second `listen` wins, as with `StartListening` |
| `async finish(session_id, discard=False) -> Result` | End **that** session only; another caller's is never touched. Value `{"text"}`. A session that already ended (taken over, failed, a silence stop) gives `{"text": "", "ended": true}` |

`VoiceDestination` (enum): `talker` (the final text also goes to the Talker as `InputReceived(source="voice")`) or `caller` (only the events). One mic, one session at a time: "sessions" means each caller owns its own session id, not two at once. Look the provider up at each call (`ctx.get_one(IVoice)`), never keep it: a reload of `voice_in` swaps it. Requiring it makes the core turn `voice_in` on first, and refuse to turn it off while you're on.

    voice = ctx.get_one(IVoice)
    session = uuid4().hex
    await voice.listen(session, VoiceDestination.CALLER)   # then follow VoiceTranscript with correlation_id == session
    text = (await voice.finish(session)).value["text"]

### `StartListening`

**Reusable** · Used by: `temp_ui` sends; `voice_in` handles (the command form of `IVoice.listen`, for UI buttons)

`StartListening(send_as_input: bool = True)` (command)

Turn the mic on. With `send_as_input=False` (dictating into a text box, say) the text goes only to `VoiceTranscript` subscribers, never to the Talker. **Result:** `ok` once the service says `started`, value `{"session_id"}`. **The second press wins** (added 2026-11-04): a start while a session is open ends that session the way `discard=True` does, with `VoiceState(idle, reason="taken_over")` and an empty final for it, so its text never reaches the Talker; a `StopListening` it was waiting on gets `ok`, value `{"text": "", "taken_over": true}`. Each UI follows only the sessions it started (by this command's id). `not_available` (retryable) if the service couldn't start or the mic or engine failed; `failed` for `busy` or a denied `microphone` permission. A running service that `voice_in` reuses gets a quick `/health` check first, so a failed model fails at once with `engine_failed`.

### `StopListening`

**Reusable** · Used by: `temp_ui` and `voice_notes` send; `voice_in` handles

`StopListening(discard: bool = False, agent_id: str | None = None)` (command)

Turn the mic off. **`agent_id`** (added 2026-11-06): the agent tab the stop was pressed in. `voice_in` keeps it on the session and publishes the final as `InputReceived(source="voice", agent_id=...)`, so the text reaches that tab's Talker even if you switch tabs while whisper finishes. `None` (another UI, or a stop by a long silence): the tab in focus when the text arrives. **Result:** `ok` after the final arrives, value `{"text", "latency_ms"}`; nothing listening: `ok` with `None`. `failed` if the mic was lost (its text is dropped), the service stopped, or no final came within `reply_timeout`.

**`discard=True`** (a clear button; added 2026-11-03): throw the session away instead. `voice_in` closes the socket (the service aborts and sends no final), publishes an empty final `VoiceTranscript` (clears the line) and `VoiceState(idle, reason="cleared")`, and sends nothing to the Talker; a final that still arrives is ignored. **Result:** `ok`, value `{"text": "", "discarded": true}`; nothing listening: `ok` with `None`. To carry on, the UI sends `StartListening` next; a `busy` answer within 2 s of a clear is retried once.

### `ListeningState`

**Reusable** · Used by: `VoiceState`

`StrEnum`: `idle` (mic off), `starting` (clicked; the service may be launching, the mic opening), `listening` (mic open, text coming), `dropped` (the mic went away mid-session; waiting for it to come back, then `listening` or `failed`; added 2026-11-03), `finishing` (the mic is off and the last piece is being cleaned; the detail is "cleaning up…", then `idle`; added 2026-11-03 for [two passes](../architecture/voice.md#two-passes-live-text-cleaned-piece-by-piece)), `failed` (went wrong; the event's `reason` and `detail` say what).

### `VoiceState`

**Reusable** · Used by: `voice_in` publishes; `temp_ui` subscribes

`VoiceState(state: ListeningState, reason: str | None = None, detail: str | None = None)` (event)

The mic's state changed. `reason` is the service's error code (`busy`, `mic_unavailable`, `mic_lost`, `engine_failed`), one of the app's own (`not_allowed`, `service_unavailable`, `service_stopped`, `timed_out`), `"mic_dropped"` on `dropped`, `"silence"` on an idle after a silence stop, `"cleared"` on an idle after `StopListening(discard=True)`, or `"taken_over"` on an idle when a second `StartListening` took the mic (the UI says cancelled); `detail` is a short sentence for the button (on `dropped`: *mic dropped, waiting 15 s for it to come back*).

### `VoiceTranscript`

**Reusable** · Used by: `voice_in` publishes; `temp_ui` and any module that wants voice text subscribe

`VoiceTranscript(session_id: str, text: str, final: bool = False, settled_chars: int = 0)` (event)

The live text: each partial (`final=False`), then once the final text (`final=True`; empty clears the line). `settled_chars` (added 2026-11-03): how many characters from the start of `text` are settled (cleaned by the final engine, or given up on); the rest is rough live text, which a UI may dim. Always 0 with one engine. `voice_in` publishes it in sentence case, and the final with one end mark ([text cleanup](../architecture/voice.md#the-voice_in-module), `[modules.voice_in] cleanup`); the engine's raw text is only in the log. This is the public stream of voice text; `InputReceived(source="voice")` is only the Talker's way in.

**Defined in:** `src/assistant/contracts/voice.py`

### The voice service protocol

**Reusable** · Used by: `voice_service` server (`server.py`, `session.py`), `voice_in` client (`module.py`)

`from voice_service.protocol import ...` (not `assistant.contracts`: the service never imports the assistant). The [`/ws/listen` protocol](../architecture/voice.md#the-protocol) as frozen pydantic models, one JSON object per text frame, so the service and its Python clients share one definition. `voice_service/__init__.py` is empty, so importing it doesn't pull in FastAPI or sherpa-onnx.

| Item | Kind | Summary |
|------|------|---------|
| `Start(partials=True)`, `Stop` | app → service | `{"type": "start", "partials": true}`, `{"type": "stop"}`. `partials=False` asks for the text on send only (added 2026-11-03) |
| `Started(partials=True, clean_pieces=False)` | service → app | The mic is open; `partials` says whether live text will come this session (added 2026-11-03). `clean_pieces`: two passes, so `cleaned` and `refining` come and the final is the final engine's text (added 2026-11-03). All fields are optional on the wire, so older clients and services still work |
| `Partial(text)` | service → app | The text so far |
| `Cleaned(piece, start, end, text="", fallback="")` | service → app | Piece `piece` is done: live words `[start, end)` (split on spaces, from the session's start) are replaced by `text`. `fallback` (`failed`, `empty`, `timed_out`): `text` is empty and the span keeps its live words. In piece order, spans back to back; only with `clean_pieces` and `partials` (added 2026-11-03) |
| `Refining(text="", pending=0)` | service → app | After stop, with `clean_pieces`: the live engine's final text (empty with `partials` off) and how many pieces are still being cleaned; `final` follows (added 2026-11-03) |
| `MicDropped(detail="", wait_seconds)` | service → app | The mic went away; the service tries to reopen it for `wait_seconds` (added 2026-11-03) |
| `MicBack` | service → app | A mic opened again; the session carries on (added 2026-11-03) |
| `Final(text, latency_ms, complete=True, ended_by="stop", parts=())` | service → app | The finished text; `ended_by` is `"stop"` or `"silence"`; `complete` is false after a mic that didn't come back. `parts` (two passes, added 2026-11-03): one `FinalPart(text, cleaned=True, fallback="")` per piece, in order; `text` is them joined with spaces |
| `Error(reason: ErrorCode, detail="")` | service → app | A fixed code and a sentence for the log |
| `ErrorCode` | `StrEnum` | `busy`, `mic_unavailable`, `mic_lost`, `engine_failed`, `bad_message` |
| `parse_client_message(raw)` | function | A frame from the app: `Start \| Stop`. Raises `ProtocolError` |
| `parse_service_message(raw)` | function | A frame from the service: `Started \| Partial \| Cleaned \| Refining \| MicDropped \| MicBack \| Final \| Error`. Raises `ProtocolError` |
| `dump(message)` | function | A message as one JSON text frame |
| `ProtocolError` | exception (`ValueError`) | Not JSON, not an object, unknown `type`, a missing or bad field, or the wrong direction; the service answers `bad_message` |

**Defined in:** `src/voice_service/protocol.py`

### The voice service's parts

**Reusable** · Used by: `voice_service` (`server.py`, `session.py`, `transcribe.py`, `__main__.py`); `WhisperEngine` adds an `SttEngine`, `FileSource` an `AudioSource`; the Nemotron engine (step 7, planned) adds an `SttEngine` and reuses `transcribe` for the comparison; `RemoteSource` for `/ws/audio` (later) adds an `AudioSource`

The service's own API, inside `src/voice_service/` (its own app: never imported by the assistant; `voice_in` uses only the protocol above). Built 2026-11-03; design: [Voice: files and classes](../architecture/voice.md#the-voice-service-files-and-classes).

| Item | Kind | Summary |
|------|------|---------|
| `SttEngine` | ABC (`engines`) | A speech engine: `name`, `live_partials: bool = True` (whether its streams give text while audio comes in; False: text only from `finish`, and the session sends no partials), `load()` (blocking, once, raises on failure; default no-op), `new_stream() -> SttStream` |
| `SttStream` | ABC (`engines`) | One session's recognition: `accept(pcm: bytes)` (PCM16, 16 kHz mono), `partial() -> str` (never called when `live_partials` is False), `finish() -> str` (flush, final text). Optional, default no-ops (added 2026-11-03): `set_prompt(text)` (the previous piece's text, so the next reads on; whisper's `initial_prompt`) and `cancel()` (throw the result away; whisper decodes its window in one call, so `cancel` can't cut it short, only drop its text) |
| `load_engine(name, config) -> SttEngine` | function (`engines`) | The only place that knows engine names: `"zipformer"`, `"whisper"` or `"fake"`; configured, not loaded. Raises `EngineError` for an unknown name. Called once per role: the live engine (`[engine] name`) and the final engine (`final_engine_name(config)`: `[engine] final`, or `""` for one engine when it's empty or the same as `name`). `create_app(..., final_engine=...)` runs a live engine with no live text (whisper) alone, with a log line; `/health` adds `final`, `final_ready`, `final_error` |
| `PieceCutter(*, chunk_ms, speech_rms, pause_seconds, min_seconds, max_seconds, cut_search_seconds)`, `.from_config(pieces, chunk_ms=, speech_rms=)` | class (`pieces`) | Two passes: where the audio is cut into pieces for the final engine. `feed(level)` per chunk returns `None` or how many of the piece's chunks the cut keeps (the rest starts the next piece): after `[pieces] pause_seconds` of quiet once the piece is `min_seconds` long, or at `max_seconds` at the quietest chunk of the last `cut_search_seconds`. Quiet with no speech never cuts. Pure, no threads (added 2026-11-03) |
| `EngineError` | exception (`RuntimeError`) | The engine can't be used (unknown, model missing, sherpa-onnx or faster-whisper missing); the message is the `engine_failed` detail |
| `WhisperEngine(model_dir, config)` | class (`engines.whisper`) | Whisper through faster-whisper (CTranslate2), `live_partials = False`. A stream buffers the audio; `finish` transcribes it all (`language="en"`, `vad_filter=True`, `[engine.whisper] beam_size`). Reads a local model folder only (`local_files_only`); faster-whisper and numpy are imported in `load` / `finish` (added 2026-11-03) |
| `transcribe(engine, source, *, load=True, timings=None) -> str` | function (`transcribe`) | One stream of `engine` over all of `source`'s chunks; the final text. `timings` gets `audio_seconds`, `load_seconds`, `accept_seconds`, `finish_seconds`. No server, no mic, no session thread (added 2026-11-03) |
| `transcribe_file(path, engine_name=None, config=None, *, timings=None) -> str` | function (`transcribe`) | The text of a 16 kHz mono WAV with the named engine (default: the config's). `python -m voice_service transcribe <file> [--engine E] [--model M]` prints it and the time taken (added 2026-11-03) |
| `ZipformerEngine(model_dir, config)` | class (`engines.zipformer`) | Streaming Zipformer EN through sherpa-onnx; int8 or full-precision files per `[engine.zipformer] int8`; `model_files()` finds them, and a missing model names the `download` command. sherpa-onnx is imported only in `load` |
| `FakeEngine(text, *, chunks_per_word=2, fail_on_load=False, fail_on_accept=False, load_gate=None)` | class (`engines.fake`) | For tests: one more word every `chunks_per_word` chunks; can fail on load, or once on accept; `load_gate` holds the load |
| `AudioSource` | ABC (`audio`) | `start(on_chunk, on_lost)` (raises `MicUnavailable`), `stop()`; `on_chunk` comes from the source's thread and must not block |
| `MicSource(device="", chunk_ms=32)` | class (`audio`) | The mic through a sounddevice `RawInputStream` (int16, 16 kHz, mono); a stream that ends without `stop` calls `on_lost`. sounddevice is imported only in `start`. After a lost mic, or one stopped while it had gone quiet, the next `start` reloads PortAudio's device list (`MicSource.stale_devices`) |
| `run_check(config, seconds=3.0, model=True, out=print) -> bool`, `level(samples)`, `mic_privacy()` | functions (`check`) | `python -m voice_service check`: the voice extra, Windows' mic privacy values (read only), the input devices, the model's load time, and a real-mic level check through `MicSource`, transcribing what it heard. True if sound arrived (and the model loaded) |
| `FileSource(path, *, chunk_ms=32, realtime=False)` | class (`audio`) | A 16 kHz mono 16-bit WAV in chunks: read whole (`chunks`, `seconds`) or `start`ed like a mic, at the speed of speech with `realtime=True`. Any other format raises `ValueError` (added 2026-11-03) |
| `FakeSource(chunks=(), *, interval=0, fail_on_open=False, lose_after=None)`, `FakeSource.from_wav(path, *, chunk_ms=32, realtime=True)` | class (`audio`) | Chunks from a list or a 16 kHz mono WAV (read by `FileSource`), for tests and offline checks; can fail to open or "unplug" after N chunks |
| `rms(pcm) -> float` | function (`session`) | A PCM16 chunk's level (0 to 32768); the silence stop's speech test without live text, against `[audio] speech_rms` |
| `MicUnavailable` | exception (`RuntimeError`) | The source couldn't open; the message names the device and the reason |
| `create_app(config, engine, source_factory, *, config_path=None, watch_seconds=2.0) -> FastAPI` | function (`server`) | `GET /health`, `POST /quit`, `WS /ws/listen`, one listener at a time; loads the engine on a background thread at startup. With `config_path`, watches that file and its `.local` override and quits (through `app.state.on_quit`) once the `[engine]` section changed and nothing is listening (added 2026-11-03). Set `app.state.on_quit` to what ends the server |
| `ServiceConfig`, `load_service_config(path=None, *, host=None, port=None)`, `models_dir(config)` | model, functions (`config`) | Built-in defaults, then `config/voice_service.toml` and its `.local.toml` through `load_layered`, then flags; the models folder (env `VOICE_SERVICE_MODELS`, `[engine] models_dir`, else `%LOCALAPPDATA%\AI_Assistant\voice_models`) |
| `download_model(engine, config, *, fetch=None) -> Path` | function (`download`) | Fetch and extract a model once (tarfile's safe `data` filter); does nothing if it's there. `python -m voice_service download zipformer`, or `download whisper [--model small.en]` (a CTranslate2 model from Hugging Face into `faster-whisper-<model>`) |

**Examples** (an offline check on a recording, the whole service path, no mic; and a file straight through an engine, no server):

    app = create_app(config, load_engine("zipformer", config), lambda: FakeSource.from_wav("0.wav"))
    text = transcribe_file("talk.wav", "whisper")

**Defined in:** `src/voice_service/` (`engines/`, `audio.py`, `transcribe.py`, `server.py`, `config.py`, `download.py`)
