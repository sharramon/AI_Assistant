"""The job agent, bundled with its own module (the multi-agent note's decision).

One `ProfileAgent` (agent id `job_search_agent` by default, the module id plus `_agent`, as for
every module agent; `agent_id` in config) working in the job project
(`C:\\Chang\\Jobs\\CV`, see its docs/job-project.md), provided as `ITaskAgent`, so the Agent Hub lists
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
`job.open_ui` starts the job project's job UI if needed and opens its window on the Tracker
(`ui.py`: `JobUi`, through `CompanionHandover`, kept across a reload like the CV Tool).

cv's results reach the agent through cv's named events, never a direct message: the agent hands a
job to cv with the `cv.task` tool; cv publishes `cv.job_finished` when its worker's task ends and
`cv.job_submitted` at the user's Submit. This module subscribes to both, keeps the ones whose
`reply_to` is its agent, and wakes the agent with a `DeliverMessage` (`cv_finished_text`,
`cv_submitted_text`), never into a running turn. The agent then updates the job's tracker row as
its project's skills say; the module writes nothing into the job project.

The project's `handoff.ps1` is replaced by the agent's `HANDOFF:` line (a fresh session for the
same job only; a finished job ends with a plain report, so the task ends as done), and the
project never submits or sends anything: the prompt says both.
"""

from __future__ import annotations

import asyncio
from typing import Any

from assistant.contracts import (
    AgentNotice,
    DeliverMessage,
    ITaskAgent,
    Manifest,
    Menu,
    ModuleContext,
    ModuleEvent,
    ModuleProtocol,
    PermissionChanged,
    Result,
)
from assistant.infra import AGENT_LISTENS, AGENT_PUBLISHES, AGENT_SENDS, AGENT_USES, AgentKit, ProfileAgent
from assistant.modules.job_search.ui import JobUi, ui_settings

menu = Menu()

# The user's standing wish (2026-11-10): "open the UI" is job.open_ui at once, its own window every time.
# In the job prompt and in the agent's description, which its tab's Talker reads ("{agent}'s job: ...").
UI_SHORTCUT = ('"Open the UI" or "open the job UI" means calling job.open_ui (the job_search menu, with '
               "use_item) straight away, with no searching for a tool and no looking in the folder: it opens "
               "the job UI in its own window every time")  # fmt: skip

JOB_PROMPT = """\
You are {agent_id}, the job-search agent of a personal AI assistant. You run the job project in \
your working folder: its CLAUDE.md and skills are yours to follow.

- Tasks reach you through the assistant; when the user turns to you, their words reach you \
unchanged. You never talk with the user in the main chat.
- At the end of a job, write the next-session note and next_prompt.txt as the apply-session \
skill says, but don't run handoff.ps1, and finish with a normal final report: no `HANDOFF:` \
line, so the task ends as done. Use a last line `HANDOFF: <that note's path>` only to carry \
the same job on in a fresh session (your context is large, or you're asked to reset).
- Never submit an application or send a message: fill the form and stop before Submit. The user \
submits.
- Confirm with the user (a NEED: question) before running any search, as the project's CLAUDE.md says.
- {ui_shortcut}."""

SEARCH_STUB = ("job.search: the search runner isn't built yet, so nothing ran ({days} days asked). "
               "Ask the job agent to run the company-sweep skill instead.")  # fmt: skip

CV_FINISHED = "cv.job_finished"  # cv's worker ended a job's task (cv's handoff.job_finished has the data)
CV_SUBMITTED = "cv.job_submitted"  # the user pressed Submit in the CV Tool (cv's reply.job_submitted)


def cv_finished_text(data: dict[str, Any]) -> str:
    """The job agent's message when cv's worker ends a job: the job, the folder, the result in one
    line, and what next."""
    task = data.get("task_id") or "?"
    return (f"cv's worker {data.get('agent_id') or 'cv_agent'} ended {data.get('state') or '?'} on the CV for "
            f"{data.get('role') or '?'} at {data.get('company') or '?'} (task {task}, job folder "
            f"{data.get('job_dir') or '?'}).\n{data.get('summary') or ''}\n"
            "Next: update this job's row in the tracker as your project's skills say. The whole result: "
            f"cv.read_result task_id={task}. The user's Submit in the CV Tool, if any, comes later as its own "
            "message.")  # fmt: skip


def cv_submitted_text(data: dict[str, Any]) -> str:
    """The job agent's message at the user's Submit: cv's summary (the PDF, the score, the user's
    yes), the folder, and what next."""
    return (f"{data.get('summary') or 'The user submitted the CV in the CV Tool.'}\n"
            f"Job folder: {data.get('job_dir') or '?'} (CV Tool job {data.get('job_id') or '?'}).\n"
            "Next: update this job's row in the tracker as your project's skills say, then carry on with the "
            "application.")  # fmt: skip


class JobSearchModule(ModuleProtocol):
    manifest = Manifest(
        id="job_search",
        description="The job agent (applies to jobs, runs searches in the job project), with its job.* menu",
        provides=(ITaskAgent,),
        uses=AGENT_USES,
        sends=(*AGENT_SENDS, DeliverMessage,),  # DeliverMessage: wakes its agent with cv's events
        publishes=(*AGENT_PUBLISHES, AgentNotice,),
        listens=(*AGENT_LISTENS, PermissionChanged,),
        listens_named=(CV_FINISHED, CV_SUBMITTED),
        permissions=("agent.access",),
    )
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        config = dict(ctx.config)
        self._agent_id = str(config.pop("agent_id", f"{self.manifest.id}_agent"))
        config.setdefault("description", "The job agent: applies to one job per session and runs job searches. "
                          + UI_SHORTCUT)  # fmt: skip
        ui = ui_settings(config.pop("ui", {}), str(config.get("workspace", "")), str(config.get("python", "")))
        given = ctx.handover if isinstance(ctx.handover, dict) else {}
        self.ui = JobUi(given.get("ui"), ui, ctx.log)  # the running job UI from before a reload, if any
        self._config = config
        self._agent: ProfileAgent | None = None
        self._work: set[asyncio.Task] = set()
        self._kit = AgentKit(ctx)  # resets it; a changed grant reaches it live
        self._kit.follow_grant(self._agent_id, config)
        ctx.subscribe_named(CV_FINISHED, self._on_cv)
        ctx.subscribe_named(CV_SUBMITTED, self._on_cv)

    async def _on_cv(self, event: ModuleEvent) -> None:
        """One of cv's events for this module's agent (`reply_to`): wake it with one message."""
        data = event.data
        if data.get("reply_to") != self._agent_id:
            return
        text = cv_finished_text(data) if event.name == CV_FINISHED else cv_submitted_text(data)
        sent = await self._ctx.send(DeliverMessage(agent_id=self._agent_id, text=text, sender="job_search"))
        self._ctx.log.info("job_search: %s for %s -> %s", event.name, self._agent_id,
                           sent.value if sent.is_ok else f"failed: {sent.error}")  # fmt: skip

    async def start(self) -> None:
        """Ask for its access list (a card unless the saved grant still matches; AccessPending
        ends this start, and your Allow turns it on), then build the agent from what you allowed."""
        self._agent = await self._kit.open(self._agent_id, self._config, JOB_PROMPT.format(agent_id=self._agent_id, ui_shortcut=UI_SHORTCUT),
                                           subject=self._agent_id,
                                           reason="the job agent's folders, commands and Chrome")  # fmt: skip

    async def stop(self) -> None:
        for task in self._work:
            task.cancel()
        await asyncio.gather(*self._work, return_exceptions=True)
        await self._kit.stop()
        await self.ui.stop()

    def busy(self) -> str | None:
        """A reload restarts the agent, so it waits while it has a task or a search runs."""
        return self._kit.busy() or ("a job search is running" if self._work else None)

    def export_state(self) -> Any:
        """The running job UI, for the new copy (kept: its window stays)."""
        return {"ui": self.ui.export()}

    @menu.item("job.open_ui", "Opens the job UI (Tracker, Job stack, Live search, Keywords) in its own window on "
               "the Tracker page, every time: starts its local server first if it isn't answering, and closes "
               "the job UI window already open, so there's only one", {})  # fmt: skip
    async def open_ui(self) -> Result:
        try:
            opened = await self.ui.open()
        except (OSError, TimeoutError) as exc:
            return Result.not_available(f"job.open_ui: the job UI didn't start or answer: {exc}")
        return Result.ok(opened)

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
