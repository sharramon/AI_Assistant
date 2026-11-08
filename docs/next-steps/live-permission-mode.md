# Auto / Manual applies at once

> **Status: built (waiting for the batched restart) (2026-11-08).** Queue item 2. Approved as written, plus your clarification: clicking Auto mid-turn interrupts the agent, takes effect at once, and from then on its permission requests are approved automatically. Nothing reloaded or restarted. It needs an **app restart** (the code is in `assistant.infra` and `assistant.contracts`); a module reload isn't enough. Then the checks below.

**Asked:** the Auto / Manual button should change the running session of the tab you're in right away, not from the next task. Only that tab's agent. Only you switch to Auto.

## What I found

- **Per tab already worked.** The button sends the agent of the tab you pressed it in (`page.html`: `agent = focused()`), and `SetPermissionMode` changes only that agent.
- **Only-you-for-Auto already held.** Only the UI button sends Auto; the Talker can only switch to Manual (`ONLY_YOU_AUTO`). Unchanged.
- **Manual already applied at once** (a live control request to `acceptEdits`).
- **Auto waited for the next task, on purpose.** A running `claude` process can't safely be switched to real Auto (`bypassPermissions`): the `git push` block is a launch flag (`--disallowedTools`) and can't be added live; Claude Code may refuse the live switch; and the prompt, with the risky-step rule, is fixed at launch.

## What was built: live Auto, run by the app

- **Click Auto mid-task:** the process keeps its Manual mode and `SessionTaskAgent` answers its permission requests: every tool allowed with no card (`allowed in Auto: …` in the worker pane), except a PowerShell or Bash command containing `git push`, which is refused ("git push is blocked in Auto").
- **Mid-turn it's interrupted at once** with "The user switched you to Auto mode" and the Auto rules (including the risky-step rule). It answers briefly, then carries on. If it's waiting on you, the rules go with your next message.
- **A card already open** when you click Auto is answered (allowed, or refused for `git push`), and the Hub closes it ("permission allowed (Auto)").
- **Back to Manual:** the app stops answering, so cards come back at once; the rules go with its next message (no interrupt). A process started in real Auto still gets the live switch to `acceptEdits`.
- **Approvals unchanged:** reloads and adds run at once in Auto; `request_approval` still asks.
- **Next task or handoff** starts a real Auto session, as before.
- `PermissionModeChanged.applies` is now `now`; `next_task` only if a live switch to Manual fails.

**Code:** `src/assistant/infra/session_agent.py` (`set_permission_mode`, `_tell_mode`, `_auto_answer`, `_is_git_push`; the rules ride on `_with_feed`), `src/assistant/modules/agent_hub/module.py` (`_set_permission_mode` closes an answered card), docstrings in `src/assistant/contracts/agents.py`. **Tests** (`tests/test_permission_mode.py`): `test_switch_applies_now_idle_and_mid_task`, `test_auto_mid_turn_interrupts_with_the_rules_and_carries_on`, `test_live_auto_answers_requests_but_refuses_git_push_and_manual_asks_again`, `test_auto_closes_an_open_card_and_allows_it`; `tests/fake_claude.py` has a `PUSHPERMIT` case. 641 tests pass, ruff clean. **Docs:** `docs/agents/runtime.md` (Permission mode), `docs/api/infra.md` (`SessionTaskAgent`), `docs/api/agents.md`. No new reusable part.

## Your checks (after the restart)

1. **The core one.** In a tab in Manual, give its agent a task that needs a permission (e.g. "write a file outside your folders"). While it's working (mid-turn), click **Auto**. Its worker pane shows it was interrupted ("The user switched you to Auto mode…"), then it carries on and its tools run with **no cards** (`allowed in Auto: …`). If a card was already open when you clicked, it closes by itself.
2. Only that tab changed: another tab's agent still asks with cards.
3. In the Auto tab, ask it to run `git push`: refused, with no card.
4. Click **Manual** in that tab mid-task: its next tool outside its rules shows a card again.
5. Ask the Talker to switch to Auto: it still refuses ("Only the user can…").
