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

Changes you asked for, each with a note written before anything is built ([`app-update`](../../.claude/skills/app-update/SKILL.md) skill). Statuses: **proposed** · **approved** · **building** · **built (waiting on you)** (a restart or your check is left) · **done**. A note that is done with nothing waiting on you moves to the [archive](archive/README.md).

| Change | Status | Date |
|--------|--------|------|
| [Module folders: the checklist (what, why, how, and each item's check)](module-folders-checklist.md) | building (overnight, 2026-11-13): 14 of 20 done; each item marked done only after its check against the code; the morning report goes at the top of the page | 2026-11-13 |
| [Module folders: what was promised, what was done, why it was called done](module-folders-audit.md) | findings: of the 14 items in the [module-folders plan](module-folders.html), docs done, 2 partly, 11 not done; neither agent's workspace moved; the plan was never started as a build, only a docs move was reported done, with no open list; ten safeguards proposed, waiting on you | 2026-11-13 |
| [An agent in Auto gets no permission cards: one check at the gate](auto-skips-cards.md) | proposed: why Auto still shows cards (the core handler never reads the mode; the smoke test's cards were Manual ones), every place a card is raised, and one check in the handler's `_open`; four decisions waiting on you | 2026-11-13 |
| [Job ↔ cv: module-to-module through named events](job-cv-finish-event.md) | fake-job check run 2026-11-12: the event path works (2.1–2.4 pass, 2.5 fail on a Hub race). Fixes for the race and the `section_order` case are on disk but **not verified** (suite stopped mid-run). Next, on your go: tests, restart, smoke test 4, the lost-events gap, the design-notes skill. The job agent calls `cv.task`; cv publishes `cv.job_finished` and `cv.job_submitted`; job_search wakes its agent; one path only | 2026-11-12 |
| [Job ↔ cv through tools and the Hub's child-result message](job-cv-result-via-tools.md) | replaced by [job-cv-finish-event](job-cv-finish-event.md): its result path (`parent_note`, the brief quote) is removed; `cv.read_result task_id` kept | 2026-11-12 |
| [Named module events: any module raises and hears custom events, reload only](named-module-events.md) | built: `ModuleEvent(name, source, data)`, `ctx.publish_named / subscribe_named / unsubscribe`; the way modules talk to each other (cv → job_search, [job-cv-finish-event](job-cv-finish-event.md)) | 2026-11-12 |
| ["You" means the Talker and its worker together](you-means-the-pair.md) | built (waiting on you): `RELOAD: talker`, then ask a tab "can you look over the files" and check it hands the work over | 2026-11-10 |
| [Agents talk to each other freely, and a question never makes an agent busy](agent-talk-and-questions.md) | built (waiting on you): hand checks 1 and 4 passed; 2 failed, then passed when redone with the fix in [cv-submit-delivers](cv-submit-delivers.md); cv_agent's repo write grants revoked ([handoff](handoff-3720fc90.md)) | 2026-11-10 |
| [The Submit reaches the job agent by itself, and is never refused](cv-submit-delivers.md) | done: hand check passed 2026-11-10 (delivered by itself, once, with PDF and score); the small-text warning is covered by its automated test only | 2026-11-10 |
| [cv_agent hears about the Submit, without being woken; the font floor back to 9 pt](cv-submit-notice.md) | built (waiting on you): one `AgentNotice` line for cv_agent's next turn when the watch delivers a Submit; 9 pt, a warning only; follow-up 1 as design A (cv_agent ends with status `"ready"` before your Submit, no NEED, no `cv.tool_result`). Waits on `RELOAD: cv`, then tested on your next real job | 2026-11-10 |
| [The "Send JD and CV to Rezi" click reaches cv_agent](cv-rezi-click-signal.md) | parked: the user will ask for it after the current job application; fix agreed (publish `rezi_request`, the cv watcher delivers it to cv_agent as your yes), nothing built | 2026-11-10 |
| [The Hub's folder check skips the starting task](hub-folder-check-parent.md) | cancelled, never built: replaced by agent-talk-and-questions | 2026-11-09 |
| [Permissions handler](permissions-handler.md) | proposed; its first piece (access lists, in the core) is built by agent-permissions | 2026-10-26 |
| [Viewer edits write back to the Markdown](markdown-write-back.md) | built (waiting on you): not yet tried by hand in the real window | 2026-10-27 |
| [Voice in](voice-in.md) | building; design moved to [Voice](../../src/assistant/modules/voice_in/docs/voice-service.md) | 2026-10-28 |
| [Handoff question stops repeating](handoff-repeat-fix.md) | built (waiting on you): app restart (infra) and job_search reload left | 2026-11-08 |
| [cv module: PDF in, PDF out](cv-pdf-only.md) | built (waiting on you): a `cv` reload, and your yes for the job agent's 3 files | 2026-11-09 |
| [Handoff: CV Tool as the cv module's UI](handoff-b31b8901.md) | superseded by handoff-2389decf | 2026-11-09 |
| [cv module: the CV Tool is its UI](cv-uses-cv-tool.md) | built (waiting on you): live since the cv reload; the later fixes (Internal items, truth check, sign-in prompt) load with this restart; ExampleCorp First Draft waits for your review | 2026-11-09 |
| [cv agent: everything in one folder](cv-agent-folders.md) | built (waiting on you): `C:\Chang\Jobs\CV_Module` is cv_agent's workspace (copies; the originals stay until you say) | 2026-11-09 |
| [Handoff: cv one folder + CV Tool build](handoff-2389decf.md) | built (waiting on the restart): the stale-task Hub fix, `cv.tool_draft`, `cv.tool_internal_round`, the truth check, the sign-in prompt; then the hand checks in its last section | 2026-11-09 |
| [cv path: only cv.task for the job agent, a return address that survives a relaunch](cv-path-hardening.md) | built: part 1 (caller checks, `start_only_by`, the coordinator hand-off, the archive) and part 2 (`reply_to`, cleanup, round cap); loaded by the app restart; the four hand checks in its Build status are due | 2026-11-09 |
| [The cv module at a glance](cv-module-flow.md) | built (waiting on you): merged into the cv module's overview page; kept until you say it can go | 2026-11-09 |
| [Voice in: code design](voice-in.md#code-design-2026-11-02) | building: phase 1 steps 1 to 4 built, step 6's code built; your mic check left, step 7 next | 2026-11-02 |
| [Handoff: voice in](handoff-voice-in.md) | building: where the voice-in build stands | 2026-11-03 |
| [Voice streamer: reusable parts](voice-reusable-parts.md) | built (waiting on you): steps 0 to 4 built; the try on your mic is left | 2026-11-02 |
| [Voice text cleanup (sentence case), then a hot-swap test](voice-text-cleanup.md) | built (waiting on you): `RELOAD: voice_in` worked; your mic checks left | 2026-11-03 |
| [Voice: the layers in code, and whisper as a second engine](voice-layers-whisper.md) | built (waiting on you): loaded; your check: switch `[engine] name` to whisper | 2026-11-03 |
| [Voice: two passes (live text while you talk, whisper cleans it piece by piece)](voice-two-pass.md) | built (waiting on you): real check passed, loaded; your check (step 3.5) | 2026-11-03 |
| [Module shape: directory, menus, and clean boundaries](module-shape-refactor.md) | superseded by the module system note below; kept for its docs table | 2026-11-04 |
| [Module system: one interface, a directory, menus everywhere](module-system.md) | built (waiting on you): restart test run; the mic checks (7, 8) and the `agent_hub` / `main_assistant` reloads are left | 2026-11-05 |
| [Voice notes: a quick record-to-page module](voice-notes.md) | built (waiting on you): v1, own module, second press wins; your mic checks next | 2026-11-04 |
| [Job agent: run the job project from the assistant](job-agent.md) | built (waiting on you): `job_search` module, stub search; access list settled by agent-permissions; the real runner open; restart needed | 2026-11-05 |
| [Opening a page turns the viewer on](viewer-start-on-use.md) | built (waiting on you): app restart, then try SHOW and Open in viewer with the viewer off | 2026-11-05 |
| [Temp UI: paste an image into the chat box](temp-ui-paste-image.md) | built (waiting on you): loaded with `RELOAD`; your paste checks by hand | 2026-11-05 |
| [Multi-agent: several task agents at once](multi-agent.md) | built (waiting on you): chunks 1–7 built (cap: 3 extra agents, from config); app restart, then the checks in the handoff | 2026-11-05 |
| [Task agents ask for their access when turned on](agent-permissions.md) | built (waiting on you): the permissions handler's first piece, in the core; 474 tests pass; app restart, then try the job_search card, Allow, and the rough Grants screen | 2026-11-05 |
| [Usage tallies for all agents](usage-tallies.md) | built (waiting on the restart): totals per agent since launch, a dropdown with sub-agents nested and the Talker as its own row, in its own `usage` module | 2026-11-05 |
| [The Main Assistant's session starts without the module door](door-at-session-start.md) | built (waiting on you): an idle worker restarts once when the door is up; app restart, then rerun the helper launch test | 2026-11-05 |
| [Agent names: ids, named helpers, the duplicate check](agent-names.md) | built (restart pending): the Hub refuses a taken id; helpers launched by name with your yes; `job` → `job_search_agent` | 2026-11-05 |
| [Temp UI: send a snip on its own, show it on the sent message, log every snip step](temp-ui-snip-send.md) | built (waiting on you): app restart, then send a snip alone, with text, spoken, and × one; check the log | 2026-11-05 |
| [Temp UI: a plus button to open your own agent tab](plus-agent-tab.md) | built (waiting on you): `RELOAD: task_agents` and `RELOAD: temp_ui`, then press + and try ×; later `ctx.permissions.is_you` | 2026-11-05 |
| [Rezi: a module for its MCP, the job agent tailoring through it, a PDF viewer](rezi-module.md) | approved, building: replaced by one `cv` module with its worker; its three docs pages are in, chunk 1 (code) next | 2026-11-06 |
| [Agent talkers: every tab a pair, its own Talker and worker](agent-talkers.md) | built (waiting on you): hand checks 1–5 pass; check 6 (closing a tab) failed, fix proposed in the note below | 2026-11-05 |
| [Closing a helper's tab ends its Talker at once; its usage row says "closed"](close-tab-ends-talker.md) | built (waiting on you): reload `task_agents`, `usage`, `temp_ui` (no restart), then redo hand check 6 | 2026-11-06 |
| [Code review: the code against our principles, and a cleanup plan](code-review.md) | built (waiting on you): chunks 1–4 built (voice service safety, principles 18–22 and the code map, small fixes, one SHOW helper); waiting on the batched restart and your pick on chunks 5–8 | 2026-11-08 |
| [Closing the tab you're in moves you to the Main Assistant's tab](closed-tab-moves-focus.md) | built (waiting on you): reload `agent_hub`, `temp_ui` (no restart), then close the tab you're on | 2026-11-06 |
| [Voice text goes to the tab you pressed stop in](voice-to-stop-tab.md) | built, waiting on the restart: the exact version (`StopListening.agent_id`, a contract field); tests pass | 2026-11-06 |
| [A new grant reaches a running agent without off and on](live-agent-grants.md) | built, waiting on the restart: plan B with the recommended answers (live grants, `permissions.request`, snips readable); tests pass | 2026-11-06 |
| [Each agent's own Auto/Manual toggle, shown in the UI](per-agent-mode-toggle.md) | idea, for later; nothing built | 2026-11-06 |
| [The Auto button sets the agent of the tab you're in](per-agent-auto-button.md) | built, waiting on the restart (with the others; a reload of `temp_ui` and `talker` would also do); tests pass | 2026-11-06 |
| [Temp UI: switching tabs lands at the bottom, unless you'd scrolled up](temp-ui-tab-scroll.md) | built (waiting on you): `RELOAD: temp_ui`, then the six hand checks in the note | 2026-11-06 |
| [Self-contained modules, like downloadable extensions](module-self-contained.md) | building: steps 0 to 2 and the standard docs layout built (three required pages: overview, architecture, tools from the menu; HTML in the standard frame); step 3 moved usage, console_io, assistant_view; umbrellas designed, not built | 2026-11-06 |
| [Restarts that keep the agents running](restart-keep-agents.md) | proposed: keep and re-hook by default when harmless, Stop all as the option; three designs, C recommended; waiting on your check | 2026-11-06 |
| [Extensions like a marketplace: what's built, what's missing](extension-marketplace.md) | proposed, answers in: extensions always in their own process, contracts loadable while running (overrides the restart rule), `cv` the pilot, store later; nine steps; waiting on your check | 2026-11-07 |
| [Helpers' context reminder and reset](helper-context-reset.md) | built (waiting on you): reminders reach every pair (checked, tested); the Reset buttons now reset the pair of the tab you're in. `RELOAD: temp_ui` or the batched restart, then the three checks | 2026-11-07 |
| [The restart note says everything the next launch needs](restart-note-complete.md) | built, waiting on the batched restart (a `RELOAD: talker` would also do): the app adds the tabs, agents, modes, open tasks and questions; the worker lists the changes waiting on the restart and their hand checks; tests pass | 2026-11-08 |
| [Temp UI: drag the typing box taller or shorter](temp-ui-box-resize.md) | built, waiting on the batched restart (a `RELOAD: temp_ui` would also do): a drag handle on the box's top edge, one size for every tab, kept after sending; six hand checks | 2026-11-08 |
| [Agents and tasks: only two states, active and idle](two-agent-states.md) | built as part of [agent-talk-and-questions](agent-talk-and-questions.md) (step 3), waiting on the restart | 2026-11-10 |
| [A Chrome agent keeps its tab across a context reset](chrome-tab-after-reset.md) | built, waiting on the restart (2026-11-10 batch): a Chrome agent's handoff compacts the session instead of starting fresh; hand check: a Chrome task past a handoff still reaches its tab | 2026-11-10 |
| [Close an agent's Chrome tabs when it's done with them](chrome-tabs-close.md) | built, waiting on the restart (2026-11-10 batch): the prompt rule plus one close turn at a Chrome task's end; tabs stay on a cancel or failure; hand check: a finished Chrome task leaves only the tabs you should act on | 2026-11-10 |
| [Flash the app's taskbar icon when an agent needs you](taskbar-flash.md) | built, waiting on the restart (2026-11-10 batch): `flash_window` in `app_kit`, called by `temp_ui`; hand check: with the window in the back, a done or failed task, a question and a card each flash it; progress, replies and a cancel don't | 2026-11-10 |
| [Usage: tokens only, clearer labels, two token fixes](usage-tokens-only.md) | built (waiting on you): no ~$ anywhere, labelled context and used, a session id so restarts keep totals, sub-agent tokens from each turn's result, and the temp UI's header following the selected tab's own worker and Talker; one app restart, then the hand checks | 2026-11-07 |

Finished notes (done, nothing waiting on you) are in the [archive](archive/README.md).

## Next: voice in, phase 1

The next thing to build. The design is [Voice](../../src/assistant/modules/voice_in/docs/voice-service.md), with the code-level design (threads, files, config, errors, the `voice_in` manifest and contracts) in its [Code design (phase 1)](../../src/assistant/modules/voice_in/docs/voice-service.md#code-design-phase-1) section, approved 2026-11-02. Follow `app-update` and `architecture-first`. Steps 1 to 4 are built. Step 6 is built: the `check` command and the unplug fixes. What's left of it is you speaking and unplugging a mic. Step 7, the engine comparison, is next. Where the build stands: [handoff](handoff-voice-in.md).

**The first version includes:** the shared `voice_service` app with the recorder, the receiver, and the Streaming Zipformer engine. It also includes the thin `voice_in` module, a mic button and a live-text line in the temp UI, one message to the Talker when the mic turns off, and latency per utterance in the log.

**Left out of it:** Silero VAD (not needed with a button), Ctrl+Space, the "didn't catch that" message, auto-restarting the service, `/ws/audio` for remote recorders, several listeners at once, and Nemotron (step 7).

**Before step 1:** the code steps of [Reusable parts](archive/reusable-parts.md#downstream-effects-in-order) (`app_kit` and the `ctx.permissions` stand-in, both built 2026-11-02), as revised in the [voice streamer note](voice-reusable-parts.md). Step 3 below then uses `CompanionApp` and `ctx.permissions` instead of copying `_ensure_running` and logging its own warning; step 2 uses `app_kit.load_layered`.

**Steps:**
1. ~~**Contracts:** `StartListening`, `StopListening`, `ListeningState`, `VoiceState`, `VoiceTranscript` in `src/assistant/contracts/voice.py`, and the protocol's messages in `src/voice_service/protocol.py`, with entries in the [Messaging API](../api/messaging.md#voice).~~ Done 2026-11-03 ([note](archive/voice-contracts.md)).
2. ~~**`src/voice_service/`** (doesn't import the assistant): the [files and classes](../../src/assistant/modules/voice_in/docs/voice-service.md#the-voice-service-files-and-classes), [threads](../../src/assistant/modules/voice_in/docs/voice-service.md#the-voice-service-threads-and-audio-flow), [config](../../src/assistant/modules/voice_in/docs/voice-service.md#the-voice-service-config) (`config/voice_service.toml`), and [error handling](../../src/assistant/modules/voice_in/docs/voice-service.md#the-voice-service-errors) in the design. FastAPI + Uvicorn on `127.0.0.1:8767`, `/health`, `/quit`, `/ws/listen` per the [protocol](../../src/assistant/modules/voice_in/docs/voice-service.md#the-protocol); `SttEngine` / `SttStream` with `zipformer` and `fake`; `MicSource` and `FakeSource`; the `download` command. Runs alone with `python -m voice_service`.~~ Done 2026-11-03 ([note](archive/voice-service.md)): int8 Zipformer by default, the model downloaded outside the repo, checked on the model's test recordings.
3. ~~**`src/assistant/modules/voice_in/`:** per [the voice_in module](../../src/assistant/modules/voice_in/docs/voice-service.md#the-voice_in-module): launches the service through the shared `CompanionApp`, asks `ctx.permissions.request("microphone", ...)` on each start (the stand-in logs the warning), one WebSocket per mic session using `voice_service.protocol`, handles the two commands, publishes `VoiceState` and `VoiceTranscript`, and sends the final text as `InputReceived(source="voice")`. Off by default; `[modules.voice_in]` in `config/default.toml`, plus `core.command_timeouts.StartListening = 30`.~~ Done 2026-11-03 ([note](archive/voice-in-module.md)), with a wait for a dropped mic in the service (`mic_recovery_seconds`) and a `/health` check before reusing a running service.
4. ~~**`temp_ui`:** the mic button (shows *listening* or *failed*) and a grey live-text line above the input box; `dropped` as a drop symbol with a countdown from the `detail` and the word count of the last partial (added by step 3); `voice_in` in `enabled`.~~ Done 2026-11-03 ([note](archive/voice-temp-ui.md)).
5. ~~**`pyproject.toml`:** an optional `voice` extra (FastAPI, Uvicorn, sherpa-onnx, sounddevice, and `websockets` for `voice_in`'s client).~~ Done with step 2; CI installs it too.
6. **Tests and check:** the service with the `fake` engine and a fake recorder; `voice_in` against the real service app with its fake engine and fake mic (option A; built with step 3). No real mic or model in CI. Run `pytest` and `ruff`, then try it on your mic. That's the first real test of the latency targets. Update the docs (Voice: planned → built, the overview's Parts table, the [runtime](../agents/runtime.md) page) and rebuild.
7. **Next:** a Nemotron Speech Streaming EN 0.6B INT8 engine, and a comparison script on a folder of recordings with reference text (word error rate, latency, CPU per engine).

## Now: self-improvement

The [self-improvement plan](../agents/self-improvement.md): edits on a branch, tests on the new version, merge only when you're satisfied, CI/CD later.

1. ~~**Standing rules:** the Main Assistant reads the whole repo and writes `docs/` and `.claude/skills/`.~~ Done 2026-10-25.
2. ~~**Spike, then permission requests in the app**~~ ([note](archive/permission-requests.md)). Done 2026-10-26.
3. **Branch workflow** for `src/` edits, then CI/CD. Until then the worker edits the repo directly, with the [same access as Claude Code](archive/worker-access.md), and the [permission mode button](archive/permission-mode-button.md) (Manual / Auto, 2026-11-02) decides whether it asks.

**Also open:** the [UI handler](../architecture/decisions.md#open-decisions) design; the temp UI stands in until then. Voice in is next to build ([above](#next-voice-in-phase-1)); voice out after it.

## Testing and CI

- `pytest` runs the unit tests (fast, no `claude`). Tests that run a real `claude` process are marked `@pytest.mark.claude`, skipped by default and in CI; run them locally with `pytest -m claude`.
- Code that wraps `claude` is tested against fakes: a fake process replaying recorded events, a fake `ITaskAgent`.
- `ruff check src tests scripts` lints (config in `pyproject.toml`).
- **CI** (`.github/workflows/ci.yml`), on every push and pull request: tests on Windows and Linux (Python 3.12), then `ruff` and a docs check that fails if `docs/html` or `docs/html-next-steps` wasn't rebuilt after a Markdown change.
- Real `claude` calls stay out of CI: they'd need your login on GitHub's machines. Use an API key as a GitHub secret if that's ever wanted.
- No CD yet: nothing is deployed while it runs on your PC.
