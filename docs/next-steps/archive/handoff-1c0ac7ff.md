# Handoff: voice layers and whisper

> **Finished (2026-11-03):** the build is done; results and your check are in [the note](../voice-layers-whisper.md).

Task: build [voice-layers-whisper.md](../voice-layers-whisper.md) (approved 2026-11-03, answers recorded there and on the [voice page](../../../src/assistant/modules/voice_in/docs/voice-service.md#hot-swappable-engines)). Follow the batching and architecture-first skills, run architecture-check before the final report. No commit, no push. **The user said yes (2026-11-03) to the install, the model downloads and the config edits: all done.**

## Done (sessions 1–3)

- **Code, all of it:** `app_kit/config.py` `local_path`; `voice_service` (`FileSource`, `transcribe.py`, `engines/whisper.py`, `live_partials`, `rms` silence stop, `Start/Started.partials`, the config watch and swap in `server.py`, `download whisper`, the `transcribe` command); `voice_in` (`live_text`, `final_timeout_on_send`, the "text appears when you stop" detail); `cleanup.py` (cased text kept, terms only); the temp UI's listening line shows the detail.
- **Tests:** contracts' wire, cleanup, voice_in on-send (2 tests), voice service (whisper load/stream/download, FileSource, transcribe + subprocess import check, flag, rms silence, swap). **310 passed** after the install (numpy 2.5.4); ruff clean. Chunk-1 architecture check OK (voice_service imports no `assistant`; voice_in imports only `protocol`; new protocol fields default True).
- **Installed** faster-whisper 1.2.1 (ctranslate2 4.8.5, numpy 2.5.4, 17 packages); `pyproject.toml` voice extra has `faster-whisper>=1.2`.
- **Config edited:** `config/voice_service.toml` (`speech_rms = 300`, engine name comment, `[engine.whisper]` block matching the defaults; engine still `zipformer`); `config/default.toml` (`live_text = true`, `final_timeout_on_send = 90.0`, cleanup comment; `[core.command_timeouts] StopListening = 120.0`).
- **Models:** `faster-whisper-base.en` and `faster-whisper-small.en` are in `%LOCALAPPDATA%\AI_Assistant\voice_models`. `distil-large-v3.5` was still downloading in a background shell at the reset: check that its folder `faster-whisper-distil-large-v3.5` exists with a `model.bin`; if not, rerun `.\.venv\Scripts\python -m voice_service download whisper --model distil-large-v3.5`.
- **Measured (CPU int8, Ultra 9 275HX; the wait after the audio ends; script `%TEMP%\voice_bench\bench.py <test_wavs dir> <out dir> <models…>`, run with `python -I`):**

  | Engine | 0.wav (6.6 s) | 1.wav (16.7 s) | long.wav (46.7 s, 0+1+0+1) | Load |
  |---|---|---|---|---|
  | zipformer (live; its real wait after stop is `finish` only, 0.03 s) | 0.03 s | 0.03 s | 0.03 s | 2.1 s |
  | whisper base.en | 0.42 s | 0.56 s | 1.83 s | 0.5 s |
  | **whisper small.en** (default) | **1.19 s** | **1.62 s** | **5.17 s** | 1.0 s |
  | distil-large-v3.5 | not measured yet | | | |

  Text: whisper gave correct, cased, punctuated text ("After early nightfall, the yellow lamps would light up here and there the squalid quarter of the brothels."); zipformer all caps, also correct. small.en is within the note's estimate (about 1–3 s for 20 s of speech); about 5 s for a 47 s message.
- **Swap tried by hand** (`%TEMP%\voice_bench\swap.py`): the real service on a temp config with the fake engine; an `[audio]` change left it running; changing `[engine] name` to zipformer made it log "engine changed: fake → zipformer; restarting" and exit 0 in 1.2 s; the relaunch came up with zipformer, ready after the load.

## Next

1. Measure distil-large-v3.5 with the bench script (`... distil-large-v3.5`), add its row.
2. **Docs** (each file: read once, edit all spots in one pass):
   - `docs/architecture/voice.md`: status block, a "Built: layers and whisper" paragraph with the table above and the swap test; Layers banner, diagram (file source, whisper, utility now built: drop the `planned` class) and table; Hot-swappable banner → built; the Receiver row (sherpa-onnx or faster-whisper); protocol rows (`start.partials`, `started.partials`); the silence-stop bullet (level rule `speech_rms` without live text); files tree (`transcribe.py`, `engines/whisper.py`, `FileSource`, `transcribe` and `download whisper` commands) and class diagram (`FileSource`, `WhisperEngine`, `live_partials`); the service config block; the dependencies line; voice_in config block (`live_text`, `final_timeout_on_send`), the StopListening row (the on-send wait), the cleanup paragraph (cased text kept), the errors table row "No final within reply_timeout" (or final_timeout_on_send); Engines (measured waits).
   - `docs/api/messaging.md` (protocol fields; FileSource, transcribe, transcribe_file, WhisperEngine, live_partials), `docs/api/reusable.md` (FileSource, transcribe/transcribe_file, local_path, WhisperEngine on SttEngine's line), `docs/api/app_kit.md` (`local_path`), the overview Parts row "Voice handler" (engines: zipformer live, whisper on send; swap by config), `docs/agents/runtime.md` temp UI line ("Listening… text appears when you stop").
   - The change note: status "built", a Results section with the table; `docs/next-steps/README.md` row → built.
   - Rebuild: `.\.venv\Scripts\python scripts\build_docs.py`.
3. Final architecture-check (diagrams updated), `pytest`, `ruff check`.
4. Report: changed files, 310 tests passing, the measured waits, **an app restart is needed** (new protocol fields and `app_kit` changed; `RELOAD: voice_in` isn't enough). The user's check after the restart: set `[engine] name = "whisper"` (in `config/voice_service.local.toml`), talk, stop, see the text arrive on send. No commit.
