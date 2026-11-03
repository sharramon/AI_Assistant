# Reusable parts as a core principle

> **Status: approved (2026-11-02).** All four open questions answered ([Decided](#decided)). Permanent docs done; `app_kit` (step 3) and `agent_tags` (step 4) built 2026-11-02. Next: the `ctx.permissions` stand-in (step 5). It revises parts of the approved [voice streamer note](voice-reusable-parts.md) (see [What changes in the voice note](#what-changes-in-the-voice-note)).

**Asked:** "Can you redo the architecture of the app AND this module with this 'reusable parts' idea more core to everything?" Then: "the wider architecture redo first, because it'll have downstream effects."

**Why:** some behavior is already built twice: the Edge window code, the SHOW tag parsing, and the launch-and-call code for an independent app. The voice build would add more copies: another launcher, another layered TOML loader, and its own permission warning. Today nothing says when something should become a shared part, where it goes, or how anyone finds it.

**Touches:** principles, a new architecture page, the overview, the API reference, `assistant.infra`, `assistant.contracts` (Manifest, ModuleContext), `core/context.py`, a new `src/app_kit/` package, `html_viewer` (app and module), `temp_ui`, `talker`, `pyproject.toml`, tests, the `architecture-first` skill, `CLAUDE.md`, and the voice note.

## The rule (new principle 13)

> **Build it once.** When two parts need the same behavior, it becomes one **reusable part**: written once, tested on its own, listed in the API reference, and used by both. A second copy is a bug.

- **When something counts:** a second user exists, or is in an approved note. Or it implements a decided pattern, such as task agents or companion apps. "Might be useful one day" doesn't count; [principle 10](../architecture/principles.md) still holds.
- **What qualifies:** the behavior is the same, not just similar, and it knows nothing about any one module. If it needs a module's specifics, it takes them as parameters.
- **How it's built:** by composition ([principle 12](../architecture/principles.md)). A reusable part is an object or function you compose, never a base class with code in it.
- **Before writing code:** check the catalogue (below). The `architecture-first` skill gets this as an explicit step.

## Where reusable parts live: three places, by who may import them

| Place | Holds | Imports | Who uses it |
|-------|-------|---------|-------------|
| `assistant.contracts` | Interfaces, commands, events (already reusable by definition) | nothing | core, modules |
| `assistant.infra` | Helpers for **modules** of the main app: `ClaudeSession`, `SessionTaskAgent`, `LogSession`, and the new `agent_tags` | contracts, `app_kit` | core, modules |
| **`src/app_kit/`** (new) | Helpers shared by the main app **and** the independent apps: window, layered config, `CompanionApp` | stdlib only | `html_viewer`, `voice_service`, `temp_ui`, thin modules, other apps |

`app_kit` is new because the independent apps can't import `assistant`. Today that rule forces copies (`html_viewer/window.py` duplicates `infra/app_window.py`), and the voice service would add more. `app_kit` is a small package in the same repo, ships with each app that uses it, and never imports `assistant`.

## The catalogue: what becomes, stays, or isn't a reusable part

| Part | Where | Used by | Change |
|------|-------|---------|--------|
| Event Bus as the stream (`ctx.subscribe` / `publish`) | core | everyone; voice text | none. Still no `Streamable` (approved) |
| `ClaudeSession`, `claude_command`, `path_rule`, `session_usage` | `assistant.infra` | Talker, `SessionTaskAgent` | none; listed in the catalogue |
| `SessionTaskAgent` | `assistant.infra` | `main_assistant`, later subagents | none; listed |
| `LogSession`, `LogSink`, `theme_slug` | `assistant.infra` | `__main__`, every transcript | none; listed. The independent apps keep plain stderr/file logging |
| **Edge app window** (`open_app_window`, `close_app_windows`, `raise_window`, optional DevTools port) | `app_kit.window` | `temp_ui`, the viewer app | **merge the two copies**; removes `html_viewer/window.py` and `infra/app_window.py` |
| **Layered TOML config** (`load_layered(base, local)`: a file plus its `.local` override, deep-merged) | `app_kit.config` | `assistant.infra.load_config` (becomes a thin wrapper), `voice_service` | **new**; replaces the voice service's planned own loader |
| **`CompanionApp`** (ping, launch, wait, `call`, `events()` stream reader, quit only if we launched it) | `app_kit.companion` | `html_viewer` module, `voice_in`, other apps launching `voice_service` | **moved** from `assistant.infra` (approved there) to `app_kit`; gains `events()` for the viewer's event-stream relay |
| **Companion app pattern** | architecture page | `html_viewer`, `voice_service` | **written down as a checklist**: own package, `python -m <app>`, no `assistant` import, localhost, a ping answering `{"app": "<name>"}`, a JSON POST quit, a thin module built on `CompanionApp` |
| **Agent tags** (`find_tags(text, names)`, `last_line(text, prefix)` for `NEED:`/`HANDOFF:`, `parse_show`) | `assistant.infra.agent_tags` | Talker, `html_viewer` module, `SessionTaskAgent` | **new**; today the SHOW argument is parsed twice, with different quote handling |
| **`ctx.permissions` stand-in** (`has`, `request`: allow and log a warning) | core (`ScopedContext`), with `Manifest.permissions` / `optional_permissions` | `voice_in` first; every module that asks later | **new now**, per the already decided "no handler running" rule. The [permissions handler](permissions-handler.md) later plugs in behind it without touching the modules |

**Not made into reusable parts (on purpose):**
- **HTTP servers:** the temp UI (raw asyncio), the viewer (stdlib), and voice (FastAPI) each serve differently. The temp UI is throwaway, and the viewer works. **New companion apps use FastAPI, like the voice service;** nothing gets migrated.
- **Agent prompts:** the SHOW instructions appear in both prompts. Modules can't share text without importing each other. This goes away once agents call tools directly.
- **SSE writing** (viewer app, temp UI): only one long-lived user, since the temp UI is throwaway.
- **Viewer events** stay in `contracts/messages.py`. Moving them is churn with no gain.

## How it shows in the docs

- **Principles:** principle 13, as above.
- **New page `docs/architecture/reusable-parts.md`:** the rule, the three places, the catalogue, and the companion app checklist. Linked from the overview's Pages.
- **Overview:** one Parts row, "Reusable parts" (`assistant.contracts`, `assistant.infra`, `src/app_kit/`), linking to the page. The bird's-eye diagram stays as it is.
- **API reference:** a new group **App kit** (`from app_kit import ...`). Every reusable entry gets a **Used by** line, so a part with one user stands out. The window functions move from Infrastructure to App kit.
- **`CLAUDE.md` and `architecture-first`:** "check the catalogue before writing a helper", and after building, "add Used by".

## What changes in the voice note

Its three decisions still hold. What changes:

1. **`CompanionApp`** lives in `app_kit/companion.py`, not `assistant/infra/companion.py`, so other apps can launch `voice_service` with it too.
2. **The voice service's config** uses `app_kit.load_layered`. Its "kept separate on purpose" reason (no `assistant` import) goes away.
3. **The mic check:** `voice_in` declares `optional_permissions=("microphone",)` and calls `ctx.permissions.request(...)` from day one. It doesn't log its own warning anymore; the stand-in does that.
These three changes were approved with this note (2026-11-02) and are folded into the voice note.

## Downstream effects, in order

| # | Step | Touches |
|---|------|---------|
| 1 | ~~**You approve this note** (and the voice note's three changes)~~ Done 2026-11-02 | this note, [voice-reusable-parts](voice-reusable-parts.md), the Pending table |
| 2 | ~~**Permanent docs**~~ Done 2026-11-02, per the revised plan below (prompt pointers move to step 4) | `principles.md` (13), new `reusable-parts.md`, overview Pages and Parts, `decisions.md` (record; viewer decision 8 superseded), `html-viewer.md` (decision 8, window), `voice.md` (CompanionApp, config, mic check), `permissions.md` (stand-in built), `core.md` (module checklist, `ctx.permissions`), API README, `infra.md`, new `api/app_kit.md`, `modules.md` (Manifest, ModuleContext). Then `architecture-first`, `CLAUDE.md`, and a docs rebuild |
| 3 | ~~**Code A: `app_kit`**~~ Done 2026-11-02: window (merging both copies), `load_layered`, `CompanionApp` with `events()`. `temp_ui`, the viewer app, the `html_viewer` module, and `load_config` switched over; 133 tests pass | `src/app_kit/`, `pyproject.toml` (package), new `tests/test_app_kit.py`; `test_html_viewer.py` and `test_temp_ui.py` must still pass |
| 4 | ~~**Code B: `agent_tags`**~~ Done 2026-11-02: `find_tags`, `parse_show`, `last_line`; the Talker, the `html_viewer` module and `SessionTaskAgent` switched over, their own parsers deleted. Quotes: one matching pair removed around a quote (the page's own quote marks stay). Both prompts point at the reusable index. 139 tests pass | `infra/agent_tags.py`, `test_agents.py`, `test_html_viewer.py` |
| 5 | **Code C: the `ctx.permissions` stand-in** | `contracts/module.py`, `core/context.py`, `test_app.py` / a new test; Manifest fields checked in `test_registry.py` |
| 6 | **Voice build**, from the revised voice note | as that note says; [next steps](README.md#next-voice-in-phase-1) steps reordered so steps 3 to 5 come first |
| — | **Unaffected:** [voice-in](voice-in.md) (its design is in `voice.md`). [permissions-handler](permissions-handler.md) stays proposed and gets a line saying `ctx.permissions` already exists. Done notes such as [viewer-own-app](viewer-own-app.md) stay as history. CI is unchanged apart from the docs check |

Each code step is one session ending with `pytest` and `ruff`. Steps 3 to 5 don't depend on each other. Step 6 depends on 3 and 5.

## Open questions

1. **The name `app_kit`?** Recommend `app_kit`: short, and says it serves several apps. (Alternatives: `shared`, `companion_kit`.)
2. **`ctx.permissions` stand-in now, or wait for the full handler?** Recommend now: it's small, already decided in behavior, and it lets `voice_in` be written once.
3. **`agent_tags` in this redo, or later?** Recommend in it: it's a real duplicate with a real difference in behavior, and it's small.
4. **Re-export the moved window functions from `assistant.infra`?** Recommend no: one name per part, and the imports get updated.

## Decided

Approved by you, 2026-11-02, all as recommended:

1. **The new package is `app_kit`** (`src/app_kit/`, standard library only, never imports `assistant`).
2. **The `ctx.permissions` stand-in is built now** (allow and log a warning), so `voice_in` asks for the mic the final way from day one.
3. **`agent_tags` is part of this redo** (Talker, `html_viewer` module, `SessionTaskAgent`).
4. **The moved window functions are not re-exported from `assistant.infra`.** They're imported only from `app_kit.window`; every import gets updated.

The voice note's three changes ([above](#what-changes-in-the-voice-note)) are approved with this note.

## Planned permanent-doc edits (step 2, done 2026-11-02)

> Approved and made 2026-11-02. The agent prompts' pointer to the index (part of item 16) is done in the `agent_tags` code step (step 4), since the prompts are in the module code. Next: code steps 3 to 5, one per session.

One line per file: what changes, and why. Nothing here is edited until you answer. Pages for things not built yet (`app_kit`, `agent_tags`, the stand-in) say **planned** until their code is done.

**Revised 2026-11-02 at your request:** reusable parts are their own clearly marked group in the API reference, every reusable entry carries a visible **Reusable** marker and a **Used by** line, and one compact index lists them all (items 0, 2, 10 to 14, 16).

0. **`api/reusable.md`** (new, the compact index): one line per reusable part (name, kind, purpose, where it lives, used by), sorted by where it lives (contracts, `assistant.infra`, `app_kit`), each name linking to its detail entry. Kept short so the Talker and the Main Assistant can read it in one go. Why: one quick place to check before building anything.
1. **`architecture/principles.md`**: add principle 13, "Build it once". Why: the rule belongs with the others.
2. **`architecture/reusable-parts.md`** (new): the rule, the three places shared code lives and who may import each, what's left out on purpose, the companion-app checklist. It links to the index (item 0) instead of holding its own list. Why: the reasoning lives here, the list lives once.
3. **`architecture/README.md`**: link the new page; add a "Reusable parts" row to Parts; the viewer, Voice and Permissions rows mention `CompanionApp`, `load_layered` and the stand-in. The diagram stays. Why: the overview shows where shared code lives.
4. **`architecture/decisions.md`**: record "Build it once" and `app_kit` (2026-11-02); mark viewer decision 8 (its own window copy) as replaced. Why: keep the decision record current.
5. **`architecture/html-viewer.md`**: decision 8 becomes "one shared window copy in `app_kit.window`"; its module uses `CompanionApp` and `agent_tags`. Why: the two copies merge.
6. **`architecture/voice.md`**: config via `app_kit.load_layered`; `voice_in` uses `CompanionApp` instead of its own launch code; the mic is declared optional and asked through `ctx.permissions` from day one; plus the two approved voice decisions (no stream class, `send_as_input`). Why: the voice build follows the new rule.
7. **`architecture/permissions.md`**: what the stand-in does now (allow everything, log a warning, permission fields in the manifest) and how the real handler plugs in later with no module changes. Why: you approved building it now.
8. **`architecture/core.md`**: the "adding a module" steps gain "check the shared parts first" and "add Used by after"; mention `ctx.permissions` and link the companion-app checklist. Why: this is where people look when adding a module.
9. **`agents/runtime.md`**: window links point to `app_kit` (no more "own copy"); SHOW, NEED and HANDOFF lines are read through `agent_tags`. Why: match the merged code.
10. **`api/README.md`**: a new **Reusable parts** group at the top, marked as such, with its table sorted by where each part lives and a link to the index (item 0); in the other groups' tables, reusable rows carry a **Reusable** marker. New "App kit" group (window functions, `load_layered`, `CompanionApp`); the window functions leave Infrastructure; `agent_tags` joins it; Modules gets the permissions interface. Why: reusable parts stand out and are found first.
11. **`api/app_kit.md`** (new): signatures, parameters, errors, examples; every entry starts with **Reusable · Used by: …**. Why: every API group has a page like this.
12. **`api/infra.md`**: remove the window sections; add `agent_tags`; `load_config` wraps `load_layered`; each reusable entry starts with **Reusable · Used by: …**. Why: each part is listed once (answer 4), and marked.
13. **`api/modules.md`**: the manifest's two permission fields and `ctx.permissions` (`has`, `request`), marked **Reusable · Used by: …**. Why: the new interface modules call.
14. **`api/core.md`**, **`api/messaging.md`**, **`api/agents.md`**: `ScopedContext` builds the stand-in with the module's id; shared contracts and events (such as `AgentActivity`, `InputReceived`) get the **Reusable · Used by** line. Why: the marker is on every reusable entry, wherever it lives.
15. **`api/messaging.md`**: `send_as_input` and `VoiceTranscript` as the public voice output, once the voice contracts are built. Why: from the voice note.
16. **`CLAUDE.md`, the `architecture-first` skill, and the agent prompts' standing rules**: point to the index (`docs/api/reusable.md`): "check it before writing a helper; after building, add the part there and its Used by line". Why: every agent, the Talker included, finds it without searching.
17. **`next-steps/permissions-handler.md`**: one line saying `ctx.permissions` already exists as the stand-in. Why: keeps that note accurate.

Then both HTML outputs are rebuilt.
