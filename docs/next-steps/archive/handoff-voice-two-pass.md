# Handoff: voice two passes (chunked whisper)

> **Finished (2026-11-03):** config edited (approved), docs updated and rebuilt. Nothing left but the app restart and your check. The restart happened (relaunch 2026-11-03 16:02); your check is tracked in [voice two passes](../voice-two-pass.md).

The build of [voice-two-pass.md](../voice-two-pass.md). The user approved every recommendation (recorded in the note's Open questions; the README row says "approved (all recommendations), in progress"). Runs in Auto. **Ask with `NEED: Risky` before editing `config/voice_service.toml` or any config file.** No commit, no push. The app needs a restart at the end.

## Done

**Chunk 1 (the service): built, tested, architecture-checked (OK).**
- `src/voice_service/config.py`: `[engine] final` (default `"whisper"`), `final_timeout_seconds` (20); `PiecesConfig` (`pause_seconds` 0.7, `min_seconds` 4, `max_seconds` 20, `cut_search_seconds` 3, `prompt_previous` true); `final_engine_name(config)`.
- `pieces.py` (new): `PieceCutter`. `engines/__init__.py`: `SttStream.set_prompt` / `cancel` (no-ops). `engines/whisper.py`: prompt → `initial_prompt`; `cancel` drops the text. **Finding:** faster-whisper decodes a 30 s window at once, so cancel can't cut a piece short (at most 20 s): it only throws the text away; the session doesn't wait for it. The comment says so, and the real-whisper test is now `test_real_whisper_cancel_during_finish_drops_the_text`. The note's section 5 "Cancelling" line must say this in the docs step.
- `protocol.py`: `Started.clean_pieces`, `Cleaned`, `Refining`, `FinalPart`, `Final.parts`. `session.py`: `Piece`, `_Cleaner` (`voice-clean` thread), the cut/finish logic. `server.py`: `final_engine`, second loader, `/health` `final`/`final_ready`/`final_error`. `__main__.py`.
- Check: `voice_service` imports only its own parts and `app_kit`; reuses `rms`, `EngineLoader`; protocol additions default to today's behaviour.

**Chunk 2 (the main app): built, tested, architecture-checked.**
- `contracts/voice.py`: `ListeningState.FINISHING` (between dropped and failed), `VoiceTranscript.settled_chars`.
- `voice_in/line.py` (new): `LiveLine` (`set_live`, `settle`, `segments`), `Segment`, `render(segments, terms, final, cleanup) -> (text, settled_chars)`. Always used, so one-engine mode goes through it too (same output as before).
- `voice_in/cleanup.py`: `clean_text(..., capitalize=True)`: a part that carries on a sentence keeps a small first letter. (Note said "no change"; this one flag is the only change, document it.)
- `voice_in/module.py`: `_Session.clean_pieces`, `.line`; `Cleaned` → settle and publish (warns on fallback); `Refining` → line update, `FINISHING` "cleaning up…"; final parts rendered per part and logged; stop waits `final_timeout_on_send` when `clean_pieces` or no partials.
- `temp_ui/module.py`: `settled` in the voice item, cleared on starting/idle/failed/clear; FINISHING keeps the text. `page.html`: settled start in normal text (`#voice .settled`), rough rest dimmed; finishing: pulsing button (not a real spinner), clicks ignored, ✕ visible, "cleaning up…" after the line.
- Tests: new `tests/test_voice_line.py`; `test_voice_in.py` (`Service` takes `final`, `pieces`; two two-pass tests); `test_temp_ui.py` (settled + finishing); `test_voice_contracts.py` (state values, `settled_chars`, wire dicts with `clean_pieces` / `parts`).
- **Full suite: 341 passed, 1 deselected; ruff clean.**
- Small drift still open: `line.py` copies `_END_MARKS` from `cleanup.py`; change to `from .cleanup import _END_MARKS, clean_text` (one edit), rerun tests.

## Real check: RUN, PASSED (2026-11-03)

`_END_MARKS` drift fixed (line.py imports it). Suite 341 passed, ruff clean. Joined 49.8 s recording, 4 pieces each run, waiting ≤ 1, no fallbacks, 0 doubled words:
- live alone: CPU avg 2.84 / peak 3.25 cores, wait 0.03 to 0.09 s.
- small.en prompt on: avg 3.54 / peak 10.62; lag median 16, max 47 ms; pieces 1.14 to 1.80 s; wait 1.74 s; match 0.977 (only for ever/forever, one comma).
- small.en prompt off: avg 3.49 / peak 10.79; lag median 32, max 63 ms; pieces 1.14 to 1.45 s; wait 1.48 s; match 0.977; text identical to prompt on.
- base.en prompt on: avg 3.11 / peak 10.93; lag max 32 ms; pieces 0.44 to 0.59 s; wait 0.69 s; match 1.000.
- 0.wav / 1.wav (one piece): small.en waits 1.17 to 1.48 s, base.en 0.45 to 0.61 s.
- Prompt: no difference seen, but every cut fell at a sentence end, so its purpose (mid-sentence joins) wasn't tested. Defaults kept. Script kept as a reusable check.

## Next

1. **Real check** (done, above): `scripts/voice_two_pass_check.py` runs the service app in-process (TestClient) with the real models, config overrides in memory only (no config file touched; the code default is already `final = "whisper"`, the toml has no `final`). Recordings: 0.wav, 1.wav and the four joined with 1 s gaps, fed at speech speed. Runs: live engine alone (baseline), small.en prompt on, small.en prompt off, base.en prompt on. Prints CPU avg/peak cores, partial lag vs baseline (median/p95/max), per-piece whisper times, most waiting at a cut, fallbacks, possible doubled words, wait after stop, sent text vs whole-recording whisper (word match ratio). Run it in the background: `.\.venv\Scripts\python scripts\voice_two_pass_check.py` (~6 min; if it errors, hand it to the `debugger` subagent). Pass: partial lag within ~100 ms, at most one piece waiting (`waiting` ≤ 1 counts the new piece), wait after stop under 2 s. Report numbers plainly, including a fail; tune `[pieces]` defaults in code if needed. Decide whether to keep the script (it'd be a reusable check for the engine comparison; then list it in the docs).
2. **`NEED: Risky`** to add `final = "whisper"`, `final_timeout_seconds` and `[pieces]` to `config/voice_service.toml` (check for a `.local` override; `test_config_file_matches_the_built_in_defaults` must still pass).
3. **Docs** per the note's "Docs to update" (voice.md incl. diagrams, messaging.md, api README `ListeningState` line + `PieceCutter`, reusable.md: `SttStream` line gets `set_prompt`/`cancel`; `LiveLine` stays internal unless a second user), overview Parts row, runtime page (temp UI), whisper note pointer line, the note's Results + status, README row. Rebuild with `.\.venv\Scripts\python scripts\build_docs.py`. Final architecture-check, full pytest + ruff.
4. Final report: changed files, test results, measurements, Architecture check section, app restart needed (contract + protocol changes).

## Files edited more than once so far

`voice-two-pass.md`, `protocol.py`, `__main__.py`, `session.py`, `test_voice_pieces.py`, `whisper.py`, `contracts/voice.py`, `voice_in/module.py`, `temp_ui/module.py`, `page.html`, `test_voice_in.py`, `test_voice_contracts.py`. The README row and the note get one more edit each at the end.
