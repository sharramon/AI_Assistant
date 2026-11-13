# Test kit

The fakes and helpers every test may use: the central tests in `tests/` and each module's own tests in `src/assistant/modules/<id>/tests/`. All items: `from assistant.testkit import ...`. Every item is reusable and listed in the [reusable parts index](reusable.md). Back to the [API index](README.md).

> **Status: built (2026-11-13).** A module's tests import shared helpers from here only, never from `tests.*`, so a module's folder carries its tests whole. **For tests only:** nothing in the app imports it, and the core treats it as shared code (it can't be reloaded). Checked by `tests/test_module_folders.py` (`test_module_tests_use_only_the_testkit`, `test_only_tests_import_the_testkit`, `test_no_cv_only_test_is_central`).

It may import `assistant.*`; the builders that need a module (`start_hub`, `pre_grant_kinds`) import it when called. It needs no pytest: fixtures stay in the test files (`tests/test_agents.py`'s `hub` wraps `start_hub`).

## Helpers

**Reusable** · Used by: almost every central test; `cv` (`test_worker.py`: `pre_grant`, `wait_until`), `agent_hub` (`test_gate.py`: `wait_until`), `echo_orchestrator` (`test_echo.py`: `make_config`)

| Item | Does |
|------|------|
| `make_config(*enabled, **core) -> dict` | A test config: the enabled module ids and the `[core]` values |
| `await wait_until(predicate, timeout=1.0)` | Wait until `predicate()` is true; `TimeoutError` after `timeout` seconds |
| `Speaker` | A single-provider contract for tests (it reports itself as living in `assistant.contracts`) |
| `Calculator` | A module providing `IToolProvider` with one tool, `add` |
| `pre_grant(app, module_id, subject, config, own_folder=None)` | Save a grant for `config`'s whole access list, so `module_id` turns on with no card. `own_folder`: the list has the module's own folder (default: every module but `task_agents`) |
| `pre_grant_kinds(app, module_config, module_id="task_agents")` | Pre-grant every kind of a `task_agents` config |

**Defined in:** `src/assistant/testkit/support.py`

## The fake `claude` and agent fakes

**Reusable** · Used by: the central agent tests (`test_agents`, `test_multi_agent`, `test_permission_mode`, `test_task_agents`, ...); `cv` (`test_worker.py`: `FAKE`), `agent_hub` (`test_end_waiting.py`, `test_end_report_race.py`: `StubSession`, `StubContext`; `test_gate.py`: `FakeAgent`)

| Item | Does |
|------|------|
| `FAKE` | The command line of the fake `claude -p` (stream-json), `fake_claude.py`, run as a subprocess: put it in a module config's `program`. Its docstring lists the words that make it ask, wait, crash or hand off (`ASKME`, `SLOW`, `CRASH`, `PERMIT`, ...) |
| `FAKE_JOB_UI` | The path of `fake_job_ui.py`, a stand-in for the job project's job UI, run as a script |
| `TIMEOUT` | 10 s, the wait for a fake `claude` turn |
| `await next_matching(queue, predicate)` | The next item on an `asyncio.Queue` that `predicate` accepts, within `TIMEOUT` |
| `report(kind)` | A predicate for `next_matching`: a `TaskUpdated` of that `ReportKind` |
| `await start_hub(tmp_path, **main_config) -> (app, updates)` | A started `App` with the Agent Hub and a Main Assistant on the fake `claude` (workspace `tmp_path`), and a queue of its `TaskUpdated`. The caller stops the app |
| `StubSession`, `StubContext` | Just enough of a `ClaudeSession` and a `ModuleContext` to drive a `SessionTaskAgent` by hand |
| `FakeAgent(agent_id, folders)` | An `ITaskAgent` that only records what the Hub asks of it (`calls`, `notes`); `busy` and `working` set by the test |
| `agent_module(agent_id, folders) -> (module_class, agent)` | A module class providing one `FakeAgent` |
| `await status(app, task_id)` | A task's `TaskInfo` from the Hub (`GetTaskStatus`) |

**Example**

    from assistant.testkit import FAKE, pre_grant, wait_until

    config = {"modules": {"enabled": ["agent_hub", "cv"], "cv": {"agent": {"program": FAKE, "workspace": str(tmp_path)}}}, "core": {}}

**Defined in:** `src/assistant/testkit/agents.py`, the scripts `fake_claude.py` and `fake_job_ui.py` beside it
