# Usage meters: context now and usage so far

> **Status: done (2026-10-28).** Q1–Q3 as recommended. Checked by replaying the 2026-10-27 transcripts through the new counting: worker 20.7M tokens, ~$8.42, last context 274k; Talker 2.3M, ~$0.57, 43k. That replay found the streamed lines undercount output (2.5k against the results' 129k), so output now comes from each turn's result. Docs: [agent runtime](../../agents/runtime.md), [`SessionUsage`](../../api/agents.md#sessionusage). Needs a relaunch to go live.

**Asked:** "I want the cumulative, but also the current context size of the talker and the current worker."

**Why:** the [leaner worker](leaner-worker.md) meters show only the current context size ("context 145k"), so you can tell when a session is full but not what it has cost. They also drop to 0 when the worker starts a fresh session, so a launch's spend is invisible.

**Touches:** `infra/claude_session.py`, `infra/session_agent.py`, `contracts/agents.py`, the Talker and temp UI modules and `temp_ui/page.html`, tests; docs: `api/agents.md`, `api/infra.md`, `agents/runtime.md`.

**Approach:**
1. **Count in `ClaudeSession`, across restarts.** It already reads each call's `usage` for `context_tokens`. It also adds every call to `used_tokens` (input, cache writes, cache reads and output, each call counted once by its message id) and keeps `cost_usd` from the `result` lines (`total_cost_usd`, which counts per process, so finished processes are added up). These totals survive `close` and `start`, so the worker's fresh sessions and resets add to the same launch total.
2. **One event for both numbers.** `ContextSize` becomes `SessionUsage(agent_id, context_tokens, input_tokens, cache_write_tokens, cache_read_tokens, output_tokens, cost_usd)`, with `used_tokens` as their sum. It was added yesterday and only the Talker and temp UI read it. Published on every call, so it's live while the worker works.
3. **Separate numbers for the worker and the Talker, never added together.** Each session has its own counters and its own event (`agent_id` "main_assistant" or "talker").
4. **The Talker sees both, always.** It's the real UX (voice, glasses later), so it doesn't need a LOOK to know them. Like the `[Viewer]` note, a short line goes before each of your messages to it:

   ```
   [Usage] worker: context 145k, used 2.3M (~$5.10) · you: context 24k, used 0.4M (~$0.30)
   ```

   So "how full are you?" or "what has this cost?" is answered straight away, about either session or both. About 30 tokens a message.
5. **The Talker warns you.** When either context passes a threshold (default 150k, `[modules.talker] context_warning`), it tells you once, in a sentence, and offers a reset. It warns again only after that session has been reset and crossed the threshold again.
6. **The temp UI shows the same, secondary:** both side by side in the header (`Worker context 145k · used 2.3M · ~$5.10 | Talker …`), live; hover for the split of used tokens (fresh input, cache writes, cache reads, output).

**Open questions:**
- **Q1. Since when does "used" count?** *Recommend: since the app started.* A reset or fresh session doesn't zero it; a relaunch does. The per-launch logs keep the history.
- **Q2. Show the dollar estimate?** On your subscription you don't pay per token; `total_cost_usd` is what the same tokens would cost on the API. *Recommend: show it, marked `~`*, as the easiest way to compare sessions.
- **Q3. Warning threshold:** *Recommend 150k.* The big task on 2026-10-27 passed it about halfway through.
