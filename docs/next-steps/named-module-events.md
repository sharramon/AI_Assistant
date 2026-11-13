# Named module events: any module raises and hears custom events, reload only

> **Status (2026-11-12): built; in use as the way modules talk to each other.** cv publishes `cv.job_finished` and `cv.job_submitted`, and job_search hears them and wakes its agent with a message: [job-cv-finish-event](job-cv-finish-event.md) (built, waiting for the restart and the check).
>
> **First check (2026-11-12):** after the restart, the fake job 2 rerun showed `cv.job_finished` reaching job_search_agent, but only as a background line that woke nobody (an `AgentNotice`); job-cv-finish-event makes it a `DeliverMessage`. Details: [handoff-5eff4e83.md](handoff-5eff4e83.md), session 4. Tests: `tests/test_named_events.py`, `cv/tests/test_reply_delivery.py`. The user approved it with all five recommended answers: own-id names only; no bus queue for missed events; cv's Submit message unchanged; the Hub fix separate (built first, 2026-11-12: a child task's end goes to its parent's agent as a message); (iii) named events only for module-owned events, typed shared events kept.

**Asked (2026-11-12):** after the smoke test, cv_agent's "CV SMOKE OK" never reached the job agent. You expected the job_search module to subscribe to the cv module's events and pass them on to its agent. You asked for subscribing and unsubscribing to be functions any module can use at runtime, and for a generic `ModuleEvent(name, source, data)` with `ctx.publish_named`, `ctx.subscribe_named` and `ctx.unsubscribe`, reusable by every module.

**Why:**
- The Event Bus matches by Python class (`core/bus.py`: `isinstance(event, sub.event_type)`). A publisher and a listener must share one class, so every new event type goes into `assistant.contracts`. That package loads once, so each new type needs an app restart (`core.md`, "What still needs a restart").
- A module can't own its event class either. The listener would have to import the publisher ("no module imports another module", `code-map.md`), and a reload of the publisher makes a new class object, so the listener silently stops matching.
- `ctx.subscribe` already works at any time while a module runs, but there's no way to drop a single subscription: they all go together when the module stops.
- No generic event exists today. `AgentNotice` is addressed to an agent and becomes a background note. `TaskUpdated` is about tasks only.
- This settles the open decision "How general event types are" (`decisions.md`) for module-to-module notices: one general, named event instead of a new type each time.

**Touches:**
- **Contracts (needs the one restart):**
  - `contracts/messages.py`: `ModuleEvent(Event)`.
  - `contracts/module.py`:
    - `ModuleContext.publish_named`, `subscribe_named` and `unsubscribe`.
    - `subscribe` and `subscribe_named` return a `SubscriptionHandle`.
    - `Manifest` gets `publishes_named` and `listens_named` (tuples of names).
- **Core:** `core/context.py` (`ScopedContext`: the three methods, the name checks). The bus itself doesn't change.
- **Modules (reloads, after the restart):** `cv` (raises `cv.job_finished`) and `job_search` (listens, messages its agent). Their tests and docs.
- **Docs:**
  - API pages: `docs/api/modules.md` and `messaging.md`.
  - Architecture pages: `docs/architecture/modules.md`, `communication.md` and `decisions.md` (the open decision moves to decided).
  - The reusable index `docs/api/reusable.md`.
  - The module library generator, so named events show per module.

**Approach:**

1. **The event:** one shared class, added once.
   ```python
   class ModuleEvent(Event):
       name: str            # "<module_id>.<what>", e.g. "cv.job_finished"
       source: str          # the publishing module's id, set by the core (never by the caller)
       data: dict[str, Any] # plain JSON values only: no classes, so nothing breaks on a reload
   ```
2. **On `ctx` (every module):**
   - `ctx.publish_named(name, data)`:
     - The core sets `source` to the module's id.
     - It refuses a name that doesn't start with `<module_id>.`, so a module can't speak for another.
     - It checks that `data` is JSON-safe.
     - It publishes a `ModuleEvent`, returns at once and never waits on listeners, like `publish`.
   - `ctx.subscribe_named(name, handler) -> SubscriptionHandle`:
     - It's a thin filter over a bus subscription to `ModuleEvent`, so only events with that `name` reach the handler.
     - A trailing `.*` (`"cv.*"`) takes every event of one module.
     - It can be called at any time while the module runs, for example only while the job agent has a CV job out.
   - `ctx.unsubscribe(handle)`:
     - It drops one subscription, named or typed. `subscribe` returns a handle too, which is backward compatible because today it returns `None`.
     - Everything a module subscribed to is still dropped at its stop, as now.
   - **Declared like the rest (principle 17):**
     - `Manifest.publishes_named` and `listens_named` list the names.
     - An undeclared one still works and is logged once, the same as `listens` today.
     - The module library lists them.
3. **The one restart:**
   - `ModuleEvent`, the `ctx` methods and the manifest fields are contracts and core, so they need one app restart.
   - After that, any new named event is only a string. A module that raises one, or starts listening, is changed and reloaded, never restarted.
4. **How it reloads afterwards:**
   - Matching is by name, not class, so either side can reload on its own.
   - The publisher's new copy publishes the same name. The listener's new copy subscribes again in `start`, as every module already does.
   - An event published while its listener is off or mid-reload is missed: the bus has no queue or store. That's a gap only where missing one matters, see open question 2.
5. **First use, cv → job_search:**
   ```mermaid
   flowchart LR
       W["cv_agent's task ends<br/>(done · failed)"] -- "TaskUpdated" --> CV["cv module"]
       CV -- "publish_named('cv.job_finished',<br/>{reply_to, task_id, state, cv_result, job_dir, company, role})" --> Bus(("Event Bus"))
       Bus -- "subscribe_named('cv.job_finished')" --> JS["job_search module"]
       JS -- "AgentNotice<br/>(reply_to == its agent)" --> Hub["Agent Hub"]
       Hub -- "a line for its next turn" --> JA["job_search_agent"]
   ```
   - **Changed while building (2026-11-12):** job_search passes the event to its agent as an `AgentNotice` (a background line for its next turn), not a `DeliverMessage`. The Hub fix, built first, already messages the job agent its child task's end, so a second message would wake it twice for the same CV. The paragraph below is the original sketch.
   - **cv** listens to `TaskUpdated` for its own `cv_agent`. When a task ends `done` or `failed`, it reads the job's `job_start.json`: `reply_to` and the folder. With `cv.read_result`'s parser it reads the `CV_RESULT` line, then it publishes `cv.job_finished`.
   - **job_search** subscribes to `cv.job_finished` in `start`. For an event whose `reply_to` is its own agent, it sends a `DeliverMessage`, for example "cv_agent finished the CV for Smoke Test Engineer at Nonexistent Test Co: status ready, … Your Submit message comes separately". The Hub delivers it as it delivers any message: never into a running turn, a new task if the agent is idle. The job agent never waits.
   - The Submit message stays as it is: cv sends it straight to `reply_to` and marks it in `job_start.json`, so it survives relaunches.

**Open questions:**
1. **Name rule:** must a module publish only under its own id (`cv.*`)? **Recommended: yes.** The core enforces it, so a listener knows who spoke.
2. **Missed while off:** should named events be kept for a listener that's off or reloading? **Recommended: no, not in the bus.** A module that must never miss one keeps its own record, the way cv keeps `replied` in `job_start.json`. For `cv.job_finished`, job_search can check `cv.read_result` on its next start if needed.
3. **Move cv's Submit message onto the event too** (`cv.submitted`)? **Recommended: not now.** It works and survives relaunches; revisit once named events have been used for a while.
4. **The Hub fix (a)** (a finished child task sent to its parent's agent) is a separate choice that's still open. It covers every agent; this note covers module-to-module events. They don't conflict.
5. **What `ModuleEvent` is, against the typed events.** Three ways:
   - **(i) Every event becomes a `ModuleEvent`,** and the typed ones are migrated. About 25 typed events live in `assistant.contracts` today (`messages.py`, `agents.py`, `voice.py`, `permissions.py`, `control.py`). The core publishes `ModuleStateChanged` itself, and the Hub, the Talker, temp_ui, voice, the viewer, cv and their tests publish and subscribe to the rest.
     - **What it costs:** every publish and subscribe site and its tests change, plus the module library generator, which reads manifest types.
     - **What it breaks:**
       - pydantic's field checking at publish time, which becomes an unchecked dict;
       - subscriptions by class (a typo is a NameError today, and would become a silently empty subscription);
       - IDE and type-checker help;
       - the docs' rule that events are contracts (`modules.md`, `communication.md`).
     - **What it buys:** nothing for shared events, which already need no restart once they exist.
   - **(ii) A `Contract` interface or base class that typed events inherit:** this doesn't fit.
     - `Contract` is the DI interface type (`container.py`: only `Contract` subclasses in `assistant.contracts` are resolved), not a message type.
     - The events already share a base, `Event`, and the bus matches on it (`isinstance`).
     - A typed event that inherits from anything is still a class that publisher and listener must share, so it still lives in `assistant.contracts` and still needs the restart. That's the very problem this note solves.
   - **(iii) Two kinds, each for its own job:**
     - `ModuleEvent` is the generic named event for **module-owned** events: those only the publishing module defines, which change with its reloads (`cv.job_finished`).
     - **Shared** events stay typed in `assistant.contracts`, as now: those the core or the Hub raise, or that several modules agree on (`TaskUpdated`, `VoiceTranscript`, `PermissionRequested`, …).
     - **Promotion rule:** a named event that becomes widely used, or whose payload needs checking, gets a typed class at the next planned restart, and its listeners move over.
     - `ModuleEvent` is itself one typed `Event`, so the bus, `ctx.subscribe` and the manifests need no new mechanism, only the name filter.

   **Recommended: (iii).** It keeps the checking and the typo-proof subscriptions where most events are, adds no migration, and gives modules reload-only events where they need them.
