"""cv.task makes cv_agent's task a child of the asker's open task, and cv reports back only through
its named events: `cv.job_finished` when cv_agent's task ends, `cv.job_submitted` at the user's
Submit, each with `reply_to`. The Hub sends the asker no child-result message (`tell_parent=False`),
and cv sends the asker no message of its own."""

import asyncio
import json
from pathlib import Path

from assistant.contracts import (
    AgentInfo,
    AgentState,
    AgentStateChanged,
    GetTaskStatus,
    ITaskAgent,
    Manifest,
    ModuleContext,
    ModuleEvent,
    ModuleProtocol,
    Result,
    StartTask,
)
from assistant.modules.cv.handoff import read_job
from assistant.modules.cv.order import SectionOrder
from assistant.modules.cv.tests.pdf_fixture import write_pdf
from assistant.modules.cv.tests.test_handoff import JD, finished, use
from assistant.modules.cv.tests.test_worker import CV, DEFAULTS, app_with, cv_module

JOB_AGENT = "job_search_agent"


class JobAgent(ITaskAgent):
    """The job agent's stand-in: one task at a time; it records any message it gets."""

    def __init__(self) -> None:
        self.current: str | None = None
        self.messages: list[tuple[str, str]] = []
        self.assigned: list[str] = []

    def info(self) -> AgentInfo:
        return AgentInfo(agent_id=JOB_AGENT, description="job agent", state=AgentState.IDLE)

    async def assign(self, task) -> Result:
        self.current = task.id
        self.assigned.append(task.text)
        return Result.ok()

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        self.messages.append((task_id, text))
        return Result.ok()

    async def cancel(self, task_id: str) -> Result:
        return Result.ok()

    async def answer_permission(self, task_id, allow):
        return Result.ok()

    async def set_permission_mode(self, mode):
        return Result.ok()

    async def request_approval(self, action, run):
        return Result.ok()

    def note(self, text: str) -> None:
        pass


AGENT = JobAgent()


class JobModule(ModuleProtocol):
    """The job module's stand-in: provides the agent and keeps cv's named events."""

    manifest = Manifest(id="job_fake", description="The job agent's stand-in", provides=(ITaskAgent,),
                        publishes=(AgentStateChanged,), listens_named=("cv.job_finished", "cv.job_submitted"))  # fmt: skip

    async def init(self, ctx: ModuleContext) -> None:
        self.ctx = ctx
        self.events: asyncio.Queue[ModuleEvent] = asyncio.Queue()
        ctx.provide(ITaskAgent, AGENT)
        ctx.subscribe_named("cv.job_finished", self.events.put)
        ctx.subscribe_named("cv.job_submitted", self.events.put)

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


async def test_cv_reports_the_end_and_the_submit_as_events_and_messages_no_one(tmp_path):
    AGENT.__init__()
    base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_Base.pdf")
    app = app_with(tmp_path, extra=(JobModule,))
    await app.start()
    try:
        job_module = app._lifecycle._active["job_fake"][0]
        parent = (await app.router.send(StartTask(text="apply to Acme", agent_id=JOB_AGENT))).value
        made = await use(app, "cv.task", caller=JOB_AGENT, company="Acme", role="Senior Engineer", jd_text=JD,
                         base_cv=str(base))  # fmt: skip
        assert made.is_ok, made.error
        child = (await app.router.send(GetTaskStatus(task_id=made.value["task_id"]))).value[0]
        assert child.agent_id == "cv_agent" and child.parent_task_id == parent  # the job agent may hub.send to it
        folder = read_job((await finished(app, made.value["task_id"])).result).work_dir

        async with asyncio.timeout(5):
            ended = await job_module.events.get()
        assert ended.name == "cv.job_finished" and ended.source == "cv"
        data = ended.data
        assert (data["reply_to"], data["task_id"], data["parent_task_id"], data["job_dir"]) == (
            JOB_AGENT, child.id, parent, folder)
        assert (data["company"], data["role"], data["state"]) == ("Acme", "Senior Engineer", "done")
        assert data["cv_result"] is None and "No valid CV_RESULT" in data["summary"]  # the fake worker has none
        await asyncio.sleep(0.2)
        assert AGENT.messages == [] and AGENT.assigned == ["apply to Acme"]  # no Hub child-result message

        submit = {"work_dir": folder, "result": {"submitted_at": "t1", "company": "Acme", "role": "Senior Engineer",
                                                 "pdf_path": "CV_Test_Acme.pdf", "final_score": 92}}  # fmt: skip
        assert await cv_module(app)._pass_submit(submit) == f"{JOB_AGENT} (published cv.job_submitted)"
        async with asyncio.timeout(5):
            submitted = await job_module.events.get()
        assert submitted.name == "cv.job_submitted" and submitted.data["reply_to"] == JOB_AGENT
        assert submitted.data["job_dir"] == folder and submitted.data["final_score"] == 92
        assert submitted.data["summary"].startswith("From the cv module: the CV for Senior Engineer at Acme")
        record = json.loads((Path(folder) / "job_start.json").read_text(encoding="utf-8"))
        assert record["replied"] == {"submitted_at": "t1", "to": JOB_AGENT, "how": "published cv.job_submitted"}
        assert await cv_module(app)._pass_submit(submit) is None  # the same Submit: passed on once
        await asyncio.sleep(0.1)
        assert job_module.events.empty() and AGENT.messages == [] and AGENT.assigned == ["apply to Acme"]
    finally:
        await app.stop()
