# Mic clear button

> **Status: done (2026-11-03).** Loaded after a restart; the user checked that the ✕ clears the heard words. Approved 2026-11-03 as proposed (keep listening, no voice app change). Built and tested: 289 tests pass, ruff clean.
>
> **Correction to "a reload is enough" below:** the `discard` field is in `assistant.contracts`, which a reload can't swap. Worse, the running app's old `StopListening` silently ignores an unknown field (pydantic's default), so a reloaded ✕ would do a normal stop and **send** the text to the Talker. So: restart the app once instead of `RELOAD: voice_in` / `temp_ui`. The voice service app is still unchanged. The "same voice app kept across a reload" check can be done after the restart: use the mic once, then `RELOAD: voice_in` (no code change needed for that test).
>
> **Same-voice-app check: passed (2026-11-03 14:18).** The voice app had been running since 13:23:30, with several mic sessions. `RELOAD: voice_in` (its new code reads `discard` with `getattr`, so it runs on the old contract) logged "Kept the running voice service from before the reload", and the next mic click started a session 49 ms later with no new "Started voice_service" line. No warnings or errors. `temp_ui` was deliberately not reloaded, so the ✕ waits for the restart.
>
> **Left after the restart:** the user tries the ✕ while listening (the words vanish, nothing reaches the Talker, the mic keeps listening; the log should show "Voice session … cleared; nothing was sent" and then a new session). If that's OK, set the Pending changes row to done. Nothing is committed yet (the user commits and pushes).

**Asked:** "a reset mic button, so I'm not sending everything that is recorded so far", because the mic sometimes picks up other people in the room. Throw away what's been recorded and transcribed, live text included, send nothing to the Talker, and leave the mic ready to go on. The filter for other voices and the Whisper second pass aren't part of this.

**Why:** today the only way out of a session is Stop, and Stop always sends the final text to the Talker.

**Touches:**
- `src/assistant/contracts/voice.py`: one option on `StopListening`. No new command, event or state.
- `src/assistant/modules/voice_in/module.py`: the discard path.
- `src/assistant/modules/temp_ui/` (`module.py`, `page.html`): a small ✕ button next to the mic, and `POST /mic {"clear": true}`.
- Tests: `tests/test_voice_in*.py`, `tests/test_temp_ui.py`.
- Docs: [Messaging API](../../api/messaging.md#stoplistening), [Voice](../../../src/assistant/modules/voice_in/docs/voice-service.md#the-voice_in-module), the [runtime](../../agents/runtime.md#temp-ui) page's temp UI section.
- **The voice service app doesn't change.** The protocol stays as it is, so reloading `voice_in` and `temp_ui` is enough and the running voice app doesn't need a restart.

**Approach:**
- **Reuse `StopListening`:** add `StopListening(discard: bool = False)`. With `discard=True`, `voice_in` closes the session's socket instead of sending `stop`. The service already treats a closed socket as an abort: mic closed, engine stream dropped, no final. Then `voice_in`:
  - marks the session discarded and ends it, so a final that still arrives is ignored and never becomes `InputReceived`;
  - publishes an empty final `VoiceTranscript`, which clears the live line on any UI;
  - publishes `VoiceState(idle, reason="cleared")`;
  - returns `ok` with `{"text": "", "discarded": true}`. With nothing listening, it returns `ok` with `None`, the same as today.
- **Then the mic carries on.** The temp UI's ✕ sends `StopListening(discard=True)` and then `StartListening()`. The mic goes `idle → starting → listening`, so no new state is needed. The new session has a new id, so anything late from the old one is dropped by id, both in `voice_in` and in the temp UI.
  - **Why carry on, and why in the UI:** you clear because you want to say it again, so leaving the mic on saves a click. The choice stays with the UI because a dictation box might want the mic off after a clear. `voice_in` keeps one simple meaning: discard and stop.
- **Page:** the ✕ shows only while the mic is `listening` or `dropped`. A click empties the grey live line at once, and the server's empty final confirms it.
- **Restarting straight after an abort:** if the service hasn't freed its mic slot yet, the new `start` can get `busy`. Right after a discard, `voice_in` retries such a `start` once after a short wait (about 0.3 s).
- **Tests:**
  - `voice_in` against the real service app with its fake engine and fake mic: partials, then a discard. Checks: no `InputReceived`, an empty final, `idle`/`cleared`, and a new `StartListening` works.
  - A fake socket that sends a `Final` after the discard: still nothing sent to the Talker.
  - `temp_ui`: `POST /mic {"clear": true}` sends both commands and empties the line.

**Open questions:**
1. **After a clear, keep listening or turn off?** Recommended: keep listening, as above. The cost is a short gap while the mic reopens, under half a second; the model stays loaded.
2. **Gapless clear?** A new protocol message (`reset`: the service starts a fresh engine stream on the same open mic) would avoid the gap. It changes the voice service app, though, so the running voice app would need a restart. Recommended: not now. Add it only if the gap turns out to cut off your first words.

**The open reload check:** "the same running voice app is kept across a reload" needs a mic session before the reload. If you use the mic once before I send `RELOAD: voice_in`, the log will show whether the old voice app was kept or a new one was launched, and I'll report it.
