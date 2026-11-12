# Voice text goes to the tab you pressed stop in

> **Status: built, waiting on the restart (2026-11-06).** Built as (b), the exact version below, since a restart was coming anyway. Open question 1 taken as recommended: a silence stop goes to the tab in focus when the text arrives. Tests: `test_voice_in.py::test_the_final_goes_to_the_tab_the_stop_was_pressed_in` (and no id still gives `agent_id=None`), `test_temp_ui.py::test_mic_button_round_trip` (the stop carries `agent`). Docs: messaging API, voice, temp_ui, runtime, reusable index.

**Two ways to build it, when picked up:**
- **(a) Hot swap, no restart:** `voice_in` alone subscribes to `FocusChanged` (an existing event), keeps the last focused tab (handed over on a reload), and puts it on the session when the stop comes; the final goes out as `InputReceived(agent_id=...)`. Only `voice_in` changes (`RELOAD: voice_in`). Gap: after a launch or a reload, until the first tab switch it doesn't know the tab and behaves as today.
- **(b) As below:** the stop carries its tab (`StopListening.agent_id`). Exact, but a contract change, so an app restart.

Neither touches `agent_hub` or `talker`.

**Asked:** "when I stop the recording, it takes whisper a little bit to solve the sentence. And then it sends into whatever active talker it is. I wanted it sent to the talker that was active when I said stop recording."

**Why:** `voice_in` publishes the final text as `InputReceived(source="voice")` with no `agent_id`, and the Talker sends input with no `agent_id` to the tab in focus *when the event arrives* (`talker/module.py` `_on_input`). Whisper takes a moment after the stop, so if you switch tabs in that moment, the text lands in the wrong tab.

**Touches:**
- `contracts/voice.py`: `StopListening` gets `agent_id: str | None = None` (the tab the stop was pressed in). A contract change, so it **needs an app restart**.
- `modules/voice_in/module.py`: `_finish_session` keeps that id on the session; `_finish` publishes `InputReceived(..., agent_id=session.agent_id)`.
- `modules/temp_ui/`: `page.html` sends `agent: focused()` with `POST /mic {on: false}` (as it already does for `/say`), and `module.py` passes it to `StopListening(agent_id=...)`.
- Tests: `tests/test_voice_in.py` (the final carries the stop's `agent_id`; no id still means the focused tab), `temp_ui`'s `/mic` test (the id is passed on).
- Docs: [Messaging API](../api/messaging.md) (`StopListening`, and `InputReceived`'s note "None (voice, terminal 1) means the tab in focus"), [Voice](../../src/assistant/modules/voice_in/docs/voice-service.md) (the `voice_in` module: where the final goes), [temp_ui](../../src/assistant/modules/temp_ui/docs/README.md) (`/mic`), [reusable parts](../api/reusable.md) (`StopListening` line), the [module library](../architecture/module-library.md) if it lists the fields. Then the docs rebuild.

**Approach:**
- **At stop, not at start.** You may start the mic, then move to the tab you mean to talk to, then speak; you press stop in the tab you were talking to. Stop is the last moment you chose a tab, and it's what you asked for.
- **The stop carries its tab.** The UI you press stop in knows exactly which tab you're looking at, so it says so. Nothing is reused or tracked on the side: `InputReceived.agent_id` already exists and the Talker already routes by it (the same path typed text takes, `agent: focused()`).
- No `agent_id` on the stop (another UI, or an older one) behaves as today: the tab in focus when the text arrives.
- `IVoice` is unchanged: its sessions send to the caller only (`voice_notes`), never to a Talker tab.
- Reusable parts checked: nothing new is needed; `InputReceived.agent_id` and the Talker's routing are reused.

```
press stop (tab A) ──StopListening(agent_id=A)──▶ voice_in ──(whisper finishes)──▶ InputReceived(agent_id=A) ──▶ Talker A
                       you move to tab B meanwhile: no effect
```

**Open questions:**
1. **When the mic turns itself off after a long silence** (no stop press), where should the text go? Recommended: the tab in focus when the text arrives, as today. You didn't choose a moment, and the text comes right after the silence ends it.
