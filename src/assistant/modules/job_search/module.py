"""The job agent, bundled with its own module (the multi-agent note's decision).

One `ProfileAgent` (agent id `job_search_agent` by default, the module id plus `_agent`, as for
every module agent; `agent_id` in config) working in the job project, copied into this module's
own `workspace/` (gitignored; see docs/job-project.md), provided as `ITaskAgent`, so the Agent Hub lists
it, starts its tasks, holds its questions behind its tab's **!**, and feeds its `STATUS:` lines to
the coordinator. Its config section takes `ProfileAgent`'s keys; `chrome = true` gives it the
Claude in Chrome tools. It starts in Manual, like every agent.

`job_config` reads the two folder keys: `workspace` (default `workspace`, a relative one from this
module's folder) and `documents` (your CVs and cover letters, outside the repo; none by default,
yours in `config/local.toml`), which becomes a write folder on the access list.

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

cv stays off until the agent needs a CV (job_search's `needs` is empty: turning it on turns on only
job_search). Then the agent calls `job.tailor_cv` (only it may), which answers at once; in the
background this module turns cv on (`ActivateModule`: in Manual the user gets cv_agent's access card
now, and the module waits for cv to be on, up to `cv_wait` seconds, or stops at a Deny), then sends
`cv.task` for its agent (`for_agent`, allowed by cv's `[hand_off] modules`) and tells the agent the
outcome with a `DeliverMessage`. If cv can't come on or refuses the job, that message asks the agent
to ask the user whether to go on with the base PDF untailored.

cv's results reach the agent through cv's named events, never a direct message: cv publishes
`cv.job_finished` when its worker's task ends and `cv.job_submitted` at the user's Submit, with
`reply_to` the job agent. This module subscribes to both from its start (a named event is matched by
name, so cv may be off then), keeps the ones whose `reply_to` is its agent, and wakes the agent with
a `DeliverMessage` (`cv_finished_text`, `cv_submitted_text`), never into a running turn. The agent
then updates the job's tracker row as its project's skills say; the module writes nothing into the
job project.

The project's `handoff.ps1` is replaced by the agent's `HANDOFF:` line (a fresh session for the
same job only; a finished job ends with a plain report, so the task ends as done), and the
project never submits or sends anything: the prompt says both.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from assistant.contracts import (
    ActivateModule,
    AgentNotice,
    DeliverMessage,
    InvokeTool,
    ITaskAgent,
    Manifest,
    Menu,
    ModuleContext,
    ModuleEvent,
    ModuleProtocol,
    ModuleState,
    ModuleStateChanged,
    PermissionChanged,
    Result,
)
from assistant.infra import (
    AGENT_LISTENS,
    AGENT_PUBLISHES,
    AGENT_SENDS,
    AGENT_USES,
    AgentKit,
    ProfileAgent,
    copy_data_once,
    data_folder,
    in_module_folder,
)
from assistant.modules.job_search.ui import JobUi, ui_settings

MODULE_ID = "job_search"


def job_config(config: dict[str, Any]) -> dict[str, Any]:
    """The agent's config with its folders resolved: `workspace` (your `data_folder` when set, outside
    the repo; else `workspace`, default this module's own `workspace/`, gitignored) and `documents`
    (your CV folder, read and write; none by default) added to `write_dirs`, both relative from this
    module's folder when relative. ValueError if `documents` isn't a string or `data_folder` is wrong."""
    config = dict(config)
    data = data_folder(MODULE_ID, config)
    config.pop("data_folder", None)
    config["workspace"] = str(data or own_workspace(config))
    documents = config.pop("documents", "") or ""
    if not isinstance(documents, str):
        raise ValueError(f"job_search: documents must be a folder, not {documents!r}")
    if documents.strip():
        folder = str(in_module_folder(MODULE_ID, documents.strip()))
        writes = [str(d) for d in config.get("write_dirs", [])]
        config["write_dirs"] = writes if folder in writes else [*writes, folder]
    return config

def own_workspace(config: dict[str, Any]) -> Path:
    """The workspace a data folder replaces (`workspace`, default this module's own `workspace/`)."""
    return in_module_folder(MODULE_ID, config.get("workspace") or "workspace")


def copy_job_data(config: dict[str, Any]) -> bool:
    """Your data folder's first use (`data_folder` set, the folder missing or empty): the old
    workspace copied in (`copy_data_once`, never moved or deleted), then the copy's `job_paths.json`
    made to still point where it did: each relative path (the `cv_output` link into cv's workspace)
    written absolute, from the old workspace. True when it copied."""
    data = data_folder(MODULE_ID, config)
    if data is None or not copy_data_once(own_workspace(config), data):
        return False
    fix_copied_paths(own_workspace(config), data)
    return True


def fix_copied_paths(old: Path, new: Path) -> None:
    """Rewrite the relative paths of `new/job_paths.json` (a copy of `old`'s) as absolute ones from
    `old`, so the copied scripts find the same folders. A missing or unreadable file is left alone."""
    file = new / "job_paths.json"
    try:
        paths = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(paths, dict):
        return
    for key, value in paths.items():
        if isinstance(value, str) and value and not Path(os.path.expanduser(value)).is_absolute():
            paths[key] = Path(os.path.normpath(old / value)).as_posix()
    file.write_text(json.dumps(paths, indent=2) + "\n", encoding="utf-8")


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
CV = "cv"  # the module job.tailor_cv turns on and hands the job to
CV_WAIT = 600.0  # seconds job.tailor_cv waits for cv to come on (your answer on cv_agent's card); `cv_wait`
PENDING_CARD = "access card"  # in the error of a start that waits on its card (the core's AccessPending text)

_TAILOR_ARGS = {
    "company": {"type": "string", "minLength": 1, "description": "The job's company"},
    "role": {"type": "string", "minLength": 1, "description": "The job's title"},
    "base_cv": {"type": "string", "minLength": 1, "description": "The chosen base CV, a .pdf (its path)"},
    "jd_text": {"type": "string", "description": "The job description as text; or give jd_file"},
    "jd_file": {"type": "string", "description": "The job description as a file cv may read"},
    "jd_url": {"type": "string", "description": "The posting"},
    "degree_first": {"type": "boolean", "description": "Education under Skills (unset: cv's worker decides)"},
    "target_score": {"type": "integer", "minimum": 1, "maximum": 100, "description": "The ATS score to reach"},
    "notes": {"type": "string", "description": "Anything else for cv's worker"},
}  # fmt: skip

TAILOR_STARTED = ("The job module is turning cv on (in Manual the user gets cv_agent's access card now) and hands "
                  "it the CV job for {role} at {company}; the outcome reaches you as a message. Nothing more to "
                  "call: carry on with the form, or end your turn.")  # fmt: skip


def cv_taken_text(args: dict[str, Any], value: Any) -> str:
    """The agent's message when cv took the job: who has it, its task, and what comes next."""
    value = value if isinstance(value, dict) else {}
    task = value.get("task_id") or "?"
    return (f"cv has the CV job for {args['role']} at {args['company']}: {value.get('agent_id') or 'cv_agent'} is "
            f"on it (task {task}, your child task). Its end (cv.job_finished) and the user's Submit in the CV Tool "
            f"(cv.job_submitted) reach you as messages; the whole result: cv.read_result task_id={task}. "
            "Don't call cv.task for this job.")  # fmt: skip


def cv_untailored_text(args: dict[str, Any], why: str) -> str:
    """The agent's message when cv couldn't take the job: why, and the question for the user."""
    return (f"cv couldn't take the CV job for {args['role']} at {args['company']}: {why}. Ask the user (a NEED: "
            f"line) whether to go on with the chosen base PDF untailored ({args['base_cv']}).")  # fmt: skip


class _CvWait:
    """One job.tailor_cv waiting for cv to come on: what cv's state events and grants said."""

    def __init__(self) -> None:
        self.changed = asyncio.Event()
        self.state: ModuleState | None = None  # cv's last state seen
        self.starts = 0  # cv's STARTING events seen: the first is our own try, a second the start after Allow
        self.denied = ""  # the text of a PermissionChanged for cv with nothing granted (Deny, or the card closed)


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
        # DeliverMessage: wakes its agent with cv's events; ActivateModule, InvokeTool: job.tailor_cv turns cv on and sends cv.task
        # AgentNotice: job.search's result for its caller's next turn
        sends=(*AGENT_SENDS, DeliverMessage, ActivateModule, InvokeTool, AgentNotice),
        publishes=AGENT_PUBLISHES,
        listens=(*AGENT_LISTENS, PermissionChanged),  # ModuleStateChanged (in AGENT_LISTENS) and PermissionChanged: job.tailor_cv's wait for cv
        listens_named=(CV_FINISHED, CV_SUBMITTED),
        permissions=("agent.access",),
    )
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        config = job_config(ctx.config)  # a bad config stops the module here, with the reason
        await asyncio.to_thread(copy_job_data, ctx.config)  # your data folder's first use (never a move)
        self._agent_id = str(config.pop("agent_id", f"{self.manifest.id}_agent"))
        self._cv_wait = float(config.pop("cv_wait", CV_WAIT))
        self._cv_waits: set[_CvWait] = set()
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
        ctx.subscribe(ModuleStateChanged, self._on_cv_state)
        ctx.subscribe(PermissionChanged, self._on_cv_grant)

    async def _on_cv_state(self, event: ModuleStateChanged) -> None:
        if event.module_id != CV:
            return
        for wait in self._cv_waits:
            wait.state = event.state
            wait.starts += event.state is ModuleState.STARTING
            wait.changed.set()

    async def _on_cv_grant(self, event: PermissionChanged) -> None:
        if event.module_id != CV or event.granted:
            return
        for wait in self._cv_waits:
            wait.denied = event.text or "the user denied cv_agent's access card"
            wait.changed.set()

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
        return self._kit.busy() or ("a job search or a CV hand-off is running" if self._work else None)

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
        await self._ctx.send(AgentNotice(agent_id=caller, text=SEARCH_STUB.format(days=days), source="job.search"))

    @menu.item("job.tailor_cv", "Hands one job's CV to cv (only the job agent): answers at once; the job module "
               "turns cv on (cv_agent's access card is asked then), sends it the base PDF and the JD, and tells you "
               "the outcome as a message. cv's end and the user's Submit come later as messages too",
               _TAILOR_ARGS, required=["company", "role", "base_cv"])  # fmt: skip
    async def tailor_cv(self, company: str, role: str, base_cv: str, caller: str = "", **rest: Any) -> Result:
        if caller != self._agent_id:
            return Result.not_available(f"job.tailor_cv is only for {self._agent_id}")
        args = {"company": company, "role": role, "base_cv": base_cv, **rest}
        task = asyncio.create_task(self._tailor(args))
        self._work.add(task)
        task.add_done_callback(self._work.discard)
        return Result.ok(TAILOR_STARTED.format(role=role, company=company))

    async def _tailor(self, args: dict[str, Any]) -> None:
        """Turn cv on, send it `cv.task` for the agent, and tell the agent the outcome."""
        why = await self._cv_on()
        if why is None:
            sent = await self._ctx.send(InvokeTool(name="cv.task", args={**args, "for_agent": self._agent_id}))
            text = cv_taken_text(args, sent.value) if sent.is_ok else cv_untailored_text(args, sent.error or "refused")
        else:
            text = cv_untailored_text(args, why)
        told = await self._ctx.send(DeliverMessage(agent_id=self._agent_id, text=text, sender="job_search"))
        self._ctx.log.info("job.tailor_cv for %s at %s: %s -> %s", args["role"], args["company"],
                           "taken" if text.startswith("cv has") else "untailored",
                           told.value if told.is_ok else f"failed: {told.error}")  # fmt: skip

    async def _cv_on(self) -> str | None:
        """Turn cv on; None once it's on, else why not. A start that waits on cv_agent's access card
        waits for your answer (cv on: done; a Deny or a closed card: why), up to `cv_wait` seconds."""
        wait = _CvWait()
        self._cv_waits.add(wait)
        try:
            started = await self._ctx.send(ActivateModule(module_id=CV))
            if started.is_ok:
                return None
            if PENDING_CARD not in (started.error or ""):
                return f"cv didn't turn on: {started.error}"
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._cv_wait
            while True:
                if wait.state is ModuleState.ACTIVE:
                    return None
                if wait.denied:
                    return f"cv_agent's access card wasn't allowed: {wait.denied}"
                if wait.starts >= 2 and wait.state is ModuleState.FAILED:  # the start after your Allow failed
                    return "cv was allowed but didn't start (see the log)"
                left = deadline - loop.time()
                if left <= 0:
                    return f"no answer on cv_agent's access card in {self._cv_wait:g} seconds"
                wait.changed.clear()
                try:
                    await asyncio.wait_for(wait.changed.wait(), left)
                except TimeoutError:
                    pass
        finally:
            self._cv_waits.discard(wait)
