# voice_notes: speak into a page of notes

## Purpose

A small page in its own window: Record / Stop, a notes area you can edit, a status line, and Copy. What you say goes only to this page, never to the Talker. v1, built 2026-11-04; off by default (turn it on with the core's `modules.on`, which turns `voice_in` on first if needed).
## Wrapper

| Field | Value |
|-------|-------|
| id | `voice_notes` |
| provides | nothing |
| requires / optional | requires [`IVoice`](../../../../../docs/api/messaging.md#ivoice): turning voice notes on turns `voice_in` on first. Record calls `listen(id, caller)`, Stop `finish(id)`, looked up at each call; if no provider is there for a moment (mid-reload), Record says "voice input is off" |
| permissions | none of its own (the mic is `voice_in`'s) |

## Config

`[modules.voice_notes]`: `port` (8770), `window` (`app`, `browser`, `none`), `host`, `window_profile`.

## Code and tests

- `src/assistant/modules/voice_notes/` (`module.py`, `page.html`)
- `tests/test_voice_notes.py` in this folder (on the [test kit](../../../../../docs/api/testkit.md), and voice_in's test rig for the real voice service)
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
