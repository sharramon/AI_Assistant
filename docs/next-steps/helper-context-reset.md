# Helpers' context reminder and reset

> **Status: built (waiting on you) (2026-11-07).** Approved: build the Reset fix; keep both reminders as reminders (no automatic reset), and make sure the reminder fires on every pair. `RELOAD: temp_ui` (or the batched restart), then the checks below.

**Built (2026-11-07):**
- `reset_target(button, tab, coordinator)` in `temp_ui/module.py` picks the session; `POST /reset` uses it; `page.html` sends `tab: focused()`.
- **Every pair has the reminder (checked, nothing missing):** every worker (`main_assistant`, `job_search`, `cv`, every `task_agents` helper, including a tab opened with +) is built by `ProfileAgent`, which always passes `context_reminder` (150k unless a config sets it); every tab's Talker checks its own context and its worker's on each usage update (`TalkerSession.publish_usage` → `check_size`). No code change was needed there.
- **Tests:** `test_reset_buttons_reset_the_pair_of_the_tab_you_are_in`, `test_reset_post_publishes_for_the_helper_tab` (`tests/test_temp_ui.py`), and `test_a_helper_tabs_talker_is_warned_about_its_own_pair` (`tests/test_agents.py`: a helper tab's Talker is warned about its own context and its worker's, in its own tab). 638 tests pass, ruff clean.

**Asked:** check that every helper pair (its worker and its own Talker, e.g. `cv_agent`, `job_search_agent`) gets the context-size reminder and the reset handoff that the Main Assistant and the main Talker get; fix any pair that doesn't. Evidence: `cv_agent`'s worker at 175k, `job_search_agent`'s Talker at 159k.

## What I found

**The reminder is wired for every agent, and it reaches them.**
- **Workers:** every helper is a `ProfileAgent`, which gives its `SessionTaskAgent` its own `ContextWatch` at `context_reminder` (150k by default). This launch's log shows it working for all of them: `cv` reminded its task 6 times, `job_search` 10, `task_agents` (rezi, helpers) 6, `main_assistant` 3. Each re-arm means the agent handed off to a fresh session and came back under 150k.
- **Talkers:** every tab's Talker session checks its own context and its partner's through the Talker module's `ContextWatch`, keyed by its own id (`talker:<agent>`). `job_search_agent`'s Talker got its own warning at 151k ("Your own (the Talker's) context is at 151k…") and 9 warnings about its worker.

**Why the numbers still went past 150k.** That's how the reminder is built today, not a wiring gap:
- **Worker: a reminder only.** At 150k the task is interrupted with "find a safe point, write a handoff note, end with `HANDOFF:`". The agent picks the point, so it keeps working until then. `cv_agent` was reminded at 165k (one big turn jumped past the line) and was still finishing its step at 175k. Nothing resets it automatically.
- **Talker: a warning only.** The Talker tells you once and offers a reset; nothing happens until you say yes (it then writes `RESET: talker`). `job_search_agent`'s Talker was warned at 151k and kept going to 159k because no reset was asked for.

**The real gap: the Reset buttons in a helper's tab reset the wrong pair.** The temp UI's two Reset buttons send only `"worker"` or `"talker"`, and the server maps those to the Main Assistant and the main Talker, whatever tab you're in. So pressing Reset in `cv_agent`'s tab resets the Main Assistant (mid-task, it hands off) or the main Talker, and `cv_agent`'s pair is untouched. A reset through the Talker (`RESET:` in that tab) works for helpers; only the buttons are wrong.

## The fix

- **`page.html`:** the Reset buttons send the selected tab too: `post("/reset", { agent: "worker" | "talker", tab: focused() })`.
- **`temp_ui/module.py`, `POST /reset`:** `worker` → the tab's agent (`cv_agent`); `talker` → `talker` for the main tab, `talker:<agent>` for a helper's tab. With no `tab`, the main pair as today.
- **Tests:** one for each mapping (main tab, helper tab, no tab).
- **Docs:** `docs/modules/temp_ui.md` (the `/reset` line), the docstring at the top of the module.
- No new helper; nothing in `docs/api/reusable.md` covers this.

**Not changed:** the reminder stays a reminder (the agent picks its safe point) and the Talker's warning stays an offer. Making either reset automatically is your call; say if you want it.

**Restart or reload:** `temp_ui` only, so `RELOAD: temp_ui` is enough; the batched restart loads it too.

## Your checks (after the reload; refresh the window)

1. In `cv_agent`'s tab, press the worker's Reset: the header's Worker number for `cv_agent` drops (mid-task, it writes a handoff first); the Main Assistant's doesn't.
2. In the same tab, press the Talker's Reset: that tab's Talker number drops; the main tab's doesn't.
3. In the Main Assistant's tab, both buttons reset the main pair as before.
