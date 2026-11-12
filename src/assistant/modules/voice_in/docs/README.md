# voice_in: voice input and the voice service

## Purpose

Speech to text for the whole app. `voice_in` is the thin module; the **voice service** (`src/voice_service`) is its own app that owns the mic and the speech engines. On by default. Full design: [voice](voice-service.md).

## Wrapper

| Field | Value |
|-------|-------|
| id | `voice_in` |
| provides | [`IVoice`](../../../../../docs/api/messaging.md#ivoice), the voice contract (a `_Voice` part using the same sessions as the commands) |
| requires / optional | none |
| permissions | optional: `microphone` |

## Config

`[modules.voice_in]`: `host`, `port` (8767), `start_timeout`, `service_config`, `reply_timeout`, `live_text`, `final_timeout_on_send`, `cleanup`, `terms`. The service: `config/voice_service.toml` (engine choice, mic-drop wait). Command timeouts: `[core.command_timeouts]` `StartListening`, `StopListening`.

## Code and tests

- Module: `src/assistant/modules/voice_in/` (`module.py`, `line.py`, `cleanup.py`)
- Service: `src/voice_service/`
- Tests: `tests/test_voice_in.py`, `test_voice_line.py`, `test_voice_text_cleanup.py`, `test_voice_service.py`, `test_voice_pieces.py`, `test_voice_contracts.py`
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), [the voice service](voice-service.md), and `docs.toml` (its docs tab and group)
