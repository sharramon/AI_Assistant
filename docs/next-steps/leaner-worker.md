# Leaner worker: smaller contexts, fewer calls

> **Status: done (2026-10-27).** Built as below; tests in `tests/test_agents.py`. Checked against the real `claude`: the `PowerShell(<command> *)` rule form lets pytest run without asking, and the `debugger` subagent's permission requests reach the app like the Main Assistant's. Docs: [agent runtime](../agents/runtime.md#fresh-sessions-and-handoffs), [Agents API](../api/agents.md#sessionusage) (the meter event is now `SessionUsage`, see [usage meters](usage-meters.md)). Needs a relaunch to go live.

**Asked:** after one session's token burn (2026-10-27, about $8.40, most of it in one 22-minute turn): "the Talker as the main context, and the main starting new sessions per task", with the docs as the source of truth; "the worker should be able to update docs, create a handoff for itself, and then start up a new worker"; "a subagent per debug"; "what are you doing?" should be "just a peek at the main, not a whole interrupt. Unless I ask for a pause"; give the test and ruff commands up front. Subagents: "let's go the easier route" (Claude Code's built-in ones, not Hub subagents).

**Why:** the logs (`logs/2026-10-27_17-08-42_next-steps-html-viewer/`) show:
- **One task held everything.** The Talker sent four changes (write-back, highlight, viewer as its own app, snip) into one running task with ASK, so the Main Assistant's context grew from 39k to 273k tokens. Every call resends it all.
- **126 calls at about 165k each.** Edits were mostly batched (158 edits in about 50 calls). The rest went on reads one file at a time (35), checks (20), and interrupts.
- **Interrupts cost 2–3 calls each.** The Main answers, the Hub sends "continue", then the Talker's own "Continue. Go ahead…" arrives as another interrupt.
- **The peek was too thin.** "What is going on?" got only the task text, so the follow-up became an interrupt at 266k.
- **A debug loop in the big context.** Three real-Edge bugs fixed one after another (17 calls at about 220k each). It was never delegated: no `Task` call appears in any log.
- **37 permission prompts**, almost all PowerShell, each also costing a Talker turn.

**Touches:** `infra/session_agent.py`, `modules/main_assistant/module.py` (prompt), `modules/talker/module.py` (prompt, status text), `modules/agent_hub/module.py` (recent activity), `config/default.toml`, new `.claude/agents/debugger.md`; docs: `architecture/agents.md`, `agents/runtime.md`, `api/agents.md`, `api/infra.md`.

**Approach:**
1. **One change per task (Talker).** WORK starts a task for each new request; ASK is only for questions, answers and corrections about the running one. A new request while a task runs: the Talker tells you what's running now and what stopping it would leave unfinished, and you choose: wait, pause it, or cancel it. After a reply to ASK the task carries on by itself: no extra "continue".
2. **Fresh session per task (worker).** `SessionTaskAgent.assign` restarts the `claude` session when the last one has been used, so each task starts at the fixed ~31k. The task text points at its change note in `docs/next-steps/`; the docs, not the chat, carry the decisions.
3. **Self-handoff (worker).** At the start of a task the worker judges whether it holds separate, big parts (like write-back, highlight, independence and snip). If so, it does one part per session: when a part is built, it updates the docs, writes what's done and next in the change note, and ends with `HANDOFF: <note path>`. Small or tightly linked work stays in one session. No call count. `SessionTaskAgent` then starts a fresh session on the same task with "Continue from the handoff in <note>". The task id stays the same, so the Talker and Hub see no break. At most a few handoffs per task (default 3), then it ends with NEED to check in with you.
4. **Debug subagents.** A `debugger` agent in `.claude/agents/` (model `sonnet`, file tools and PowerShell). The Main's prompt: hand debugging loops and broad searches to subagents with the file, the symptom, and how to reproduce it; take back only the fix and the proof.
5. **Peek, don't interrupt.** The Hub keeps the last 15 activity lines per task (text and tool calls with file names, from `AgentActivity`) in `TaskInfo.activity`; the Talker's [Status] shows them. The Talker's prompt: "what are you doing / why" questions → LOOK; ASK or PAUSE only to change what it does or when you ask to pause.
6. **Permissions up front.** New `[modules.main_assistant] allowed_commands`: the tests, `ruff` and `scripts/build_docs.py`. File read and write in the project are already allowed. Other shell commands, including scripts the worker writes for itself, still ask.
7. **Context meters.** `ClaudeSession` reads each call's context size (input + cache tokens in `usage`) and publishes it in a new event (agent id, tokens), now `SessionUsage`. The temp UI shows it on both panes ("Worker 145k · Talker 24k"), and the Talker's [Status] includes it, so you can ask "how full are you?".

**Decided (2026-10-27):** Q1 the Talker explains and you choose; Q2 handoff by separate, big parts, not a call count; Q3 the debugger runs on `sonnet`; Q4 the worker's own scripts keep asking.

Q5 **resetting:** say "reset" to the Talker, or press a Reset button on that pane. A Talker reset keeps the last few exchanges (`context_exchanges`) so it doesn't forget what you were doing. A worker reset between tasks is automatic (item 2); during a task it's a handoff.

**To verify while building:** the exact rule syntax for allowing PowerShell commands, and that a subagent's permission requests still reach the app's Allow / Deny.
