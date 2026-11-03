---
name: architecture-check
description: Use during and at the end of any multi-chunk build. After each big chunk is done (the chunks planned with the batching skill), and once more before the final report, stop and check what was just built against the philosophy, structure, and flow of the whole app: modularity, reuse, and fit with the main app. The final report gets a short "Architecture check" section.
---

# Architecture Check

`architecture-first` plans a change before the code. This skill checks the code while it's being built, so drift is caught one chunk in, not at the end. The practice worked well in the voice service build (voice input step 2): a check after the main pieces worked, and one at the end.

## When

- **After each big chunk** of a build is done and working (for example: the server and engine run; the module is wired; the docs are written). Not after every edit.
- **Once at the end**, after the last chunk and before ruff, the tests, and the report.

Small one-chunk changes skip the mid-build check but still get the end check.

## Read first

Once per task, not once per check: `docs/architecture/principles.md`, `docs/architecture/reusable-parts.md` (with its companion app checklist), `docs/api/reusable.md`, and the architecture page for the area being built. Re-read only what changed since.

## The three checks

1. **Modularity.**
   - An independent app stays independent: it never imports `assistant`, only `app_kit` and its own libraries. A test enforces it; if the app gained a new subpackage, make sure the test covers it.
   - It still follows the [companion app checklist](../../../docs/architecture/reusable-parts.md#companion-app-checklist).
   - The thin module boundary holds: the module in the main app only launches, calls, and relays; the app's logic stays in the app. Modules don't import each other's internals (principle 3), and nothing module-specific went into the core (principle 4).
2. **Reusability.**
   - Did the chunk write something that already exists in `docs/api/reusable.md`? If so, use the existing part and delete the copy (principle 13: a second copy is a bug).
   - Did it build something that now has a second user, or implements a decided pattern? List it in the index with its **Used by** line, and update the Used by line of every existing part it now uses.
3. **Fit with the main app.**
   - Do the commands, events, and protocol still fit how the main app talks to its parts: commands with one handler and a `Result`, events for notifications, plain serializable data across boundaries (principle 9)?
   - Is it clear how the next step connects: which contract, command, or endpoint it will call, and with what? If you can't say it in a sentence, that's a finding.

## What to do with a finding

- **Small drift** (a missed Used by line, a stray import, a name that breaks the conventions, a doc line that's now wrong): fix it on the spot, in the pending edits for that file (see `batching`: one edit per file).
- **Real drift or a design question** (a principle broken, a boundary that has to move, a change to an approved design or a contract): stop. Report it plainly, or ask with a `NEED:` line, before changing course. Don't quietly redesign.

## In the final report

Add a short **Architecture check** section: when the checks ran, and one line each for **Modularity**, **Reuse**, and **Fit with the main app** saying what was checked and what was found (OK, fixed on the spot, or open). End with any structure choice the user should look at.

```markdown
**Architecture check** (after the server worked, and at the end):
- **Modularity:** OK. `voice_service` imports only `app_kit`, pydantic, and FastAPI; the test scans the whole package.
- **Reuse:** fixed one: added the fake engine to the index with its Used by line.
- **Fit with the main app:** OK. Protocol unchanged; step 3 connects with `CompanionApp("voice_service", ...)` and one WebSocket per mic session.
- **To look at:** the service's parts are documented on the Messaging page, not their own page.
```

## Batching

Follow the [batching](../batching/SKILL.md) skill: a check reads, it doesn't trigger extra edit rounds. Fold its fixes into files not yet edited, or note them for the end.
