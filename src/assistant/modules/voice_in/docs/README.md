# voice_in: voice input and the voice service

## Purpose

Speech to text for the whole app. `voice_in` is the thin module; the **voice service** (`app/voice_service` in this folder) is its own app that owns the mic and the speech engines. On by default. Full design: [voice](voice-service.md).

## Wrapper

| Field | Value |
|-------|-------|
| id | `voice_in` |
| provides | [`IVoice`](../../../../../docs/api/messaging.md#ivoice), the voice contract (a `_Voice` part using the same sessions as the commands) |
| requires / optional | none |
| permissions | optional: `microphone` |

## Config

Defaults in `module.toml` (with `needs = []` and its `packages`: the voice service's and the `websockets` client; nothing installs them), overridden by `[modules.voice_in]`: `host`, `port` (8767), `start_timeout`, `service_config`, `reply_timeout`, `live_text`, `final_timeout_on_send`, `cleanup`, `terms`. The service: `app/voice_service/voice_service.toml` (engine choice, mic-drop wait), overridden by `voice_service.local.toml` beside it (not committed). Command timeouts: `[core.command_timeouts]` `StartListening`, `StopListening`.

## Code and tests

- Module: `src/assistant/modules/voice_in/` (`module.py`, `line.py`, `cleanup.py`)
- Service: `app/voice_service/` (the core puts `app/` on the import path; run it alone with `python -m voice_service` and that folder on `PYTHONPATH`)
- Tests: `tests/` in this folder: `test_voice_in.py`, `test_voice_line.py`, `test_voice_text_cleanup.py`, `test_voice_service.py`, `test_voice_pieces.py`, `test_voice_contracts.py`, and `voice_client.py` (a local test client); on the [test kit](../../../../../docs/api/testkit.md)
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), [the voice service](voice-service.md), and `docs.toml` (its docs tab and group)
