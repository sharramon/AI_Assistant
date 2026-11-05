# Voice in

Moved 2026-10-28: the design is now [Voice](../architecture/voice.md) in the architecture docs, and the build plan is under [Next: voice in, phase 1](README.md#next-voice-in-phase-1).

## Code design (2026-11-02)

> **Status: building (2026-11-02).** Approved 2026-11-02; phase 1 is being built (steps 1 to 4 done, step 6 waits on your mic). The additions are approved, except the two-minute cap, which became a silence stop at the user's request: a session stops itself only after 2 minutes with no speech detected (`audio.silence_stop_seconds`, final `ended_by: "silence"`) and stays on while the user talks.

**Asked:** write the missing code-level design for voice in, phase 1, before anything is built.
**Why:** the boundaries and protocol were designed, but not the service's threads, files, config, and error handling, or the `voice_in` manifest and contract fields.
**Touches:** docs only: [Voice](../architecture/voice.md#code-design-phase-1) (new section, small protocol additions) and the build steps in [Next steps](README.md#next-voice-in-phase-1).
**Approach:** one asyncio loop for the network, a mic-callback thread that only queues, and one engine thread per session; `voice_service` split into `server`, `session`, `audio`, `engines/`, `config`, `protocol`, `download`; `voice_in` copies the `html_viewer` launch pattern, with one WebSocket per mic session and no contracts provided or required.
**Decided** (see the design's [For you to check](../architecture/voice.md#for-you-to-check)): the `started` reply and `starting` state, approved; not sending text from a lost mic to the Talker, approved; the two-minute cap, replaced by a stop after 2 minutes of silence; port 8767 and the models folder, approved.
