"""Chunk 14: the Talker's restart flow on its own (`RestartFlow`) and its tag table."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from assistant.contracts import ReportKind, Result, ShutdownRequested, TaskState, TaskUpdated
from assistant.modules.talker.restart import APP_STATE_HEAD, RESTART_INPUT, RESTART_READY, RestartFlow
from assistant.modules.talker.session import TAG_NAMES, TalkerSession


class FakeCtx:
    def __init__(self) -> None:
        self.published: list = []
        self.sent: list = []
        self.log = logging.getLogger("talker-parts")

    def publish(self, event) -> None:
        self.published.append(event)

    async def send(self, command) -> Result:
        self.sent.append(command)
        return Result.ok([])


def fake_talker() -> SimpleNamespace:
    main = SimpleNamespace(history=["User: hi", "Assistant: hello"], said=[])
    main.status = main.said.append

    async def hub(name: str, **args) -> Result:
        return Result.ok([])

    return SimpleNamespace(ctx=FakeCtx(), worker_id="main_assistant", focus="main_assistant", main=main,
                           name=lambda agent: agent, task_of=lambda agent: None, hub=hub)


def update(kind: ReportKind, text: str, agent: str = "main_assistant") -> TaskUpdated:
    return TaskUpdated(task_id="t1", agent_id=agent, kind=kind, state=TaskState.DONE, text=text)


async def test_the_note_is_the_first_input_once_and_a_plain_stop_deletes_it(tmp_path) -> None:
    note = tmp_path / "restart.md"
    flow = RestartFlow(fake_talker(), note, 5)
    assert flow.first_input() is None
    note.write_text("carry on\n", encoding="utf-8")
    assert flow.first_input() == RESTART_INPUT + "carry on"
    flow.used()
    assert not note.exists()
    note.write_text("left over", encoding="utf-8")
    await flow.close()
    assert not note.exists()


async def test_the_workers_ready_reply_saves_the_note_and_restarts(tmp_path) -> None:
    note = tmp_path / "restart.md"
    talker = fake_talker()
    flow = RestartFlow(talker, note, 60)
    assert not await flow.on_worker_update(update(ReportKind.DONE, f"x\n{RESTART_READY}"), "main_assistant")
    await flow.ask()  # no task: a small task of its own, then waits
    assert flow.waiting
    assert not await flow.on_worker_update(update(ReportKind.DONE, "not yet"), "main_assistant")
    assert not await flow.on_worker_update(update(ReportKind.DONE, RESTART_READY, "helper"), "helper")
    assert await flow.on_worker_update(update(ReportKind.REPLY, f"Do the docs next.\n{RESTART_READY}"), "main_assistant")
    text = note.read_text(encoding="utf-8")
    assert text.startswith("Do the docs next.") and APP_STATE_HEAD in text and RESTART_READY not in text
    assert flow.restarting and not flow.waiting
    assert [type(c) for c in talker.ctx.sent if isinstance(c, ShutdownRequested)] == [ShutdownRequested]  # a command now
    assert talker.ctx.published == []
    await flow.close()
    assert note.exists()  # kept for the next launch


def test_every_tag_has_its_handler() -> None:
    """Each tag split_tags finds has one handler method (the table in __init__ maps them)."""
    handlers = {name for name in dir(TalkerSession) if name.startswith("_tag_")}
    shared = {"ALLOW": "answer", "DENY": "answer", "ASK": "send", "PAUSE": "send"}
    assert {"_tag_" + shared.get(t, t.lower()) for t in TAG_NAMES} == handlers
