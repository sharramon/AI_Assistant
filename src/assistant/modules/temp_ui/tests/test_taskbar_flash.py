"""The temp UI flashes the app's taskbar button when a task of any agent ends (done or failed)
or asks you something, and on a permissions card; not on progress, replies or a cancel."""

import asyncio

from assistant.contracts import QuestionKind, ReportKind, TaskState, TaskUpdated
from assistant.core import App
from assistant.modules.temp_ui import TempUIModule
from assistant.testkit import sample_card, wait_until


async def flashing_app():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    await app.start()
    flashes: list[int] = []
    app._lifecycle._active["temp_ui"][0]._flash = lambda: flashes.append(1)
    return app, flashes


async def test_ends_and_questions_of_every_agent_flash():
    app, flashes = await flashing_app()
    try:
        flashing = [
            TaskUpdated(task_id="t1", state=TaskState.DONE, kind=ReportKind.DONE, agent_id="main_assistant"),
            TaskUpdated(task_id="t2", state=TaskState.FAILED, kind=ReportKind.FAILED, text="boom", agent_id="flight_search"),
            TaskUpdated(task_id="t3", state=TaskState.FAILED, agent_id="job_search_agent"),  # the Hub failed it
            TaskUpdated(task_id="t4", state=TaskState.IDLE, kind=ReportKind.NEED, text="which?", agent_id="cv_agent",
                        held=True, question_kind=QuestionKind.NEED),
            TaskUpdated(task_id="t5", state=TaskState.IDLE, kind=ReportKind.PERMISSION, text="Bash", agent_id="main_assistant"),
        ]
        for event in flashing:
            app.bus.publish(event)
        app.bus.publish(sample_card())
        await wait_until(lambda: len(flashes) == len(flashing) + 1)
    finally:
        await app.stop()


async def test_a_failed_helper_task_flashes():
    app, flashes = await flashing_app()
    try:
        app.bus.publish(TaskUpdated(task_id="h1", state=TaskState.FAILED, kind=ReportKind.FAILED,
                                    text="The agent's claude process exited", agent_id="flight_search"))
        await wait_until(lambda: len(flashes) == 1)
    finally:
        await app.stop()


async def test_progress_replies_and_a_cancel_dont_flash():
    app, flashes = await flashing_app()
    try:
        for event in (
            TaskUpdated(task_id="t1", state=TaskState.ACTIVE, kind=ReportKind.PROGRESS, text="working"),
            TaskUpdated(task_id="t1", state=TaskState.ACTIVE, kind=ReportKind.MILESTONE, text="half way"),
            TaskUpdated(task_id="t1", state=TaskState.ACTIVE, kind=ReportKind.REPLY, text="ok"),
            TaskUpdated(task_id="t1", state=TaskState.CANCELLED),
        ):
            app.bus.publish(event)
        await asyncio.sleep(0.1)
        assert flashes == []
    finally:
        await app.stop()
