# Next steps

What we're working on now. This page changes as the work moves on.

## Where we are

**Decided earlier:**
- **Agent Hub** ([agents](../architecture/agents.md)): one module coordinating a Talker, a Main Assistant, and later subagents. Not an AI, not part of the core, launches nothing.
- **Two terminals for now:** terminal 1 to talk to the Talker, terminal 2 view-only on the Main Assistant. The chat window comes later as nicer UX for the same thing.
- **Modules own their resources** and start expensive things (a `claude` process, a model, a window) lazily.
- [Runtime module control](../architecture/core.md#runtime-module-control) is built (`ListModules`, `ActivateModule`, `DeactivateModule`).
- **Interfaces by inheritance, functionality by composition** ([principle 12](../architecture/principles.md)), with the `I` prefix for `Contract` subclasses only.
- **Subscription terms** (checked): runs on your subscription (personal use, official unmodified `claude` binary). Revisit subscription vs API key when the Hub becomes an always-on service. Sources: [Consumer Terms](https://www.anthropic.com/legal/consumer-terms) §3, [Claude Code legal page](https://code.claude.com/docs/en/legal-and-compliance).

**Done 2026-10-22:**
- **The task-agent design** is written: [agents](../architecture/agents.md#task-agents) and the [Agents API page](../api/agents.md) (planned). `message` = typing into Claude Code while it works (interrupt, quick reply, continue unless you meant stop or pause; the Talker infers which). `cancel` = Esc. Minimal Hub in v1. `AgentInfo` has `busy` and `working`, with `ListAgents` and `AgentStateChanged` for UIs.
- **The spike is done** and confirmed the design: interrupt → reply → continue works, and a session survives a cancel with its memory. Details on the [spike page](../agents/spike.md#findings). The relay script was never built.
- **CI:** GitHub Actions runs the tests on Windows and Linux, `ruff`, and checks that `docs/html` matches the Markdown. See [Testing and CI](#testing-and-ci).

## Done: the two-terminal setup (2026-10-25)

The [Agent runtime](../agents/runtime.md) is built and runs: `.\.venv\Scripts\python -m assistant` starts both `claude` sessions and opens the [temp UI](../agents/runtime.md#temp-ui) (Main Assistant left, Talker right) in its own window. Transcripts of both sessions go to `talker.jsonl` and `main_assistant.jsonl` in the launch's [log folder](../architecture/core.md#logging). Tested end to end (hand off, work, "done" notice, file in `workspace/`) and by `tests/test_agents.py`, which runs against `tests/fake_claude.py`.

**Known issues:**
- **Exit crash with piped stdin:** typing `exit` when stdin is a pipe (not a console) ends with "Fatal Python error … stdin … daemon threads". `console_io`'s stdin thread holds the stdin lock at shutdown. It also happened before the agents were added.
- **Interrupt and NEED untried with the real agents:** the fake-`claude` tests cover them; try a mid-task question, pause, and cancel by hand.
- **The Talker's working directory** is the app's, so it loads this project's `CLAUDE.md`. Set `[modules.talker] cwd` to a neutral folder if that slows it down.
- **The Talker invented facts** (that the worker could read the repo, that it had "granted" access, a permission prompt to approve). Its prompt now lists the facts about the system and forbids going beyond them; watch whether that holds.

## Pending changes

Changes you asked for, each with a note written before anything is built ([`app-update`](../../.claude/skills/app-update/SKILL.md) skill). Statuses: proposed → approved → done (or ready to build).

| Change | Status | Date |
|--------|--------|------|
| [Logs per session](session-logs.md) | done | 2026-10-26 |
| [Permission requests on the Talker side](permission-on-talker-side.md) | done | 2026-10-26 |
| [Permissions handler](permissions-handler.md) | proposed | 2026-10-26 |
| [Worker gets full access](worker-access.md) | done | 2026-10-26 |
| [Permission requests in the app](permission-requests.md) | done | 2026-10-26 |
| [Logs button](logs-button.md) | done | 2026-10-26 |
| [Relaunch opens one fresh window](relaunch-keeps-window.md) | done | 2026-10-26 |
| [No logs until the first message](logs-after-first-message.md) | done | 2026-10-26 |
| [Base HTML viewer](base-html-viewer.md) | done | 2026-10-27 |
| [Viewer edits write back to the Markdown](markdown-write-back.md) | done | 2026-10-27 |
| [Snip for viewer](snip-for-viewer.md) | done | 2026-10-27 |
| [Highlight for viewer](highlight-for-viewer.md) | done | 2026-10-27 |
| [Leaner worker: smaller contexts, fewer calls](leaner-worker.md) | done | 2026-10-27 |
| [Usage meters: context now and usage so far](usage-meters.md) | done | 2026-10-28 |
| [Blue highlight in the HTML viewer](blue-highlight.md) | done | 2026-10-28 |
| [Voice in](voice-in.md) | ready to build; design moved to [Voice](../architecture/voice.md) | 2026-10-28 |
| [Voice in: code design](voice-in.md#code-design-2026-11-02) | approved | 2026-11-02 |
| [Open in viewer brings the viewer to the front](viewer-to-front.md) | done | 2026-10-28 |
| [Voice streamer: reusable parts](voice-reusable-parts.md) | approved; revised by the note below (CompanionApp in `app_kit`, `load_layered`, mic check via `ctx.permissions`) | 2026-11-02 |
| [Reusable parts as a core principle](reusable-parts.md) | approved; permanent docs done; `app_kit` and `agent_tags` built (2026-11-02); permissions stand-in built (2026-11-02); next: the voice build | 2026-11-02 |
| [Permissions stand-in (`ctx.permissions`)](permissions-stand-in.md) | done | 2026-11-02 |
| [Voice in: contracts (step 1)](voice-contracts.md) | done | 2026-11-03 |
| [Voice in: the voice service app (step 2)](voice-service.md) | done | 2026-11-03 |
| [Voice in: the voice_in module (step 3)](voice-in-module.md) | done (with the mic-drop wait and the health check; [handoff](handoff-voice-in.md)) | 2026-11-03 |
| [Voice in: the temp UI's mic button (step 4)](voice-temp-ui.md) | done (approved in advance: full auto) | 2026-11-03 |
| [Permission mode button (Manual / Auto)](permission-mode-button.md) | done (spike passed: `git push` blocked under bypass; button on the Talker side; restart the app to get it) | 2026-11-02 |

## Next: voice in, phase 1

The next thing to build. The design is [Voice](../architecture/voice.md), with the code-level design (threads, files, config, errors, the `voice_in` manifest and contracts) in its [Code design (phase 1)](../architecture/voice.md#code-design-phase-1) section, approved 2026-11-02. Follow `app-update` and `architecture-first`. Steps 1 to 4 are built; your own mic (step 6) is next. Where the build stands: [handoff](handoff-voice-in.md).

**The first version includes:** the shared `voice_service` app with the recorder, the receiver, and the Streaming Zipformer engine. It also includes the thin `voice_in` module, a mic button and a live-text line in the temp UI, one message to the Talker when the mic turns off, and latency per utterance in the log.

**Left out of it:** Silero VAD (not needed with a button), Ctrl+Space, the "didn't catch that" message, auto-restarting the service, `/ws/audio` for remote recorders, several listeners at once, and Nemotron (step 7).

**Before step 1:** the code steps of [Reusable parts](reusable-parts.md#downstream-effects-in-order) (`app_kit` and the `ctx.permissions` stand-in, both built 2026-11-02), as revised in the [voice streamer note](voice-reusable-parts.md). Step 3 below then uses `CompanionApp` and `ctx.permissions` instead of copying `_ensure_running` and logging its own warning; step 2 uses `app_kit.load_layered`.

**Steps:**
1. ~~**Contracts:** `StartListening`, `StopListening`, `ListeningState`, `VoiceState`, `VoiceTranscript` in `src/assistant/contracts/voice.py`, and the protocol's messages in `src/voice_service/protocol.py`, with entries in the [Messaging API](../api/messaging.md#voice).~~ Done 2026-11-03 ([note](voice-contracts.md)).
2. ~~**`src/voice_service/`** (doesn't import the assistant): the [files and classes](../architecture/voice.md#the-voice-service-files-and-classes), [threads](../architecture/voice.md#the-voice-service-threads-and-audio-flow), [config](../architecture/voice.md#the-voice-service-config) (`config/voice_service.toml`), and [error handling](../architecture/voice.md#the-voice-service-errors) in the design. FastAPI + Uvicorn on `127.0.0.1:8767`, `/health`, `/quit`, `/ws/listen` per the [protocol](../architecture/voice.md#the-protocol); `SttEngine` / `SttStream` with `zipformer` and `fake`; `MicSource` and `FakeSource`; the `download` command. Runs alone with `python -m voice_service`.~~ Done 2026-11-03 ([note](voice-service.md)): int8 Zipformer by default, the model downloaded outside the repo, checked on the model's test recordings.
3. ~~**`src/assistant/modules/voice_in/`:** per [the voice_in module](../architecture/voice.md#the-voice_in-module): launches the service through the shared `CompanionApp`, asks `ctx.permissions.request("microphone", ...)` on each start (the stand-in logs the warning), one WebSocket per mic session using `voice_service.protocol`, handles the two commands, publishes `VoiceState` and `VoiceTranscript`, and sends the final text as `InputReceived(source="voice")`. Off by default; `[modules.voice_in]` in `config/default.toml`, plus `core.command_timeouts.StartListening = 30`.~~ Done 2026-11-03 ([note](voice-in-module.md)), with a wait for a dropped mic in the service (`mic_recovery_seconds`) and a `/health` check before reusing a running service.
4. ~~**`temp_ui`:** the mic button (shows *listening* or *failed*) and a grey live-text line above the input box; `dropped` as a drop symbol with a countdown from the `detail` and the word count of the last partial (added by step 3); `voice_in` in `enabled`.~~ Done 2026-11-03 ([note](voice-temp-ui.md)).
5. ~~**`pyproject.toml`:** an optional `voice` extra (FastAPI, Uvicorn, sherpa-onnx, sounddevice, and `websockets` for `voice_in`'s client).~~ Done with step 2; CI installs it too.
6. **Tests and check:** the service with the `fake` engine and a fake recorder; `voice_in` against the real service app with its fake engine and fake mic (option A; built with step 3). No real mic or model in CI. Run `pytest` and `ruff`, then try it on your mic. That's the first real test of the latency targets. Update the docs (Voice: planned → built, the overview's Parts table, the [runtime](../agents/runtime.md) page) and rebuild.
7. **Next:** a Nemotron Speech Streaming EN 0.6B INT8 engine, and a comparison script on a folder of recordings with reference text (word error rate, latency, CPU per engine).

## Now: self-improvement

The [self-improvement plan](../agents/self-improvement.md): edits on a branch, tests on the new version, merge only when you're satisfied, CI/CD later.

1. ~~**Standing rules:** the Main Assistant reads the whole repo and writes `docs/` and `.claude/skills/`.~~ Done 2026-10-25.
2. ~~**Spike, then permission requests in the app**~~ ([note](permission-requests.md)). Done 2026-10-26.
3. **Branch workflow** for `src/` edits, then CI/CD. Until then the worker edits the repo directly, with the [same access as Claude Code](worker-access.md), and the [permission mode button](permission-mode-button.md) (Manual / Auto, 2026-11-02) decides whether it asks.

**Also open:** the [UI handler](../architecture/decisions.md#open-decisions) design; the temp UI stands in until then. Voice in is next to build ([above](#next-voice-in-phase-1)); voice out after it.

## Testing and CI

- `pytest` runs the unit tests (fast, no `claude`). Tests that run a real `claude` process are marked `@pytest.mark.claude`, skipped by default and in CI; run them locally with `pytest -m claude`.
- Code that wraps `claude` is tested against fakes: a fake process replaying recorded events, a fake `ITaskAgent`.
- `ruff check src tests scripts` lints (config in `pyproject.toml`).
- **CI** (`.github/workflows/ci.yml`), on every push and pull request: tests on Windows and Linux (Python 3.12), then `ruff` and a docs check that fails if `docs/html` or `docs/html-next-steps` wasn't rebuilt after a Markdown change.
- Real `claude` calls stay out of CI: they'd need your login on GitHub's machines. Use an API key as a GitHub secret if that's ever wanted.
- No CD yet: nothing is deployed while it runs on your PC.
