# "You" means the Talker and its worker together

> **Status: built (waiting on you) (2026-11-10).** Approved with the user's wording (naming a side targets it; everything else, "you" or an implicit request, is the pair) and built: `ONE_PAIR` in `talker/prompt.py`, test `tests/test_talker_prompt.py`, a line on the Talker's page. Waits on `RELOAD: talker`, then a hand check: ask a tab "can you look over the files" and see it hand the work over, with no "I can't, but the agent can".

**Asked:** "Whenever I say 'you', I mean the agent/talker pair. I need this to be built into every agent/talker pair moving forward. If I want specifically talker or worker I'll say 'the talker' or 'the worker/agent'. If I say you, I need the default understanding to be 'the pair'."

**Why:** the Talker answers "I can't, but the agent can" and goes round in loops, as if its worker were someone else. Its prompt opens with "You can't do work yourself (no files, no tools)", which sets up that barrier; the line saying "you" means both comes much later, at the end of the rules.

**Touches:** one file, `src/assistant/modules/talker/prompt.py` (`talker_prompt`, the one builder every tab's Talker uses: the main tab and every helper's tab, now and future). Its tests in `src/assistant/modules/talker/tests/` (or `tests/`) get a check that every tab's prompt has the new block and not the old line. Docs: the Talker's page (`docs/modules/talker.md`) and the Talker section of `docs/architecture/agents.md`, one line each. No config, no contract.

**Approach:**
- Rewrite the opening of both heads (`_MAIN_HEAD`, `_HELPER_HEAD`). Instead of "You can't do work yourself", say: "You and {agent} are one assistant to the user. You are its voice; {agent} does the work (files, tools, commands) in the background. Hand work to it with these tags, which the user never sees:".
- Move the "you means the pair" rule from the end of `_RULES` into a new shared block `_ONE_PAIR`, placed right after the head of every tab, and make it stronger:
  - Everything the user says is aimed at the pair: "you", "can you", "do you know", and requests with no "you" at all ("look over the files").
  - When the user names one side explicitly ("the talker", "the worker", "the agent", {agent}'s name, or similar words that pick one side), it means that side alone. Without such a name it's the pair.
  - Never say "I can't, but {agent} can", or tell the user to ask the worker. If {agent} can do it, say "I'll do that" and hand it over with WORK (or LOOK to check on it, ASK for its running task) in the same reply.
  - Speak as one ("I can read my source", "I'll do that").
- Reword "Answer simple things yourself" in `_RULES` to "Answer simple things directly, without a task", so it doesn't read as "you" being only the Talker.
- Nothing else in the prompts says the Talker is separate; the door note ("hand real work to the worker") stays, as it's the Talker's own tool rule.

**Picking it up:** the prompt is set when a Talker's session starts, so a running Talker keeps the old one. It needs `RELOAD: talker`, a Reset of each Talker (`RESET: talker`, or the Reset button on each tab), or an app relaunch.

**Open questions:**
1. How to load it: `RELOAD: talker` (no restart; every tab's Talker restarts with the new prompt, keeping its last few exchanges) or the next app relaunch? **Recommended:** `RELOAD: talker`.
