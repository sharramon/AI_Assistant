"""The job agent, bundled with its own module (the multi-agent note's decision).

One `ProfileAgent` (agent id `job_search_agent` by default, the module id plus `_agent`, as for
every module agent; `agent_id` in config) working in the job project
(`C:\\Chang\\Jobs\\CV`, see docs/job-project), provided as `ITaskAgent`, so the Agent Hub lists
it, starts its tasks, holds its questions behind its tab's **!**, and feeds its `STATUS:` lines to
the coordinator. Its config section takes `ProfileAgent`'s keys; `chrome = true` gives it the
Claude in Chrome tools. It starts in Manual, like every agent.

Its access (workspace, folders, Python, commands, Chrome) is asked for when it's turned on, in one
request (`request_access`, subject `job_search_agent`): from the saved grant when the list is
unchanged, otherwise on your card. The agent is built from what you allowed. A grant widened
later (`permissions.grant`, or the agent's own `permissions.request`) reaches it live
(`AgentKit.follow_grant` → `ProfileAgent.set_access`), with no off and on.

Its menu: `job.search`, which answers at once and later sends its result to the caller as an
`AgentNotice` (the Hub hands it to that agent at its next turn). The search runner isn't built
yet: today the notice says so, and the job agent runs the project's `company-sweep` skill itself.

The project's `handoff.ps1` is replaced by the agent's `HANDOFF:` line (a fresh session), and the
project never submits or sends anything: the prompt says both.
"""

from __future__ import annotations

import asyncio

from assistant.contracts import (
    AgentNotice,
    ITaskAgent,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    PermissionChanged,
    Result,
)
from assistant.infra import AGENT_LISTENS, AGENT_PUBLISHES, AGENT_SENDS, AGENT_USES, AgentKit, ProfileAgent

menu = Menu()

JOB_PROMPT = """\
You are {agent_id}, the job-search agent of a personal AI assistant. You run the job project in \
your working folder: its CLAUDE.md and skills are yours to follow.

- Tasks reach you through the assistant; when the user turns to you, their words reach you \
unchanged. You never talk with the user in the main chat.
- One job per session. At the end of a job, write the next-session note and next_prompt.txt as \
the apply-session skill says, but don't run handoff.ps1: end with a last line \
`HANDOFF: <that note's path>` and a fresh session carries on.
- Never submit an application or send a message: fill the form and stop before Submit. The user \
submits.
- Confirm with the user (a NEED: question) before running any search, as the project's CLAUDE.md says."""

SEARCH_STUB = ("job.search: the search runner isn't built yet, so nothing ran ({days} days asked). "
               "Ask the job agent to run the company-sweep skill instead.")  # fmt: skip


class JobSearchModule(ModuleProtocol):
    manifest = Manifest(
        id="job_search",
        description="The job agent (applies to jobs, runs searches in the job project), with its job.* menu",
        provides=(ITaskAgent,),
        uses=AGENT_USES,
        sends=AGENT_SENDS,
        publishes=(*AGENT_PUBLISHES, AgentNotice,),
        listens=(*AGENT_LISTENS, PermissionChanged,),
        permissions=("agent.access",),
    )
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        config = dict(ctx.config)
        self._agent_id = str(config.pop("agent_id", f"{self.manifest.id}_agent"))
        config.setdefault("description", "The job agent: applies to one job per session and runs job searches")
        self._config = config
        self._agent: ProfileAgent | None = None
        self._work: set[asyncio.Task] = set()
        self._kit = AgentKit(ctx)  # resets it; a changed grant reaches it live
        self._kit.follow_grant(self._agent_id, config)

    async def start(self) -> None:
        """Ask for its access list (a card unless the saved grant still matches; AccessPending
        ends this start, and your Allow turns it on), then build the agent from what you allowed."""
        self._agent = await self._kit.open(self._agent_id, self._config, JOB_PROMPT.format(agent_id=self._agent_id),
                                           subject=self._agent_id,
                                           reason="the job agent's folders, commands and Chrome")  # fmt: skip

    async def stop(self) -> None:
        for task in self._work:
            task.cancel()
        await asyncio.gather(*self._work, return_exceptions=True)
        await self._kit.stop()

    def busy(self) -> str | None:
        """A reload restarts the agent, so it waits while it has a task or a search runs."""
        return self._kit.busy() or ("a job search is running" if self._work else None)

    @menu.item("job.search", "Start a job search; answers at once, and the result reaches you as a note at "
               "your next turn (the runner is a stub for now)",
               {"days": {"type": "integer", "minimum": 1}})  # fmt: skip
    async def search(self, days: int = 14, caller: str = "") -> Result:
        if not caller:
            return Result.invalid_arguments("job.search sends its result to its caller; there is none")
        task = asyncio.create_task(self._search(days, caller))
        self._work.add(task)
        task.add_done_callback(self._work.discard)
        return Result.ok(f"Search started ({days} days); the result reaches {caller} as a note")

    async def _search(self, days: int, caller: str) -> None:
        # The real runner (sweep.py with JobRadar's Python) goes here; see the job-agent note.
        self._ctx.publish(AgentNotice(agent_id=caller, text=SEARCH_STUB.format(days=days), source="job.search"))
