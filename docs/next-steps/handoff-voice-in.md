# Handoff: voice in, after step 3 (the voice_in module)

> **Written 2026-11-03** at the end of step 3, for a fresh session. Nothing is committed or pushed; the user commits and pushes. The design is on [Voice](../architecture/voice.md) (built parts are marked there); the step's note is [voice-in-module.md](voice-in-module.md), with what was built differently at its top. The step list is in [Next steps](README.md#next-voice-in-phase-1).

## Done

- **Steps 1 and 2** (committed earlier): the voice contracts, the protocol, and the `voice_service` app.
- **Step 3, `voice_in`** (built, not committed): `src/assistant/modules/voice_in/`, listed in `MODULES` and off by default.
  - **Launch and stop:** it uses `CompanionApp("voice_service", ping="/health", quit="/quit")`. The service is launched on the first `StartListening`, not in `start`. At `stop()`, an open session is aborted (nothing goes to the Talker), and the service is quit only if this module launched it.
  - **One session at a time:** `StartListening` and `StopListening` run under one `asyncio.Lock`. Starting again while a session is open returns that session's id.
  - **Steps per start:** `VoiceState(starting)`, then `ctx.permissions.request("microphone")`, then `_ensure_service()` (the health check below). Then it connects the WebSocket, sends `start`, and waits up to `reply_timeout` for `started`. A reader task maps every frame after that.
  - **Health check:** it runs only when `ensure_running()` didn't launch the service just now. It sends `GET /health` with a 2 s timeout:
    - `ready: false` with an error fails at once with `engine_failed`.
    - Still loading: carry on.
    - No answer: `ensure_running()` again, which relaunches the service.
  - **Error mapping:** the table under [Voice: how errors reach the button](../architecture/voice.md#the-voice_in-module-how-errors-reach-the-button).
- **Mic-drop recovery, a change to the step 2 service:**
  - **Config:** `[audio] mic_recovery_seconds = 15` in `config/voice_service.toml` and `config.py`. Setting it to 0 keeps the old behavior.
  - **Protocol:** two new service messages, `MicDropped(detail, wait_seconds)` and `MicBack`. Every other message is unchanged.
  - **Session (`session.py`):** `ListenSession` now takes the server's `source_factory`. On `on_lost`, it reads what's queued, sends the last partial and then `mic_dropped`, and tries a fresh source every `retry_seconds` (1 s). The silence timer is paused meanwhile. If a source opens, it sends `mic_back` and keeps the same engine stream. On a timeout, or a `stop` while dropped, it sends `final complete=false` and then `error mic_lost`.
  - **`voice_in`:** `mic_dropped` becomes `VoiceState(dropped, "mic_dropped", "mic dropped, waiting 15 s…")` and `mic_back` becomes `listening`. An incomplete final drops the text: `VoiceTranscript(final=True, text="")` clears the line, then `VoiceState(failed, mic_lost)`, and nothing goes to the Talker.
  - **Contract:** a new `ListeningState.DROPPED`.
- **Tests:**
  - `tests/test_voice_in.py` (21 test functions, 23 cases) runs the real service app with `FakeEngine` and `FakeSource` under Uvicorn, on a free local port in a thread.
  - `tests/test_voice_service.py` has 4 new mic-drop tests.
  - Results: ruff is clean, and 224 tests pass (1 deselected).
- **Docs:**
  - Updated: Voice (the status, the protocol table, config, errors, the voice_in section, the three-part flowchart with built and planned marks, the full sequence diagram, and the error table), the overview (diagram, Built today, Parts, Modules, Pages), Messaging, the reusable index, App kit, Modules, runtime (the voice service process), and Next steps.
  - Rebuilt with `scripts/build_docs.py`.

## Decisions made with the user

1. **Tests: option A.** They use the real `voice_service` app with its fake engine and fake mic on a local port, not a hand-written fake server. This is the stand-in until the user tries their own mic.
2. **Health check** only when reusing an already-running service. A fresh launch is already pinged by `CompanionApp`.
3. **A lost mic:** try to recover it for a short, configurable wait (`mic_recovery_seconds`, 15 s). If it comes back, carry on. If not, end the session and discard its text, and send nothing to the Talker.
4. **Process rule:** after each big chunk of a build, update the architecture docs and their flowcharts as the build goes (diagrams included, built versus planned marked), not only at the end, and run the `architecture-check` skill.

## Files touched (uncommitted)

- **New:** `src/assistant/modules/voice_in/__init__.py`, `module.py`; `tests/test_voice_in.py`; this note.
- **Changed, code:** `src/voice_service/protocol.py`, `session.py`, `config.py`, `server.py`; `config/voice_service.toml`; `src/assistant/contracts/voice.py`; `src/assistant/__main__.py`; `config/default.toml`; `tests/test_voice_service.py`, `tests/test_voice_contracts.py`.
- **Changed, docs:** `docs/architecture/voice.md`, `docs/architecture/README.md`, `docs/api/messaging.md`, `docs/api/reusable.md`, `docs/api/app_kit.md`, `docs/api/modules.md`, `docs/agents/runtime.md`, `docs/next-steps/README.md`, `docs/next-steps/voice-in-module.md`, and the regenerated `docs/html/` and `docs/html-next-steps/`.

## Half-finished or open

- Nothing is half-built. The code, tests and docs match.
- **Not covered:** if Windows doesn't report an unplug (the mic just goes quiet), no drop is detected. A "no audio for 2 s counts as a drop" check would cover it. Decide in step 6.
- **Possible reusable part:** the `Service` harness in `tests/test_voice_in.py` (the real service on a free port). If step 4's temp UI tests need it, move it to `tests/support.py` and list it in the [reusable index](../api/reusable.md).

## Next

1. ~~**Step 4, the temp UI**~~ done 2026-11-03 ([note](voice-temp-ui.md)); `voice_in` is now enabled. As planned:
   - The mic button sends `StartListening` and `StopListening`, and shows `VoiceState`: *starting* as a spinner, *dropped* as an amber crossed-out mic with a countdown and the word count of the last partial, and *failed* with its `detail`.
   - The grey live line comes from `VoiceTranscript`. Drop updates whose `correlation_id` isn't the current session's, and clear the line on `final=True`.
   - Show `InputReceived(source="voice")` as your own message.
   - Add `voice_in` to `enabled`.
2. **Step 6, the user's real mic on this laptop.** Needed:
   - The `voice` extra installed (it is in this venv).
   - The Zipformer model in `%LOCALAPPDATA%\AI_Assistant\voice_models` (downloaded in step 2).
   - Windows' microphone privacy setting allowing desktop apps.
   - `voice_in` enabled, and step 4's button to click. Without step 4, start `python -m voice_service` alone and drive `/ws/listen` by hand.
   - Check the latency and the partials, and unplug a USB or Bluetooth mic mid-sentence to see `mic_dropped` and `mic_back`, and whether Windows reports the unplug at all.
3. **Step 7:** Nemotron and the engine comparison. It needs no change to `voice_in`.
