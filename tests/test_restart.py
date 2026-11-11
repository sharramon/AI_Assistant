"""Restart with reset instructions: the Talker's <<RESTART>>, the note kept across it, and the launcher."""

import asyncio
import subprocess

from assistant import __main__ as entry
from assistant.contracts import InputReceived, ResponseReady, ShutdownRequested
from assistant.core import App
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.main_assistant import MainAssistantModule
from assistant.modules.talker import TalkerModule
from assistant.modules.talker.module import AFTER_RESTART, APP_STATE_HEAD
from tests.test_agents import FAKE, TIMEOUT, next_matching


def _app(tmp_path, with_worker: bool = True) -> App:
    modules = [AgentHubModule, MainAssistantModule, TalkerModule] if with_worker else [TalkerModule]
    config = {
        "modules": {
            "enabled": [m.manifest.id for m in modules],
            "main_assistant": {"program": FAKE, "workspace": str(tmp_path)},
            "talker": {"program": FAKE, "restart_note": str(tmp_path / "state" / "reset.md")},
        },
        "core": {},
    }
    return App(modules, config)


def _queues(app: App) -> tuple[asyncio.Queue, asyncio.Queue]:
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    shutdowns: asyncio.Queue[ShutdownRequested] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    app.bus.subscribe(ShutdownRequested, shutdowns.put)
    return replies, shutdowns


async def test_restart_with_an_idle_worker_saves_its_note_and_keeps_it(tmp_path):
    app = _app(tmp_path)
    replies, shutdowns = _queues(app)
    await app.start()
    try:
        # The fake Talker repeats what it's sent, so the input is its reply.
        app.bus.publish(InputReceived(text="Restarting, back in a moment. <<RESTART>>", source="test"))
        event = await asyncio.wait_for(shutdowns.get(), TIMEOUT)
        assert event.restart and app.restart_requested
    finally:
        await app.stop()
    # A restart keeps the note, without its RESTART_READY line, and the app's state section under it.
    note = (tmp_path / "state" / "reset.md").read_text(encoding="utf-8")
    assert note.startswith("Was building the poems; part one done.\n\n" + APP_STATE_HEAD)
    assert "RESTART_READY" not in note
    assert "- The user was in the Main Assistant's tab (main_assistant)." in note
    assert "\n- main_assistant" in note and ": manual" in note  # every agent with its mode
    assert note.rstrip().endswith(AFTER_RESTART)


async def test_restart_note_lists_a_task_waiting_on_the_user(tmp_path):
    app = _app(tmp_path)
    replies, shutdowns = _queues(app)
    await app.start()
    try:
        app.bus.publish(InputReceived(text="<<WORK: poems ASKME>>", source="test"))
        await next_matching(replies, lambda e: e.text.startswith("[Task update: need]"))
        state = await app._lifecycle._active["talker"][0].restart.app_state()
    finally:
        await app.stop()
    assert "  - task " in state and "poems ASKME" in state and "waiting on the user: Which style?" in state


async def test_the_restart_goes_ahead_and_the_question_stays_open(tmp_path):
    app = _app(tmp_path)
    replies, shutdowns = _queues(app)
    await app.start()
    try:
        app.bus.publish(InputReceived(text="<<WORK: poems ASKME>>", source="test"))
        await next_matching(replies, lambda e: e.text.startswith("[Task update: need]"))
        app.bus.publish(InputReceived(text="<<RESTART>>", source="test"))
        assert (await asyncio.wait_for(shutdowns.get(), TIMEOUT)).restart  # no refusal, no "anyway"
    finally:
        await app.stop()
    note = (tmp_path / "state" / "reset.md").read_text(encoding="utf-8")
    assert "part one done" in note
    assert "poems ASKME" in note and "waiting on the user: Which style?" in note  # the question stayed open


async def test_restart_without_a_worker_writes_its_own_note(tmp_path):
    app = _app(tmp_path, with_worker=False)
    replies, shutdowns = _queues(app)
    await app.start()
    try:
        app.bus.publish(InputReceived(text="we were on the logs", source="test"))
        await next_matching(replies, lambda e: e.text == "we were on the logs")
        app.bus.publish(InputReceived(text="<<RESTART>>", source="test"))
        assert (await asyncio.wait_for(shutdowns.get(), TIMEOUT)).restart
    finally:
        await app.stop()
    note = (tmp_path / "state" / "reset.md").read_text(encoding="utf-8")
    assert note.startswith("The Main Assistant didn't write reset instructions") and "we were on the logs" in note


async def test_next_launch_gets_the_note_first_then_deletes_it(tmp_path):
    note = tmp_path / "state" / "reset.md"
    note.parent.mkdir()
    note.write_text("Was on step 2 of docs/next-steps/x.md.", encoding="utf-8")
    app = _app(tmp_path, with_worker=False)
    replies, _ = _queues(app)
    await app.start()
    try:
        first = await next_matching(replies, lambda e: True)
        assert first.text.startswith("[Restart] The app was just restarted.")
        assert first.text.endswith("Was on step 2 of docs/next-steps/x.md.")
        assert not note.exists()
    finally:
        await app.stop()


async def test_a_stop_that_isnt_a_restart_deletes_a_leftover_note(tmp_path):
    app = _app(tmp_path, with_worker=False)
    await app.start()
    note = tmp_path / "state" / "reset.md"
    note.parent.mkdir()
    note.write_text("old", encoding="utf-8")
    await app.stop()
    assert not note.exists() and not app.restart_requested


class _FakeChild:
    def __init__(self, code: int):
        self.code = code

    def wait(self) -> int:
        return self.code


def test_launcher_starts_the_app_again_on_the_restart_code(monkeypatch):
    codes = iter([entry.RESTART_EXIT_CODE, entry.RESTART_EXIT_CODE, 0])
    calls = []

    def popen(args, env) -> subprocess.Popen:
        calls.append((args, env[entry.CHILD_ENV]))
        return _FakeChild(next(codes))  # type: ignore[return-value]

    monkeypatch.setattr(entry, "load_config", lambda: {"core": {}})
    assert entry.launch(popen) == 0
    assert len(calls) == 3 and all(args[1:3] == ["-m", "assistant"] and child == "1" for args, child in calls)
