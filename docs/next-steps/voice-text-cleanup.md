# Voice text cleanup (sentence case), then a hot-swap test

> **Status: built (waiting on you), 2026-11-03.** Approved with these answers: raw text in the log only; an end mark on short finals too; **one end mark per final, no commas, no sentence splitting: `?` if the first word is a question word (what, how, why, can, could, do, does, is, are, will, would, should and similar), `.` otherwise** (this replaces rule 2 below: only the first letter is capitalized); the starter terms only (`Claude` dropped). Local only, no paid or cloud service. Built: `voice_in/cleanup.py` (`clean_text`, `QUESTION_WORDS`), 284 tests pass, ruff clean. **Reload test (2026-11-03 13:19:11):** `RELOAD: voice_in` succeeded, the first live reload in the real app. The log says "Kept the running voice service from before the reload", "Activated voice_in", "Reloaded voice_in", with no warnings or errors, and the other modules weren't touched. No mic session had run in this launch before the swap, so the voice app probably hadn't been launched yet: what was handed over was the launcher, not a running process. Left for the user: the mic button during and after the swap, the first spoken sentence in sentence case, and a second reload after a mic session (to see a running voice app reused).

**Asked:** "Go from cheaper => expensive. After the cheaper fix is in, let's try hot swapping, just to see if it works." The cheap fix: the voice text arrives in ALL CAPS from the Zipformer (int8, `config/voice_service.toml`); make the live line and the final text normal sentence case with simple rules.

**Why:** all-caps text is hard to read in the live line and the chat. This fixes only the casing. Misheard words need the later steps (a second-pass recognizer, the engine comparison), which aren't part of this change.

**Touches:**
- `src/assistant/modules/voice_in/cleanup.py` (new): one pure function, `clean_text(raw, terms, final)`.
- `src/assistant/modules/voice_in/module.py`: clean every `Partial` and the `Final` before publishing; log the raw and the cleaned text of each final.
- `config/default.toml`, `[modules.voice_in]`: `cleanup = true` and a `terms` list. Your own terms go in `config/local.toml` (the usual local override).
- Tests: `tests/test_voice_text_cleanup.py` (the rules), plus one case in `tests/test_voice_in.py` (the module publishes cleaned text).
- Docs: `docs/architecture/voice.md` (the `voice_in` section), `docs/api/messaging.md` (`VoiceTranscript`: the text is cleaned).

**Where it lives: the `voice_in` module, not the voice service.** Casing is presentation of the text, not recognition, so it sits fine in the thin module. The service keeps sending the engine's raw text, which is what an engine comparison should measure. And a change in `voice_in` reloads in place (`RELOAD: voice_in`), so the running voice app is kept and nothing needs a restart. That makes it a real hot-swap test.

**Approach:**
- The rules, in order:
  1. Lowercase everything.
  2. Capitalize the first letter of each sentence (the start, and after `.`, `?`, `!`). The Zipformer outputs no punctuation, so today that's just the first letter.
  3. Capitalize the standalone word `i` and `i'm`, `i'll`, `i've`, `i'd` → `I`, `I'm`, `I'll`, `I've`, `I'd`.
  4. Put back the terms from config, matched as whole words or phrases, ignoring case, longest first: `isaac sim` → `Isaac Sim`, `usd` → `USD`.
  5. Final text only: add a `.` if it doesn't end with `.`, `?` or `!`. The live line gets no period, since it is still growing.
- Default terms: `Isaac Sim`, `USD`, `glTF`, `Unity`, `Unitree`, `Zipformer`, `Claude`. A term the engine never spells right (it hears "where house") isn't fixed by this; that's the second pass's job.
- The raw text is kept in the log: one line per final, `raw: "I WANT TO ..." → clean: "I want to ..."`. Not as a field on `VoiceTranscript`: a new field changes a contract, and that needs an app restart, which would spoil the hot-swap test.
- The Talker gets the cleaned text (`InputReceived(source="voice")`), still marked as spoken.
- No new shared helper: `clean_text` is used only by `voice_in`. If the second pass later needs it inside the voice service, it moves to a shared place and goes into the reusable parts index then.

**Then the hot-swap test:** after the tests and ruff pass, the worker ends with `RELOAD: voice_in`. In Manual you're asked first. Check that the chat window and the Talker stay up, the mic button shows crossed out during the swap and works again after it, that the log says "Kept the running voice service from before the reload", and that the next spoken sentence comes out in sentence case. I'll report exactly what happened, including any failure.

**Open questions:**
1. Raw text in the log only, or also a `raw` field on `VoiceTranscript` (needs a restart)? **Recommend: log only for now;** add the field with the comparison script in step 7, where a restart is fine.
2. Add a period to the final text even when it's one or two words ("yes" → "Yes.")? **Recommend: yes,** to keep the rule simple.
3. Any terms to add to the default list?
