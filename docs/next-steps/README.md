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

## Done: the two-terminal setup (2026-10-25)

The [Agent runtime](../agents/runtime.md) is built and runs: `.\.venv\Scripts\python -m assistant` opens terminal 2 and starts both `claude` sessions. Tested end to end (hand off, work, "done" notice, file in `workspace/`) and by `tests/test_agents.py`, which runs against `tests/fake_claude.py`.

**Known issues:**
- **Exit crash with piped stdin:** typing `exit` when stdin is a pipe (not a console) ends with "Fatal Python error … stdin … daemon threads". `console_io`'s stdin thread holds the stdin lock at shutdown. It also happened before the agents were added.
- **Interrupt and NEED untried with the real agents:** the fake-`claude` tests cover them; try a mid-task question, pause, and cancel by hand.
- **The Talker's working directory** is the app's, so it loads this project's `CLAUDE.md`. Set `[modules.talker] cwd` to a neutral folder if that slows it down.

## Now

Try it by hand, then speech-to-text (voice in) and voice out.

## Testing and CI

- `pytest` runs the unit tests (fast, no `claude`). Tests that run a real `claude` process are marked `@pytest.mark.claude`, skipped by default and in CI; run them locally with `pytest -m claude`.
- Code that wraps `claude` is tested against fakes: a fake process replaying recorded events, a fake `ITaskAgent`.
- `ruff check src tests scripts` lints (config in `pyproject.toml`).
- **CI** (`.github/workflows/ci.yml`), on every push and pull request: tests on Windows and Linux (Python 3.12), then `ruff` and a docs check that fails if `docs/html` wasn't rebuilt after a Markdown change.
- Real `claude` calls stay out of CI: they'd need your login on GitHub's machines. Use an API key as a GitHub secret if that's ever wanted.
- No CD yet: nothing is deployed while it runs on your PC.
