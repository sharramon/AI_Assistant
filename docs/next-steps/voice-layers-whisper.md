# Voice: the layers in code, and whisper as a second engine

> **Status: built (waiting on you), 2026-11-03.** Loaded at the relaunch of 2026-11-03 16:02. You checked the note and answered its [open questions](#open-questions). The design it builds is on the voice page: [Layers](../../src/assistant/modules/voice_in/docs/voice-service.md#layers) and [Hot-swappable engines](../../src/assistant/modules/voice_in/docs/voice-service.md#hot-swappable-engines). Measured waits are under [Results](#results). Your check: set `[engine] name = "whisper"` in `config/voice_service.local.toml`, talk, stop, and see the text arrive on send.
>
> **Decision 4 revised (2026-11-03):** whisper is now by default the final engine of [two passes](voice-two-pass.md), cleaning the Zipformer's live text piece by piece.

## Results

Built as planned, in four steps; faster-whisper 1.2.1 installed (ctranslate2 4.8.5, numpy 2.5.4); the config files edited with your yes. Models in `%LOCALAPPDATA%\AI_Assistant\voice_models`: `faster-whisper-base.en`, `-small.en`, `-distil-large-v3.5`.

The wait after the audio ends, CPU int8, Ultra 9 275HX, through `transcribe` (the Zipformer's test recordings, and the four joined):

| Engine | 6.6 s | 16.7 s | 46.7 s | Load |
|---|---|---|---|---|
| zipformer (live; at the stop only `finish` is left) | 0.03 s | 0.03 s | 0.03 s | 2.1 s |
| whisper `base.en` | 0.42 s | 0.56 s | 1.83 s | 0.5 s |
| **whisper `small.en`** (default) | **1.19 s** | **1.62 s** | **5.17 s** | 1.0 s |
| whisper `distil-large-v3.5` | 3.72 s | 3.85 s | 8.28 s | 2.8 s |

`small.en` is inside the estimate (1 to 3 s for 20 s of speech), so the recommendation stands. `distil-large-v3.5` is slower than estimated for long talk. All whisper models gave correct, cased, punctuated text. The swap was tried by hand on the real service: an `[audio]` change kept it running; an `[engine] name` change restarted it in 1.2 s with the new engine.

**Asked:** build the voice service's layers in code, then add whisper through them. The engine has to work by itself, with no mic and no server, so other things (a utility transcribing a recording, say) can use it without going through the assistant. Engines swap by config with a restart of the voice service. Whisper is used for now, for the live mic too, and its text appears on send. Each engine says whether it gives live partial text, and a setting forces on-send even for a live engine. `voice_in` and the Talker never learn which engine runs.

**Why:** today the engine can only be reached through `/ws/listen` and a mic. Whisper is more accurate than the streaming Zipformer on long dictation, and the layers let it and the next engines (Nemotron, step 7) plug in without touching the main app.

## Touches

- **`src/voice_service/`** (the voice service app; still never imports `assistant`):
  - `engines/__init__.py`: the `live_partials` flag on `SttEngine`, and `whisper` in `load_engine`.
  - `engines/whisper.py` (new): `WhisperEngine`, `WhisperStream`.
  - `audio.py`: `FileSource`.
  - `transcribe.py` (new): `transcribe(engine, source)` and `transcribe_file(path, engine_name, config)`, with no server and no session thread.
  - `session.py`: no partials when the engine gives none or the client asks for none, and a level-based silence check for that case.
  - `config.py`: `[engine.whisper]`, `[audio] speech_rms`.
  - `protocol.py`: `start.partials`, `started.partials` (both optional, so older clients still work).
  - `server.py`: watch the config and restart when the engine changes.
  - `download.py`: `download whisper`.
  - `__main__.py`: `transcribe <file>`.
- **`src/assistant/modules/voice_in/`**:
  - `module.py`: send `partials` from its setting, read `started.partials`, and wait longer for an on-send final.
  - `cleanup.py`: leave text that comes already cased alone.
- **`src/assistant/modules/temp_ui/`**: show "text appears when you stop" while listening without partials. This may need no change if the line already shows `VoiceState.detail`; check it in the build.
- **`config/voice_service.toml`, `config/default.toml`**: new settings (below). Those are config files, so the build asks you before editing them.
- **`pyproject.toml`**: `faster-whisper` in the `voice` extra. Installing it is a package install, so the build stops and asks first.
- **Restart and reload:** the voice service restarts itself when its engine changes (that's the feature). `voice_in` and `temp_ui` changes reload with `RELOAD`. **The new protocol fields need one app restart**, because a reload of `voice_in` re-imports only `assistant.modules.voice_in`, not `voice_service.protocol`. Until that restart, `voice_in` reads the fields with `getattr` and behaves as today.

## Approach, layer by layer

### 1. Audio sources: `FileSource`

- `FileSource(path, chunk_ms=32, realtime=False)` reads a 16 kHz mono PCM16 WAV and gives it out in chunks through the usual `start(on_chunk, on_lost)`. With `realtime=True` it paces chunks at the speed of speech, so the service can be tested on a recording as if it were a mic.
- **Reuse:** `FakeSource.from_wav` already reads WAVs. That reading moves into `FileSource`, and `FakeSource.from_wav` calls it, so there's one WAV reader.
- Any other format or rate is refused with a clear error, for now ([question 4](#open-questions)).

### 2. Speech engine: the flag, whisper, and use without a server

- **`SttEngine.live_partials: bool = True`**, a class attribute. `ZipformerEngine` and `FakeEngine` keep `True`. `WhisperEngine` sets `False`. Its stream's `partial()` returns `""` and is never called by the session.
- **`WhisperEngine`** (recommended runtime: **faster-whisper**, CPU, int8; reasons [below](#recommended-whisper-runtime-and-model)):
  - `load()` builds a `WhisperModel` from a **local folder** under `models_dir`, `local_files_only=True`. That keeps the page's rule that models are never downloaded while running.
  - `WhisperStream.accept(pcm)` only appends to a buffer. That's 32 KB/s, about 4 MB for two minutes.
  - `finish()` converts the buffer to float32, then runs `transcribe(language="en", vad_filter=True, beam_size=…)`. It returns the segments' text, joined and stripped. Its built-in VAD skips silence, which also stops whisper's habit of inventing "Thank you." on empty audio.
- **`load_engine("whisper", config)`** is the only place that knows the name. It imports `faster_whisper` lazily, so a missing package is an `EngineError` ("install the voice extra"), the same as sherpa-onnx today.
- **Used by itself (the utility layer):** `voice_service/transcribe.py` has `transcribe(engine, source) -> str`. It loads the engine if needed, runs one stream over the source's chunks, and returns `finish()`. `transcribe_file(path, engine_name, config)` wraps it with `FileSource` and `load_engine`. It imports neither the server nor sounddevice. `python -m voice_service transcribe <file.wav> [--engine whisper]` prints the text and the time taken. The engine comparison (step 7) reuses this instead of writing its own loop.

### 3. The voice service app: partials or not, and the swap

- **Partials are sent only if** the engine has `live_partials` **and** the client didn't send `start` with `partials: false`. `started` carries `partials: bool`, saying which way this session goes. The protocol still names no models: a client learns only whether live text will come.
- **The force-on-send setting** lives in `voice_in` as `[modules.voice_in] live_text = true` (false = on-send even for a live engine). It's sent per session in `start`, so changing it needs only a `voice_in` reload, and later a checkbox can set it without touching the service ([question 1](#open-questions)).
- **The silence stop without partials:** today it watches the recognized text change. Whisper has no text until the end, so a 2-minute talk would be cut off as "silence". For sessions without engine partials, the session counts a chunk as speech when its level (RMS) is above `[audio] speech_rms` (default about 300 on the int16 scale, tuned in the build on your mic). It uses no new dependency. A forced on-send session on a live engine still reads the engine's partials internally and just doesn't send them, so it keeps today's check.
- **The final's latency:** with whisper, `latency_ms` is the whole decode, which is the cost of on-send. It's logged as today.
- **Swap by config with a service restart** (decided):
  - The service checks its config files (the file and its `.local` override) every 2 s.
  - When the `[engine]` section has changed, it waits until nothing is listening, logs "engine changed: zipformer → whisper; restarting", and shuts down through the same path as `/quit`.
  - The next mic click relaunches it through `CompanionApp.ensure_running`, which `voice_in` already does after a crash. The new model loads in the background, and a `start` during the load buffers the audio, as today.
  - A service started by hand (`python -m voice_service`) exits with that log line, and you start it again.
  - Other config changes (audio, logging) don't restart it.

### 4. Users: `voice_in` stays engine-blind

- **`voice_in`** sends `start` with `partials` from `live_text` and reads `started.partials`. When it's false, `VoiceState(listening)` gets the detail "text appears when you stop". It never reads the engine's name; `/health`'s `engine` field stays for logs only.
- **Waiting for an on-send final:** `reply_timeout` (10 s) is too short for whisper decoding a long talk on a CPU. When `started.partials` is false, the wait after `stop` is `final_timeout_on_send` (new, default 90 s), and `core.command_timeouts.StopListening` becomes 120 s. A live session keeps 10 s.
- **The text cleanup:** `clean_text` lowercases and adds an end mark because the Zipformer gives all capitals with no punctuation. Whisper's text is already cased and punctuated, and lowercasing it would lose that. New rule, based on the text and not on the engine: case and end mark are fixed only when the text has no lowercase letters. `terms` still apply to every text.
- **The Talker doesn't change:** it gets `InputReceived(source="voice")` as today.

## Recommended whisper runtime and model

**Checked on this machine (2026-11-03):**
- **Hardware:** Python 3.12.7 (64-bit), an Intel Core Ultra 9 275HX (24 threads), 31 GB RAM, and an NVIDIA RTX 5070 Laptop GPU with 8 GB.
- **faster-whisper:** `pip install --dry-run faster-whisper` resolves to faster-whisper 1.2.1 and ctranslate2 4.8.5, all as Windows wheels with nothing to compile. It also pulls in `av`, `onnxruntime`, `tokenizers`, `huggingface_hub` and a few small packages, plus numpy 2.5.4.
- **sherpa-onnx:** 2.0.1, already installed, also has `OfflineRecognizer.from_whisper`.

| | **faster-whisper** (recommended) | sherpa-onnx's whisper |
|---|---|---|
| New dependencies | Yes, about 17 packages (wheels) | None |
| Speed on CPU | CTranslate2 int8, the fastest common CPU runtime for whisper | ONNX, slower for whisper's decoder |
| Long audio | Handles any length, with a built-in VAD that skips silence | 30 s per call, so the engine would have to cut and stitch the audio itself |
| GPU later | CUDA, through config (`device = "cuda"`) | CUDA builds are separate |
| Fits "every engine through sherpa-onnx" | No: the page's Engines section would get a whisper exception | Yes |

**Recommendation: faster-whisper on CPU, int8, with `small.en` as the default model.**
- **Why faster-whisper:** a spoken message here can run a minute or two. faster-whisper handles that length and skips the silences, and it's the fastest of the two on a CPU. The sherpa-onnx route would mean writing our own cutting and stitching.
- **The cost:** a bigger `voice` extra, and an exception to the page's "every engine through sherpa-onnx".
- **The numpy upgrade:** sherpa-onnx and the existing tests have to pass on the new numpy, which the build checks right after the install.

**Model size, speed against accuracy.** These are estimates for this CPU; the build measures them (step 3 below):

| Model | Size | Accuracy | On-send wait, CPU int8 (estimate) |
|-------|------|----------|-----------------------------------|
| `base.en` | 74 M | Fair; misses names and technical words | Under 1 s for 20 s of speech |
| **`small.en`** (default) | 244 M | Good for English dictation; clearly better than the streaming Zipformer on long talk | About 1 to 3 s for 20 s of speech |
| `distil-large-v3.5` | 756 M | Close to large-v3, English only | About 3 to 6 s for 20 s |
| `large-v3-turbo` | 809 M | Best of these | About 4 to 8 s for 20 s on CPU; under 1 s on the GPU |

`small.en` keeps the wait after you stop at a few seconds for a normal message. The bigger models are one config change (`[engine.whisper] model`), the same swap. The GPU would make `large-v3-turbo` fast. It needs NVIDIA's CUDA 12 and cuDNN 9 libraries, though, and whether CTranslate2's wheels support this Blackwell GPU is unchecked, so it's left for later ([question 3](#open-questions)).

## Config

```toml
# config/voice_service.toml
[audio]
speech_rms = 300            # level that counts as speech, for the silence stop when no partials come

[engine]
name = "zipformer"          # "zipformer", "whisper", or "fake"; changing it restarts the service

[engine.whisper]
model = "faster-whisper-small.en"   # folder under models_dir (`python -m voice_service download whisper`)
device = "cpu"              # "cuda" later
compute_type = "int8"
beam_size = 5
cpu_threads = 8

# config/default.toml
[modules.voice_in]
live_text = true            # false = text on send even when the engine gives live text
final_timeout_on_send = 90.0

[core.command_timeouts]
StopListening = 120.0       # an on-send final may take a while to decode
```

`python -m voice_service download whisper [--model small.en]` fetches the CTranslate2 model once into `models_dir`, the same way as `download zipformer`.

## Steps

Each step ends with `pytest` and `ruff`. Steps 1 and 2 are one chunk, and steps 3 and 4 the next; the [architecture-check](../../.claude/skills/architecture-check/SKILL.md) runs after each chunk and before the final report.

1. **The layers, no whisper yet:** `FileSource` (with `FakeSource.from_wav` reusing it), `live_partials` on `SttEngine`, `transcribe.py` and the `transcribe` command, `start.partials` and `started.partials`, the session's no-partials path and level-based silence stop, and `voice_in`'s `live_text`, longer final wait, and cleanup rule. All of it can be tested with the fake engine and needs nothing installed.
2. **The swap:** the config watch and the restart when idle. Then try it by hand between `zipformer` and `fake`.
3. **Whisper.** First ask you before installing (`NEED: Risky`). Then add `faster-whisper` to the `voice` extra, `WhisperEngine`, and `download whisper`. Then run `python -m voice_service transcribe` on the Zipformer model's test recordings and a longer recording, with `base.en`, `small.en` and `distil-large-v3.5`, and record the wait and the text. If the numbers differ much from the table, update the recommendation before you choose.
4. **Docs, then hand over:** the docs below, rebuilt. Then `RELOAD: voice_in` and `temp_ui`, then one app restart for the protocol fields. Then your check: switch `[engine] name` to `whisper`, talk, stop, and see the text arrive on send.

## Tests

- **`FileSource`:** chunk sizes and the total length, `realtime` pacing, a non-16 kHz file refused; `FakeSource.from_wav` unchanged.
- **`transcribe`:** `FakeEngine` + `FileSource` gives the fake's text with no server running, and `transcribe.py` imports neither the server nor sounddevice (checked in a subprocess).
- **The flag:** a fake engine with `live_partials = False` sends no `partial` and `started.partials` is false. A live engine with `start.partials: false` sends no partials either. Both still send the final.
- **Silence stop without partials:** a loud fake source keeps the session going past `silence_stop_seconds`, and a quiet one ends it with `ended_by: "silence"`.
- **The swap:** changing `[engine] name` in a temp config while idle shuts the server down. During a session, it waits until the session ends. A change elsewhere in the config doesn't restart it.
- **`WhisperEngine`:** `load_engine` without faster-whisper installed raises `EngineError` with the install hint. A test with the real model on a short WAV, marked to skip when the model folder is missing (not in CI).
- **`voice_in`:** `live_text = false` sends `partials: false`. `started.partials: false` sets the detail and uses the longer final wait. An older service with no `partials` field works as today.
- **Cleanup:** all-caps text is cleaned as today. Cased, punctuated text comes back unchanged apart from `terms`.

## Docs to update

- **[Voice](../../src/assistant/modules/voice_in/docs/voice-service.md):**
  - The Layers table and diagram: file source, whisper and the utility move from planned to built.
  - The files tree and class diagram: `FileSource`, `transcribe.py`, `engines/whisper.py`, `live_partials`.
  - The config block, the protocol table (`start.partials`, `started.partials`), the voice_in config, and the cleanup rule.
  - Engines: whisper on faster-whisper, as the exception to "through sherpa-onnx".
  - Hot-swappable engines: built.
- **[Messaging API](../api/messaging.md):** the protocol's new fields, and the voice service parts (`FileSource`, `transcribe`, `transcribe_file`, `WhisperEngine`, `live_partials`).
- **[Reusable parts index](../api/reusable.md):**
  - Add `FileSource` (used by `transcribe_file`, `FakeSource.from_wav`, the engine comparison) and `transcribe` / `transcribe_file` (used by the `transcribe` command and the engine comparison, step 7).
  - Add `WhisperEngine` to `SttEngine`'s Used by line.
- **Overview [Parts table](../architecture/README.md#parts):** the Voice handler row mentions the engines and the swap.
- **The [runtime](../agents/runtime.md#temp-ui) page:** the temp UI's line when text comes on send.
- **This note and the [next-steps list](README.md):** the status.

## Open questions

Answered by you, 2026-11-03 (the anchors above still point here):

1. **Where the force-on-send setting lives:** in `voice_in` (`live_text`), sent with each session, so changing it needs only a reload.
2. **Runtime:** faster-whisper (about 17 new packages, and an exception to "every engine through sherpa-onnx").
3. **Model and GPU:** `small.en` on the CPU (int8) now; the GPU later, as its own small step.
4. **File formats for `FileSource`:** 16 kHz mono PCM16 WAV only, for now.
5. **Hiding whisper's wait:** no background decoding while you talk; measure the plain wait first.
6. **What triggers a swap:** the config file is the only trigger for now. A picker or a command from the main app is a possible later option; nothing is built for it.
