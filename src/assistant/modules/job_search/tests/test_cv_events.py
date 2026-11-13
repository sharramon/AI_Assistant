"""job_search hears cv's named events and wakes its own agent with one message each; another
agent's events are left alone."""

import logging

from assistant.contracts import DeliverMessage, ModuleEvent, Result
from assistant.modules.job_search.module import CV_FINISHED, CV_SUBMITTED, JobSearchModule

AGENT = "job_search_agent"


class FakeCtx:
    def __init__(self) -> None:
        self.sent: list[DeliverMessage] = []
        self.log = logging.getLogger("test")

    async def send(self, command, timeout=None) -> Result:
        self.sent.append(command)
        return Result.ok("message")


def module() -> tuple[JobSearchModule, FakeCtx]:
    job = JobSearchModule.__new__(JobSearchModule)  # no init: no agent, no access card
    ctx = FakeCtx()
    job._ctx, job._agent_id = ctx, AGENT
    return job, ctx


FINISHED = {"reply_to": AGENT, "agent_id": "cv_agent", "task_id": "3f2a91c0", "parent_task_id": "632c9ff5",
            "state": "done", "job_dir": "C:/work/2026-11-12_Acme_Engineer", "company": "Acme", "role": "Engineer",
            "cv_result": None, "summary": "CV_RESULT status stopped (test); PDF: (none); last score: (none)."}  # fmt: skip


async def test_the_end_of_its_cv_job_wakes_the_agent_with_one_message():
    job, ctx = module()
    await job._on_cv(ModuleEvent(name=CV_FINISHED, source="cv", data=FINISHED))
    (message,) = ctx.sent
    assert message.agent_id == AGENT and message.sender == "job_search"
    assert "Engineer at Acme" in message.text and "C:/work/2026-11-12_Acme_Engineer" in message.text
    assert "CV_RESULT status stopped" in message.text and "cv.read_result task_id=3f2a91c0" in message.text
    assert "tracker" in message.text


async def test_the_submit_wakes_the_agent_with_cvs_summary():
    job, ctx = module()
    data = {"reply_to": AGENT, "job_id": "j1", "job_dir": "C:/work/x", "summary": "From the cv module: ready."}
    await job._on_cv(ModuleEvent(name=CV_SUBMITTED, source="cv", data=data))
    (message,) = ctx.sent
    assert message.text.startswith("From the cv module: ready.") and "CV Tool job j1" in message.text


async def test_another_agents_event_is_left_alone():
    job, ctx = module()
    await job._on_cv(ModuleEvent(name=CV_FINISHED, source="cv", data=FINISHED | {"reply_to": "main_assistant"}))
    assert ctx.sent == []


def test_the_manifest_declares_both_events_and_the_message():
    manifest = JobSearchModule.manifest
    assert set(manifest.listens_named) == {CV_FINISHED, CV_SUBMITTED} and DeliverMessage in manifest.sends
