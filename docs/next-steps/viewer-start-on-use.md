# Opening a page turns the viewer on

> **Status: built (waiting on you) (2026-11-05).** Approved with one change (your answer 1: opening a page turns the viewer on even if you turned it off). Tests pass; an **app restart** is left (core and infra changed), then try a SHOW link and the Open in viewer button with the viewer off.

**Asked:** "the opening viewer button actually launches the viewer": opening a page should turn the `html_viewer` module on first if it's off (it no longer starts with the app).

**Why:** with the viewer off, every way of opening a page failed:
- the Talker's `<<SHOW: …>>` and the temp UI's **Open in viewer** button got `No tool named 'viewer.open'` from the core's `dispatch_tool`;
- the Main Assistant's SHOW tags were worse: the `html_viewer` module itself read them from `AgentActivity`, so while it was off nobody read them and they were **silently lost**.

**Touches:** `core/tools.py` (`dispatch_tool`), `core/app.py` (`_start_for_tool`), `infra/session_agent.py` (`SessionTaskAgent`), `html_viewer` module (dropped its `AgentActivity` listener), `main_assistant` manifest (`sends` `InvokeTool`), `config/default.toml` (`start_on_use = true`), `tests/test_start_on_use.py`, `tests/test_html_viewer.py`; docs: [core](../architecture/core.md), [Core host API](../api/core.md#dispatch_tool), [infra API](../api/infra.md#sessiontaskagent), [HTML viewer](../../src/assistant/modules/html_viewer/docs/viewer-app.md), [html_viewer page](../../src/assistant/modules/html_viewer/docs/README.md), [runtime](../agents/runtime.md), [reusable index](../api/reusable.md). **Needs an app restart** (core and infra change).

## Approach

Checked [reusable.md](../api/reusable.md): nothing started a module on demand. The one shared place is the core's `InvokeTool` handler, so every caller gets it without code of its own:

- **Start on use, in `dispatch_tool`.** When no running module offers the tool, the core looks in the menus of the modules that are off (menus are readable without starting a module). If one has it and that module has `start_on_use = true` in its `[modules.<id>]` config, the core turns it on through the same path as `modules.on` / `ActivateModule` (`LifecycleManager.activate`, with what it requires), then calls the tool. Opt-in per module; `html_viewer` is the only one. The setting is your standing yes, so the core menu's "ask first" for `modules.on` doesn't apply.
- **Callers change nothing:** the Talker's SHOW, the temp UI's button, and the agents' `use_item` through the door all send `InvokeTool` already.
- **The Main Assistant's SHOW moved out of the viewer** into `SessionTaskAgent` (which already reads `NEED:` and `HANDOFF:` with `agent_tags`): it sends `viewer.open` / `viewer.highlight` as `InvokeTool`, so it starts the viewer too, and every future task agent gets SHOW for free.
- **Reusable index:** added "Start on use" with its Used by line; `agent_tags`, `SessionTaskAgent` and `AgentActivity` rows updated.

**Rejected:** a helper each caller uses (`invoke_starting(ctx, …)`): the door and future callers could forget it, and it would need `ListModules` + `GetMenu` per call to find the owner, which the core already knows.

## Edge cases

- **The viewer fails to start:** the answer is "The html_viewer module couldn't start: …" (retryable), not "No tool named". The Talker shows it as its status line; the Main Assistant's failure is logged and shown in its activity (`couldn't show …`). No retry loop: the next open tries again.
- **It's already starting** (several SHOW tags at once, or a click during an agent's SHOW): activation is behind the lifecycle's lock, so later calls wait for the first and find it on; one start, every page opens.
- **You turned it off on purpose:** opening a page turns it on again (your answer 1). To keep it off, take `start_on_use` out of its config.

## Decided

1. Opening a page (the button and SHOW links) turns the viewer on even after you turned it off (user, 2026-11-05).
2. Voice notes doesn't get `start_on_use` for now (user, 2026-11-05).
