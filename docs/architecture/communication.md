# Communication

How modules talk to each other through the core: the three mechanisms, who may send what, command results, timeouts, and event delivery. The pictures of a tool call, a command and an event through the core, and of the core's six parts, are on [core](core.md#how-modules-talk-through-the-core). Back to the [overview](README.md).

## Mechanisms

| Mechanism | Shape | Use for | Example |
|-----------|-------|---------|---------|
| Tool call | `InvokeTool(name, args)`, a command the core's gate handles | Asking a module to do one of its menu items, from code or from an agent | job_search → `cv.task` |
| Interface (via DI) | Direct call through a shared contract | Querying or driving a capability another module provides | voice_notes → `IVoice.listen` |
| Command | Exactly one handler, returns a typed result, has a timeout, cancellable | An explicit action someone wants done | `DeliverMessage` (the Agent Hub), `ActivateModule` (the core) |
| Event | Zero or more subscribers, no result | Notifying that something happened | `VoiceTranscript`, `cv.job_finished` |

Commands and events are plain data records defined in Contracts, not objects with behavior.

## How modules reach each other

A module never holds a reference to another module. Its only access to the app is the `ModuleContext` the core passes to `init`, which wraps the router, the bus and the DI container, and removes everything the module registered when it stops. Contracts only define shapes (interfaces and message types); the core does the delivery. A module importing or calling another directly is never allowed (`tests/test_boundaries.py` checks it).

- **Tool call:** `await ctx.send(InvokeTool(name="cv.task", args=…))`. The core's gate (`dispatch_tool`) finds the one module whose menu offers the name, at call time, checks the call and asks you first if the item asks ([the gate](core.md#the-ask-first-gate)). Agents call the same items through the core's module door. They find them with the [directory, then menu](modules.md#find-a-module-then-open-its-menu): `ListModules`, then `GetMenu(id)` for that module's `ToolSpec`s (name, description, argument schema). So the orchestrator and the agents need no per-tool code.
- **Interface call:** the module asks DI for a contract (`ctx.get_one(IVoice)`) and calls methods on it directly, getting return values back. This is still direct communication between modules; it's only decoupled from the concrete implementation. Use it deliberately, and only through interfaces defined in Contracts. If no module provides it, the module gets nothing (an empty list or `None`), so it must handle absence. Contract calls don't pass the gate.
- **Command (request/response):** `result = await ctx.send(command, timeout=None)`. The router finds the one module registered as that command's handler, calls it, and returns a typed result ([command results](#command-results)). If no handler is registered, the sender gets `NotAvailable` instead of a crash.
- **Event (one-way):** `ctx.publish(event)`. Every subscriber gets a copy; the publisher gets nothing back. When a reply is needed for long-running work, the event carries a **correlation id**, and the replying module publishes its own event (progress, completed, failed) with the same id.

Choosing between them:

| Need | Use |
|------|-----|
| One of another module's menu items, with a result back | Tool call |
| An answer now, from a capability that may have zero or many providers | Interface |
| Something done by one owner, with a result back | Command |
| Tell whoever cares that something happened | Event |
| Long-running work with progress or a delayed result | A tool call or command to start it, then events with a correlation id |

**Where message types live:** shared commands and events (`InputReceived`, `ResponseReady`, `InvokeTool`, `VoiceTranscript`) are typed classes in Contracts. A **module-owned** event, one only its module defines, is a [`ModuleEvent`](../api/messaging.md#moduleevent) matched by name: `ctx.publish_named` / `ctx.subscribe_named`, no new class and no restart, and either side reloads on its own. Its name starts with the publisher's id and its data is plain JSON. The bus keeps nothing, so a listener that's off misses it. Modules talk to each other this way, and a tool is only for a call out: the job agent calls `cv.task`, cv publishes `cv.job_finished` and `cv.job_submitted`, and job_search hears them and wakes its agent. The HTML viewer's tabs and snips are its named events too (`html_viewer.tabs_changed`, `html_viewer.clip`), heard by the Talker and the temp UI. A typed command is added to Contracts only when one module needs to call another directly.

**Known gap:** job_search reads cv's output by file path, not through a tool or event: the job project's `cv_output` link in `job_paths.json` points into cv's workspace. That goes past the core, so wherever cv's workspace sits, the link has to point there ([modules](modules.md)).

## Who sent it, and what may control

The rules behind these are decisions D3 and D5 in [decisions](decisions.md). Every check below runs in the module's own context (`ScopedContext`, `core/context.py`) before the router delivers.

- **The sender is stamped.** Every command carries `sent_by`: `ctx.send` sets it to the sending module's id, and the router sets `"core"` when it's empty (the core's own sends, the door's). A module can't send as another. `InvokeTool.caller` is always the sending module too, except for the door, which sets the caller its token proved. The field is named `sent_by` because `DeliverMessage.sender` already means the agent a message is from.
- **What is strict, what is loose.** `sends`: a command type not in the manifest is refused (`invalid_arguments`, "must list X in manifest.sends") and logged as an error. `publishes`: a typed event not in the manifest is dropped and logged as an error; `ctx.publish` raises for a hand-built `ModuleEvent` (use `ctx.publish_named`, which stamps the source). `handles` and `provides`: an undeclared one raises. Listening is loose: an undeclared `subscribe`, `subscribe_named`, named publish or contract lookup still works and is logged once, so the manifest gets fixed.
- **Control commands come only from you.** The `CONTROL` table in `context.py` lists the commands only the core and a `you` caller (`[core.permissions] you`, `temp_ui` by default) may send, plus the others each one names:

| Command | Also from |
|---------|-----------|
| `DeactivateModule`, `RemoveModule` | nobody else |
| `AnswerPermission`, `AnswerPermissionRequest` | the relays (`[core.permissions] relays`: the Talker passing on your ALLOW / DENY) |
| `ReloadModule`, `AddModule` | a module that provides `ITaskAgent` (its `RELOAD:` / `ADD_MODULE:` line, after your Allow on its card) |

A refused send gives `Result.failed("... is a control command ...")`. Left out on purpose, with the reason:
- `ActivateModule`: the module's own access card guards its start, and job_search turns cv on.
- `CancelTask`: it goes through the Hub's menu, which checks the caller.
- `SetPermissionMode`: its handler, the core's, lets Auto in only from you or the core, and Manual is always safe.
- `ShutdownRequested`: the strict `sends` check alone, so the core names no add-on.

**Good to know:**
- The core's menu sends its control commands as `core`. So an agent's `modules.off`, `modules.remove`, `modules.reload` or `modules.add` isn't refused by the table; the gate's confirm card stands in for it. `modules.off` without `with_dependents` shows no card.
- The Talker's card answers count as yours, through `relays`. Whether they should is an open decision ([decisions](decisions.md)).

**Events never control.** An event only tells what happened. Anything that makes a part act is a command with one handler: `ShutdownRequested` (the core), `AgentNotice` and `ResetRequested` (the Agent Hub), `ReviewAccessList` (the Hub) and `AddCardNotes` (the core). Why: each has one handler and a known sender, and with no handler the sender gets `not_available` at once instead of a silent drop.

## Chaining modules

One module uses another through these same mechanisms, with no glue code: it listens to the events the other announces (voice_notes listening to `VoiceTranscript`), calls its contract (`IVoice`), or calls its menu items. A shared service serves several users through sessions, each with its own destination, instead of running copies ([modules](modules.md#chaining-modules)).

## Commands

`CommandRouter.send`:
- One handler per command type; registering a second raises `ValueError`.
- Each send runs the handler as its own task and waits up to the timeout: the per-call `timeout`, else `core.command_timeouts.<ClassName>`, else `core.command_timeout`.
- Every outcome becomes a `Result`: no handler → `NotAvailable`; exception → `Failed`; timeout → `TimedOut` (handler cancelled); cancelled → `Cancelled`; a non-`Result` return → `Failed`.
- If the sender is cancelled, the handler is cancelled too.
- While a module is being reloaded (`CommandRouter.hold`), a command with no handler waits for one, up to its timeout, instead of failing at once.

## Command results

Every command returns exactly one of these statuses. They mean different things, especially to an AI agent deciding what to do next:

| Status | Meaning | Typical agent reaction |
|--------|---------|------------------------|
| `Ok` | Succeeded; carries the result payload | Continue |
| `InvalidArguments` | Handler rejected the input; carries what was wrong | Fix the arguments and retry |
| `NotAvailable` | No handler registered, or the module is off ("The X module isn't on …": ask the user, then `modules.on`) | Use another approach or tell the user |
| `Failed` | Handler ran and hit an error; carries the error and `retryable` (whether a retry might help) | Retry if retryable, else report |
| `TimedOut` | No result within the timeout; always `retryable` | Retry, or ask the user whether to wait longer |
| `Cancelled` | Cancelled by the sender, the user, or shutdown | Stop; don't retry automatically |

Handler exceptions never propagate to the sender. The router catches them and returns `Failed`.

## Timeouts and cancellation

- Every command has a timeout: a default from config, overridable per command type or per call. When it expires, the router returns `TimedOut` and cancels the handler.
- Cancellation is cooperative asyncio task cancellation: the handler gets `CancelledError` at its next `await`. In-flight commands are found by id or correlation id and cancelled with `ctx.cancel(correlation_id)`, from the sender, the UI, or shutdown. Handlers that start external processes clean those up themselves; there's no extra machinery for that.
- Handlers for long-running work must check the cancellation signal and stop promptly, or answer at once and report later (the gate's "Asked the user on a card" does this, so the router's timeout never cuts a call waiting for you).
- On shutdown, `App.stop` cancels all in-flight commands (`router.cancel_all()`) before stopping modules.

## Event delivery

`EventBus`:
- `publish` only enqueues and returns at once, so it never blocks the publisher.
- Each subscription has a bounded queue (`core.event_queue_size`) and exactly one worker task, so one slow or failing subscriber can't block the bus or the others. Task count grows with subscriptions, never with traffic.
- When a subscriber's queue is full, the event is dropped for that subscriber and a warning is logged.
- Subscriber exceptions are caught and logged, never passed back to the publisher. A handler is cancelled after `core.event_handler_timeout` seconds and logged. In both cases the worker moves on to the next event. Heavy work belongs in a command or background worker, not inside an event handler.
- Subscribing to a base type receives subclasses too, so subscribing to `Event` receives everything.
- A named subscription (`subscribe_named("cv.job_finished")`, or `"cv.*"`) is a `ModuleEvent` subscription filtered by name.
- Events still queued for a stopped module are dropped, and a stopped module's context drops what it publishes.
