# Voice in: the voice service app (step 2)

> **Status: done (2026-11-03).** Approved with your four answers (install the packages, CI installs the voice extra, download the model, int8 by default); built and tested. Not committed. Results under [Built](#built-2026-11-03). Next: step 3, `voice_in`.

**Asked:** step 2 of [voice in](README.md#next-voice-in-phase-1): the `voice_service` app itself, as its own independent app in `src/voice_service/`. It holds the mic and the speech engine, serves the WebSocket protocol from `protocol.py`, and uses `app_kit` pieces like `load_layered` where they fit. It never imports `assistant`. The thin `voice_in` module is step 3.

**Why:** everything else in voice input talks to this service. Built and tested alone first, step 3 can be built against a real service.

**The design is already approved** ([Code design (phase 1)](../architecture/voice.md#code-design-phase-1)): threads, files, config, and errors. This note only says how it gets built, plus four choices for you at the end. The engine itself is already decided: Streaming Zipformer EN through sherpa-onnx.

## Touches

- **New, `src/voice_service/`:** `__main__.py`, `config.py`, `server.py`, `session.py`, `audio.py`, `download.py`, `engines/__init__.py`, `engines/zipformer.py`, `engines/fake.py`. `__init__.py` stays empty and `protocol.py` stays as built.
- **New:** `config/voice_service.toml` (the design's file as is); `tests/test_voice_service.py`.
- **Changed:** `pyproject.toml` (the `voice` extra; `voice_service` in ruff's first-party list; a `voice-service` script like `html-viewer`); `.gitignore` (`config/*.local.toml`, so `voice_service.local.toml` is never committed); `.github/workflows/ci.yml` (question 2).
- **Docs:** [Voice](../architecture/voice.md) (status: step 2 built), the overview's Parts table (the voice handler's location), [App kit](../api/app_kit.md) and the [reusable parts index](../api/reusable.md) (Used by lines), [Next steps](README.md). Then rebuild.

## How it starts and stops

- **Start:** `python -m voice_service [--config F] [--host H] [--port P]` (or `voice-service`). It reads the config, sets up logging, builds the FastAPI app, and runs Uvicorn on `127.0.0.1:8767`. The model loads in the background (`asyncio.to_thread`), so `/health` answers at once with `ready: false` until the model is in.
- **`/health`** answers `{"app": "voice_service", "engine", "ready", "error"}`: the convention [`CompanionApp`](../api/app_kit.md#companionapp) pings, so step 3 needs no launch code of its own.
- **Stop:** `POST /quit` (JSON body, like the viewer) aborts any session (mic closed, engine thread joined, no final) and tells Uvicorn to exit. Ctrl+C does the same. Step 3 passes `quit="/quit"` to `CompanionApp`.
- **`python -m voice_service download zipformer`** fetches the model once into `models_dir` (standard library `urllib` and `tarfile`, extracted with tarfile's safe `data` filter). It's never called while the service runs.

## How the engine is chosen and configured

- `[engine] name` in the config picks it: `"zipformer"` (the default) or `"fake"`. `load_engine(name, config)` in `engines/__init__.py` is the only place that knows the names; the server, the session, and the protocol see only `SttEngine` / `SttStream`.
- **Zipformer:** `[engine.zipformer]` (`model` folder under `models_dir`, `num_threads`, `decoding`, and `int8`, question 4). It checks the model files exist before importing sherpa-onnx, so a missing model gives a clear error naming the `download` command. sherpa-onnx and sounddevice are imported only inside `zipformer.py` and `MicSource`, so the server and the tests run without them.
- **`models_dir`:** `""` means `%LOCALAPPDATA%\AI_Assistant\voice_models`; the env var `VOICE_SERVICE_MODELS` overrides it.
- **Config layers:** the built-in defaults (a pydantic `ServiceConfig`), then `config/voice_service.toml` and its `.local.toml` through `app_kit.load_layered`, then the command-line flags. If the default file is missing, the built-in defaults apply; a `--config` that doesn't exist is an error.

## How the five error codes are produced

| Code | Produced when | Then |
|------|---------------|------|
| `busy` | A `start` arrives while another connection holds the one session slot | That connection gets the error; the first session carries on |
| `mic_unavailable` | `AudioSource.start()` raises (sounddevice can't open the device, no device, Windows' mic privacy switch off); `MicSource` turns it into `MicUnavailable` with the device and reason | Session over, slot freed |
| `mic_lost` | The stream ends without our `stop` (sounddevice's finished callback) or reports an input error | The engine thread finishes with what it has: `final` with `complete: false`, then the error |
| `engine_failed` | The model failed to load (every `start` gets it; `/health` shows the error), or `accept` / `partial` / `finish` raised in the engine thread | Session over; a loaded model stays loaded for the next try |
| `bad_message` | `parse_client_message` raises `ProtocolError` (bad JSON, unknown type) | Only the error; the session, if any, carries on |

Also as designed: a `stop` with nothing listening gets an empty `final`; a long silence ends with `final` and `ended_by: "silence"`; a client that disconnects mid-session gets `abort()`. A `start` while the model is still loading opens the mic at once and buffers, as designed.

## Tests (no mic, no model, no network)

- **The fakes:** `FakeEngine` reveals a set text one word per few chunks (a different word each time `partial()` changes), and can be told to fail on load or on `accept`. `FakeSource` feeds chunks from a list on its own thread, and can be told to fail on open (`mic_unavailable`) or stop after N chunks as if unplugged (`mic_lost`). Tests build the app with `create_app(config, FakeEngine(...), lambda: FakeSource(...))` and drive `/ws/listen` with FastAPI's test client.
- **Cases:** `/health` before and after the model loads; start → started → partials (only when changed) → stop → final with the text and `latency_ms`; stop with nothing listening → empty final; a second client → `busy`; bad JSON and an unknown type → `bad_message`, session still running; load failure → `engine_failed` and `/health` shows it; engine crash → `engine_failed`, next start works; open failure → `mic_unavailable`; lost mic → `final(complete=false)` then `mic_lost`; a tiny `silence_stop_seconds` → `ended_by: "silence"`; disconnect mid-session → slot freed; `/quit` ends the server.
- **Config:** defaults, the `.local.toml` override, flags over both, `models_dir` from the env var. **Zipformer:** a missing model folder → the load error names `download` (no sherpa-onnx needed). **Download:** extracts a small tar made in the test, with the fetch faked (no network). **Import rule:** the existing check that `voice_service` never imports `assistant` covers every new file.
- Then all of `pytest` and `ruff`.

## Reuse

- **Used:** `app_kit.load_layered` (config), `voice_service.protocol` (every frame in and out), and the `CompanionApp` conventions (`/health` with `app`, JSON `POST /quit`).
- **Checked, not reusable here:** `setup_logging` and `load_config` are in `assistant.infra`, which the service can't import, so `__main__.py` sets up logging in a few lines of its own. `app_kit.window` isn't needed (no window).
- **New parts for the index:** `SttEngine` / `SttStream` and `AudioSource` (the extension points for Nemotron in step 7 and `RemoteSource` for `/ws/audio` later), listed under `voice_service`.

## Left for step 3 and later

- **Step 3, `voice_in`:** `CompanionApp("voice_service", host, 8767, ping="/health", quit="/quit")`, the mic permission through `ctx.permissions`, one WebSocket per session with the `websockets` client, the two commands and the events, `[modules.voice_in]` config, `core.command_timeouts.StartListening = 30`.
- **Steps 4 to 7:** the temp UI's mic button and live line; trying it on your own mic (the real latency check); Nemotron and the comparison.

## Open questions (for you)

1. **Install the packages into `.venv`?** `fastapi`, `uvicorn`, `sherpa-onnx`, `sounddevice` (the `voice` extra, plus `websockets` for step 3), and `httpx` in the `dev` extra (FastAPI's test client needs it). Nothing can run or be tested without them. **Recommend: yes**, with `pip install -e ".[dev,voice]"`.
2. **CI:** install the `voice` extra on GitHub too, so the service tests run there. They never touch a mic or a model, and sherpa-onnx and sounddevice are only imported by the real engine and mic. **Recommend: yes.** The other choice: the tests skip themselves when FastAPI isn't installed, and CI stays as it is.
3. **Download the Zipformer model now?** It comes once from sherpa-onnx's GitHub releases (a few hundred MB, into `%LOCALAPPDATA%\AI_Assistant\voice_models`). With it, I can check the real engine on the model's bundled test recordings (latency, the text) without a mic. **Recommend: yes**, and leave your own mic try for step 6. Without it, the real engine is built but only checked up to "model missing".
4. **int8 or full-precision model?** The download has both. int8 is smaller and faster on a CPU, with a small loss of accuracy. **Recommend: int8 by default**, with `int8 = false` in `[engine.zipformer]` to switch.

## Built (2026-11-03)

- **Installed** into `.venv` with `pip install -e ".[dev,voice]"`: fastapi 0.162.0, uvicorn 0.54.0, sherpa-onnx 2.0.1, sounddevice 0.5.6, websockets 17.4, httpx 0.28.1 (and their dependencies, starlette 1.10.0 among them). sherpa-onnx brought no numpy, so the Zipformer stream converts PCM16 with the standard library's `array`; no numpy is needed.
- **CI** installs `.[dev,voice]` in the test job.
- **The model** (`sherpa-onnx-streaming-zipformer-en-2023-06-26`, 310 MB with both the int8 and full-precision files) is in `%LOCALAPPDATA%\AI_Assistant\voice_models`, outside the repo, so it can never be committed and git lfs isn't needed. `.gitignore` also has `voice_models/` in case `models_dir` is ever pointed inside the repo, and `config/*.local.toml`.
- **Real-engine check** on the model's test recordings (`0.wav`, 6.7 s; `1.wav`, 16.7 s), fed at the speed of speech through the whole service (`create_app` + `ZipformerEngine` + `FakeSource.from_wav`): the model loads in about 1.9 s. int8 matched both reference texts exactly; the final came 46 and 78 ms after `stop`. The first partial came about 1.1 s after `start`, including the recording's lead-in before the first word, so the real first-partial latency is measured on your mic in step 6. Full precision: the same text except *dishonored* for *dishonoured*, finals 62 and 93 ms.
- **Changed from the design:** the model loads on a daemon thread rather than `asyncio.to_thread`, so a shutdown never waits on a load. `SttEngine` got a `load()` method (blocking, once), so the server loads any engine in the background and `/health` reports it.
- **Tests:** `tests/test_voice_service.py`; the import rule in `tests/test_voice_contracts.py` now scans the whole package, `engines/` included.
