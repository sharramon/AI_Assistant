# Spoken input reaches the Talker marked as spoken

> **Status: done (2026-11-03).** Approved as written, caps left on screen. Built in `talker/module.py` (`SPOKEN` prefix `[Spoken] `, `_Item.source`, a prompt paragraph); test `test_talker_marks_spoken_input`; 232 tests pass, ruff clean. Docs updated: [Messaging](../../api/messaging.md#inputreceived), [Agents](../../architecture/agents.md), [Voice](../../../src/assistant/modules/voice_in/docs/voice-service.md). **Loaded** at the relaunch of 2026-11-03 12:59: spoken messages now reach the Talker marked `[Spoken]`.
>
> **Can the voice part be changed and restarted while the app runs? (checked 2026-11-03)**
> - **The `voice_service` app: yes.** It's its own process. Quit it (or let it crash), edit its code, and the next mic click relaunches it with the new code (`voice_in` health-checks before reusing it). A session in progress just ends as failed. The chat window and the Talker carry on.
> - **Turning `voice_in` off and on: the core can, but nothing calls it yet.** `DeactivateModule` / `ActivateModule` work (tests in `test_control.py`), and nothing depends on `voice_in`, so the chat and the Talker aren't touched. The mic button then just fails ("not available"). But no button or Talker tag sends these commands; that's the planned control panel.
> - **Edits to `voice_in`'s own code: not without a restart.** Reactivating makes a fresh instance of the class already loaded; new code needs an app relaunch, which also restarts the Talker's session. That's by design (no hot code reload).

**Asked:** while testing the mic: "I thought that we had tags to show if text is typed or over the mic", "why is the entire text in caps", and the Talker should "figure out what I am trying to say based on context", with no separate cleanup model call.

**Why:** the Talker can't tell a spoken message from a typed one, so it can't allow for mishearings ("mike" for mic, "O fool" for Whisper).

**What happens today:**
- `voice_in` already tags its final text: `InputReceived(text=..., source="voice")` (`voice_in/module.py`). The temp UI uses the tag to mark the message as spoken in the chat.
- The Talker drops the tag. `_on_input` (`talker/module.py`) keeps only `text`, `id` and `conversation_id` in its `_Item`, so the model gets the bare text. The Talker doesn't subscribe to `VoiceState` or `VoiceTranscript`; only the temp UI does.
- Its prompt says nothing about spoken input or mishearings.
- **All caps:** this comes from the speech engine. The Streaming Zipformer model (`sherpa-onnx-streaming-zipformer-en-2023-06-26`) was trained on uppercase text with no punctuation, so it writes everything in capitals. `zipformer.py` only strips spaces, `voice_in` passes the text on unchanged, and the chat doesn't change the case.

**Touches:** `src/assistant/modules/talker/module.py` (`_Item`, `_on_input`, the prompt), `tests/test_agents.py`, and the docs [Agents](../../architecture/agents.md) and [Voice](../../../src/assistant/modules/voice_in/docs/voice-service.md).

**Approach:**
1. `_Item` gets a `source` field, which `_on_input` copies from the event.
2. When `source == "voice"`, the Talker puts a short prefix on the text it sends to its session, `[Spoken] ...` (the prompt explains it: mishearings, no punctuation, all caps). The history keeps the same prefix, so the Main Assistant's task context shows it too. Typed input is sent as it is now.
3. One paragraph in the Talker's prompt: spoken messages are marked; read them for what was meant, using the conversation; quietly fix obvious mishearings; ask only when a likely reading changes what you'd do; when you pass spoken work to the Main Assistant, write it in clean words.
4. Tests: a `source="voice"` input reaches the fake session with the prefix; a typed input doesn't.

No extra model call, and nothing changes in `voice_in` or the contracts: the tag is already there.

**Open questions:**
- **Cleaning the case for the display?** The chat would still show the caps. Recommend: leave it for now. The Talker reads it fine, and the Nemotron engine in step 7 writes normal case with punctuation, which may settle it.
- **Should the chat show the Talker's reading?** Recommend: no, not now. The Talker can say "I took that as …" in its reply when it had to guess.
