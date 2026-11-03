# Voice in: the temp UI's mic button (step 4)

> **Status: done (2026-11-03).** Approved in advance: the user asked for voice in end to end in full auto ("assume yes to everything"), so the design choices below were made from the docs and principles and are recorded here instead of stopping for a check. The [temp UI is throwaway](../agents/runtime.md#temp-ui): nothing new is shared, no contract changes.

## What it does

- **A mic button** next to Send. Click: `POST /mic {"on": true}` → `StartListening`. Click again: `{"on": false}` → `StopListening`. The page shows the result's error only when `voice_in` didn't publish a state of its own.
- **The button shows `VoiceState`:** idle (outline mic), *starting* (pulsing, not clickable), *listening* (red), *dropped* (amber, crossed-out mic), *failed* (outline, with the reason under it).
- **A grey line above the input** shows, in order of what's happening:
  - *listening:* the live text from `VoiceTranscript` partials ("Listening…" before the first one);
  - *dropped:* "⦸ Mic dropped, waiting 12 s for it to come back · 8 words so far", the countdown ticking down;
  - *failed:* "Mic: " and the state's `detail` (already a short plain sentence, from [the error table](../architecture/voice.md#the-voice_in-module-how-errors-reach-the-button)); it stays until the next click;
  - *idle after a silence stop:* "Mic: mic turned off after a long silence".
- **Your spoken message** shows in the chat as your own message, like typed text, marked "spoken" next to its time (`InputReceived(source="voice")`; the temp UI already showed every `InputReceived`).
- **`voice_in` is on:** added to `[modules] enabled` in `config/default.toml`. Without the voice extra its `init` fails and the core skips it; the rest of the app runs, and the button says "voice input is off".

## Decisions made for the user

1. **`voice_in` is turned on in config, not by the temp UI.** The design says "add `voice_in` to `enabled`" ([handoff](handoff-voice-in.md)); a UI that activates modules is the control panel's job, not the temp UI's.
2. **The countdown is read from the `dropped` state's `detail`** ("waiting 15 s…"), as step 3's note planned, instead of adding a `wait_seconds` field to `VoiceState`. The temp UI is throwaway, so no contract change for it; the real UI handler can ask for the field when it's designed. If the number isn't there, the line shows the detail without a countdown.
3. **The word count** is the words of the last partial, counted in the page.
4. **Stale sessions:** the temp UI follows the session that sent `VoiceState(starting)` and ignores `VoiceState` and `VoiceTranscript` with any other `correlation_id`.
5. **"voice input is off":** when `StartListening` fails and no `VoiceState` came for it (no handler: `voice_in` isn't running), the temp UI shows this itself.
6. **The voice state is a "current state" SSE item** (like the usage meters and the permission mode), not history: a reconnect shows the button as it is now, not replayed.
7. **No shared test harness:** the temp UI's tests use a tiny fake `voice_in` (a module that handles the two commands), not the real service, so `tests/test_voice_in.py`'s `Service` stays where it is.

## Files

- `src/assistant/modules/temp_ui/module.py` (`POST /mic`, `VoiceState` and `VoiceTranscript` subscribers, the `voice` state item, `voice: true` on spoken input), `page.html` (button, line, countdown).
- `config/default.toml` (`voice_in` in `enabled`).
- `tests/test_temp_ui.py` (the mic round trip, stale sessions, the dropped countdown, voice input off).
- Docs: [runtime: temp UI](../agents/runtime.md#temp-ui), [Voice](../architecture/voice.md) (status, flowcharts), the overview, [Next steps](README.md).
