# Handoff: voice in, after step 3 (the voice_in module)

## Update 2026-11-03, later: step 6 built

**Done and committed:** "Voice in step 6: mic check and unplug detection".
- **`python -m voice_service check`:** wired in. On this laptop, privacy is Allow everywhere, the default mic is the Realtek array (MME), and the model loads in 1.9 s. The mic opens in 12 ms with the first audio at 50 ms, and decoding runs at 0.03× real time.
- **The level:** near silent (rms 0, peak 1) on every device and every host API (MME, DirectSound, WASAPI, WDM-KS). Chunks arrive on time and the values aren't exact zeros, so this isn't the privacy block. It's either a quiet room behind Realtek's noise suppression, or a mic muted by the key or the input volume. Only the user speaking can tell which.
- **Through the real service** (real model and mic): `started` came 283 ms after `start`, and the final 78 ms after `stop`. 5 s of live mic gave no false stall.
- **Stall watchdog:** `[audio] stall_seconds = 2` in `session.py`, with tests for a stall that recovers, one that doesn't, and a steady source. The test configs default it to 0.
- **Device refresh:** `MicSource.stale_devices` is set by the finished callback, or by a `stop` while the mic had been quiet for over 1 s. The next `start` calls `sd._terminate()` and `sd._initialize()`. Tested with a stand-in sounddevice.
- **Results:** ruff is clean and 231 tests pass.

**Decisions:**
- No NEED for privacy: Windows already allows the mic.
- The quiet level goes on the user's checklist rather than in a fix.
- `check` stays inside the service: it isn't reusable, so it isn't in the index.

**Left, for the user only:** speak during `check`; click the mic and speak, noting the delay to the first partial and from stop to the final; unplug a USB or Bluetooth mic mid-sentence. **Next for the build:** step 7, the engine comparison.

## Update 2026-11-03: step 4 done, step 6 (the real mic) in progress

The task runs in **full auto**: the user pre-approved everything. Decide from the docs, record each decision here or in the change note, commit locally per finished chunk (short messages like recent commits), never push, never touch git config. Run ruff and the full tests, plus the `architecture-check` skill, after each chunk. The final report includes a Diagrams line, the relaunch steps (ask whether to relaunch), and a checklist for the user.

**Done and committed:** step 4, the temp UI's mic button and live line (`b22be25`, [note](archive/voice-temp-ui.md), with 7 decisions). `voice_in` is in `enabled`. Ruff is clean and 226 tests pass. The architecture check passed, and the Voice flowchart, the sequence diagram, and the runtime temp UI flowchart are updated.

**Found on this laptop (step 6):**
- The voice extra is installed: sounddevice 0.5.6, sherpa-onnx 2.0.1.
- The Zipformer model is present in `%LOCALAPPDATA%\AI_Assistant\voice_models`, both the int8 and the full-precision files.
- The default input is device 1, "Microphone Array (Realtek(R) Au…)" on MME. The Oculus virtual headset mic is also listed.
- The real-mic level probe hasn't run yet. PowerShell mangles `python -c` quotes, so the probe is being made a command instead.

**In progress (uncommitted):**
- `src/voice_service/check.py` is written but not wired in yet. `run_check(config, seconds, model)` checks the extra, Windows' mic privacy registry values (read only), the devices, the model's load time, and a level check through the real `MicSource`. It also transcribes what it heard and reports the decode speed.
- `__main__.py` has only the docstring line so far. Still to do: in `_parse`, accept `check` with `--seconds` (default 3) and `--no-model`. In `main`, call `run_check` and return 0 if it passes, else 1.

**Next:**
1. **Wire up and run `check`:**
   - Wire `check` in `__main__.py`, then run `.\.venv\Scripts\python -m voice_service check --seconds 3`.
   - If the result is all zeros or the privacy setting is Deny, give the user the exact Settings path with a `NEED:` line: Settings > Privacy & security > Microphone, then "Microphone access" and "Let desktop apps access your microphone".
   - Add a test for `level()` and `mic_privacy()`, and for `run_check` with a fake recorder if it stays cheap.
2. **Fix an unplug that isn't reported (decided):**
   - Add a stall watchdog in `ListenSession`, plus `[audio] stall_seconds = 2` (0 turns it off) in `config.py` and `config/voice_service.toml`.
   - `_on_chunk` records `self._last_chunk`, and `_open_source` resets it.
   - In `_listen`, while the source is open, not stopping and not lost, and no chunk has arrived for `stall_seconds`, set `self._lost = "no audio from the mic for 2 s"`. The existing recovery then runs.
   - Exact zeros don't count as a drop, since a mute key sends zeros too.
   - Check that the existing FakeSource tests don't trip it. Set `stall_seconds = 0` in the tests that idle, and add a stall test.
3. **Fix the stale device list on reopen (decided):**
   - PortAudio reads its device list once, at import, so a reopen after an unplug can fail even when another mic exists.
   - In `MicSource`, set a class-level "needs refresh" flag when a source is lost. The next `start` calls `sd._terminate(); sd._initialize()`, guarded with `getattr`, before it opens. Clear the flag after an open succeeds.
4. **Measure, commit, write the docs:**
   - Measure what's possible without speech: open time, first chunk, and `check`'s decode speed. Startup to `started` through the real service is optional.
   - Commit: "Voice in step 6: mic check and unplug detection".
   - Docs: on the Voice page, add `check`, `stall_seconds` in the config block, the errors table row for a stall, and the step 6 status. Update the API messaging page ("Voice service parts"), the reusable index if `check` counts as reusable (probably not), and Next steps. Then rebuild the docs.
5. **Report:**
   - The relaunch steps.
   - A user checklist: run `check` while speaking; click the mic and speak; note the delay to the first partial and from stop to the final; unplug a USB or Bluetooth mic mid-sentence and look for the drop symbol, then the mic coming back or failing.

> **Written 2026-11-03** at the end of step 3, for a fresh session. Nothing is committed or pushed; the user commits and pushes. The design is on [Voice](../architecture/voice.md) (built parts are marked there); the step's note is [voice-in-module.md](archive/voice-in-module.md), with what was built differently at its top. The step list is in [Next steps](README.md#next-voice-in-phase-1).

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
- **Changed, docs:** `docs/architecture/voice.md`, `docs/architecture/README.md`, `docs/api/messaging.md`, `docs/api/reusable.md`, `docs/api/app_kit.md`, `docs/api/modules.md`, `docs/agents/runtime.md`, `docs/next-steps/README.md`, `docs/next-steps/archive/voice-in-module.md`, and the regenerated `docs/html/` and `docs/html-next-steps/`.

## Half-finished or open

- Nothing is half-built. The code, tests and docs match.
- **Not covered:** if Windows doesn't report an unplug (the mic just goes quiet), no drop is detected. A "no audio for 2 s counts as a drop" check would cover it. Decide in step 6.
- **Possible reusable part:** the `Service` harness in `tests/test_voice_in.py` (the real service on a free port). If step 4's temp UI tests need it, move it to `tests/support.py` and list it in the [reusable index](../api/reusable.md).

## Next

1. ~~**Step 4, the temp UI**~~ done 2026-11-03 ([note](archive/voice-temp-ui.md)); `voice_in` is now enabled. As planned:
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
