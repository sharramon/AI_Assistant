# Voice in: contracts (step 1)

> **Status: done (2026-11-03).** Approved with your two decisions; built and tested (174 tests pass, ruff clean). Not committed. Next: step 2, the `voice_service` app.

**Asked:** start the voice input build with step 1 of [the plan](README.md#next-voice-in-phase-1): the shared contracts and shapes that the `voice_service` app and the thin `voice_in` module will use. Contracts only; no service, no module yet.

**Why:** both later steps build on these shapes. If they're fixed and tested first, the service (step 2) and `voice_in` (step 3) can each be built and tested against them on their own.

**Touches:**
- `src/assistant/contracts/voice.py` (new): the two commands, two events, and the `ListeningState` enum.
- `src/assistant/contracts/__init__.py`: export them.
- `src/voice_service/__init__.py` (new, empty) and `src/voice_service/protocol.py` (new): the WebSocket protocol's messages. See open question 1.
- `tests/test_voice_contracts.py` (new).
- Docs: [Messaging API](../api/messaging.md) (four entries, plus the protocol), the [API index](../api/README.md), the [reusable parts index](../api/reusable.md), [Voice](../architecture/voice.md) (status line; `VoiceState.state` becomes `ListeningState`), and [Next steps](README.md) (step 1 done; step 3's text still says "copy `_ensure_running`, log its own warning", which I'd fix to say `CompanionApp` and `ctx.permissions`, as already decided). Then rebuild.
- No module, config, or `pyproject.toml` changes. Nothing uses the new types yet.

**Approach:** the fields are the ones already approved in [the voice_in module](../architecture/voice.md#the-voice_in-module), as frozen pydantic models like every other message.

```python
# assistant/contracts/voice.py
class StartListening(Command):
    send_as_input: bool = True      # False: text only to VoiceTranscript subscribers, never the Talker

class StopListening(Command):
    pass

class ListeningState(StrEnum):     # like TaskState
    IDLE = "idle"                   # mic off, nothing happening
    STARTING = "starting"           # clicked; service launching / mic opening
    LISTENING = "listening"         # mic open, text coming
    FAILED = "failed"               # went wrong; reason and detail say what

class VoiceState(Event):           # correlation_id = session_id
    state: ListeningState
    reason: str | None = None       # error code, "service_stopped", or "silence"
    detail: str | None = None       # a short sentence for the button

class VoiceTranscript(Event):      # correlation_id = session_id
    session_id: str
    text: str
    final: bool = False             # True once, with the final text; "" clears the line
```

```python
# voice_service/protocol.py: no assistant import; pydantic only
class ErrorCode(StrEnum): BUSY, MIC_UNAVAILABLE, MIC_LOST, ENGINE_FAILED, BAD_MESSAGE
# app → service
class Start:   type: Literal["start"]
class Stop:    type: Literal["stop"]
# service → app
class Started: type: Literal["started"]
class Partial: type: Literal["partial"]; text: str
class Final:   type: Literal["final"]; text: str; latency_ms: int; complete: bool = True;
               ended_by: Literal["stop", "silence"] = "stop"
class Error:   type: Literal["error"]; reason: ErrorCode; detail: str = ""
def parse_client_message(raw: str) -> Start | Stop          # raises ProtocolError → bad_message
def parse_service_message(raw: str) -> Started | Partial | Final | Error
def dump(msg) -> str                                         # one JSON text frame
```

- **Reuse checked:** nothing in the [reusable parts index](../api/reusable.md) parses a WebSocket protocol, so `protocol.py` is new. `CompanionApp` and `load_layered` aren't used in this step; the service's config (step 2) and `voice_in`'s launch (step 3) use them.
- **The mic permission** needs no contract: `voice_in` will call the built `ctx.permissions.request("microphone", ...)` and declare `optional_permissions=("microphone",)` in step 3.

**Tests** (`tests/test_voice_contracts.py`, no mic, no model, no network):
- The contracts: defaults (`send_as_input=True`, `final=False`), frozen, `ListeningState` has exactly the four values, a bad `state` rejected, a plain `"listening"` accepted and turned into `ListeningState.LISTENING`, all exported from `assistant.contracts`.
- The protocol: each message dumps and parses back unchanged; JSON matches the [protocol table](../architecture/voice.md#the-protocol) exactly (`{"type": "start"}`, etc.); unknown `type`, bad JSON, or a missing field raises `ProtocolError`; a client parser refuses service messages and the reverse; the error codes are exactly the five listed.
- `voice_service.protocol` imports nothing from `assistant` (checked in the test).
- Then all of `pytest` and `ruff`.

**Reusable parts index, after the build:** `StartListening` / `StopListening`, `VoiceState` with `ListeningState`, `VoiceTranscript` (Used by: `voice_in`, `temp_ui`, planned), and the protocol (Used by: `voice_service` server and `voice_in` client, both planned) in a new `voice_service` row group.

**Left for the next steps:**
- **Step 2, the `voice_service` app:** `config.py` on `load_layered`, `server.py` (`/health`, `/quit`, `/ws/listen`), `session.py`, `audio.py` (`MicSource`, `FakeSource`), `engines/` (`zipformer`, `fake`), `download.py`, `__main__.py`, `config/voice_service.toml`, and the `voice` extra in `pyproject.toml`.
- **Step 3, the `voice_in` module:** launch through `CompanionApp`, `ctx.permissions` for the mic, one WebSocket per session, the two commands, `[modules.voice_in]` config and `core.command_timeouts.StartListening = 30`.
- **Steps 4 to 7:** the temp UI's mic button and live line, tests against a fake service, trying it on your mic, then Nemotron.

**Decided by you (2026-11-03):**
1. **The protocol's shapes live in `voice_service/protocol.py`**, built now, and `voice_in` imports that one file, so the service and the client share one definition and can't drift. `voice_service/__init__.py` stays empty, so the import doesn't pull in FastAPI or sherpa-onnx. **Approved.**
2. **The voice state is a named enum, `ListeningState`** (a `StrEnum`, like `TaskState`), not the design's `Literal` of plain strings: these are real states, and an enum is easier to edit later. The JSON is unchanged (`"listening"` etc.). [Voice](../architecture/voice.md#the-voice_in-module) and the Messaging API get updated to match. **Changed as you asked.**

**Open questions:** none.
