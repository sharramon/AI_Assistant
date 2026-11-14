"""The Hub's side of the access-list review (D6): `ReviewAccessList` runs a task on the reviewer
and answers with `AddCardNotes`. The full flow through the core: `tests/test_permissions_handler.py`."""

import logging

from assistant.contracts import CancelTask, Result, ReviewAccessList, StartTask, Status, TaskState, TaskUpdated
from assistant.modules.agent_hub.review import Reviewer, review_lines
from assistant.testkit import wait_until


def test_review_lines_strip_bullets_and_the_all_clear():
    assert review_lines("- It could post your CV.\n\n* Another\nNo further warnings.") == ("It could post your CV.", "Another")
    assert review_lines("") == ()


async def test_the_reviewer_cancels_a_late_review_and_reports_not_reviewed():
    sent: list = []
    cancelled: list = []

    async def start(cmd: StartTask) -> Result:
        return Result.ok("t1")

    async def cancel(cmd: CancelTask) -> Result:
        cancelled.append(cmd.task_id)
        return Result.ok()

    async def send(cmd) -> Result:
        sent.append(cmd)
        return Result.ok()

    reviewer = Reviewer(start, cancel, send, logging.getLogger("test"))
    assert (await reviewer.review(ReviewAccessList(request_id="c1", reviewer="r", who="jobs", timeout=0.05))).is_ok
    await wait_until(lambda: sent)
    assert cancelled == ["t1"] and sent[0].request_id == "c1" and sent[0].reviewed is False

    sent.clear()
    assert (await reviewer.review(ReviewAccessList(request_id="c2", reviewer="r", who="jobs", timeout=5))).is_ok
    reviewer.on_task_updated(TaskUpdated(task_id="t1", state=TaskState.DONE, text="- Risky\nNo further warnings."))
    await wait_until(lambda: sent)
    assert sent[0].notes == ("Risky",) and sent[0].reviewed is True
    await reviewer.close()


async def test_a_busy_reviewer_answers_not_available():
    async def start(cmd: StartTask) -> Result:
        return Result.not_available("busy")

    async def unused(cmd) -> Result:
        raise AssertionError("not called")

    reviewer = Reviewer(start, unused, unused, logging.getLogger("test"))
    result = await reviewer.review(ReviewAccessList(request_id="c1", reviewer="r", who="jobs"))
    assert result.status is Status.NOT_AVAILABLE
