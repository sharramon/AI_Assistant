# Test kit

The fakes and helpers every test may use: the central tests in `tests/` and each module's own tests in `src/assistant/modules/<id>/tests/`. All items: `from assistant.testkit import ...`. Every item is reusable and listed in the [reusable parts index](reusable.md). Back to the [API index](README.md).

> **Status: built (2026-11-13).** A module's tests import shared helpers from here only, never from `tests.*`, so a module's folder carries its tests whole. **For tests only:** nothing in the app imports it, and the core treats it as shared code (it can't be reloaded). Checked by `tests/test_module_folders.py` (`test_module_tests_use_only_the_testkit`, `test_only_tests_import_the_testkit`, `test_no_cv_only_test_is_central`, `test_no_module_only_test_file_is_central`).

It may import `assistant.*`; the builders that need a module (`start_hub`, `pre_grant_kinds`) import it when called. It needs no pytest: fixtures stay in the test files (`tests/test_agents.py`'s `hub` wraps `start_hub`).

## Helpers

**Reusable** · Used by: almost every central test; `cv` (`test_worker.py`: `pre_grant`, `wait_until`), `agent_hub` (`test_gate.py`: `wait_until`), `echo_orchestrator` (`test_echo.py`: `make_config`), `agent_hub`, `main_assistant`, `task_agents`, `console_io`, `temp_ui` and `usage` (their defaults tests: `module_config`), `console_io` (`test_console_io.py`: `make_config`, `wait_until`), `temp_ui` (`test_taskbar_flash.py`: `sample_card`, `wait_until`), `job_search` (`test_job_search.py`: `pre_grant`, `module_config`, `stand_in`, `free_port`, `wait_until`), `voice_in` (`test_voice_in.py`: `free_port`, `wait_until`), `test_companion_reload`, `test_swap_every_module` (`free_port`); `module_config` and `stand_in` also `test_access_cards`, `test_agent_names`, `test_agent_tabs`; `sample_card` also `test_access_cards`

| Item | Does |
|------|------|
| `make_config(*enabled, **core) -> dict` | A test config: the enabled module ids and the `[core]` values |
| `await wait_until(predicate, timeout=1.0)` | Wait until `predicate()` is true; `TimeoutError` after `timeout` seconds |
| `Speaker` | A single-provider contract for tests (it reports itself as living in `assistant.contracts`) |
| `Calculator` | A module providing `IToolProvider` with one tool, `add` |
| `pre_grant(app, module_id, subject, config, own_folder=None)` | Save a grant for `config`'s whole access list, so `module_id` turns on with no card. `own_folder`: the list has the module's own folder (default: every module but `task_agents`). Give it the config the module sees: for a module with defaults, `module_config(module_id, section)` |
| `module_config(module_id, section=None) -> dict` | The config a module sees, built as the core builds it: its `module.toml` defaults (read with the core's `loader.module_defaults`) with `section` merged over them |
| `stand_in(module_id) -> type` | A bare module class with that id and nothing else, standing in for a module another one `needs` (job_search needs cv), so a test starts the one under test without the real one |
| `free_port() -> int` | A free TCP port on 127.0.0.1, for a test server |
| `sample_card(**over) -> PermissionRequested` | An access card as a module's access list opens it (job_search asking for job_search_agent's workspace and Chrome, not reviewed); `over` replaces any field. Moved from `tests/test_access_cards.py` (module folders item 11) |
| `pre_grant_kinds(app, section, module_id="task_agents")` | Pre-grant every kind of a `task_agents` config: its `module.toml` defaults (the shipped kinds too) with `section` (its `[modules.task_agents]`) merged over them |

**Defined in:** `src/assistant/testkit/support.py`

## Pages and a voice_in stand-in

**Reusable** · Used by: `temp_ui` (`test_temp_ui.py`, `test_temp_ui_snips.py`), `voice_notes` (`test_voice_notes.py`); `post`, `request`, `ui_port` and `read_events` also `test_access_cards`, `test_agent_tabs`, `test_permission_mode`; `clip_event` and `dropped_event`: `talker` (`test_talker_snips.py`), `temp_ui` (`test_temp_ui_snips.py`)

| Item | Does |
|------|------|
| `await request(port, raw) -> (reader, writer)` | Send raw HTTP bytes to `127.0.0.1:port`; the open stream |
| `await post(port, path, body) -> dict` | POST `body` as JSON; the JSON answer |
| `await next_item(reader, match) -> dict` | The next item on an open `/events` stream that `match` accepts, within 2 s |
| `ui_port(app, module_id="temp_ui") -> int` | The port a started app's page module listens on, from its `url` |
| `await read_events(port, count) -> list[dict]` | The first `count` items on a page's `/events` stream after its leading `hello` (checked, and returned first) |
| `clip_event(snip_id, image, file, heading=None, source="html_viewer")` | A snip as its publisher sends it: the named event `<source>.clip` (`html_viewer.clip`, or `temp_ui.clip` for a pasted image) |
| `dropped_event(snip_id)` | The temp UI's `temp_ui.clip_dropped`: you dropped that snip with its x |
| `FakeVoiceIn` | A module with id `voice_in` that answers `StartListening` / `StopListening` and `IVoice` with the events voice_in publishes (no voice service); `fail` makes the next start fail |

**Defined in:** `src/assistant/testkit/pages.py` (moved from `tests/test_temp_ui.py`, 2026-11-13; the snip events from `tests/test_viewer_listeners.py`, and `ui_port` / `read_events` from `tests/test_temp_ui.py`, module folders item 11)

## The fake `claude` and agent fakes

**Reusable** · Used by: the central agent tests (`test_agents`, `test_multi_agent`, `test_permission_mode`, ...); `task_agents` (`test_task_agents.py`), `talker` (`test_talker.py`: `FAKE`, `next_matching`), `cv` (`test_worker.py`: `FAKE`), `agent_hub` (`test_end_waiting.py`, `test_end_report_race.py`: `StubSession`, `StubContext`; `test_gate.py`: `FakeAgent`)

| Item | Does |
|------|------|
| `FAKE` | The command line of the fake `claude -p` (stream-json), `fake_claude.py`, run as a subprocess: put it in a module config's `program`. Its docstring lists the words that make it ask, wait, crash or hand off (`ASKME`, `SLOW`, `CRASH`, `PERMIT`, ...) |
| `FAKE_JOB_UI` | The path of `fake_job_ui.py`, a stand-in for the job project's job UI, run as a script |
| `TIMEOUT` | 10 s, the wait for a fake `claude` turn |
| `await next_matching(queue, predicate)` | The next item on an `asyncio.Queue` that `predicate` accepts, within `TIMEOUT` |
| `report(kind)` | A predicate for `next_matching`: a `TaskUpdated` of that `ReportKind` |
| `await start_hub(tmp_path, **main_config) -> (app, updates)` | A started `App` with the Agent Hub and a Main Assistant on the fake `claude` (workspace `tmp_path`), and a queue of its `TaskUpdated`. The caller stops the app |
| `StubSession`, `StubContext` | Just enough of a `ClaudeSession` and a `ModuleContext` to drive a `SessionTaskAgent` by hand; `StubContext.provided` (`{IPageOpener: a_fake}`) answers `get_one` |
| `FakeAgent(agent_id, folders)` | An `ITaskAgent` that only records what the Hub asks of it (`calls`, `notes`); `busy` and `working` set by the test |
| `agent_module(agent_id, folders) -> (module_class, agent)` | A module class providing one `FakeAgent` |
| `await status(app, task_id)` | A task's `TaskInfo` from the Hub (`GetTaskStatus`) |

**Example**

    from assistant.testkit import FAKE, pre_grant, wait_until

    config = {"modules": {"enabled": ["agent_hub", "cv"], "cv": {"agent": {"program": FAKE, "workspace": str(tmp_path)}}}, "core": {}}

**Defined in:** `src/assistant/testkit/agents.py`, the scripts `fake_claude.py` and `fake_job_ui.py` beside it
