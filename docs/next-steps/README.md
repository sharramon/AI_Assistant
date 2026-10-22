# Next steps

What we're working on now. This page changes as the work moves on.

## Where we are

**Decided earlier:**
- **Agent Hub** ([agents](../architecture/agents.md)): one module coordinating a Talker, a Main Assistant, and later subagents. Not an AI, not part of the core, launches nothing.
- **Two terminals for now:** terminal 1 to talk to the Talker, terminal 2 view-only on the Main Assistant. The chat window comes later as nicer UX for the same thing.
- **Modules own their resources** and start expensive things (a `claude` process, a model, a window) lazily.
- [Runtime module control](../architecture/core.md#runtime-module-control) is built (`ListModules`, `ActivateModule`, `DeactivateModule`).
- **Interfaces by inheritance, functionality by composition** ([principle 12](../architecture/principles.md)), with the `I` prefix for `Contract` subclasses only.
- **Subscription terms** (checked): runs on your subscription (personal use, official unmodified `claude` binary). Revisit subscription vs API key when the Hub becomes an always-on service. Sources: [Consumer Terms](https://www.anthropic.com/legal/consumer-terms) §3, [Claude Code legal page](https://code.claude.com/docs/en/legal-and-compliance).

**Done 2026-10-22:**
- **The task-agent design** is written: [agents](../architecture/agents.md#task-agents) and the [Agents API page](../api/agents.md) (planned). `message` = typing into Claude Code while it works (interrupt, quick reply, continue unless you meant stop or pause; the Talker infers which). `cancel` = Esc. Minimal Hub in v1. `AgentInfo` has `busy` and `working`, with `ListAgents` and `AgentStateChanged` for UIs.
- **The spike is done** and confirmed the design: interrupt → reply → continue works, and a session survives a cancel with its memory. Details on the [spike page](../agents/spike.md#findings). The relay script was never built.
- **CI:** GitHub Actions runs the tests on Windows and Linux, `ruff`, and checks that `docs/html` matches the Markdown. See [Testing and CI](#testing-and-ci).

## Now: the two-terminal setup

**Start next session with:** review the [Agent runtime](../agents/runtime.md) page together (launch from the main app, messaging through the core, each agent's loop, prompts, the `NEED:` convention, the tags). If it looks right, build.

Build the real modules, in this order, each with the `architecture-first` skill:

| # | Build | What it does | Test without the rest |
|---|-------|--------------|-----------------------|
| 1 | `infra/ClaudeSession` | One `claude -p` stream-json process: start, send, interrupt, read events, track `working` | Unit tests replay the spike's recorded events; one `claude`-marked test against a real session |
| 2 | `main_assistant` | Provides `ITaskAgent` through `SessionTaskAgent`; reports with `ReportTask`; publishes `AgentActivity` and `AgentStateChanged` | Against a fake Hub |
| 3 | `agent_hub` | Task state; handles `StartTask`, `GetTaskStatus`, `SendToTask`, `CancelTask`, `ReportTask`, `ListAgents` | Against a fake `ITaskAgent` |
| 4 | `talker` | A fast `claude` session for conversation; turns its tags into Hub commands; tells you about task updates | Terminal 1 works from here |
| 5 | `assistant_view` | Opens terminal 2 and shows `AgentActivity` | Terminal 2 works from here |

**Gaps found in the current code** (fix while building; no core changes):
- **The Talker can't speak first:** `console_io` only prints a `ResponseReady` that answers one of its own inputs, once. It must also print uncorrelated ones (e.g. "the task is done").
- **Event handler timeout (10 s):** the Talker must not wait for its `claude` reply inside the `InputReceived` handler; it hands the input to its own loop and returns.
- **Terminal 2 has no mechanism yet:** to decide with `assistant_view` (simplest: open a new console running a small viewer, fed over a local pipe).
- **Interrupted turns end with `is_error: true`:** `SessionTaskAgent` must know it sent the interrupt and not report the task as failed.

After this: speech-to-text (voice in) and voice out.

## Testing and CI

- `pytest` runs the unit tests (fast, no `claude`). Tests that run a real `claude` process are marked `@pytest.mark.claude`, skipped by default and in CI; run them locally with `pytest -m claude`.
- Code that wraps `claude` is tested against fakes: a fake process replaying recorded events, a fake `ITaskAgent`.
- `ruff check src tests scripts` lints (config in `pyproject.toml`).
- **CI** (`.github/workflows/ci.yml`), on every push and pull request: tests on Windows and Linux (Python 3.12), then `ruff` and a docs check that fails if `docs/html` wasn't rebuilt after a Markdown change.
- Real `claude` calls stay out of CI: they'd need your login on GitHub's machines. Use an API key as a GitHub secret if that's ever wanted.
- No CD yet: nothing is deployed while it runs on your PC.
