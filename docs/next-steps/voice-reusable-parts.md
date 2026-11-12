# Voice streamer: reusable parts

> **Status: built (waiting on you), 2026-11-03.** All three open questions approved as recommended ([Decided](#decided)). It adds to the approved [voice code design](../../src/assistant/modules/voice_in/docs/voice-service.md#code-design-phase-1); steps 0 to 4 below are built (2026-11-02 to 11-03). Left: step 5's try on your mic, which is step 6 of [voice in, phase 1](README.md#next-voice-in-phase-1).

> **Revised (2026-11-02):** [Reusable parts as a core principle](archive/reusable-parts.md#decided) is approved, and three points here changed with it (folded in below):
> 1. **Where `CompanionApp` lives:** `app_kit/companion.py`, not `assistant/infra/companion.py`, so other apps can launch `voice_service` too.
> 2. **The voice service's config loader:** `app_kit.load_layered`, not its own TOML loader.
> 3. **How the mic check is done:** `voice_in` declares `optional_permissions=("microphone",)` and calls `ctx.permissions.request(...)`; the stand-in allows and logs the warning.
>
> Build the reusable-parts code steps (`app_kit`, the permissions stand-in) before this note's steps.

**Asked:** "Can you make the voice streamer? … it's just a tool to use as a voice to text with the text being able to be received anywhere … we'll just [use] a subscription model. Should we have a 'streamable' class? Can you look at all the things we'll use for it and see what classes and interfaces we want to actually make into reusable parts?"

**Why:** voice text should reach any module that wants it, with the Talker only the first subscriber, and the parts the voice streamer shares with other features should be built once.

**Touches:** `src/app_kit/` (`CompanionApp`, built by the reusable-parts note), `src/assistant/contracts/voice.py` (as planned, plus one field), `modules/html_viewer` (switches to the helper), the new `voice_service` and `voice_in`. Docs: [Voice](../../src/assistant/modules/voice_in/docs/voice-service.md), App kit API (new, from the reusable-parts note), [Messaging API](../api/messaging.md).

## The "streamable" question: no new class; the Event Bus is the stream

**Recommendation:** don't add a `Streamable` contract or helper. Voice text is an event, `VoiceTranscript`, and any module that wants it calls `ctx.subscribe(VoiceTranscript, ...)`.

- **The bus already does what a stream class would.** `subscribe` and unsubscribe (automatic when a module stops), any number of subscribers, a bounded queue per subscriber, and a failing subscriber can't block the others ([event delivery](../architecture/communication.md#event-delivery)). A `Streamable` would be a second delivery path beside the bus, with its own bugs.
- **Start and stop belong to the source, not the stream.** They're already commands (`StartListening`, `StopListening`) with one owner, `voice_in`. Subscribers only listen.
- **Agent activity proves it.** `AgentActivity` is already a stream on the bus, and terminal 2, the temp UI, and `html_viewer` (for `<<SHOW:>>`) all subscribe to it. Nothing about it needed a stream class.
- **Across processes** (other apps, the Quest) the stream is the service's WebSocket protocol, and later the gateway. A Python class wouldn't help there either.
- **Inside `voice_service`** there's one listener at a time and the audio goes mic → queue → engine. `AudioSource.start(on_chunk)` is a callback, which is all that needs.

**One change so "anywhere" really holds:** in the current design every voice session ends as `InputReceived` to the Talker. Add `send_as_input: bool = True` to `StartListening`. With `False` (say, dictating into a text box later), the text arrives only as `VoiceTranscript(final=True)` for whoever subscribed, and the Talker never sees it. `VoiceTranscript` becomes the public output; `InputReceived` is just the Talker's way in.

## Reusable parts

| Name | Kind | Purpose | Where | New or reused |
|------|------|---------|-------|---------------|
| `EventBus` / `ctx.subscribe` / `ctx.publish` | core | The subscription model for voice text, state, and agent activity | `core/bus.py` | **reused** |
| `InputReceived` | event | Final voice text to the Talker (`source="voice"`) | `contracts/messages.py` | **reused** |
| `StartListening`, `StopListening` | commands | Turn the mic on and off; any UI may send them. `StartListening` gains `send_as_input` | `contracts/voice.py` | new (planned), one new field |
| `VoiceState`, `VoiceTranscript` | events | Button state; live and final text for any subscriber | `contracts/voice.py` | new (planned) |
| **`CompanionApp`** | class (`app_kit` helper) | Launch a local companion app if nothing answers its ping, wait until it's up, call its HTTP API, read its event stream, and on stop quit it (only if we launched it) | `src/app_kit/companion.py` | **new**; replaces the copy in `html_viewer` |
| `load_layered` | function (`app_kit` helper) | The voice service's config: `config/voice_service.toml` plus its `.local` override | `src/app_kit/config.py` | **new** (reusable-parts note); also behind `assistant.infra.load_config` |
| `SttEngine`, `SttStream` | abstract classes | Swappable speech engines: `zipformer`, `fake`, later Nemotron | `voice_service/engines/` | new (planned) |
| `AudioSource` | abstract class | Where audio comes from: `MicSource`, `FakeSource`, later the Quest's `RemoteSource` | `voice_service/audio.py` | new (planned) |
| `ModulePermissions` (`ctx.permissions`) | interface | The mic check: `voice_in` declares `optional_permissions=("microphone",)` and calls `ctx.permissions.request(...)`. Until the [permissions handler](permissions-handler.md) exists, the stand-in allows and logs the warning | `ScopedContext` stand-in (reusable-parts note) | **reused**; the handler later plugs in behind it |
| `ctx.log`, `[modules.voice_in]` config | existing | Logging and config of the thin module | `ModuleContext` | **reused** |

**`CompanionApp`, the one real new reusable part.** `html_viewer` already holds this logic (`_ensure_running`, `_ping`, `_call`, the quit-then-kill in `stop`), and `voice_in` needs exactly the same; it's the decided pattern for every [independent app](../architecture/decisions.md#decided). Sketch:

```python
app = CompanionApp(module="voice_service", host, port, ping="/health",
                   args=[...], start_timeout=20.0, log=ctx.log)
await app.ensure_running()        # ping; else launch `python -m <module> <args>`, poll every 100 ms
info = await app.call("GET", "/health")
await app.stop()                  # POST quit, wait 5 s, kill; only if we launched it
```

It relies on one convention every companion app keeps: its ping answers `{"app": "<name>", ...}`, and it has a POST quit endpoint. The viewer and the voice service already do (`/api/ping`, `/health`).

**Kept separate on purpose:**
- **`voice_in`'s WebSocket session** and the viewer's event-stream relay are specific to each app; nothing worth sharing yet.
- **No `IVoiceInput` contract:** `voice_in` is reached only through commands and events, as designed.

## Build steps

0. **First, from the [reusable-parts note](archive/reusable-parts.md#downstream-effects-in-order):** `app_kit` (`CompanionApp` with its tests, `load_layered`, `html_viewer` switched over) and the `ctx.permissions` stand-in.
1. ~~`CompanionApp` in `assistant.infra`~~ Moved into step 0 (`app_kit`).
2. **Contracts** `contracts/voice.py`, with `send_as_input` on `StartListening`; [Messaging API](../api/messaging.md) entries.
3. **`voice_service`** as in the approved design (steps 2 and 5 of [voice in, phase 1](README.md#next-voice-in-phase-1)), reading its config with `app_kit.load_layered`.
4. **`voice_in`** using `CompanionApp`; asks for the mic with `ctx.permissions.request("microphone")` (no warning of its own); publishes `InputReceived` only when `send_as_input` is true.
5. **`temp_ui`** mic button and live line, then tests, `ruff`, a try on your mic, and the doc updates (Voice: planned → built; `VoiceTranscript` described as the public output any module subscribes to).

## Decided

Approved by you, 2026-11-02:

1. **No `Streamable` class; the Event Bus is the stream.** Voice text is published as `VoiceTranscript`; any module subscribes.
2. **`send_as_input: bool = True` on `StartListening`.** With `False`, the text goes only to `VoiceTranscript` subscribers, not to the Talker. (Not a config flag on `voice_in`, which would be all or nothing.)
3. **`html_viewer` switches to `CompanionApp` in the same change**, so the launch code lives in one place.

**When built,** these move into the permanent docs: decisions 1 and 2 into [Voice](../../src/assistant/modules/voice_in/docs/voice-service.md) (the voice_in module section), `CompanionApp` into the App kit API (per the reusable-parts note), and the `send_as_input` field into the [Messaging API](../api/messaging.md).
