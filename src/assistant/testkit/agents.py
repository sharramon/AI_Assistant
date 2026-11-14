"""Agent fakes for tests: the fake `claude` process, a Hub with a Main Assistant on it, stubs to drive
a `SessionTaskAgent` by hand, and a task agent that only records what the Hub asks of it."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from assistant.contracts import (
    AgentInfo,
    AgentState,
    GetTaskStatus,
    InvokeTool,
    ITaskAgent,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ReportKind,
    ReportTask,
    Result,
    Task,
    TaskUpdated,
)

HERE = Path(__file__).parent
# The fake `claude -p` (stream-json), run as a subprocess: a module config's `program`.
FAKE = [sys.executable, str(HERE / "fake_claude.py")]
# A stand-in for the job project's job UI, run as a script.
FAKE_JOB_UI = str(HERE / "fake_job_ui.py")
TIMEOUT = 10.0


async def next_matching(queue: asyncio.Queue, predicate):
    """The next item on `queue` that `predicate` accepts, within `TIMEOUT`."""
    async with asyncio.timeout(TIMEOUT):
        while not predicate(event := await queue.get()):
            pass
    return event


def report(kind: ReportKind):
    """A predicate for `next_matching`: a `TaskUpdated` of this report kind."""
    return lambda event: event.kind is kind


async def start_hub(tmp_path, **main_config):
    """A started App with the Agent Hub and a Main Assistant on the fake `claude`, and a queue of
    its `TaskUpdated` events. The caller stops the app."""
    from assistant.core import App
    from assistant.modules.agent_hub import AgentHubModule
    from assistant.modules.main_assistant import MainAssistantModule

    config = {
        "modules": {
            "enabled": ["agent_hub", "main_assistant"],
            "main_assistant": {"program": FAKE, "workspace": str(tmp_path), **main_config},
        },
        "core": {},
    }
    app = App([AgentHubModule, MainAssistantModule], config)
    updates: asyncio.Queue[TaskUpdated] = asyncio.Queue()
    app.bus.subscribe(TaskUpdated, updates.put)
    await app.start()
    return app, updates


class StubSession:
    """Just enough of a `ClaudeSession` to drive a `SessionTaskAgent` by hand."""

    def __init__(self):
        self.on_event = None
        self.running = self.working = True
        self.context_tokens, self.id = 0, "stub"
        self.used = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
        self.subagents: dict[str, dict] = {}
        self.sent: list[str] = []
        self.interrupts = 0

    async def start(self):
        self.running = True

    async def close(self):
        self.running = False

    async def send(self, text):
        self.sent.append(text)

    async def interrupt(self):
        self.interrupts += 1

    async def answer_permission(self, *args):
        pass


class StubContext:
    """Just enough of a `ModuleContext` for a `SessionTaskAgent`: a log, no events, every command ok,
    and the contracts in `provided` (`{IPageOpener: a_fake}`; none by default)."""

    def __init__(self):
        self.log = logging.getLogger("test")
        self.provided: dict = {}
    def publish(self, event):
        pass

    async def send(self, command):
        return Result.ok()

    def get_one(self, contract):
        return self.provided.get(contract)


class FakeAgent(ITaskAgent):
    """A task agent that only records what the Hub asks of it."""

    def __init__(self, agent_id: str, folders: tuple[str, ...]) -> None:
        self.agent_id, self.folders = agent_id, folders
        self.busy = False  # holds a task (assign refuses a second)
        self.working = False  # in a turn: the Hub never delivers into it
        self.calls: list[tuple] = []
        self.notes: list[str] = []
        self.ctx: ModuleContext | None = None

    def info(self) -> AgentInfo:
        return AgentInfo(agent_id=self.agent_id, description="fake",
                         state=AgentState.ACTIVE if self.working else AgentState.IDLE, write_folders=self.folders)

    async def assign(self, task: Task) -> Result:
        if self.busy:
            return Result.not_available(f"{self.agent_id} is active")
        self.busy = True
        self.calls.append(("assign", task.id, task.text))
        return Result.ok()

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        self.calls.append(("message", task_id, text))
        return Result.ok()

    async def cancel(self, task_id: str) -> Result:
        self.busy = False
        self.calls.append(("cancel", task_id))
        return Result.ok()

    async def answer_permission(self, task_id: str, allow: bool) -> Result:
        self.calls.append(("permission", task_id, allow))
        return Result.ok()

    def note(self, text: str) -> None:
        self.notes.append(text)


def agent_module(agent_id: str, folders: tuple[str, ...]) -> tuple[type, FakeAgent]:
    """A module class providing one `FakeAgent` as its `ITaskAgent`, and that agent."""
    agent = FakeAgent(agent_id, folders)

    class FakeAgentModule(ModuleProtocol):
        manifest = Manifest(id=agent_id, description="A fake agent", provides=(ITaskAgent,),
                            sends=(ReportTask, InvokeTool))  # fmt: skip

        async def init(self, ctx: ModuleContext) -> None:
            agent.ctx = ctx
            ctx.provide(ITaskAgent, agent)

        async def start(self) -> None: ...

        async def stop(self) -> None: ...

    return FakeAgentModule, agent


async def status(app: Any, task_id: str):
    """A task's `TaskInfo` from the Hub (`GetTaskStatus`)."""
    return (await app.router.send(GetTaskStatus(task_id=task_id))).value[0]
