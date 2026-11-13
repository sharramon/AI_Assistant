# voice_notes: speak into a page of notes

## Purpose

A small page in its own window: Record / Stop, a notes area you can edit, a status line, and Copy. What you say goes only to this page, never to the Talker. v1, built 2026-11-04; off by default (turn it on with the core's `modules.on`, which turns `voice_in` on first if needed).
## Wrapper

| Field | Value |
|-------|-------|
| id | `voice_notes` |
| provides | nothing |
| requires / optional | requires [`IVoice`](../../../../../docs/api/messaging.md#ivoice). Record calls `listen(id, caller)`, Stop `finish(id)`, looked up at each call; if no provider is there for a moment (mid-reload), Record says "voice input is off" |
| needs | `voice_in` ([`Manifest.needs`](../../../../../docs/api/modules.md#manifest), from its `module.toml`): turning voice notes on turns `voice_in` on first, and `voice_in` can't be turned off while voice notes is on. `requires IVoice` stays: it checks the contract is there, `needs` names the module that brings it |
| packages | none (its page is served with the standard library) |
| permissions | none of its own (the mic is `voice_in`'s) |

## Config

Defaults in `module.toml` in this module's folder, with their comments: `port` (8770), `window` (`app`, `browser`, `none`); `host` (127.0.0.1) and `window_profile` are read too, with their defaults in the code. `[modules.voice_notes]` in the app's config (your `config/local.toml`) only overrides them, key by key ([how a module's config is built](../../../../../docs/api/core.md#app)). `config/default.toml` has no section for it.

## Code and tests

- `src/assistant/modules/voice_notes/` (`module.py`, `page.html`, `module.toml` (defaults, `needs`, `packages`))
- `tests/test_voice_notes.py` in this folder (on the [test kit](../../../../../docs/api/testkit.md), and voice_in's test rig for the real voice service): the page, Record, the second press winning, its config under `module.toml`, `voice_in` turned on first
- `docs/`: this overview, [Architecture](architecture.md), [Tools](tools.md) (generated from its menu), and `docs.toml` (its docs tab and group)
