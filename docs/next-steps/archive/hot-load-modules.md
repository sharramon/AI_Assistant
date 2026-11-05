# Hot-loading of main-app modules

> **Status: done (2026-11-03).** This round: the reload, its trigger, the busy wait, the voice handover and the mic button are built and tested; docs updated; architecture check passed. Loaded at the next relaunch; the first live reload (`RELOAD: voice_in`) worked at 13:19 the same day ([voice text cleanup](../voice-text-cleanup.md)). Later, as live reloads: the Talker, Main Assistant and Hub handovers, and the cross-import test.

**Asked:** "The modules should be able to be hot loaded. Which means code should not matter at all. Make these changes first." The voice side in particular must be editable, stopped and relaunched "without affecting the main chat window".

**Why:** new code in a main-app module (for example `voice_in` or the Talker) only ran after a full app restart. The restart kills the chat and both agent sessions. The [voice-input-to-talker](voice-input-to-talker.md) change is built and is waiting for this.

**Touches:** `core/loader.py` (new), `core/lifecycle.py`, `core/router.py`, `core/app.py`, `contracts/control.py`, `__main__.py`; later small handover hooks in `talker`, `agent_hub`, `main_assistant`, `voice_in`. Reuses runtime module control and `ScopedContext.close()`. Nothing in the [reusable parts index](../../api/reusable.md) reloaded code before.

## Decisions (2026-11-03)

- **Go ahead as written**, with the five doc changes below.
- **Q1:** the Main Assistant may reload modules on its own after its tests pass in Auto mode; in Manual mode it asks you first.
- **Q2:** a reload waits while the Talker is replying or the Main Assistant is mid-task; "reload now" cuts in and cancels.
- **Q3 (changed):** loading a **brand-new module** without a restart is part of the plan (`AddModule`). The one exception is a module that needs a brand-new contract or port type: contracts are shared by every module, so that still needs a restart.
- **Q4:** reloading shared helper code (`infra`) comes later.

## Doc changes (applied 2026-11-03)

| Doc | Was | Now |
|-----|-----|-----|
| [Architecture README](../../architecture/README.md), Summary | "Changing code means a rebuild and restart … Loading new code without a restart is not a goal." | A module's code change, or a new module, needs no restart; core, contracts, shared helpers, and a new contract or port type do. |
| [core.md](../../architecture/core.md#runtime-module-control) | "What needs a restart: adding or changing code." | "Reloading a module" and "What still needs a restart", plus a [Reloading a module's code](../../architecture/core.md#reloading-a-modules-code) section and `Reloading` in the state diagram. |
| [decisions.md](../../architecture/decisions.md#decided) | "Code changes still need a restart." | Reload and add while running (decided 2026-11-03); restart only for core, contracts, shared helpers, a new contract or port type. |
| [principles.md](../../architecture/principles.md), principle 11 | "Code changes may need a restart" | Module code changes and new modules never need a restart; only core, contracts, shared helpers do. |
| [self-improvement](../../agents/self-improvement.md) | "Restart to run new code … never reloads itself." | "Reload to run new code"; restart only for core, contracts, shared helpers. |

Also updated: the [module control API](../../api/control.md) (`ReloadModule`, `AddModule`, `RELOADING`), the [core API](../../api/core.md) (`App` `config_loader`, `LifecycleManager.reload` / `add`, `loader`, `CommandRouter.hold`), and the API index.

## Approach

**One reload = stop, re-import, start**, by the core under its transition lock (built in step 1):

1. **Stop the old instance** as `DeactivateModule` does, and any active module that requires something only it provides. `ScopedContext.close()` removes every handler, subscription and contract.
2. **Re-import its code:** drop the module's package and every submodule from `sys.modules` (and its `__pycache__`), import it fresh, and take the `Module` subclass with the same manifest id.
3. **Check and start** the new class with the same checks as an activation, re-reading its config section first. Start the modules stopped with it again.
4. **If the new code fails** (import error, `init` or `start` raises), the old code is put back and started. The result reports the error.

**`AddModule(package)`** imports a package that wasn't loaded at launch and activates its module. If the code imports a contract the running app doesn't have, it fails with "needs a restart". To keep a new module on the next launch, it also goes into `MODULES` and `modules.enabled`.

**What other modules see:** nothing. Commands sent during the swap wait for the new handler, up to their timeout. Events published meanwhile miss the module. Contracts are looked up at call time (checked: no module caches a provider).

**Running state (steps 2 to 4):** a fresh instance starts empty. Modules that hold live things get an optional handover. The old instance's `export_state()` returns plain data plus `infra` objects (not reloaded, so they stay valid). The new one gets it through `ctx.handover` in `init`.

| Module | Problem | Handling |
|--------|---------|----------|
| Core, contracts, `infra`, `app_kit`, `__main__` | Every module holds their classes | Not reloadable; restart (built: refused with a clear error) |
| `voice_in` | Open mic session; the voice app was launched by the old instance | Handover keeps the `CompanionApp`. The open session ends, and its text goes to the Talker. The chat window isn't touched |
| Talker | A live `claude` session | Handover keeps the running `ClaudeSession`. If it's mid-turn, the reload waits |
| Main Assistant | May be mid-task | Waits until it's idle, or "now" cancels. Handover keeps the `SessionTaskAgent` |
| Agent Hub | Holds every task's state | Handover passes the task records. Refused while a permission answer is pending |
| `temp_ui` | It's the chat window | The page reconnects to the new server; a throwaway, so no extra effort |
| Others | Little state | Plain reload |

**Triggers:** `ReloadModule` / `AddModule` from any module. Next: the Main Assistant after its tests pass (per Q1), later the control panel and the Talker. No file watcher.

## Risks

- **Old code still running:** a thread the old instance didn't stop keeps running old code, muted by its closed context. `stop` must release everything.
- **Module-level state** (globals, caches) is lost on reload.
- **Cross-imports** between modules would leave one on old code. The rules forbid them; a test should enforce it (step 5).
- **Handover across versions:** if the state shape changed, the module starts clean and logs a warning.

## Build plan (small steps, each tested)

1. ~~**Reload in the core:** `ReloadModule`, `AddModule`, `RELOADING`, `core/loader.py`, `LifecycleManager.reload` / `add` with rollback, re-read config, `CommandRouter.hold`, the contract-caching audit.~~ Done 2026-11-03: `tests/test_reload.py` (new code and submodules, broken code keeps old, failing `init` rolls back, config re-read, `AddModule`, new contract → "restart", shared code refused, dependents restarted, held commands). 241 tests pass, ruff clean.
2. **A way to trigger it:** the Main Assistant asks for a reload with a tag the app reads (like SHOW), through the Hub; in Auto it reloads, in Manual it asks you first (Q1). Without this, nothing in the running app can send `ReloadModule` yet.
3. **Handover:** `export_state()` on `Module` (default none) and `ctx.handover`; then `voice_in`, with a test that the chat keeps working through a `voice_in` reload.
4. **Talker, Main Assistant and Hub handover**, with waiting for idle and "reload now" (Q2). Tested against `tests/fake_claude.py`.
5. **Finish:** a cross-import test, docs, a final architecture check.
6. **One relaunch** to load the reloader. After that, module changes (the voice-input-to-talker change first) load with `ReloadModule`.

Steps 2 and 3 change contracts (`Module`, `ModuleContext`) and `infra`, which need a restart. So relaunching after step 4 means one relaunch in total; relaunching now means another one after step 4.

## Where the build stands (handoff, 2026-11-03)

**The user's final choice: option A, plus the mic button.** Before the one relaunch, build: the widened step 2 (the reload trigger, the handover hooks, wait-or-now), the voice module's handover, and the crossed-out mic button. After the relaunch, the first live test edits the voice module and reloads it, with the chat window and Talker staying up. Only a sentence spoken during the swap is lost. The handovers for the Talker, Main Assistant and Hub come later, as live reloads. An extensions manager is out of scope.

**Built and tested** (2026-11-03, second session: 250 pass, ruff clean):
- **Contracts:** `Module.busy()` and `Module.export_state()` (both default None), `ModuleContext.handover` (default None), `ReloadModule.now` (`contracts/module.py`, `contracts/control.py`).
- **Core:**
  - `ScopedContext(..., handover=None)`, and `App._make_context(manifest, handover=None)`.
  - `App` passes `now` and `core.reload_idle_timeout` (default 300).
  - `LifecycleManager.reload(module_id, now, idle_timeout)`: waits on `busy()` via `_wait_idle` (polls every 0.2 s) unless `now`. Before stopping, `_export` calls `export_state()`. `_activate(module_id, chain, handover)` passes the state to the new instance, and on rollback to the old one. A failing hook counts as None (`_ask`).
- **Config** (`config/default.toml`): `core.reload_idle_timeout = 300`, `command_timeouts.ReloadModule = 330`, `AddModule = 60`.
- **Trigger** (`infra/session_agent.py`): a last line `RELOAD: <id> [now]` or `ADD_MODULE: <package>` (`_code_request`, `_ask_to_load`, `_load_code`).
  - In Auto it sends the command at once; in Manual it opens a permission request `{"app_command", "action"}` reported as `PERMISSION`. `answer_permission` and `_permission_expiry` handle that kind.
  - The outcome goes back to the session as `CODE_LOADED` ("[App] …: done. / failed: … Continue the task…").
  - Reloading itself (`main_assistant`) is refused with a message.
- **Main Assistant prompt:** a bullet on `RELOAD:` / `ADD_MODULE:` and on what needs a restart.
- **`busy()`:** Talker "replying to you" (a turn is running); Hub "N task(s) open"; Main Assistant "working on a task". Without a handover these would lose state.
- **`voice_in` handover:** `export_state()` returns `{"app": CompanionApp, "app_key": (SERVICE, host, port, args)}` and sets `_handed_over`. `stop` then skips `self._app.stop()`. `init` reuses the handed-over app if `app_key` matches. An open mic session still ends at `stop`, and its words are dropped.

- **Mic button in `temp_ui`:** the `voice` SSE item has `available`, `why` and `retry`. `temp_ui` follows `voice_in`'s `ModuleStateChanged` (and `ListModules` once in `start`): reloading (kept through its `starting`), off, starting, failed each give a `why`, with no click. A `VoiceState` `failed` with `service_unavailable`/`service_stopped` gives "The voice app isn't running: … Click to try starting it again", with `retry` (still clickable); the next `starting`/`listening` clears it. `page.html`: crossed-out mic (`.mic.off`), disabled unless `retry`, `why` in the title and the grey line.
- **Tests added:** `test_reload.py` (handover to the new code and back on rollback, busy wait with its timeout message, `now`); `test_agents.py` + `fake_claude.py` `RELOADME <id>` (Auto sends at once, Manual allow/deny, self-reload refused); `test_voice_in.py` (a reload with `temp_ui` running: same voice app, fresh code, the chat module untouched, the mic available again and listening); `test_temp_ui.py` (why the mic is unavailable).

**Done (third session):** the docs below, and the architecture check (the `RELOAD:` line reuses `agent_tags.last_line`; no new contract or port; no module caches a provider; the core's state diagram already had `Reloading`).

**Left for later:** Talker, Main Assistant and Hub handovers (build plan step 4), the cross-import test (step 5).

**Was next, now done:**
1. **Docs:**
   - `temp_ui`'s module docstring: the `available`/`why`/`retry` fields.
   - `docs/api/modules.md`: `busy`, `export_state`, `ctx.handover`.
   - `docs/api/control.md`: `ReloadModule.now`.
   - `docs/architecture/core.md` *Reloading* section: replace the "Step 1 built" box, and cover the busy wait, handover and trigger.
   - `docs/agents/runtime.md` / `agents.md`: the RELOAD line.
   - `docs/architecture/voice.md`: the handover and the mic button.
   - `docs/api/reusable.md`: Used by lines for `ReloadModule`, if listed.
   - Then this note's build plan, the Pending changes row, and the rebuild (`scripts/build_docs.py`).
2. **Architecture check**, then report and ask the user about the relaunch (inside the NEED text). Worth noting there: reloading the Agent Hub from inside a task always waits out its timeout (its own task is open), and the Main Assistant stays "working" while a Manual reload request waits for an answer.
