"""agent-talk-and-questions, step 1: cv.task makes cv_agent's task a child of the asker's open task, and
the user's Submit reaches the asker through the Hub's `DeliverMessage`: at its turn's end, into its
open task (which answers a question it waits on). No coordinator and no notice."""

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
    """The job agent's stand-in: one task at a time; `working` says it's in a turn."""

    def __init__(self) -> None:
        self.current: str | None = None
        self.working = False
        self.messages: list[tuple[str, str]] = []

    def info(self) -> AgentInfo:
        state = AgentState.ACTIVE if self.working else AgentState.IDLE
        return AgentInfo(agent_id=JOB_AGENT, description="job agent", state=state)

    async def assign(self, task) -> Result:
        self.current = task.id
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
    manifest = Manifest(id="job_fake", description="The job agent's stand-in", provides=(ITaskAgent,),
                        publishes=(AgentStateChanged,))  # fmt: skip

    async def init(self, ctx: ModuleContext) -> None:
        self.ctx = ctx
        ctx.provide(ITaskAgent, AGENT)

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


async def test_the_job_is_the_askers_child_and_the_submit_reaches_it_at_its_turns_end(tmp_path):
    AGENT.__init__()
    base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_Base.pdf")
    app = app_with(tmp_path, extra=(JobModule,))
    await app.start()
    try:
        parent = (await app.router.send(StartTask(text="apply to Acme", agent_id=JOB_AGENT))).value
        made = await use(app, "cv.task", caller=JOB_AGENT, company="Acme", role="Senior Engineer", jd_text=JD,
                         base_cv=str(base))  # fmt: skip
        assert made.is_ok, made.error
        child = (await app.router.send(GetTaskStatus(task_id=made.value["task_id"]))).value[0]
        assert child.agent_id == "cv_agent" and child.parent_task_id == parent  # the job agent may hub.send to it
        folder = read_job((await finished(app, made.value["task_id"])).result).work_dir

        AGENT.working = True  # the job agent is in a turn: the Submit waits for its end
        submit = {"work_dir": folder, "result": {"submitted_at": "t1", "company": "Acme", "role": "Senior Engineer",
                                                 "pdf_path": "CV_Test_Acme.pdf", "final_score": 92}}  # fmt: skip
        assert await cv_module(app)._tell_asker(submit) == f"{JOB_AGENT} (pending)"
        assert AGENT.messages == []
        AGENT.working = False
        app._lifecycle._active["job_fake"][0].ctx.publish(AgentStateChanged(agent_id=JOB_AGENT, state=AgentState.IDLE))
        async with asyncio.timeout(5):
            while not AGENT.messages:
                await asyncio.sleep(0.02)
        (task, text), = AGENT.messages
        assert task == parent and text.startswith("[Message from cv] From the cv module: the CV for Senior Engineer")
        record = json.loads((Path(folder) / "job_start.json").read_text(encoding="utf-8"))
        assert record["replied"] == {"submitted_at": "t1", "to": JOB_AGENT, "how": "pending"}
        assert await cv_module(app)._tell_asker(submit) is None  # the same Submit: told once
    finally:
        await app.stop()
