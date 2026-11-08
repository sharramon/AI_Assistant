"""The job agent bundled with its module: an ITaskAgent beside the others, Chrome, its job.search callback."""

import asyncio

from assistant.contracts import (
    AgentNotice,
    AnswerPermissionRequest,
    InvokeTool,
    ListAgents,
    PermissionMode,
    PermissionRequested,
    Status,
)
from assistant.core import App
from assistant.infra.agent_profile import path_rule
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.job_search import JobSearchModule
from assistant.modules.job_search.module import JOB_PROMPT
from tests.support import pre_grant, wait_until
from tests.test_agents import FAKE


async def start_app(tmp_path) -> App:
    config = {
        "modules": {
            "enabled": ["agent_hub", "job_search"],
            "agent_hub": {"door": False},
            "job_search": {"program": FAKE, "workspace": str(tmp_path / "CV"), "chrome": True},
        },
        "core": {},
    }
    app = App([AgentHubModule, JobSearchModule], config)
    pre_grant(app, "job_search", "job_search_agent", config["modules"]["job_search"])
    await app.start()
    return app


async def test_the_job_agent_is_a_big_agent_with_chrome_and_the_projects_rules(tmp_path):
    app = await start_app(tmp_path)
    try:
        listed = await app.router.send(ListAgents())
        assert [a.agent_id for a in listed.value] == ["job_search_agent"] and listed.value[0].permission_mode is PermissionMode.MANUAL
        job = app._lifecycle._active["job_search"][0]._agent
        command = job.profile.command("prompt", PermissionMode.MANUAL)
        assert "--chrome" in command
        assert "don't run handoff.ps1" in JOB_PROMPT and "Never submit" in JOB_PROMPT
        assert job.profile.write_folders() == (str((tmp_path / "CV").resolve()),)
    finally:
        await app.stop()


async def test_job_search_answers_at_once_and_notes_its_caller(tmp_path):
    app = await start_app(tmp_path)
    notices: asyncio.Queue[AgentNotice] = asyncio.Queue()
    app.bus.subscribe(AgentNotice, notices.put)
    try:
        started = await app.router.send(InvokeTool(name="job.search", args={"days": 7}, caller="main_assistant"))
        assert started.is_ok and "main_assistant" in started.value
        notice = await asyncio.wait_for(notices.get(), 2)
        assert (notice.agent_id, notice.source) == ("main_assistant", "job.search") and "7 days" in notice.text
        nobody = await app.router.send(InvokeTool(name="job.search", args={}))
        assert nobody.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()


async def test_a_grant_reaches_the_job_agents_next_session_live(tmp_path):
    app = await start_app(tmp_path)
    cards: list[PermissionRequested] = []

    async def record(event):
        cards.append(event)

    app.bus.subscribe(PermissionRequested, record)
    try:
        job = app._lifecycle._active["job_search"][0]._agent
        snips = str(tmp_path / "logs" / "snips")
        assert path_rule("Read", snips) in ",".join(job.profile.command("p", PermissionMode.MANUAL, snips=snips))
        more = tmp_path / "drafts"
        asked = await app.router.send(InvokeTool(name="permissions.request", caller="job_search_agent",
                                                 args={"write": [str(more)], "read": [str(tmp_path / "jobs")]}))  # fmt: skip
        assert asked.is_ok, asked.error
        await wait_until(lambda: cards)
        await app.router.send(AnswerPermissionRequest(request_id=cards[0].request_id, allow=True,
                                                      keep=tuple(i.key for i in cards[0].items)))  # fmt: skip
        resolved = str(more.resolve())
        await wait_until(lambda: resolved in job.agent.info().write_folders)
        command = ",".join(job.profile.command("p", PermissionMode.MANUAL))
        assert path_rule("Edit", resolved) in command and path_rule("Read", str((tmp_path / "jobs").resolve())) in command
        assert app._lifecycle._active["job_search"][0]._agent is job  # no off and on
    finally:
        await app.stop()
