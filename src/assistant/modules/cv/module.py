"""cv: tailor a CV for one job with Rezi, one clean page, your yes.

Built so far (chunks 1 to 5): the wrapper, its config (defaults in `module.toml`, `[modules.cv]`
overrides), the CV content and the section order rules, `cv.build`: the one-page PDF, fitted,
checked and exported into the job's folder (`build.py`; its `.odt` stays in a temp folder), `cv.compare` (step 6, `compare.py`), `cv.report` (step 8's
`report.md`, `report.py`), the Rezi connection (`mcp.py`): `self.rezi`, an `McpClient` built from
the config, which connects only when an item uses it, and the `rezi.*` items (`rezi.py`) with the
resume guard (`guard.py`), `cv.read` (a CV PDF, `pdf_read.py`; the cv module takes PDFs only and
refuses an `.odt`), the worker `cv_agent` (chunk 6, `worker.py`), and the
job agent's hand-off (chunk 7, `handoff.py`): `cv.task` starts cv_agent on one job itself, as a
child of the caller's open task, with `tell_parent=False`. cv reports back only through named
events: `cv.job_finished` when cv_agent's job task ends, `cv.job_submitted` at the user's Submit,
each with the asker's id (`reply_to`); the asker's module hears them and wakes its agent. cv sends
the asker no message itself. `cv.read_result` checks the `CV_RESULT` line the worker ends with.

The worker is a `ProfileAgent` built the way `job_search` builds its agent: on start, one access
request for `[agent]`'s list (`request_access`, subject the agent's id: a card unless the saved
grant still matches, and the module turns on when you allow), then the agent from what you
allowed, provided as `ITaskAgent` so the Hub lists it and starts its tasks. A later grant reaches
it live, and a reset reaches it (`AgentKit`). `agent.enabled = false` gives the menu only, with no card. Its `claude`
session starts on its first task, never on load. The token lives in its file, and a reload hands
over only the ids of the resumes this module made (`export_state`).
"""

from __future__ import annotations

import asyncio
import json
import tomllib
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from assistant.contracts import (
    AgentNotice,
    DeliverMessage,
    GetTaskStatus,
    ITaskAgent,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    PermissionChanged,
    ReportKind,
    ResponseReady,
    Result,
    StartTask,
    TaskUpdated,
)
from assistant.infra import AGENT_LISTENS, AGENT_PUBLISHES, AGENT_SENDS, AGENT_USES, AgentKit, ProfileAgent
from assistant.modules.cv.build import build_cv
from assistant.modules.cv.compare import Comparison, FieldCompare
from assistant.modules.cv.content import SECTIONS, CvContent
from assistant.modules.cv.data import TOOL_PICKS, CvRequest, CvResult, check_cv_prefix, cv_prefix, set_cv_prefix
from assistant.modules.cv.guard import ResumeGuard
from assistant.modules.cv.handoff import (
    JOB_FINISHED,
    job_finished,
    read_jd_file,
    read_request,
    read_result,
    result_view,
    task_text,
)
from assistant.modules.cv.job_start import COMPANY_WORDS, JobStart, JobStartAgent, job_notes, name_part, read_record
from assistant.modules.cv.mcp import CALLBACK_PORT, REZI_URL, McpClient, OpenBrowser, TokenStore, default_token_file
from assistant.modules.cv.order import SectionOrder, wants_masters
from assistant.modules.cv.pdf import ExportError, PdfExport
from assistant.modules.cv.pdf_read import read_pdf
from assistant.modules.cv.reply import (
    JOB_SUBMITTED,
    job_submitted,
    mark_replied,
    pending_reply,
    rezi_click_text,
    submit_notice,
)
from assistant.modules.cv.report import ReportWriter, Round
from assistant.modules.cv.rezi import ReziTools, run
from assistant.modules.cv.submit_watch import SubmitWatch
from assistant.modules.cv.tool import MIN_PT_ADVICE, CvTool, ToolError, tool_settings
from assistant.modules.cv.worker import worker_config, worker_prompt

#: The job agent's hand-off items; `[hand_off] callers` may use them. Anyone may use OPEN_ITEMS;
#: every other item is only for the worker (`agent.agent_id`).
HAND_OFF_ITEMS = ("cv.task", "cv.read_result")
OPEN_ITEMS = ("rezi.status",)


class CallerMenu(Menu):
    """cv's menu: the core's checks, then who may call each item, from cv's config (the module's
    `may_call`). The caller is set by the core (the module door proves an agent's id with its
    token), so it can't be faked; the ids come from config, so no agent id is in the code."""

    async def call(self, module: Any, name: str, args: Any, caller: str = "") -> Result:
        refused = module.may_call(name, caller) if hasattr(module, "may_call") else None
        if refused is not None:
            return Result.not_available(refused)
        return await super().call(module, name, args, caller)


menu = CallerMenu()

PAPERS = ("letter", "a4")
REPO = Path(__file__).resolve().parents[4]  # src/assistant/modules/cv -> the repo: no token file in it

_BUILD_ARGS = {
    "company": {"type": "string", "minLength": 1, "description": "The job's company; names the folder and the files"},
    "base_cv": {"type": "string", "description": "Any .pdf to build from (read only; an .odt is refused); "
                "or give `sections`"},
    "job_dir": {"type": "string", "description": "The job's folder (CV_JOB's work_dir): the final PDF is exported "
                "there as <cv_prefix><Company>.pdf. Unset: <output_dir>/<date>_<Company>/"},
    "sections": {"type": "object", "description": f"The CV as section -> list of lines ({', '.join(SECTIONS)}); "
                 "`• ` starts a bullet, `left | dates` an entry line; the first contact line is the name"},
    "jd_text": {"type": "string", "description": "The job description: a master's in it puts Education under Skills"},
    "degree_first": {"type": "boolean", "description": "Education under Skills (overrides the guess from jd_text)"},
    "drop": {"type": "integer", "description": "Sections of the drop list (Publications, then Awards) left out from the start"},
    "auto_drop": {"type": "boolean", "description": "Leave out more of the drop list if it's still over a page (default true)"},
    "paper": {"type": "string", "enum": list(PAPERS), "description": "Overrides the config's paper"},
}  # fmt: skip

_LINES = "section -> list of lines, as for cv.build"
_COMPARE_ARGS = {
    "edited_pdf": {"type": "string", "description": "The edited CV as a PDF (the one cv.build made); or give `edited`"},
    "edited": {"type": "object", "description": f"The edited CV as {_LINES}"},
    "parsed": {"type": "object", "description": f"What Rezi read from the imported PDF, as {_LINES}; or give `parsed_text`"},
    "parsed_text": {"type": "string", "description": "What was read as one text (cv.build's `text`, or copied from Rezi): "
                    "checks only for missing lines"},
    "parsed_resume": {"type": "object", "description": "What was read as Rezi's resume JSON (rezi.read_resume's `data` "
                      "for the check copy), read into sections here"},
}  # fmt: skip

_EXTRA = {"type": "object", "description": "More arguments for Rezi's tool, passed as they are (if its live schema "
          "needs them: see rezi.sign_in's `check`)"}  # fmt: skip
_SIGN_IN_ARGS = {
    "force": {"type": "boolean", "description": "Sign in again even with a valid token (default false)"},
    "timeout": {"type": "integer", "minimum": 30, "maximum": 900, "description": "Seconds to wait for the browser (default 300)"},
}  # fmt: skip
_READ_ARGS = {"resume_id": {"type": "string", "minLength": 1, "description": "The resume's id (from rezi.list_resumes)"},
              "extra": _EXTRA}  # fmt: skip
_WRITE_ARGS = {
    "sections": {"type": "object", "description": "The CV as sections (cv.read's), written into Rezi's format here; "
                 "or give resume"},
    "name": {"type": "string", "description": "With sections: the resume's name, e.g. \"<Company> – <Role>\""},
    "job_title": {"type": "string", "description": "With sections: the job's title (Rezi's jobTitle)"},
    "job_company": {"type": "string", "description": "With sections: the job's company (Rezi's jobCompany)"},
    "jd_text": {"type": "string", "description": "With sections: the job description (Rezi's jobDescription)"},
    "resume": {"type": "object", "description": "Or the whole resume object in Rezi's format (name, jobTitle, "
               "jobCompany, jobDescription, data: see rezi.get_resume_format); no id in here"},
    "resume_id": {"type": "string", "description": "Only to update a resume this module made; leave out to make a new one"},
    "verify": {"type": "boolean", "description": "Read the resume back after the write (default true)"},
}  # fmt: skip
_KEYWORD_ARGS = {"resume_id": {"type": "string", "minLength": 1, "description": "A resume made here, written with the JD (jd_text)"}}
_SEARCH_ARGS = {"role": {"type": "string", "minLength": 1, "description": "The job title to search for"},
                "location": {"type": "string", "description": "Where"}, "extra": _EXTRA}  # fmt: skip
_JOB_ARGS = {"job_id": {"type": "string", "minLength": 1, "description": "A job's id from rezi.search_jobs"},
             "extra": _EXTRA}  # fmt: skip

_TASK_ARGS = {
    "company": {"type": "string", "minLength": 1, "description": "The job's company"},
    "role": {"type": "string", "minLength": 1, "description": "The job's title"},
    "jd_text": {"type": "string", "description": "The job description as text; or give jd_file"},
    "jd_file": {"type": "string", "description": "The job description as a .txt, .md or .html file in cv_dir, output_dir or work_dir "
                "(read into jd_text)"},
    "base_cv": {"type": "string", "minLength": 1, "description": "The base CV: any .pdf file, its path used as given "
                "(read only; it must exist; a non-.pdf such as an .odt is refused)"},
    "jd_url": {"type": "string", "description": "The posting"},
    "degree_first": {"type": "boolean", "description": "Education under Skills (unset: the worker decides from the JD)"},
    "target_score": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Overrides the config's target"},
    "notes": {"type": "string", "description": "Anything else for the worker"},
    "tool": {"type": "string", "enum": list(TOOL_PICKS), "description": "The CV Tool's pick (unset: the user "
             "picks Internal or Rezi in its tab 2)"},
}  # fmt: skip

_JOB_ID = {"job_id": {"type": "string", "minLength": 1, "description": "The CV Tool's job id (cv.open_tool's)"}}
_STRINGS = {"type": "array", "items": {"type": "string"}}
_ROUND_ARGS = {
    **_JOB_ID,
    "content": {"type": "object", "description": "The whole CV in the app's shape (cv.tool_status's content, edited): "
                "name, contact, summary, skills [[label, text]], experience [{title, company, dates, bullets}], "
                "education [{degree, detail}], awards, publications, education_first. Prints a new local PDF"},
    "export": {"type": "boolean", "description": "Print a new local PDF (default: true when content is given)"},
    "score": {"type": "integer", "minimum": 0, "maximum": 100, "description": "The ATS score read for this PDF"},
    "categories": {"type": "object", "description": "The score's categories, name -> score"},
    "matched": _STRINGS | {"description": "Matched keywords"},
    "missing": _STRINGS | {"description": "Missing keywords"},
    "issues": _STRINGS | {"description": "The scorer's biggest issues"},
    "changes": {"type": "string", "description": "What changed in this round"},
    "note": {"type": "string", "description": "A note for the round"},
    "request_id": {"type": "string", "description": "The pending Rezi request this round answers (cv.tool_status)"},
    "tool": {"type": "string", "enum": list(TOOL_PICKS), "description": "Who scored it (default the job's pick)"},
}  # fmt: skip

_REPORT_ARGS = {
    "company": {"type": "string", "minLength": 1, "description": "The job's company"},
    "role": {"type": "string", "description": "The job's title"},
    "result": {"type": "object", "description": "The job's CvResult: status, stop_reason, pdf_path, "
               "report_path, rezi_resume, check_copy, target_score, rounds, scores, missing_keywords, "
               "keywords_left_out, recommendations, match_ok, compare, one_page, section_order, order_reason, "
               "approved_by_user"},
    "rounds": {"type": "array", "items": {"type": "object"}, "description": "Each score round: score, added "
               "(keywords added), missing (still missing), note; else the result's rounds"},
    "compare": {"type": "object", "description": "cv.compare's value from step 6; else the result's compare"},
    "notes": {"type": "string", "description": "Anything else for the job agent"},
    "target_score": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Overrides the config's target"},
}  # fmt: skip


class CvModule(ModuleProtocol):
    manifest = Manifest(
        id="cv",
        description="Tailors a CV for one job with Rezi: one clean page, checked by Rezi, your yes; its worker cv_agent",
        provides=(ITaskAgent,),
        uses=AGENT_USES,
        # cv.task starts cv_agent (the caller's open task as parent); DeliverMessage: only to cv_agent
        # (the Rezi click)
        sends=(*AGENT_SENDS, StartTask, GetTaskStatus, DeliverMessage,),
        # ResponseReady: the one plain reminder of a Submit pressed while cv was down (submit_watch.py);
        # AgentNotice: cv_agent's line, for its next turn, that the watch passed a Submit on
        publishes=(*AGENT_PUBLISHES, ResponseReady, AgentNotice,),
        # the job's end and the user's Submit, for the asker's module (it wakes its agent)
        publishes_named=(JOB_FINISHED, JOB_SUBMITTED),
        # TaskUpdated: cv_agent's own end of a job task, published as cv.job_finished
        listens=(*AGENT_LISTENS, PermissionChanged, TaskUpdated,),
        permissions=("agent.access",),
    )  # fmt: skip
    menu = menu
    # Test seams: the tests point these at the fake Rezi. None: the network and the system browser.
    http_transport: Any = None
    open_browser: OpenBrowser | None = None
    # rezi.sign_in waits this long, then answers "waiting" (the door gives an item 30 s; the sign-in goes on)
    sign_in_wait: float = 20.0

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self.settings = settings(with_defaults(ctx.config))  # a bad config stops the module here, with the reason
        set_cv_prefix(self.settings["cv_prefix"])
        self._export = PdfExport(self.settings["soffice"])
        self.rezi = rezi_client(self.settings, self.http_transport)  # connects only when a rezi.* item uses it
        # a reload hands over {"guard", "tool"}; a copy from before the CV Tool handed over the guard's value only
        given = ctx.handover if isinstance(ctx.handover, dict) and "guard" in ctx.handover else {"guard": ctx.handover}
        self.guard = ResumeGuard.from_value(given.get("guard"))  # the resumes made before a reload
        self.tool = CvTool(given.get("tool"), self.settings["tool"], self.settings["work_dir"], ctx.log,
                           max_rounds=self.settings["max_rounds"])  # fmt: skip
        self._telling = asyncio.Lock()  # the Submit watch and cv.tool_result: one Submit passed on at a time
        ctx.subscribe(TaskUpdated, self._on_task)  # cv_agent's job ends -> cv.job_finished
        # delivers each live Submit; one missed while cv was down is only reminded (submit_watch.py);
        # each live Send JD and CV to Rezi click goes to cv_agent (_tell_worker_rezi)
        data_dir = self.settings["tool"]["data_dir"]
        self._watch = SubmitWatch(self.tool, self._deliver_submit, ctx.log, remind=self._remind,
                                  seen_path=Path(data_dir) / "submits_seen.json" if data_dir else None,
                                  on_rezi=self._tell_worker_rezi)  # fmt: skip
        self.tool.on_running = self._watch.follow
        self._tools = ReziTools(self.rezi, self.guard, self.open_browser)
        self.worker: ProfileAgent | None = None
        self.gate: JobStartAgent | None = None  # the worker as the Hub sees it (job_start.py)
        self._job_start = JobStart(self.settings["work_dir"], self.settings["cv_dir"], self.settings["job_skills"],
                                   rules_dir=self.settings["rules_dir"])  # fmt: skip
        worker = self.settings["agent"]
        self._agent_id: str = worker["agent_id"]
        self._kit: AgentKit | None = None  # resets and live grants, with the worker on
        if worker["enabled"]:
            self._kit = AgentKit(ctx)
            self._kit.follow_grant(self._agent_id, worker["config"])

    async def start(self) -> None:
        """With the worker on: ask for its access list (a card unless the saved grant still
        matches; AccessPending ends this start and your Allow turns cv on), then build it from
        what you allowed. Its session starts on its first task. A CV Tool already running (kept
        across a reload) is watched for Submits from now on; one pressed while cv was down is
        only reminded to the user, never delivered by itself."""
        if await self.tool.running():
            self._watch.follow()
        if self._kit is None:
            return
        prompt = worker_prompt(self._agent_id, self.settings, self.settings["cv_dir"])
        config = self.settings["agent"]["config"]
        # The Hub reaches the worker only through the gate, which sets up each job first. It's
        # provided before the worker, so the Hub's lookup (the first provider per id) finds the gate
        # while the kit opens the worker; then the worker's own agent is taken back.
        gate = JobStartAgent(self._job_start, self._agent_id, config["description"], self._ctx.log)
        self._ctx.provide(ITaskAgent, gate)
        try:
            self.worker = await self._kit.open(self._agent_id, config, prompt, subject=self._agent_id,
                                               reason="the CV worker's folders and Chrome (only app.rezi.ai)")  # fmt: skip
        except BaseException:
            self._ctx.withdraw(ITaskAgent, gate)
            raise
        self._ctx.withdraw(ITaskAgent, self.worker.agent)
        gate.attach(self.worker.agent)
        # A question's key is its job's folder; a late answer gets that job's notes (job_start.job_notes).
        self.worker.agent.set_context(gate.question_key, job_notes)
        self.gate = gate

    async def stop(self) -> None:
        await self._watch.stop()
        self._tools.cancel_sign_in()
        if self._kit is not None:
            await self._kit.stop()
        self.worker = self.gate = None
        await self.tool.stop()  # quits the CV Tool only if this copy launched it and didn't hand it over

    def busy(self) -> str | None:
        """A reload restarts the worker, so it waits while the worker has a task."""
        if (self._tools.sign_in_state() or {}).get("state") == "waiting":
            return "a Rezi sign-in is waiting for the browser"
        return self.worker.busy() if self.worker is not None else None

    def export_state(self) -> Any:
        """The resumes made here, and the running CV Tool (None if its code changed: it restarts)."""
        return {"guard": self.guard.as_value(), "tool": self.tool.export()}

    # --- rezi.*: Rezi's tools ----------------------------------------------------------------------------

    @menu.item("rezi.sign_in", "Signs in to Rezi in the browser (OAuth) and keeps the 30-day token; lists Rezi's tools",
               _SIGN_IN_ARGS)  # fmt: skip
    async def rezi_sign_in(self, force: bool = False, timeout: int = 300) -> Result:
        if not 30 <= timeout <= 900:
            return Result.invalid_arguments("rezi.sign_in: timeout must be 30 to 900 seconds")
        result = await run("rezi.sign_in", self._tools.start_sign_in(force, float(timeout), self.sign_in_wait))
        self._ctx.log.info("rezi.sign_in: %s", result.status)
        return result

    @menu.item("rezi.status", "Signed in to Rezi or not, the token's days left, the resumes made here (never connects)")
    async def rezi_status(self) -> Result:
        return Result.ok(self._tools.status())

    @menu.item("rezi.list_resumes", "Your Rezi resumes, most recently changed first")
    async def rezi_list_resumes(self) -> Result:
        return await run("rezi.list_resumes", self._tools.list_resumes())

    @menu.item("rezi.read_resume", "One Rezi resume's content, also as the CV's sections", _READ_ARGS,
               required=["resume_id"])  # fmt: skip
    async def rezi_read_resume(self, resume_id: str, extra: dict[str, Any] | None = None) -> Result:
        return await run("rezi.read_resume", self._tools.read_resume(resume_id, extra))

    @menu.item("rezi.get_resume_format", "The sections and fields Rezi's resume format has, for a write")
    async def rezi_get_resume_format(self) -> Result:
        return await run("rezi.get_resume_format", self._tools.get_resume_format())

    @menu.item("rezi.write_resume", "Makes a new Rezi resume, or updates one this module made; every other is refused",
               _WRITE_ARGS)  # fmt: skip
    async def rezi_write_resume(self, resume: dict[str, Any] | None = None, resume_id: str = "", verify: bool = True,
                                sections: dict[str, Any] | None = None, name: str = "", job_title: str = "",
                                job_company: str = "", jd_text: str = "") -> Result:  # fmt: skip
        if bool(resume) == bool(sections):
            return Result.invalid_arguments("rezi.write_resume: give the CV's sections or a resume object, one of them")
        if sections:
            if not name.strip() and not resume_id:
                return Result.invalid_arguments("rezi.write_resume: a new resume from sections needs its name")
            if not all(isinstance(v, list) and all(isinstance(line, str) for line in v) for v in sections.values()):
                return Result.invalid_arguments("rezi.write_resume: each section is a list of lines")
            try:
                work = self._tools.write_cv(sections, name.strip(), resume_id or None, job_title, job_company,
                                            jd_text, verify)  # fmt: skip
                result = await run("rezi.write_resume", work)
            except ValueError as exc:  # an unknown section
                return Result.invalid_arguments(f"rezi.write_resume: {exc}")
        else:
            result = await run("rezi.write_resume", self._tools.write_resume(resume or {}, resume_id or None, verify))
        made = result.value.get("resume_id") if result.is_ok else None
        self._ctx.log.info("rezi.write_resume %s: %s %s", resume_id or "(new)", result.status, made or result.error)
        return result

    @menu.item("rezi.generate_keywords", "Rezi's keywords for the job description saved on a resume this module made",
               _KEYWORD_ARGS, required=["resume_id"])  # fmt: skip
    async def rezi_generate_keywords(self, resume_id: str) -> Result:
        return await run("rezi.generate_keywords", self._tools.generate_keywords(resume_id))

    @menu.item("rezi.search_jobs","Searches Rezi's job listings by role and location", _SEARCH_ARGS, required=["role"])
    async def rezi_search_jobs(self, role: str, location: str = "", extra: dict[str, Any] | None = None) -> Result:
        return await run("rezi.search_jobs", self._tools.search_jobs(role, location, extra))

    @menu.item("rezi.get_job_details", "One job's full details from rezi.search_jobs", _JOB_ARGS, required=["job_id"])
    async def rezi_get_job_details(self, job_id: str, extra: dict[str, Any] | None = None) -> Result:
        return await run("rezi.get_job_details", self._tools.get_job_details(job_id, extra))

    # --- cv.task / cv.read_result: the job agent's hand-off ------------------------------------------------

    @menu.item("cv.task", "Checks one job (the JD as text, the base CV as any .pdf) and starts cv_agent "
               "on it as your child task; its end and the user's Submit go out as cv's events (cv.job_finished, "
               "cv.job_submitted), which your module turns into messages for you (the job agent's hand-off)",
               _TASK_ARGS, required=["company", "role", "base_cv"])  # fmt: skip
    async def task(self, company: str, role: str, base_cv: str, jd_text: str = "", jd_file: str = "",
                   jd_url: str = "", degree_first: bool | None = None, target_score: int | None = None,
                   notes: str = "", tool: str | None = None, caller: str = "") -> Result:  # fmt: skip
        if bool(jd_text.strip()) == bool(jd_file):
            return Result.invalid_arguments("cv.task: give the job description as jd_text or jd_file, one of them")
        try:
            if jd_file:
                if not self._readable(jd_file):
                    raise ValueError(f"jd_file {jd_file} isn't in the CV folder, the output folder or the work folder")
                jd_text = await asyncio.to_thread(read_jd_file, jd_file)
            request = CvRequest(company=company, role=role, jd_text=jd_text, base_cv=base_cv, jd_file=jd_file or None,
                                jd_url=jd_url or None, degree_first=degree_first, target_score=target_score,
                                notes=notes, tool=tool or None, reply_to=caller)  # fmt: skip
        except ValueError as exc:  # a ValidationError is one too
            return Result.invalid_arguments(f"cv.task: {exc}")
        if not Path(base_cv).is_file():
            return Result.invalid_arguments(f"cv.task: base_cv not found: {base_cv}")
        if self.worker is None:
            return Result.not_available("cv.task: cv's worker is off (agent.enabled = false), so no one takes the job")
        text = task_text(request, self._agent_id)
        tasks = await self._ctx.send(GetTaskStatus())
        open_tasks = [t for t in (tasks.value or []) if not t.state.is_final] if tasks.is_ok else []
        parent = next((t.id for t in reversed(open_tasks) if t.agent_id == caller), None)
        # tell_parent=False: the end goes out only as cv.job_finished (_on_task), not as a Hub message too.
        started = await self._ctx.send(StartTask(text=text, agent_id=self._agent_id, parent_task_id=parent,
                                                 tell_parent=False))  # fmt: skip
        if not started.is_ok:
            self._ctx.log.info("cv.task from %s refused: %s", caller, started.error)
            return Result(status=started.status, error=f"cv.task: {self._agent_id} can't take this job now: "
                          f"{self._on_job(open_tasks) or started.error}. Nothing was queued; try again "
                          "when it's free")  # fmt: skip
        self._ctx.log.info("cv.task from %s: task %s on %s", caller, started.value, self._agent_id)
        return Result.ok({"agent_id": self._agent_id, "task_id": started.value, "text": text,
                          "next": f"Nothing more to call, and don't wait: end your turn. {self._agent_id} has "
                                  f"the job (task {started.value}, your child task: hub.send to it if you need "
                                  "to). When its task ends (with a CV_RESULT line: status \"ready\", or "
                                  "\"stopped\"), cv publishes cv.job_finished and your module wakes you with a "
                                  "message naming the job and the result; the whole result: cv.read_result "
                                  f"task_id={started.value}. The user then works in the CV Tool; at their Submit "
                                  "cv publishes cv.job_submitted and your module sends you the PDF and the score "
                                  "as a second message: that message is the user's yes"})  # fmt: skip

    def _on_job(self, open_tasks: list[Any]) -> str:
        """The job the worker's open task is on and who it's for, or "" (no open task, or no job in it)."""
        own = next((t for t in reversed(open_tasks) if t.agent_id == self._agent_id), None)
        if own is None:
            return ""
        try:
            job = read_request(own.text)
        except ValueError:
            return f"it's on task {own.id}"
        return f"it's on the CV for {job.role} at {job.company} (task {own.id}, for {job.reply_to or 'the user'})"

    def _remind(self, text: str) -> None:
        """One plain notice to the user, in the chat of the tab in focus."""
        self._ctx.log.info("cv: %s", text)
        self._ctx.publish(ResponseReady(text=text))

    async def _on_task(self, event: TaskUpdated) -> None:
        """cv_agent's own end (done or failed) of a job task: publish `cv.job_finished` with the
        job's asker (`reply_to`, from its `job_start.json`), so the asker's module wakes its agent.
        A cancel, another agent's end or a task with no job folder publishes nothing."""
        if event.agent_id != self._agent_id or event.kind not in (ReportKind.DONE, ReportKind.FAILED):
            return
        folder = self.gate.question_key(event.task_id) if self.gate is not None else ""
        if not folder:
            return
        record = await asyncio.to_thread(read_record, Path(folder))
        data = job_finished(self._agent_id, event.task_id, str(event.state), event.parent_task_id, folder, record,
                            event.text)  # fmt: skip
        if not data["reply_to"]:
            self._ctx.log.info("cv: task %s ended %s; no reply_to in %s, so no %s", event.task_id, event.state,
                               folder, JOB_FINISHED)  # fmt: skip
            return
        self._ctx.publish_named(JOB_FINISHED, data)
        self._ctx.log.info("cv: task %s ended %s; published %s for %s", event.task_id, event.state, JOB_FINISHED,
                           data["reply_to"])  # fmt: skip

    async def _deliver_submit(self, value: dict[str, Any]) -> str | None:
        """The Submit watch's delivery: `_pass_submit`, and cv_agent gets one line about it for its
        next turn (an `AgentNotice`: never a wake). cv.tool_result needs none: its caller sees "told"."""
        return await self._pass_submit(value, notice=True)

    async def _tell_worker_rezi(self, item: dict[str, Any]) -> str | None:
        """The user clicked Send JD and CV to Rezi: cv_agent gets one message (`DeliverMessage`, never
        into a running turn: it answers an open NEED or waits for the turn's end), so it starts the First
        Draft by itself. Gives how it went, or None with the worker off."""
        if self.worker is None:
            self._ctx.log.info("cv: the Rezi request %s: no one told (the worker is off)", item.get("request_id"))
            return None
        sent = await self._ctx.send(DeliverMessage(agent_id=self._agent_id, text=rezi_click_text(item), sender="cv"))
        how = str(sent.value) if sent.is_ok else f"failed: {sent.error}"
        self._ctx.log.info("cv: the Rezi request %s of %s for %s: %s", item.get("request_id"), item.get("job_id"),
                           self._agent_id, how)  # fmt: skip
        return how

    async def _pass_submit(self, value: dict[str, Any], notice: bool = False) -> str | None:
        """The user submitted: publish `cv.job_submitted` for the job's `reply_to` once per Submit
        (reply.py), never refused (small text goes along as a warning). The asker's module wakes
        its agent; cv messages no one. Called by the Submit watch and by cv.tool_result. With
        `notice`, cv_agent is told it went out. Gives who and how, or None (no job folder, nobody
        asked, or passed on already)."""
        result = dict(value.get("result") or {})
        result.setdefault("small_text", value.get("small_text") or [])
        submitted = str(result.get("submitted_at") or "")
        try:
            folder = self._job_folder(str(value.get("work_dir") or ""))
        except ValueError:
            return None
        async with self._telling:
            to = await asyncio.to_thread(pending_reply, folder, submitted)
            if to is None:
                return None
            job_id = str(value.get("job_id") or result.get("job_id") or Path(folder).name)
            self._ctx.publish_named(JOB_SUBMITTED, job_submitted(to, job_id, folder, result))
            how = f"published {JOB_SUBMITTED}"
            self._ctx.log.info("cv: the Submit of %s for %s: %s", job_id, to, how)
            await asyncio.to_thread(mark_replied, folder, submitted, to, how)
            if notice:
                self._ctx.publish(AgentNotice(agent_id=self._agent_id, source="cv",
                                              text=submit_notice(result, job_id, to)))  # fmt: skip
        return f"{to} ({how})"

    @menu.item("cv.read_result", "Reads and checks the CV_RESULT line at the end of a cv_agent task's result: give "
               "task_id (cv reads the ended task's whole result) or the result's text, one of them",
               {"task_id": {"type": "string", "minLength": 1, "description": "The cv_agent task's id (your child task)"},
                "text": {"type": "string", "minLength": 1, "description": "The task's result text"}})  # fmt: skip
    async def read_result_item(self, text: str = "", task_id: str = "") -> Result:
        if bool(text) == bool(task_id):
            return Result.invalid_arguments("cv.read_result: give task_id or text, one of them")
        if task_id:
            status = await self._ctx.send(GetTaskStatus(task_id=task_id))
            task = status.value[0] if status.is_ok and status.value else None
            if task is None or task.agent_id != self._agent_id:
                return Result.invalid_arguments(f"cv.read_result: no {self._agent_id} task {task_id!r}")
            if not task.state.is_final or not task.result:
                return Result.not_available(f"cv.read_result: task {task_id} hasn't ended with a result yet "
                                            f"({task.state})")  # fmt: skip
            text = task.result
        try:
            result = read_result(text)
        except ValueError as exc:
            return Result.invalid_arguments(f"cv.read_result: {exc}")
        return Result.ok(await asyncio.to_thread(result_view, result, self.settings["target_score"]))

    # --- cv.open_tool / cv.tool_*: the CV Tool, the module's UI half (tool.py) ------------------------------

    @menu.item("cv.open_tool", "Opens a job the job start set up (its folder) in the CV Tool, starting the app if "
               "needed; gives the app's job_id. Call it only when the user tells you to start",
               {"job_dir": {"type": "string", "minLength": 1, "description": "The job's folder (CV_JOB's work_dir)"}},
               required=["job_dir"])  # fmt: skip
    async def open_tool(self, job_dir: str) -> Result:
        try:
            folder = self._job_folder(job_dir)
        except ValueError as exc:
            return Result.invalid_arguments(f"cv.open_tool: {exc}")
        return await self._tool_call("cv.open_tool", self.tool.open(folder))

    @menu.item("cv.tool_status", "One CV Tool job: the pick (Internal or Rezi, empty: not picked yet), the CV's "
               "content and text, a pending Rezi request, the loop (score, issues, rounds) and Submit's state",
               _JOB_ID, required=["job_id"])  # fmt: skip
    async def tool_status(self, job_id: str) -> Result:
        return await self._tool_call("cv.tool_status", self.tool.status(job_id))

    @menu.item("cv.tool_round", "Sends one round to the CV Tool: the edited content (prints the local PDF) and/or "
               "the score read for it; gives the PDF, its text under 10 pt, the loop and the rules checklist",
               _ROUND_ARGS, required=["job_id"])  # fmt: skip
    async def tool_round(self, job_id: str, **fields: Any) -> Result:
        return await self._tool_call("cv.tool_round", self.tool.round(job_id, fields))

    @menu.item("cv.tool_draft", "The Internal First Draft, with no agent: the proposals (Skills reordered by JD rank, "
               "backed JD terms to add, terms that need the user's yes); with apply, the reorder and the named "
               "backed terms are put in and an Internal round scores it",
               {**_JOB_ID,
                "apply": {"type": "boolean", "description": "Put the proposals in and score (default false: proposals only)"},
                "reorder": {"type": "boolean", "description": "With apply: reorder the Skills items (default true)"},
                "add": _STRINGS | {"description": "With apply: backed terms from the proposals' add list to put in "
                                   "(a term not on the CVs is refused: it needs the user's yes in the app)"}},
               required=["job_id"])  # fmt: skip
    async def tool_draft(self, job_id: str, apply: bool = False, reorder: bool = True,
                         add: list[str] | None = None) -> Result:  # fmt: skip
        return await self._tool_call("cv.tool_draft", self.tool.draft(job_id, apply, reorder, add))

    @menu.item("cv.tool_internal_round", "One Internal ATS Loop round, with no agent: prints the current CV, scores it "
               "with the Internal estimate and gives the loop with the matched and missing keywords",
               _JOB_ID, required=["job_id"])  # fmt: skip
    async def tool_internal_round(self, job_id: str) -> Result:
        return await self._tool_call("cv.tool_internal_round", self.tool.internal_round(job_id))

    @menu.item("cv.check_fonts", "The CV Tool job's current PDF: any text under 10 pt (measured from the PDF; a warning)",
               _JOB_ID, required=["job_id"])  # fmt: skip
    async def check_fonts(self, job_id: str) -> Result:
        return await self._tool_call("cv.check_fonts", self.tool.fonts(job_id))

    @menu.item("cv.tool_result", "The user's Submit in the CV Tool: result.json once they submitted (ready), never "
               "refused; small_text (text under 10 pt) is a warning only. The module already passed the Submit "
               "on (cv.job_submitted) when the user submitted", _JOB_ID, required=["job_id"])  # fmt: skip
    async def tool_result(self, job_id: str) -> Result:
        result = await self._tool_call("cv.tool_result", self.tool.result(job_id))
        if result.is_ok and result.value.get("ready") and (told := await self._pass_submit(result.value)):
            result.value["told"] = told  # passed on for the asking agent now
        return result

    async def _tool_call(self, name: str, work: Any) -> Result:
        try:
            value = await work
        except ToolError as exc:
            return Result.failed(f"{name}: the CV Tool says: {exc}")
        except (ValueError, ValidationError) as exc:
            return Result.invalid_arguments(f"{name}: {exc}")
        except RuntimeError as exc:  # pypdf's layout reader changed
            return Result.not_available(f"{name}: {exc}")
        except (OSError, TimeoutError) as exc:
            return Result.not_available(f"{name}: the CV Tool didn't start or answer: {exc}")
        if value.get("small_text"):
            value["next"] = MIN_PT_ADVICE
        self._ctx.log.info("%s: %s", name, value.get("job_id") or value.get("id") or "ok")
        return Result.ok(value)

    def may_call(self, name: str, caller: str) -> str | None:
        """Why `caller` may not use item `name`, or None (checked by `CallerMenu` on every call):
        the hand-off items for `[hand_off] callers`, OPEN_ITEMS for anyone, the rest for the worker."""
        if name in OPEN_ITEMS:
            return None
        allowed = self.settings["hand_off"]["callers"] if name in HAND_OFF_ITEMS else (self._agent_id,)
        if caller in allowed:
            return None
        return f"{name} is only for: {', '.join(allowed)}"

    def _readable(self, path: str) -> bool:
        """`path` is in the CV folder, the output folder or the jobs' work folder (what cv.task's
        jd_file and cv.compare's edited_pdf may read; cv.read and base_cv take any .pdf)."""
        roots = [Path(r).resolve() for r in (self.settings["cv_dir"], self.settings["output_dir"],
                                             self.settings["work_dir"]) if r]  # fmt: skip
        return any(Path(path).resolve().is_relative_to(r) for r in roots)

    # --- cv.*: the one page --------------------------------------------------------------------------------

    @menu.item("cv.read", "Reads a CV PDF (the base CV's copy in the job's folder, a draft or another of your CVs) "
               "as its sections, with the read check: every word placed, or the unplaced text to ask you about",
               {"pdf": {"type": "string", "minLength": 1, "description": "The path of any existing .pdf, used as "
                        "given (a non-.pdf, an .odt too, is refused)"}},
               required=["pdf"])  # fmt: skip
    async def read(self, pdf: str) -> Result:
        try:
            _check_pdf(pdf, "pdf")
            read = await asyncio.to_thread(read_pdf, pdf)
        except (ValueError, ValidationError) as exc:
            return Result.invalid_arguments(f"cv.read: {exc}")
        except RuntimeError as exc:  # pypdf's layout reader changed
            return Result.not_available(f"cv.read: {exc}")
        content = read.content
        sections = {n: list(content.lines(n)) for n in content.names()}
        value: dict[str, Any] = {"pdf": pdf, "sections": sections, "names": content.names(), "pages": read.pages,
                                 "complete": read.complete, "unplaced": list(read.unplaced)}  # fmt: skip
        if not read.complete:
            value["next"] = ("Stop: some of the PDF's text couldn't be placed in a section (unplaced). Don't guess: "
                             "ask the user with NEED:, naming the unplaced text, before using these sections.")  # fmt: skip
        return Result.ok(value)

    @menu.item("cv.build", "Builds and exports the one-page PDF of a CV into the job's folder (job_dir), fitted and "
               "checked; no .odt comes out", _BUILD_ARGS, required=["company"])  # fmt: skip
    async def build(
        self,
        company: str,
        base_cv: str = "",
        sections: dict[str, Any] | None = None,
        jd_text: str = "",
        degree_first: bool | None = None,
        drop: int = 0,
        auto_drop: bool = True,
        paper: str = "",
        job_dir: str = "",
    ) -> Result:
        try:
            content = await asyncio.to_thread(_content, base_cv, sections)
        except (ValueError, ValidationError) as exc:
            return Result.invalid_arguments(f"cv.build: {exc}")
        except RuntimeError as exc:
            return Result.not_available(f"cv.build: {exc}")
        if drop < 0:
            return Result.invalid_arguments("cv.build: drop must be 0 or more")
        try:
            pdf_path = self._pdf_target(company, job_dir)
        except ValueError as exc:
            return Result.invalid_arguments(f"cv.build: {exc}")
        if pdf_path is None:
            return Result.not_available("cv.build: no output_dir in the cv module's config, and no job_dir given")
        if base_cv and pdf_path.resolve() == Path(base_cv).resolve():
            return Result.invalid_arguments("cv.build: the output would overwrite the base CV")
        if degree_first is None:
            degree_first = wants_masters(jd_text)
        try:
            built = await asyncio.to_thread(
                build_cv, content, self.settings["order"], pdf_path, self._export,
                paper=paper or self.settings["paper"], degree_first=degree_first, drop=drop, auto_drop=auto_drop,
            )  # fmt: skip
        except FileNotFoundError as exc:
            return Result.not_available(f"cv.build: {exc}")
        except ExportError as exc:
            return Result.failed(f"cv.build: {exc}", retryable=True)
        except ValueError as exc:
            return Result.invalid_arguments(f"cv.build: {exc}")
        self._ctx.log.info("cv.build %s: %d page(s), %s", pdf_path, built.report.pages, built.layout.describe())
        return Result.ok(built.as_value())

    def _pdf_target(self, company: str, job_dir: str) -> Path | None:
        """Where cv.build saves the PDF: `<job_dir>/<cv_prefix><Company>.pdf` (job_dir must be a job's
        folder in work_dir), else `output_path`; None with neither. Never over the job's copy of
        its base CV: the copy is `base_…` now, but a job folder made before that holds it under the
        base CV's own name, and then the PDF's name gets `_tailored`. ValueError if job_dir isn't allowed."""
        if not job_dir:
            return output_path(self.settings["output_dir"], company) if self.settings["output_dir"] else None
        folder = self._job_folder(job_dir)
        target = folder / output_path("", company).name
        if target.resolve() in _job_copies(folder):
            target = target.with_name(f"{target.stem}_tailored.pdf")
        return target

    def _job_folder(self, job_dir: str) -> Path:
        """`job_dir` resolved, if it's a job's folder in the work folder. ValueError otherwise."""
        work = self.settings["work_dir"]
        folder = Path(job_dir).resolve()
        if not (work and folder.is_relative_to(Path(work).resolve()) and folder != Path(work).resolve()):
            raise ValueError(f"job_dir must be a job's folder in the work folder {work or '(no work_dir)'}, not {job_dir}")
        if not folder.is_dir():
            raise ValueError(f"job_dir not found: {job_dir}")
        return folder

    @menu.item("cv.compare", "Compares what Rezi read from the PDF with the edited CV: same content or the issues",
               _COMPARE_ARGS)  # fmt: skip
    async def compare(
        self,
        edited_pdf: str = "",
        edited: dict[str, Any] | None = None,
        parsed: dict[str, Any] | None = None,
        parsed_text: str = "",
        parsed_resume: dict[str, Any] | None = None,
    ) -> Result:
        if edited_pdf and not self._readable(edited_pdf):
            return Result.invalid_arguments(f"cv.compare: {edited_pdf} isn't in the CV, output or work folder")
        try:
            mine = await asyncio.to_thread(_content, edited_pdf, edited, "edited_pdf", "edited")
            if [bool(parsed), bool(parsed_text.strip()), bool(parsed_resume)].count(True) != 1:
                raise ValueError("give one of parsed (sections), parsed_text or parsed_resume")
            fields = FieldCompare()
            if parsed:
                comparison = fields.diff(mine, _content("", parsed, "", "parsed"))
            elif parsed_resume:
                comparison = fields.diff(mine, CvContent.from_rezi(parsed_resume))
            else:
                comparison = fields.diff_text(mine, parsed_text)
        except (ValueError, ValidationError) as exc:
            return Result.invalid_arguments(f"cv.compare: {exc}")
        except RuntimeError as exc:
            return Result.not_available(f"cv.compare: {exc}")
        self._ctx.log.info("cv.compare: %s", comparison.summary())
        return Result.ok(comparison.as_value())

    @menu.item("cv.report", "Writes report.md next to the job's PDF: result, score rounds, keywords left out, the compare",
               _REPORT_ARGS, required=["company", "result"])  # fmt: skip
    async def report(
        self,
        company: str,
        result: dict[str, Any],
        role: str = "",
        rounds: list[dict[str, Any]] | None = None,
        compare: dict[str, Any] | None = None,
        notes: str = "",
        target_score: int | None = None,
    ) -> Result:
        try:
            outcome = CvResult.model_validate(result)
            steps = [Round.model_validate(r) for r in rounds or []]
            comparison = Comparison.from_value(compare) if compare else None
            if target_score is not None and not 1 <= target_score <= 100:
                raise ValueError("target_score must be 1 to 100")
        except (ValueError, ValidationError) as exc:
            return Result.invalid_arguments(f"cv.report: {exc}")
        roots = [Path(r).resolve() for r in (self.settings["output_dir"], self.settings["work_dir"]) if r]
        if outcome.pdf_path:
            folder = Path(outcome.pdf_path).parent.resolve()
        elif self.settings["output_dir"]:
            folder = output_path(self.settings["output_dir"], company).parent.resolve()
        else:
            return Result.not_available("cv.report: no pdf_path in the result and no output_dir in the cv module's config")
        if not any(folder.is_relative_to(r) for r in roots):
            return Result.invalid_arguments(f"cv.report: {folder} isn't in the output folder or the work folder")
        target = target_score if target_score is not None else outcome.target_score or self.settings["target_score"]
        writer = ReportWriter(target)
        try:
            path = writer.write(folder, outcome, company, role, steps, comparison, notes)
        except ValueError as exc:
            return Result.invalid_arguments(f"cv.report: {exc}")
        self._ctx.log.info("cv.report %s: %s", path, outcome.status)
        return Result.ok({"report_path": str(path), "text": path.read_text(encoding="utf-8")})


def _check_pdf(path: str, arg: str) -> None:
    """ValueError unless `path` is a PDF that exists (an `.odt` is refused: the cv module takes PDFs only)."""
    suffix = Path(path).suffix.lower()
    if suffix == ".odt":
        raise ValueError(f"{arg}: an .odt isn't read; give a .pdf")
    if suffix != ".pdf":
        raise ValueError(f"{arg} must be a .pdf, not {Path(path).name}")
    if not Path(path).is_file():
        raise ValueError(f"{arg} not found: {path}")


def _job_copies(folder: Path) -> set[Path]:
    """The base CV copies the job start put in `folder` (its job_start.json), resolved."""
    try:
        record = json.loads((folder / "job_start.json").read_text(encoding="utf-8"))
        return {Path(record["job"]["base_cv_copy"]).resolve()}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def _content(pdf: str, sections: dict[str, Any] | None, pdf_arg: str = "base_cv", sections_arg: str = "sections") -> CvContent:
    """A CV from a PDF (every word placed: `CvContent.from_pdf`) or from sections given as lists of
    lines (exactly one of them). `pdf_arg`, `sections_arg`: the item's argument names, for the error."""
    if bool(pdf) == bool(sections):
        either = f"{pdf_arg} (a PDF) or {sections_arg}" if pdf_arg else sections_arg
        raise ValueError(f"give either {either}, not both or neither" if pdf_arg else f"give {either}")
    if pdf:
        _check_pdf(pdf, pdf_arg)
        return CvContent.from_pdf(pdf)
    lines: dict[str, tuple[str, ...]] = {}
    for name, value in (sections or {}).items():
        if not (isinstance(value, list) and all(isinstance(line, str) for line in value)):
            raise ValueError(f"{sections_arg}[{name!r}] must be a list of lines (strings)")
        lines[name] = tuple(value)
    return CvContent(sections=lines)


def output_path(output_dir: str | Path, company: str, today: date | None = None, prefix: str | None = None) -> Path:
    """`<output_dir>/<date>_<Company>/<cv_prefix><Company>.pdf`, the company made safe for a file
    name the way the job's work folder names it (`name_part`). `prefix` None: the configured one."""
    safe = name_part(company, COMPANY_WORDS, "Company")
    day = (today or date.today()).isoformat()
    return Path(output_dir) / f"{day}_{safe}" / f"{cv_prefix() if prefix is None else prefix}{safe}.pdf"


DEFAULTS = Path(__file__).with_name("module.toml")


def with_defaults(config: dict[str, Any], defaults: Path = DEFAULTS) -> dict[str, Any]:
    """`config` over cv's own `module.toml`, key by key (tables one level deep). The core already
    does this; an app started before that core change passes only `[modules.cv]`, so cv does it
    too (found in the first real run, 2026-11-07). Same result either way."""
    with defaults.open("rb") as f:
        merged: dict[str, Any] = tomllib.load(f)
    for key, value in config.items():
        base = merged.get(key)
        merged[key] = {**base, **value} if isinstance(base, dict) and isinstance(value, dict) else value
    return merged


def settings(config: dict[str, Any]) -> dict[str, Any]:
    """The checked config: `order` (a `SectionOrder`) plus the plain values. ValueError if one is wrong."""
    paper = str(config.get("paper", "letter")).lower()
    if paper not in PAPERS:
        raise ValueError(f"cv: paper must be one of {list(PAPERS)}, not {paper!r}")
    target, rounds = config.get("target_score", 90), config.get("max_rounds", 5)
    if not (isinstance(target, int) and 1 <= target <= 100):
        raise ValueError(f"cv: target_score must be 1 to 100, not {target!r}")
    if not (isinstance(rounds, int) and rounds >= 1):
        raise ValueError(f"cv: max_rounds must be 1 or more, not {rounds!r}")
    url = str(config.get("rezi_url") or REZI_URL)
    host = urlparse(url).hostname or ""
    if not (url.startswith("https://") and host or url.startswith("http://") and host in ("127.0.0.1", "localhost")):
        raise ValueError(f"cv: rezi_url must be https:// (http:// only on this machine), not {url!r}")
    token_file = Path(str(config.get("token_file") or default_token_file())).expanduser()
    if token_file.resolve().is_relative_to(REPO):
        raise ValueError(f"cv: token_file must be outside the repo, not {token_file}")
    port = config.get("callback_port", CALLBACK_PORT)
    if not (isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535):
        raise ValueError(f"cv: callback_port must be 1 to 65535, not {port!r}")
    output_dir = str(config.get("output_dir", ""))
    cv_dir = str(config.get("cv_dir", ""))
    prefix = check_cv_prefix(config.get("cv_prefix", "CV_Test_"))
    agent = worker_config(config.get("agent", {"enabled": False}), output_dir)  # no table: the menu only
    work_dir, job_skills = job_folders(config, agent, cv_dir)
    workspace = str(agent["config"].get("workspace") or "")
    rules = Path(str(config.get("rules_dir") or "")).expanduser() if config.get("rules_dir") else None
    rules_dir = "" if rules is None else str(rules if rules.is_absolute() or not workspace else Path(workspace) / rules)
    callers = dict(config.get("hand_off", {})).get("callers", [])  # an old `coordinator` key is ignored
    if not (isinstance(callers, list) and all(isinstance(c, str) and c for c in callers)):
        raise ValueError(f"cv: hand_off.callers must be a list of agent ids, not {callers!r}")
    return {
        "hand_off": {"callers": tuple(callers)},
        "rules_dir": rules_dir,  # the cv module's general rules (SKILL.md + rules/*.md), loaded at every job
        "tool": tool_settings(config.get("tool", {}), cv_dir, rules_dir, workspace, prefix),
        "cv_prefix": prefix,  # the start of the PDFs made (and of the CVs the CV Tool lists); not a rule for base_cv
        "order": SectionOrder.from_config(config),
        "paper": paper,
        "target_score": target,
        "max_rounds": rounds,
        "output_dir": output_dir,
        "cv_dir": cv_dir,
        "work_dir": work_dir,
        "job_skills": job_skills,
        "soffice": str(config.get("soffice", "")),
        "rezi_url": url,
        "token_file": str(token_file),
        "callback_port": port,
        "agent": agent,
    }


def job_folders(config: dict[str, Any], agent: dict[str, Any], cv_dir: str) -> tuple[str, list[str]]:
    """The checked `work_dir` (each job's folder goes in it; "" = `<the worker's workspace>/work`)
    and `job_skills` (the rule files every job loads; `~` expanded, a relative path from the
    workspace). The work folder must be in the worker's workspace, so it can write its drafts there,
    and never in `cv_dir` or the repo. ValueError if one is wrong. The rule files themselves are
    read at each job's start, which refuses a missing one."""
    workspace = str(agent["config"].get("workspace") or "")
    work_dir = str(config.get("work_dir") or (Path(workspace) / "work" if workspace else ""))
    skills = config.get("job_skills", [])
    if not (isinstance(skills, list) and all(isinstance(s, str) and s.strip() for s in skills)):
        raise ValueError("cv: job_skills must be a list of file paths")
    if agent["enabled"] and not skills:
        raise ValueError("cv: job_skills must name the rule files every job loads (the worker is on)")
    if not work_dir:
        return "", []  # no worker workspace and no work_dir: no worker, so no job starts
    work = Path(work_dir).expanduser().resolve()
    if cv_dir and work.is_relative_to(Path(cv_dir).resolve()):
        raise ValueError(f"cv: work_dir must be outside your CV folder {cv_dir}, not {work_dir}")
    if work.is_relative_to(REPO):
        raise ValueError(f"cv: work_dir must be outside the repo, not {work_dir}")
    if agent["enabled"] and workspace and not work.is_relative_to(Path(workspace).resolve()):
        raise ValueError(f"cv: work_dir must be in the worker's workspace {workspace}, not {work_dir}")
    base = Path(workspace) if workspace else work
    paths = [Path(s).expanduser() for s in skills]
    return str(work), [str(p if p.is_absolute() else base / p) for p in paths]


def rezi_client(checked: dict[str, Any], http_transport: Any = None) -> McpClient:
    """The Rezi connection from the checked config. Builds only: nothing is read, written or sent.
    `http_transport`: a test server instead of the network."""
    return McpClient(TokenStore(checked["token_file"]), checked["rezi_url"], http_transport=http_transport,
                     callback_port=checked["callback_port"])  # fmt: skip
