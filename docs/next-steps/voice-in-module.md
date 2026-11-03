# Voice in: the voice_in module (step 3)

> **Status: done (2026-11-03).** Approved and built, not committed. Ruff is clean, and 224 tests pass (1 deselected). Where the build stands and what's next: [handoff](handoff-voice-in.md). The permanent design is on [Voice](../architecture/voice.md#the-voice_in-module).
>
> **Built differently from this note** (decided with you or found while building):
> - **A mic that doesn't come back drops the text** (your answer: "let it try to recover for a bit, but lose the text"). `voice_in` publishes `VoiceTranscript(final=True, text="")`, which clears the line, and then `VoiceState(failed, mic_lost)`. The text isn't kept as a last partial or greyed out, and a waiting `StopListening` gets `failed`, not `ok`. The service still sends `final complete=false` then `error mic_lost`, so the protocol is unchanged for that case.
> - **The service sends the last partial before `mic_dropped`**, after reading what the lost mic had already queued. That way the line shows the text so far during the drop.
> - **The retry interval** is `ListenSession.retry_seconds = 1.0`, a class attribute that the tests shorten, not a config setting.
> - **Tests the note didn't list:** a stub `CompanionApp` checks the health check's calls. `init` without `websockets` names the extra. The service's own tests cover the drop, the timeout, a stop while dropped, the paused silence timer, and `mic_recovery_seconds = 0`.
> - **Found by the tests:** `TimeoutError` is an `OSError`, so the launch-timeout case is caught before the launch-failure case.
>
> **Changed after your first check:** a lost mic now waits for the mic to come back ([When the mic drops](#when-the-mic-drops-mid-session-new)), and a quick `/health` check runs before reusing a running service ([The health check](#the-health-check-before-reusing-a-running-service-new)).

**Asked:** step 3 of [voice in](README.md#next-voice-in-phase-1): the thin `voice_in` module in the main app. It launches the `voice_service` through `CompanionApp`, handles `StartListening` and `StopListening`, asks for the microphone through `ctx.permissions`, opens one WebSocket per mic session using `voice_service.protocol`, publishes `VoiceState` and `VoiceTranscript`, and with `send_as_input` on, sends the final text to the Talker as `InputReceived`. It only launches, calls and relays. It has no speech logic, and it imports nothing from `voice_service` except `protocol`. No UI button (step 4).

**Why:** steps 1 and 2 built the contracts and the service. This module connects them to the app, so any UI can turn the mic on, and the Talker gets what you said.

**The design is already approved** ([the voice_in module](../architecture/voice.md#the-voice_in-module)). This note says how it gets built, fills a few gaps the design left open (marked **new**), and ends with three choices for you.

## Touches

- **New:** `src/assistant/modules/voice_in/__init__.py` and `module.py` (`VoiceInModule`); `tests/test_voice_in.py`.
- **Changed:**
  - `src/assistant/__main__.py`: `VoiceInModule` in `MODULES`. It stays out of `enabled`, so it's off by default.
  - `config/default.toml`: `[modules.voice_in]` and `StartListening = 30.0` under `[core.command_timeouts]`.
  - `src/assistant/contracts/voice.py`: a new `ListeningState.DROPPED`, for the mic drop (below), and the `VoiceState` docstring listing the three new app-side reasons. No fields change.
  - **The voice service (step 2, already committed), for the mic drop only:** `protocol.py` (two new messages), `session.py` (the recovery wait), `config.py` (one setting), `server.py` (it passes the source factory to the session), and their tests in `tests/test_voice_service.py`. The `/health` reply already fits.
- **Not changed:** `app_kit` (`CompanionApp` already does it all), the Talker (it already takes `InputReceived` from any source), `pyproject.toml` (`websockets` is already in the `voice` extra).
- **Docs:** [Voice](../architecture/voice.md) (step 3 built), [Messaging](../api/messaging.md#voice) (the reasons and who handles the commands), the [reusable parts index](../api/reusable.md) and [App kit](../api/app_kit.md) (Used by lines: `voice_in` no longer *planned*), the overview's Parts table (the `voice_in` location), the [runtime](../agents/runtime.md) page's module list, and [Next steps](README.md). Then rebuild.

## Manifest and config

```python
class VoiceInModule(Module):
    manifest = Manifest(id="voice_in", optional_permissions=("microphone",))
```

It provides, requires, and optionally uses nothing, and it isn't an `IToolProvider`, because agents don't turn on your mic.

```toml
[modules.voice_in]
# Voice input: launches the voice service (its own app) on the first mic click.
host = "127.0.0.1"
port = 8767
start_timeout = 20.0      # seconds for the service to answer /health after launch
service_config = ""       # optional path passed as --config to the service
reply_timeout = 10.0      # new: seconds to wait for `started` after start, and for `final` after stop
```

`reply_timeout` is **new**. Without it, a service that hangs without closing the socket would leave the button stuck in *starting* until the command's 30 s timeout, and in `StopListening` forever.

## How the service is launched and stopped with the module

- **`init`:** imports `websockets`. If it's missing, `init` raises "install the voice extra: pip install -e .[voice]", so this module fails to start and the rest of the app runs. It builds `CompanionApp("voice_service", host, port, ping="/health", quit="/quit", args=["--host", host, "--port", port, (+ "--config", service_config)], start_timeout=..., log=ctx.log)` and registers the two command handlers. Nothing is launched yet.
- **`start`:** does nothing. The service launches lazily, on the first `StartListening`.
- **On each `StartListening`:** `await app.ensure_running()`. A service already running (one you started yourself, or one we launched earlier) is used, after the [health check](#the-health-check-before-reusing-a-running-service-new). Otherwise it's launched with no console and polled until it answers.
- **`stop`** (app shutdown, or `DeactivateModule`): it aborts an open session (closes the socket, sends no `InputReceived`) and publishes `VoiceState(idle, reason="service_stopped")`. Then `await app.stop()` sends `POST /quit`, waits 5 s, and kills the service, but only if this module launched it. A service you started yourself keeps running.
- **No watchdog** (as designed). A crash shows up as the socket closing. The next click runs `ensure_running` again, which relaunches it.

## One mic session

All of it happens under one lock, so a double click can't open two sessions.

1. **`StartListening`.** If a session is already listening or starting, the result is `ok` with that session's id, and its `send_as_input` stays as it was. Otherwise:
2. Publish `VoiceState(starting)`. `correlation_id` is the session id, which is this command's id, on every event of the session.
3. `await ctx.permissions.request("microphone", reason="You clicked the mic")`. If it's denied, see the table below.
4. `ensure_running()` (plus the health check if it didn't launch the service just now), then connect to `ws://host:port/ws/listen` and send `dump(Start())`.
5. Wait up to `reply_timeout` for the first reply:
   - `started`: publish `VoiceState(listening)`, start the reader task, and return `ok {"session_id"}`.
   - `error`: map it with the table below.
6. **The reader task** parses every frame with `parse_service_message`:
   - `partial` → `VoiceTranscript(text, final=False)`.
   - `mic_dropped` → `VoiceState(dropped)`; `mic_back` → `VoiceState(listening)` (see [When the mic drops](#when-the-mic-drops-mid-session-new)).
   - `final` → `VoiceTranscript(text, final=True)`. Then `InputReceived(text, source="voice")` if the text is non-empty, `complete`, and `send_as_input` is on. Then `VoiceState(idle)`, with `reason="silence"` and *mic turned off after 2 minutes of silence* when `ended_by` is `"silence"`. Then it closes the socket.
   - `error` → see the table.
   - The socket closes with no final → `service_stopped`.
7. **`StopListening`.** With nothing listening, the result is `ok` with `None`. Otherwise it sends `dump(Stop())` and waits up to `reply_timeout` for the reader to deliver the final. The result is `ok {"text", "latency_ms"}`.
8. **Logging:** each session's start, the final's text, its length and `latency_ms`, and how it ended. The service's `detail` goes to the log on every error. The permission warning comes from the stand-in; `voice_in` logs none of its own.

The service never reports the audio length, so the log line has text length and latency only. The design's "audio length" would need a protocol change; I've left it out (say if you want it).

## When the mic drops mid-session (new)

**What the built service does today:** it doesn't retry. When the mic goes away, `MicSource` calls `on_lost`, and the session stops listening at once. It finishes the text heard so far, sends `final` with `complete: false`, then `error mic_lost`, and frees the slot. So `mic_lost` always ends the session, and your idea needs a change in the service. Only the service can reopen the mic, so the wait has to live there.

**The smallest version that fits your idea:**

- **Service (step 2 code, a small change):**
  - A new setting under `[audio]`: `mic_recovery_seconds = 15.0`. `0` keeps today's behavior: end at once.
  - On `on_lost`, the session doesn't end. It closes the dead source, keeps the engine stream (so the text so far is kept), and sends a new message `{"type": "mic_dropped", "detail": "...", "wait_seconds": 15}`.
  - While dropped, it tries to open a fresh source about once a second. The session gets the server's `source_factory` for this, instead of one source. The silence timer is paused, so a drop never counts as silence.
  - When a source opens, it sends `{"type": "mic_back"}` and keeps feeding the same stream. Your next words carry on from the text so far.
  - If none opens within `mic_recovery_seconds`, it ends as today: `final complete=false`, then `error mic_lost`.
  - A `stop` while dropped ends the session the same way, right away. That's you giving up on the mic, so it's treated as a drop.
  - Protocol: two new service messages, `MicDropped` and `MicBack`. No new error code, and `mic_lost` keeps its meaning (the mic didn't come back).
- **`voice_in`:**
  - `mic_dropped` → `VoiceState(dropped, reason="mic_dropped", detail="mic dropped, waiting 15 s for it to come back")`.
  - `mic_back` → `VoiceState(listening)`.
  - On a timeout it's the `mic_lost` row of the table below. The text so far is published as a last `VoiceTranscript(final=False)`, then `VoiceState(failed, mic_lost)`. It isn't sent to the Talker.
  - It needs no setting of its own. The wait comes in `wait_seconds`.
- **Contract:** `ListeningState.DROPPED = "dropped"`, so every UI can show the drop the same way.
- **Temp UI (step 4):**
  - The button shows an obvious drop symbol (a crossed-out mic, amber, with a countdown from `wait_seconds`).
  - The live line keeps the text so far, with its word count, for example *"…42 words so far"*, counted from the last partial. That needs no new field.
  - On `mic_back`, the button goes back to listening, and you carry on speaking.
  - If the mic doesn't come back, the button shows *mic disconnected*. The text stays on the line, greyed out, until your next click.

**Not covered (checked in step 6 on your real mic):** if Windows doesn't report the unplug, the mic just goes quiet, and nothing is detected. A "no audio for 2 s counts as a drop" check would cover that. I've left it out until step 6 shows whether it's needed.

## The health check before reusing a running service (new)

`ensure_running()` returns whether it launched the service just now. Right after a fresh launch, `CompanionApp` has just pinged it, so nothing more is done. When it reuses a running service, `voice_in` first calls `GET /health` with a 2 s timeout:

- `ready: false` with an `error`: fail at once with `engine_failed` and the error as the detail, without opening the WebSocket.
- `ready: false`, no error: the model is still loading. Carry on, because the service buffers the audio until it's loaded.
- No answer, or a different `app`: the service died since the last click. Run `ensure_running()` once more, which relaunches it. If that fails, it's `service_unavailable`.

This fails fast with a clear reason instead of waiting out `reply_timeout`.

## How every error maps to `ListeningState.failed`

`reason` is the service's code where there is one. Three app-side reasons are **new**: `not_allowed`, `service_unavailable`, and `timed_out` (with the design's existing `service_stopped`). `detail` is the short sentence for the button. After every failure, the socket is closed and the module is ready for the next click.

| Case | `VoiceState` | `StartListening` result | Sent to the Talker |
|------|--------------|-------------------------|--------------------|
| Permission denied | `failed`, `not_allowed`, *microphone not allowed* | `failed` "microphone not allowed" | no |
| `websockets` missing (main app has no voice extra) | the module never starts | the command has no handler: `not_available` from the router | no |
| Service can't start: the voice extra isn't in the venv, a crash on launch, or the port is taken (`ensure_running` raises `OSError`) | `failed`, `service_unavailable`, *voice service didn't start* (the log adds: run `python -m voice_service` to see why) | `not_available`, retryable | no |
| Service never answers `/health` (`TimeoutError`) | `failed`, `service_unavailable`, *voice service didn't answer* | `not_available`, retryable | no |
| Connecting the WebSocket fails | `failed`, `service_unavailable` | `not_available`, retryable | no |
| No `started` within `reply_timeout` | `failed`, `timed_out` | `not_available`, retryable | no |
| `error busy` | `failed`, `busy`, *another app is using the mic* | `failed` | no |
| `error mic_unavailable` | `failed`, `mic_unavailable`, *no microphone (or blocked in Windows settings)* | `not_available`, retryable | no |
| `/health` on a reused service says `ready: false` with an error | `failed`, `engine_failed`, *speech model not installed* | `not_available`, retryable | no |
| `error engine_failed` at start: the model is missing or didn't load, and the service's detail names the `download` command | `failed`, `engine_failed`, *speech model not installed* | `not_available`, retryable | no |
| `error engine_failed` mid-session (engine crash) | `failed`, `engine_failed`, *speech engine error* | (already `ok`); a waiting `StopListening` → `failed` | no |
| `mic_dropped` (the mic went away; the service is waiting) | `dropped`, `mic_dropped`, *mic dropped, waiting 15 s for it to come back* | (already `ok`) | not yet |
| `final complete=false` then `error mic_lost` (the mic didn't come back in time, or you stopped while dropped) | `failed`, `mic_lost`, *mic disconnected*; the text so far stays in the live line as a last partial | (already `ok`); a waiting `StopListening` → `ok` with the text, `complete: false` | no |
| Socket closes with no final (the service crashed or quit) | `failed`, `service_stopped`, *voice service stopped* | a waiting `StopListening` → `failed`, retryable | no |
| No `final` within `reply_timeout` after stop | `failed`, `timed_out` | `StopListening` → `failed` | no |
| `error bad_message` | no change: it means a bug on our side. Logged as an error; the session carries on | | |
| A frame `parse_service_message` rejects | no change. Logged as a warning and skipped | | |
| Final with empty text | `idle`; `VoiceTranscript(final=True, text="")` clears the line | `StopListening` → `ok` with `""` | no |

**Not installed, all three ways:** without `websockets`, `init` fails with the install hint. Without the service's packages (FastAPI and the rest), the launched process exits early, which gives `service_unavailable`. Without the model, the service runs but answers `engine_failed`, and its detail names `python -m voice_service download zipformer`.

## Tests (`tests/test_voice_in.py`; no mic, no model)

The module runs inside a real `App`, like the viewer tests. Commands go through `app.router.send`, and a bus subscriber collects the events. Something in the test has to play the voice service; which one is question 2.

- **Happy path:** start → `starting`, `listening` → partials → stop → `VoiceTranscript(final=True)`, `InputReceived(source="voice")`, `idle`. The result has the text and `latency_ms`, and every event carries the session's `correlation_id`.
- **The options:** `send_as_input=False` sends no `InputReceived`. Starting while listening returns the same session. Stopping with nothing listening gives `ok` with `None`. An empty final sends nothing. A silence stop gives `idle` with `reason="silence"`, then `InputReceived`.
- **Every error code:** `busy` (a second connection holds the slot), `mic_unavailable` (the source fails on open), `mic_lost` (the source stops after N chunks and no new one opens: no `InputReceived`), `engine_failed` at start (the engine fails on load) and mid-session (it fails on accept), `bad_message` (fed to the reader directly: no state change).
- **The mic drop:** the first source is lost after N chunks and the next one opens: `dropped`, then `listening`, and the final holds the text from before and after the drop. No source opens within a tiny `mic_recovery_seconds`: `dropped`, then `failed mic_lost`. A stop while dropped: `failed mic_lost`, nothing to the Talker.
- **The health check:** a reused service whose `/health` says `ready: false` with an error fails with `engine_failed` without opening a WebSocket. A fresh launch makes no extra `/health` call.
- **In the service's own tests:** `mic_dropped` and `mic_back` on the wire, the silence timer paused during a drop, and `mic_recovery_seconds = 0` keeps today's behavior.
- **The service's lifecycle:**
  - A service you started yourself is used and left running at `stop`.
  - A service that fails to launch gives `service_unavailable`. The test points `CompanionApp` at a module that doesn't exist, so `python -m` exits with 1.
  - A service that never answers gives `service_unavailable` after a tiny `start_timeout`.
  - A service that dies mid-session gives `service_stopped`.
  - A denied permission gives `not_allowed` (with a test double for `ctx.permissions`).
  - `stop()` with a session open aborts it, and nothing goes to the Talker.
- **The import rule:** a test that `assistant.modules.voice_in` imports nothing from `voice_service` except `protocol`.
- **Not tested here:** launching the real `python -m voice_service`. With no fake mic option, it would open your real mic on this PC. The launch itself is `CompanionApp`'s, already tested in `test_app_kit.py`; your own try in step 6 covers it.
- Then all of `pytest` and `ruff`.

## Reuse

- **Used:**
  - `CompanionApp` for the launch, ping and quit, with no launch code of its own.
  - `voice_service.protocol` for every frame (`Start`, `Stop`, `parse_service_message`, `dump`, `ErrorCode`).
  - `ctx.permissions` for the mic check.
  - The contracts from step 1, and the existing `InputReceived`.
- **New parts for the index:** none. `voice_in` is a module, not a shared helper. The index gets Used by updates only: `voice_in` on `CompanionApp`, the protocol, `ctx.permissions`, `InputReceived`, the two commands, and the two events.

## Left for the next steps

- **Step 4, the temp UI:**
  - The mic button: send `StartListening` and `StopListening`, and show `VoiceState`, with *starting* as a spinner, *dropped* as the drop symbol with its countdown and word count, and *failed* showing `detail`.
  - The grey live line above the input box, from `VoiceTranscript`. Drop updates whose `correlation_id` isn't the current session's. Clear the line on `final=True` and on the next start.
  - The final text as your own chat message. The temp UI shows `InputReceived(source="voice")` like typed text.
  - Turning `voice_in` on in `enabled`. Off by default until then, as designed.
- **Step 6:** try it on your mic: the first real latency check, and the docs move from planned to built (the Voice page, the overview, the runtime page).
- **Step 7:** Nemotron and the comparison. No change to `voice_in`, because the protocol names no engine.

## Open questions (for you)

1. **A lost mic. Decided:** wait for it to come back, with a drop symbol ([When the mic drops](#when-the-mic-drops-mid-session-new)). This changes the step 2 service. If it doesn't come back, the session is dropped **and so is its text** (revised at approval: the line is cleared, and nothing goes to the Talker).
2. **What plays the voice service in the tests. Decided: A.** It's the stand-in until you try your own mic (step 6).
   - **A (recommend):** the real voice service app, started inside the test on a local port. It runs with its built-in fake engine (canned text, no model) and fake mic (canned audio, no microphone). So `voice_in` is tested against the real service, and if the service changes, these tests catch it.
   - **B:** a small imitation server written in the test file, with canned replies. It's quicker to write, but it keeps passing even when the real service changes.
3. **Health check. Decided:** a quick `/health` before reusing a running service ([The health check](#the-health-check-before-reusing-a-running-service-new)).
