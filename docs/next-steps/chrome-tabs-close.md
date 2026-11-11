# Close an agent's Chrome tabs when it's done with them

> **Status (2026-11-10): built and tested; the user chose 1a (both parts) and 2a (tabs stay on a cancel or a failure).** Follows [chrome-tab-after-reset.md](chrome-tab-after-reset.md) (tabs kept across a handoff). Built in `src/assistant/infra` (`agent_profile.py`: the prompt rule, `CHROME_TAB_TOOLS` allowed with no card; `session_agent.py`: `close_tabs`, `_Mode.CLOSING_TABS`, `CLOSE_TABS`; `profile_agent.py` turns it on for Chrome agents), so it takes effect at the one app restart after all pending fixes. Tests: `tests/test_agents.py` (`test_a_chrome_task_closes_its_tabs_before_it_ends`, `test_no_close_turn_when_it_isnt_needed`, `test_a_message_during_the_close_turn_carries_the_task_on`). Documented in `docs/agents/runtime.md` and `SessionTaskAgent` in `docs/api/infra.md`.

## The problem

An agent with Chrome (the job agent, the cv worker, task agents whose kind has `chrome = true`) opens tabs and never closes them. The app never touches Chrome itself: each agent's `claude` session drives it through the Claude in Chrome tools, and that session has a `tabs_close_mcp` tool it never uses. Its prompt doesn't ask it to. Once the session is replaced (a new task starts a fresh one), its tab group can't be reached by anyone, so the tabs stay until you close them by hand.

## When a tab closes, and when it stays

| Moment | Tabs |
|---|---|
| A page is no longer needed (an ad read, a search done, a form saved) | the agent closes that tab |
| A handoff (`HANDOFF:`, context compacted) | **kept**: the same session carries on with them |
| A question to you (`NEED:`) | **kept**: the answer may need the page |
| A page you're asked to act on (a filled form for you to submit: agents never submit) | **kept**, and the final reply says which tab |
| The task's end (its final reply) | every other tab of the task is closed |
| You cancel a task, a task fails, the app stops or restarts | kept, so you can see where it stopped (see question 2) |

## The change

1. **The rule in the prompt** (the Chrome part of every agent's prompt, `infra/agent_profile.py`): close a tab with `tabs_close_mcp` as soon as you're done with its page; before your final reply, close each tab of yours you don't need any more (`tabs_context_mcp` lists them), except one you tell the user to act on; never close a tab on a handoff or while a question is open.
2. **A check at the task's end** (`SessionTaskAgent`, on only for agents with Chrome, the same switch as the compact handoff): if the task used Chrome tools and its last turn didn't close a tab, the app sends one short turn before reporting the task done: "close the tabs you no longer need, keep the ones the user should act on, reply in one line". The done report keeps the agent's real final text. This catches an agent that forgot the rule, and costs one short turn on those tasks only.
3. Tests for both, and the rule in `docs/agents/runtime.md` and `SessionTaskAgent` in `docs/api/infra.md`.

The handoff path from the earlier fix doesn't change: a compact keeps the session and its tabs, and nothing closes them there.

## The two example.com tabs

They are the earlier spike's tabs (2086284225, 2086284226), each in the tab group of a spike session that has ended. They hold nothing, and nothing in the app uses them, so they're safe to close. No agent can close them, because their sessions are gone: close each group by hand (right-click the group's label, then **Close group**).
