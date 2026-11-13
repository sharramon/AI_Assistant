# Turning a module off by hand is never refused

**Status:** built (2026-11-13), waiting on you: an **app restart** (the change is in the core, contracts and infra). Follows the [`app-update`](../../.claude/skills/app-update/SKILL.md) process. Your decisions are below; nothing turns on by itself.

## Why

`modules.off cv` used to be refused while job_search was on ("'cv' is required by job_search; deactivate them first"). You asked that turning a module off by hand always works, and that the rule is general, for every module dependency.

## Part 1: the rule (decided 2026-11-13)

1. **A manual off is never refused.** The modules that need the one turned off **stay on**, and the reply names them: "cv is off; job_search needs it and stays on". `with_dependents` stays as an explicit choice and still asks first.
2. **`modules.remove`** is never refused either: it removes the module and leaves its dependents on; the result lists them (`still_on`) and says "Still on, and needing it: …".
3. **Taking a grant back** turns off only that module (`DeactivateModule` without dependents).
4. **A needed module that fails** (at startup or at runtime) no longer stops the modules that need it. `needs` is start order only. A needed id that doesn't exist is still refused by name, and a circle of `needs` is refused. This replaces module-folders decision 13.

The same holds for `requires`: voice_in off leaves voice_notes on, which says "voice input is off" at Record. Not changed: `reload` still stops and restarts the dependents around the swap.

**Code:** `core/lifecycle.py` (`_deactivate`, `remove(module_id)`, the `needs` loop in `_activate`, `_note_missing_needs` at startup), `core/app.py` (`_remove`, `_off_owner`), `core/permissions/handler.py` (`_turn_off`), `core/directory.py` (the `modules.off` and `modules.remove` descriptions), `contracts/control.py` (`DeactivateModule`'s docstring).

## Part 2: a module that's off (decided 2026-11-13; replaces options A, B and C)

**No `start_on_use` for cv, and nothing turns on by itself.** This is general, for every module:

- A call that reaches a module that's off answers `not_available`: "The X module isn't on, so 'tool' can't run. Ask the user whether to turn X on; on their yes, use modules.on with module_id 'X', then call 'tool' again" (`dispatch_tool(..., off_owner=)` and `module_off_text` in `core/tools.py`).
- Every agent's prompt (`BASICS_BLOCK` in `infra/agent_profile.py`, the Main Assistant included) says: tell the user which module is off and ask (a NEED line); never turn it on without their yes; on yes, run `modules.on` itself and carry on.
- **The job agent:** the same, in its `apply-session` skill (step 3). If cv can't be turned on, or you say no, it asks whether to go on with your chosen base PDF untailored.

## Tests

`tests/test_control.py`, `tests/test_directory.py`, `tests/test_module_folders.py` (off leaves the needer on; a needed module that fails doesn't stop the needer, at startup and at `ActivateModule`), `tests/test_remove_module.py` (remove works while needed, `still_on`), voice_notes' test (voice_in off, voice notes stays on and copes), `tests/test_worker_parts.py` (the agent rule and the "isn't on" text).

## Build status (2026-11-13)

**Done:** code, tests, docs, the docs rebuild, the architecture check. Full suite: 924 pass; 1 fails, `test_main_docs_never_link_into_next_steps`, from the Restructuring section's links in `docs/architecture/README.md` (not this change; left alone on your word). ruff clean. You said yes to the restart.

**Left:** after the restart, first the module-folders smoke test (look and report only, agents in Manual so the cards show): the job UI opens; the access cards for cv_agent and job_search_agent come up and you click Allow; the job agent starts and sees its job state; cv's output folder is found at `modules/cv/workspace/out`. Then the hand checks below. Then the row moves to done.

## After the restart (your hand check)

1. `modules.off cv` with job_search on: it works, and the reply says job_search stays on.
2. Ask the job agent for a job's CV with cv off: it asks you whether to turn cv on.
3. `modules.on cv` again: cv comes back and job_search was never turned off.
