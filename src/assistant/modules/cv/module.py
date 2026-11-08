"""cv: tailor a CV for one job with Rezi, one clean page, your yes.

Built so far (chunks 1 to 5): the wrapper, its config (defaults in `module.toml`, `[modules.cv]`
overrides), the CV content and the section order rules, `cv.build`: the one-page `.odt` and
PDF, fitted and checked (`build.py`), `cv.compare` (step 6, `compare.py`), `cv.report` (step 8's
`report.md`, `report.py`), the Rezi connection (`mcp.py`): `self.rezi`, an `McpClient` built from
the config, which connects only when an item uses it, and the `rezi.*` items (`rezi.py`) with the
resume guard (`guard.py`), `cv.read`, the worker `cv_agent` (chunk 6, `worker.py`), and the
job agent's hand-off (chunk 7, `handoff.py`): `cv.task` gives the `hub.start` text for one job,
`cv.read_result` checks the `CV_RESULT` line the worker ends with.

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
import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

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
from assistant.modules.cv.build import build_cv
from assistant.modules.cv.compare import Comparison, FieldCompare
from assistant.modules.cv.content import SECTIONS, CvContent
from assistant.modules.cv.data import CvRequest, CvResult
from assistant.modules.cv.guard import ResumeGuard
from assistant.modules.cv.handoff import read_jd_file, read_result, result_view, task_text
from assistant.modules.cv.mcp import CALLBACK_PORT, REZI_URL, McpClient, OpenBrowser, TokenStore, default_token_file
from assistant.modules.cv.order import SectionOrder, wants_masters
from assistant.modules.cv.pdf import ExportError, PdfExport
from assistant.modules.cv.report import ReportWriter, Round
from assistant.modules.cv.rezi import ReziTools, run
from assistant.modules.cv.worker import worker_config, worker_prompt

menu = Menu()

PAPERS = ("letter", "a4")
REPO = Path(__file__).resolve().parents[4]  # src/assistant/modules/cv -> the repo: no token file in it

_BUILD_ARGS = {
    "company": {"type": "string", "minLength": 1, "description": "The job's company; names the folder and the files"},
    "base_cv": {"type": "string", "description": "A CV_Test_*.odt to build from (read only); or give `sections`"},
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
    "edited_odt": {"type": "string", "description": "The edited CV as an .odt (the one cv.build made); or give `edited`"},
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
    "jd_file": {"type": "string", "description": "The job description as a .txt, .md or .html file in cv_dir or output_dir"},
    "base_cv": {"type": "string", "minLength": 1, "description": "The CV_Test_*.odt you recommend, in cv_dir (read only)"},
    "jd_url": {"type": "string", "description": "The posting"},
    "degree_first": {"type": "boolean", "description": "Education under Skills (unset: the worker decides from the JD)"},
    "target_score": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Overrides the config's target"},
    "notes": {"type": "string", "description": "Anything else for the worker"},
}  # fmt: skip

_REPORT_ARGS = {
    "company": {"type": "string", "minLength": 1, "description": "The job's company"},
    "role": {"type": "string", "description": "The job's title"},
    "result": {"type": "object", "description": "The job's CvResult: status, stop_reason, pdf_path, odt_path, "
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
        sends=AGENT_SENDS,
        publishes=(*AGENT_PUBLISHES, AgentNotice,),
        listens=(*AGENT_LISTENS, PermissionChanged,),
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
        self._export = PdfExport(self.settings["soffice"])
        self.rezi = rezi_client(self.settings, self.http_transport)  # connects only when a rezi.* item uses it
        self.guard = ResumeGuard.from_value(ctx.handover)  # the resumes made before a reload
        self._tools = ReziTools(self.rezi, self.guard, self.open_browser)
        self.worker: ProfileAgent | None = None
        worker = self.settings["agent"]
        self._agent_id: str = worker["agent_id"]
        self._kit: AgentKit | None = None  # resets and live grants, with the worker on
        if worker["enabled"]:
            self._kit = AgentKit(ctx)
            self._kit.follow_grant(self._agent_id, worker["config"])

    async def start(self) -> None:
        """With the worker on: ask for its access list (a card unless the saved grant still
        matches; AccessPending ends this start and your Allow turns cv on), then build it from
        what you allowed. Its session starts on its first task."""
        if self._kit is None:
            return
        prompt = worker_prompt(self._agent_id, self.settings, self.settings["cv_dir"])
        self.worker = await self._kit.open(self._agent_id, self.settings["agent"]["config"], prompt,
                                           subject=self._agent_id,
                                           reason="the CV worker's folders and Chrome (only app.rezi.ai)")  # fmt: skip

    async def stop(self) -> None:
        self._tools.cancel_sign_in()
        if self._kit is not None:
            await self._kit.stop()
        self.worker = None

    def busy(self) -> str | None:
        """A reload restarts the worker, so it waits while the worker has a task."""
        if (self._tools.sign_in_state() or {}).get("state") == "waiting":
            return "a Rezi sign-in is waiting for the browser"
        return self.worker.busy() if self.worker is not None else None

    def export_state(self) -> Any:
        return self.guard.as_value()

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

    @menu.item("cv.task", "Checks one job and gives the text to send to cv_agent with hub.start (the job agent's hand-off)",
               _TASK_ARGS, required=["company", "role", "base_cv"])  # fmt: skip
    async def task(self, company: str, role: str, base_cv: str, jd_text: str = "", jd_file: str = "",
                   jd_url: str = "", degree_first: bool | None = None, target_score: int | None = None,
                   notes: str = "") -> Result:  # fmt: skip
        if bool(jd_text.strip()) == bool(jd_file):
            return Result.invalid_arguments("cv.task: give the job description as jd_text or jd_file, one of them")
        try:
            if jd_file:
                if not self._readable(jd_file):
                    raise ValueError(f"jd_file {jd_file} isn't in the CV folder or the output folder")
                jd_text = await asyncio.to_thread(read_jd_file, jd_file)
            request = CvRequest(company=company, role=role, jd_text=jd_text, base_cv=base_cv, jd_file=jd_file or None,
                                jd_url=jd_url or None, degree_first=degree_first, target_score=target_score,
                                notes=notes)  # fmt: skip
        except ValueError as exc:  # a ValidationError is one too
            return Result.invalid_arguments(f"cv.task: {exc}")
        root = self.settings["cv_dir"]
        if not (root and Path(base_cv).resolve().is_relative_to(Path(root).resolve())):
            return Result.invalid_arguments(f"cv.task: base_cv must be one of your CVs in {root or 'cv_dir'}")
        if not Path(base_cv).is_file():
            return Result.invalid_arguments(f"cv.task: base_cv not found: {base_cv}")
        if self.worker is None:
            return Result.not_available("cv.task: cv's worker is off (agent.enabled = false), so no one takes the job")
        return Result.ok({"agent_id": self._agent_id, "text": task_text(request, self._agent_id),
                          "next": f"hub.start with this text and agent_id {self._agent_id!r}; the task's result "
                                  "ends with a CV_RESULT line: check it with cv.read_result"})  # fmt: skip

    @menu.item("cv.read_result", "Reads and checks the CV_RESULT line at the end of a cv_agent task's result",
               {"text": {"type": "string", "minLength": 1, "description": "The task's result text"}}, required=["text"])  # fmt: skip
    async def read_result_item(self, text: str) -> Result:
        try:
            result = read_result(text)
        except ValueError as exc:
            return Result.invalid_arguments(f"cv.read_result: {exc}")
        return Result.ok(await asyncio.to_thread(result_view, result, self.settings["target_score"]))

    def _readable(self, path: str) -> bool:
        """`path` is in the CV folder or the output folder (what cv.read and cv.task may read)."""
        roots = [Path(r).resolve() for r in (self.settings["cv_dir"], self.settings["output_dir"]) if r]
        return any(Path(path).resolve().is_relative_to(r) for r in roots)

    # --- cv.*: the one page --------------------------------------------------------------------------------

    @menu.item("cv.read", "Reads a CV .odt (in the CV folder or the output folder) as its sections, for the worker",
               {"odt": {"type": "string", "minLength": 1, "description": "A CV_Test_*.odt in cv_dir or output_dir"}},
               required=["odt"])  # fmt: skip
    async def read(self, odt: str) -> Result:
        path = Path(odt)
        if not self._readable(odt):
            return Result.invalid_arguments(f"cv.read: {odt} isn't in the CV folder or the output folder")
        try:
            content = await asyncio.to_thread(_content, odt, None, "odt")
        except (ValueError, ValidationError) as exc:
            return Result.invalid_arguments(f"cv.read: {exc}")
        sections = {n: list(content.lines(n)) for n in content.names()}
        return Result.ok({"odt": str(path), "sections": sections, "names": content.names()})

    @menu.item("cv.build", "Builds the one-page .odt and PDF of a CV in the output folder, fitted and checked",
               _BUILD_ARGS, required=["company"])  # fmt: skip
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
    ) -> Result:
        try:
            content = _content(base_cv, sections)
        except (ValueError, ValidationError) as exc:
            return Result.invalid_arguments(f"cv.build: {exc}")
        if drop < 0:
            return Result.invalid_arguments("cv.build: drop must be 0 or more")
        if not self.settings["output_dir"]:
            return Result.not_available("cv.build: no output_dir in the cv module's config")
        odt_path = output_path(self.settings["output_dir"], company)
        if base_cv and odt_path.resolve() == Path(base_cv).resolve():
            return Result.invalid_arguments("cv.build: the output would overwrite the base CV")
        if degree_first is None:
            degree_first = wants_masters(jd_text)
        try:
            built = await asyncio.to_thread(
                build_cv, content, self.settings["order"], odt_path, self._export,
                paper=paper or self.settings["paper"], degree_first=degree_first, drop=drop, auto_drop=auto_drop,
            )  # fmt: skip
        except FileNotFoundError as exc:
            return Result.not_available(f"cv.build: {exc}")
        except ExportError as exc:
            return Result.failed(f"cv.build: {exc}", retryable=True)
        except ValueError as exc:
            return Result.invalid_arguments(f"cv.build: {exc}")
        self._ctx.log.info("cv.build %s: %d page(s), %s", odt_path.name, built.report.pages, built.layout.describe())
        return Result.ok(built.as_value())

    @menu.item("cv.compare", "Compares what Rezi read from the PDF with the edited CV: same content or the issues",
               _COMPARE_ARGS)  # fmt: skip
    async def compare(
        self,
        edited_odt: str = "",
        edited: dict[str, Any] | None = None,
        parsed: dict[str, Any] | None = None,
        parsed_text: str = "",
        parsed_resume: dict[str, Any] | None = None,
    ) -> Result:
        try:
            mine = _content(edited_odt, edited, "edited_odt", "edited")
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
        if not self.settings["output_dir"]:
            return Result.not_available("cv.report: no output_dir in the cv module's config")
        root = Path(self.settings["output_dir"]).resolve()
        made = outcome.pdf_path or outcome.odt_path
        folder = (Path(made).parent if made else output_path(root, company).parent).resolve()
        if not folder.is_relative_to(root):
            return Result.invalid_arguments(f"cv.report: {folder} isn't in the output folder {root}")
        target = target_score if target_score is not None else outcome.target_score or self.settings["target_score"]
        writer = ReportWriter(target)
        try:
            path = writer.write(folder, outcome, company, role, steps, comparison, notes)
        except ValueError as exc:
            return Result.invalid_arguments(f"cv.report: {exc}")
        self._ctx.log.info("cv.report %s: %s", path, outcome.status)
        return Result.ok({"report_path": str(path), "text": path.read_text(encoding="utf-8")})


def _content(odt: str, sections: dict[str, Any] | None, odt_arg: str = "base_cv", sections_arg: str = "sections") -> CvContent:
    """A CV from an `.odt` or from sections given as lists of lines (exactly one of them).
    `odt_arg`, `sections_arg`: the item's argument names, for the error."""
    if bool(odt) == bool(sections):
        either = f"{odt_arg} (an .odt) or {sections_arg}" if odt_arg else sections_arg
        raise ValueError(f"give either {either}, not both or neither" if odt_arg else f"give {either}")
    if odt:
        if not odt.lower().endswith(".odt"):
            raise ValueError(f"{odt_arg} must be an .odt, not {Path(odt).name}")
        if not Path(odt).is_file():
            raise ValueError(f"{odt_arg} not found: {odt}")
        return CvContent.from_odt(odt)
    lines: dict[str, tuple[str, ...]] = {}
    for name, value in (sections or {}).items():
        if not (isinstance(value, list) and all(isinstance(line, str) for line in value)):
            raise ValueError(f"{sections_arg}[{name!r}] must be a list of lines (strings)")
        lines[name] = tuple(value)
    return CvContent(sections=lines)


def output_path(output_dir: str | Path, company: str, today: date | None = None) -> Path:
    """`<output_dir>/<date>_<Company>/CV_Test_<Company>.odt`, the company made safe for a file name."""
    safe = re.sub(r"[^A-Za-z0-9]+", "_", company).strip("_") or "Company"
    day = (today or date.today()).isoformat()
    return Path(output_dir) / f"{day}_{safe}" / f"CV_Test_{safe}.odt"


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
    agent = worker_config(config.get("agent", {"enabled": False}), output_dir)  # no table: the menu only
    return {
        "order": SectionOrder.from_config(config),
        "paper": paper,
        "target_score": target,
        "max_rounds": rounds,
        "output_dir": output_dir,
        "cv_dir": str(config.get("cv_dir", "")),
        "soffice": str(config.get("soffice", "")),
        "rezi_url": url,
        "token_file": str(token_file),
        "callback_port": port,
        "agent": agent,
    }


def rezi_client(checked: dict[str, Any], http_transport: Any = None) -> McpClient:
    """The Rezi connection from the checked config. Builds only: nothing is read, written or sent.
    `http_transport`: a test server instead of the network."""
    return McpClient(TokenStore(checked["token_file"]), checked["rezi_url"], http_transport=http_transport,
                     callback_port=checked["callback_port"])  # fmt: skip
