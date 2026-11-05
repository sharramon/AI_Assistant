# Archive

Finished change notes: done, with nothing waiting on you. They stay as a record of what was asked, decided and built; the design itself lives in the permanent docs. Active notes are on the [Next steps](../README.md#pending-changes) page.

Archived 2026-11-04.

| Change | Date | What it did |
|--------|------|-------------|
| [Logs button](logs-button.md) | 2026-10-26 | A Logs button opens the launch's log folder in Explorer. |
| [Logs per session](session-logs.md) | 2026-10-26 | One log folder per launch, named by start time and a theme of the first question. |
| [No logs until the first message](logs-after-first-message.md) | 2026-10-26 | No log folder until the first message and its theme exist. |
| [Permission requests in the app](permission-requests.md) | 2026-10-26 | The worker asks you in the app (buttons or the Talker); allow once, deny after 10 minutes. |
| [Permission requests on the Talker side](permission-on-talker-side.md) | 2026-10-26 | The worker's permission requests show on the Talker's side, not the worker's. |
| [Relaunch opens one fresh window](relaunch-keeps-window.md) | 2026-10-26 | A relaunch closes the old window and opens exactly one new one, on its own Edge profile. |
| [Worker gets full access](worker-access.md) | 2026-10-26 | The Main Assistant reads all the docs and edits every file, like Claude Code. |
| [Base HTML viewer](base-html-viewer.md) | 2026-10-27 | View and edit HTML in tabs, with undo; chat-opened HTML goes to the viewer. |
| [HTML viewer as its own app](viewer-own-app.md) | 2026-10-27 | The viewer is its own app, launched by the main app, with two-way hooks. |
| [Highlight for viewer](highlight-for-viewer.md) | 2026-10-27 | The AI opens a page in the viewer and highlights the part it means. |
| [Leaner worker: smaller contexts, fewer calls](leaner-worker.md) | 2026-10-27 | A fresh worker session per task, handoffs, a debugger subagent, peeks without interrupts. |
| [Snip for viewer](snip-for-viewer.md) | 2026-10-27 | Snip part of a viewer page; the image goes to the Talker. |
| [Blue highlight in the HTML viewer](blue-highlight.md) | 2026-10-28 | The viewer's highlight is blue, readable in the dark theme. |
| [Open in viewer brings the viewer to the front](viewer-to-front.md) | 2026-10-28 | Opening a page brings the viewer window to the front. |
| [Usage meters: context now and usage so far](usage-meters.md) | 2026-10-28 | Context size now and tokens and ~$ so far, for the Talker and the worker. |
| [Permission mode button (Manual / Auto)](permission-mode-button.md) | 2026-11-02 | A button switches the Main Assistant between Manual and Auto; `git push` stays blocked. |
| [Permissions stand-in (`ctx.permissions`)](permissions-stand-in.md) | 2026-11-02 | `ctx.permissions` with `has` and `request`: allows and logs until the real handler exists. |
| [Reusable parts as a core principle](reusable-parts.md) | 2026-11-02 | Principle 13, `app_kit`, `agent_tags` and the `ctx.permissions` stand-in; the voice build carries on in voice in. |
| [Handoff: voice layers and whisper](handoff-1c0ac7ff.md) | 2026-11-03 | The build handoff for the voice layers and whisper; finished. |
| [Handoff: voice two passes](handoff-voice-two-pass.md) | 2026-11-03 | The build handoff for the two passes; finished. |
| [Hot-loading of main-app modules](hot-load-modules.md) | 2026-11-03 | Reload a module's code while the app runs (`RELOAD:`), with the busy wait and the voice handover. |
| [Mic clear button](mic-clear-button.md) | 2026-11-03 | The ✕ throws away what the mic heard, sends nothing, and keeps listening. |
| [Restart with reset instructions](restart.md) | 2026-11-03 | A restart closes and reopens the app, with the worker's reset instructions as the first input. |
| [Spoken input reaches the Talker marked as spoken](voice-input-to-talker.md) | 2026-11-03 | Voice input reaches the Talker prefixed `[Spoken]`. |
| [Voice in: contracts (step 1)](voice-contracts.md) | 2026-11-03 | The voice commands, events and the service protocol's messages. |
| [Voice in: the temp UI's mic button (step 4)](voice-temp-ui.md) | 2026-11-03 | The temp UI's mic button and live-text line. |
| [Voice in: the voice service app (step 2)](voice-service.md) | 2026-11-03 | The `voice_service` app with the mic and the Zipformer engine. |
| [Voice in: the voice_in module (step 3)](voice-in-module.md) | 2026-11-03 | The thin `voice_in` module, with the mic-drop wait and the health check. |
| [Worker batching reminder](worker-batching-reminder.md) | 2026-11-03 | The worker is reminded when it edits a file it already edited in the task. |
| [Worker context reminder at 150k](worker-context-reminder.md) | 2026-11-03 | Past 150k the worker is reminded to find a reset point and hand off. |
