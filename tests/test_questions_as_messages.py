"""Questions as messages: an agent that asks (`NEED:`) drops the task and is free; the Hub keeps
the question on the task, idle; the answer comes back as the same task, with the module's notes
when the session that asked is gone (agent-talk-and-questions)."""

import asyncio
import json

from assistant.contracts import (
    CancelTask,
    GetTaskStatus,
    ListAgents,
    ReportKind,
    SendToTask,
    StartTask,
    TaskState,
)
from assistant.infra.session_agent import CONTEXT_AGAIN, default_context
from assistant.modules.cv.job_start import job_notes
from tests.test_agents import next_matching, report, start_hub


def _module(app, module_id):
    return app._lifecycle._active[module_id][0]


async def test_an_agent_that_asks_is_free_and_takes_new_work(tmp_path):
    app, updates = await start_hub(tmp_path)
    try:
        asked = (await app.router.send(StartTask(text="ASKME then write"))).value
        need = await next_matching(updates, report(ReportKind.NEED))
        assert need.task_id == asked and need.state is TaskState.IDLE
        agents = (await app.router.send(ListAgents())).value
        assert not agents[0].active  # idle while its question is open
        hub = _module(app, "agent_hub")
        assert hub.busy() is None  # a question waiting on you doesn't hold a reload
        assert [q["id"] for q in hub.export_state()["questions"]] == [asked]

        other = await app.router.send(StartTask(text="write a poem"))
        assert other.is_ok and other.value != asked
        done = await next_matching(updates, report(ReportKind.DONE))
        assert done.task_id == other.value
        status = (await app.router.send(GetTaskStatus(task_id=asked))).value[0]
        assert status.state is TaskState.IDLE and status.question == "Which style?"  # still open
    finally:
        await app.stop()


async def test_a_late_answer_gets_the_modules_notes_in_a_fresh_session(tmp_path):
    app, updates = await start_hub(tmp_path)
    try:
        _module(app, "main_assistant")._agent.set_context(lambda task_id: f"key-{task_id}",
                                                          lambda key: f"notes for {key}")  # fmt: skip
        asked = (await app.router.send(StartTask(text="ASKME then write"))).value
        need = await next_matching(updates, report(ReportKind.NEED))
        status = (await app.router.send(GetTaskStatus(task_id=asked))).value[0]
        assert need.task_id == asked and status.question_key == f"key-{asked}"
        other = (await app.router.send(StartTask(text="write a poem"))).value  # the asking session is gone
        await next_matching(updates, lambda e: e.task_id == other and e.kind is ReportKind.DONE)

        assert (await app.router.send(SendToTask(task_id=asked, text="modern"))).is_ok
        done = await next_matching(updates, lambda e: e.task_id == asked and e.kind is ReportKind.DONE)
        assert done.text.startswith(f'Answer to your question in task {asked} ("Which style?"): modern')
        assert CONTEXT_AGAIN.format(notes=f"notes for key-{asked}") in done.text
    finally:
        await app.stop()


async def test_an_answer_while_the_agent_is_in_a_turn_waits_for_the_turn_to_end(tmp_path):
    app, updates = await start_hub(tmp_path)
    try:
        asked = (await app.router.send(StartTask(text="ASKME then write"))).value
        await next_matching(updates, report(ReportKind.NEED))
        slow = (await app.router.send(StartTask(text="SLOW job"))).value
        await next_matching(updates, lambda e: e.task_id == slow and e.text == "started")

        waiting = await app.router.send(SendToTask(task_id=asked, text="modern"))
        assert waiting.is_ok and waiting.value == "pending"
        assert (await app.router.send(CancelTask(task_id=slow))).is_ok  # the turn ends: the answer goes in
        done = await asyncio.wait_for(
            next_matching(updates, lambda e: e.task_id == asked and e.kind is ReportKind.DONE), 15)
        assert "Answer to your question" in done.text
    finally:
        await app.stop()


async def test_cancelling_a_question_needs_no_agent(tmp_path):
    app, updates = await start_hub(tmp_path)
    try:
        asked = (await app.router.send(StartTask(text="ASKME then write"))).value
        await next_matching(updates, report(ReportKind.NEED))
        assert (await app.router.send(CancelTask(task_id=asked))).is_ok
        status = (await app.router.send(GetTaskStatus(task_id=asked))).value[0]
        assert status.state is TaskState.CANCELLED and status.question is None
    finally:
        await app.stop()


def test_job_notes_read_the_jobs_record_and_its_handoff_note(tmp_path):
    folder = tmp_path / "2026-11-10_Acme_Engineer"
    folder.mkdir()
    (folder / "job_start.json").write_text(json.dumps({
        "request": {"company": "Acme", "role": "Engineer"},
        "job": {"base_cv_copy": str(folder / "cv.json"), "jd_file": str(folder / "jd.txt")},
        "replied": {"to": "job_search_agent", "how": "message 1234", "submitted_at": "t1"},
    }), encoding="utf-8")  # fmt: skip
    (folder / "cv_handoff.md").write_text("where I was", encoding="utf-8")
    notes = job_notes(str(folder))
    assert "Acme (Engineer)" in notes and str(folder) in notes
    assert "job_search_agent (message 1234)" in notes
    assert f"Read your handoff note first: {folder / 'cv_handoff.md'}" in notes
    assert job_notes("docs/next-steps/x.md") == default_context("docs/next-steps/x.md")
    assert job_notes("") == ""
