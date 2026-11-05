# Voice notes: a quick record-to-page module

> **Status: built (waiting on you), 2026-11-04.** v1; your checks with the fake engine and the real mic are next. `voice_in`, `temp_ui` and the new `voice_notes` module are changed as below; tests and ruff pass. Docs updated now: the messaging API page only. The architecture pages (Modules, Voice, the overview's row, runtime) wait for the module-shape refactor, as decided. The reusable index's `window` row doesn't list `voice_notes` yet. Your decisions are in: **whoever presses second gets the mic, and the first is cancelled** (2026-11-04). The other two choices use the defaults below: notes kept in local storage only, and the temp UI's page server copied for v1. This is a throwaway first version of the voice-notes module planned in the [module-shape change](module-shape-refactor.md). The voice contract and voice sessions planned there replace its workaround later.

## What is built

- **A notes page** in its own small window: a blank text area, a **Record** button, and a grey live line.
- **Record:** the mic turns on and the live text shows in the grey line while you talk.
- **Stop:** the final text is put into the text area where the cursor is. You can type and edit in it like any text box.
- **Copy** button. The text is kept in the page's local storage, so closing the window doesn't lose it. No file is written (**chosen by default**); saving to a file can be added later.
- **The text goes only to the page.** The temp UI's mic button still sends its text to the Talker, as it does today.
- **Second press wins:** pressing Record while the chat's mic is on cancels the chat's recording, and the other way round. The cancelled side's words are dropped, and its button resets and says it was cancelled.

## Own module or part of the temp UI

**Recommended: its own module.** The temp UI is throwaway, and voice notes is meant to be the first module built in the new shape. A part of the temp UI would have to be moved out later. The cost is a second small page server (see Risks).

## How it fits the module shape

| Rule ([modules](../architecture/modules.md)) | Voice notes v1 |
|---|---|
| Own folder | `src/assistant/modules/voice_notes/` (`__init__.py`, `module.py`, `page.html`) |
| Manifest id | `Manifest(id="voice_notes")`. Provides nothing. No permissions of its own: `voice_in` asks for the mic |
| One-line description | `Manifest` has no `description` field yet (`contracts/module.py:31-41`). Adding one changes a contract and needs a restart. In v1 the line goes in the module's docstring and moves into the manifest with the refactor |
| `requires` | Nothing in v1. The voice contract it should require doesn't exist yet. If `voice_in` is off, Record shows "voice input is off" |
| Listens to voice events | Subscribes to `VoiceState` and `VoiceTranscript`, and sends `StartListening` / `StopListening` through `ctx.send` |
| Imports | `assistant.contracts` and `app_kit.window` (the shared window helper). No other module, no core code |

## Answers about the voice code today

**1. What `StartListening` does with `send_as_input`, and what the events carry**
- `send_as_input` defaults to `True` (`src/assistant/contracts/voice.py:30`). `voice_in` stores it on the session (`src/assistant/modules/voice_in/module.py:157`) and uses it in one place: after the final text, `if text and session.send_as_input` publishes `InputReceived(source="voice")` to the Talker (`module.py:364-365`). With `False`, the text goes only to `VoiceTranscript` subscribers.
- `VoiceTranscript` carries `session_id`, `text`, `final` and `settled_chars` (`voice.py:58-69`). It is published for live text (`module.py:339`), the final (`module.py:363`), and empty finals on clear or mic loss (`module.py:190`, `349`).
- `VoiceState` carries `state`, `reason` and `detail` (`voice.py:44-56`), with `correlation_id` set to the session id (`module.py:374`). **`reason` is a plain string, not an enum** (`voice.py:54`), so a new reason value needs no contract change.
- **Neither event says who started the session or where the text goes.** The session id is just the `StartListening` command's id (`module.py:78`, `157`), and the start's result returns it (`module.py:255`). A consumer can only recognize its own session by remembering the id of the command it sent.

**2. A second consumer today**
- `voice_in` holds **one session** (`module.py:124`). A second `StartListening` while one is open **returns ok with the first session's id** (`module.py:155-156`). It raises no error, and the second caller's `send_as_input` is ignored. Today the first caller wins, silently.
- `StopListening` has no session id. It stops **whatever session is open** (`module.py:167`), so either button can stop the other's recording.
- The temp UI follows **any** session that starts (`src/assistant/modules/temp_ui/module.py:233-235`). If notes started recording, the chat's mic button would turn red, show the notes' live text, and stop the notes session when clicked.

**3. The change: the second press wins**

- **`voice_in`** (`module.py:155-156`): when a session is open, a new `StartListening` no longer joins it. It **ends the open session the way the clear button does** and then starts the new one:
  - it reuses `_discard` (`module.py:186-199`), given the reason and detail to publish: the old session gets an empty final `VoiceTranscript` (clears its live line) and `VoiceState(idle, reason="taken_over", detail="another part of the app took the mic")`, with the old session's id as `correlation_id`;
  - the socket is closed before any final arrives, so nothing goes to the Talker. A final that still arrives is dropped by the existing `session.ended` check (`module.py:344-346`);
  - a `StopListening` the first side was already waiting on gets `Result.ok({"text": "", "taken_over": True})`;
  - `_discard` sets `_cleared_at`, so the existing retry covers the service not having freed the mic yet when the new start arrives (`module.py:229-232`);
  - this all runs inside the existing lock, so a start that comes while the first is still opening waits until it's open, then cancels it.
- **The cancelled side learns it** through the existing `VoiceState` event: `idle` with `reason="taken_over"` and its own session id. Both UIs reset their button and show "cancelled: another part of the app took the mic".
- **The temp UI's rules** (`temp_ui/module.py:232-247`):
  - it remembers the id of each `StartListening` it sends and follows only that session (today it follows any `STARTING`);
  - events and `VoiceTranscript`s of other sessions are ignored, so the chat's button and live line stay idle while notes records;
  - on its own session's `idle` with `taken_over`, it clears the live line and shows the cancelled note; the button stays enabled, and pressing it takes the mic back;
  - its own text still reaches the Talker (`send_as_input=True`, unchanged).
- **Voice notes** follows the same rules with `send_as_input=False`.
- **Contract change: none.** `ListeningState` gets no new state and no event or command gets a field: `idle` plus the free-text `reason` already carries "taken over". The new reason is listed in the [messaging API page](../api/messaging.md#voicestate); the `VoiceState` docstring in `contracts/voice.py` gets the line at the refactor, so the contracts file isn't touched now. **No restart:** `RELOAD: voice_in`, `RELOAD: temp_ui`, and `ADD_MODULE` for voice notes.
- **What this doesn't handle:**
  - Only one user of the mic at a time; the second takes it, there's no queue.
  - `StopListening` still isn't scoped. A UI that sends stop at the moment the other side takes over could end the new session. Both UIs stop only a session they follow and drop it on `taken_over`, so the window is small.
  - Pressing during the first side's **finishing** (stop sent, final not in yet) also cancels it, and those words are dropped.
  - The notes' text is visible to any `VoiceTranscript` subscriber. Nothing marks it "for notes".
  - No `requires`: turning on voice notes doesn't turn on `voice_in`.
  - A reload of `voice_in` mid-recording drops those words, as it does today.
- **The full fix later** is sessions in the contract (a destination on `StartListening`, echoed on the events; a `session_id` on `StopListening`). That changes `contracts/voice.py`, needs a restart, and belongs to the module-shape refactor.

## Files

- **Add** `src/assistant/modules/voice_notes/__init__.py`, `module.py`, `page.html`:
  - a small asyncio server on a fixed port (`[modules.voice_notes] port`, default 8770) with `GET /`, `GET /events` (SSE: state and live line), and `POST /record {"on": bool}`. Copied from the temp UI's page server, about 40 lines (**chosen by default**);
  - the window opened with `app_kit.window.open_app_window`.
- **Change** `src/assistant/modules/voice_in/module.py`: a start while a session is open cancels it through `_discard` with reason `taken_over`, then starts the new one.
- **Change** `src/assistant/modules/temp_ui/module.py` (and its page if needed): follow only its own sessions; show "cancelled" when taken over.
- **Change** `config/default.toml` (`[modules.voice_notes]`, and `voice_notes` in `enabled`) and `src/assistant/__main__.py` (`MODULES`). Both only matter at the next launch; today's run uses `ADD_MODULE`.
- **Add** `tests/test_voice_notes.py`; **extend** `tests/test_voice_in.py` and `tests/test_temp_ui.py`.
- **Docs:** [Modules](../architecture/modules.md) (voice notes v1 built, by workaround), [Voice](../architecture/voice.md) (one user at a time, the second press wins), the [messaging API page](../api/messaging.md#voicestate) (reason `taken_over`; a second `StartListening` cancels the open session), the overview's Voice notes row, and the [runtime](../agents/runtime.md#temp-ui) page.

## How to test

- **Automated** (no mic, no model):
  - `voice_in` (`tests/test_voice_in.py`, with its fake service): a second start ends the first session with `idle` / `taken_over` and an empty final for it, then opens the new one; the first session's late final is dropped and never becomes `InputReceived`, even with `send_as_input=True`; a stop the first side was waiting on returns `taken_over`.
  - Voice notes and the temp UI, with a tiny fake `voice_in` module as `tests/test_temp_ui.py` uses:
    - Record sends `send_as_input=False`, and the final reaches the page but never `InputReceived`;
    - another session's events are ignored;
    - **notes pressed while the chat mic is on:** the temp UI shows cancelled, its text is dropped, the notes session records;
    - **chat mic pressed while notes is on:** the notes page shows cancelled, its text is dropped, the chat session's text reaches the Talker;
    - in both directions, the cancelled side sends no stop afterwards.
- **Fake audio, by hand:** the running service always uses the real mic (`src/voice_service/__main__.py:112`). `FakeSource` is for tests only. For a check without speech, set `[engine] name = "fake"` in `config/voice_service.local.toml`. Record, stop, and "Hello from the fake engine." should land in the notes page and not in the Talker's chat. Remove the line afterwards.
- **Real mic:**
  - Record, speak, and stop. The live line moves, the text lands at the cursor, and the Talker gets nothing.
  - The chat's mic button still sends to the Talker.
  - Start the chat mic, speak, then press Record in notes: the chat button resets to "cancelled", the Talker gets none of those words, and notes records.
  - The other way round: notes records, then press the chat mic. Notes shows "cancelled" and keeps none of those words; the chat's text reaches the Talker.
  - Clear and silence stops behave as before.

## Risks

- **A second hand-rolled page server.** The temp UI has the first. [Principle 13](../architecture/principles.md) says to build it once. For a throwaway, about 40 lines are copied (chosen by default); a shared page server is extracted with the refactor.
- **Cancelled words are lost.** By design, but a press on the other button by mistake throws away what you just said, including during finishing. The cancelled note on the button makes it visible.
- **`voice_in`'s behavior changes for every caller.** Today a second start joins; after this it cancels. Only the temp UI and voice notes send `StartListening` today, and both are changed together.
- **Reload order:** `voice_in` first, then `temp_ui`, then voice notes. An old temp UI on the new `voice_in` would follow the new session (it follows any `STARTING`) until it's reloaded.
- **v1 is off the planned shape** in three places: no description field, no `requires`, owner by command id. The refactor replaces all three, and the temp UI's follow rule moves to the voice contract then.
- **With two passes** the final text can take a few seconds after Stop (up to `final_timeout_on_send`). The button shows "finishing" meanwhile.

## Checklist

- [x] You do the final check of this note: own module, second press wins, local storage only, page server copied
- [x] `voice_in`: a second start cancels the open session (`taken_over`), then starts
- [x] `voice_notes` module, page, config, `MODULES` entry
- [x] temp UI follows only its own sessions and shows cancelled when taken over
- [x] tests: notes pressed while the chat mic is on; chat mic pressed while notes is on; the cancelled side's text dropped in both directions (`tests/test_voice_notes.py`, real `voice_in` on fake audio)
- [x] tests and ruff pass
- [x] `RELOAD: voice_in`, `RELOAD: temp_ui`, `ADD_MODULE: assistant.modules.voice_notes` (no restart; done 2026-11-04)
- [ ] your checks: fake engine, then real mic, then both buttons in both orders
- [ ] docs updated and rebuilt; this note's status set
