"""What a job sends in (`CvRequest`), what the module sets up for it (`CvJob`) and what it gets
back (`CvResult`): plain, serializable data.

A caller (later the job agent) sends one job to `cv_agent` through the Hub (`cv.task`, then `hub.start`); the
worker reads it as a `CvRequest` and ends the task with a `CvResult` (`cv.read_result` checks it).
Fields as on the module's Tools page.
"""

from __future__ import annotations

import re
from pathlib import PureWindowsPath
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from assistant.modules.cv.content import check_sections

BASE_CV_NAME = re.compile(r"CV_Test_.+\.pdf", re.IGNORECASE)  # the base CV: a PDF, never an .odt
ToolPick = Literal["Internal", "Rezi"]  # the CV Tool's pick (its tab 2): who drafts and scores
TOOL_PICKS: tuple[str, ...] = get_args(ToolPick)


class Round(BaseModel):
    """One score round: the Rezi Score after it, the keywords added (true ones only), the keywords
    still missing, and a note."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: int = Field(ge=0, le=100)
    added: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    note: str = ""


class CvRequest(BaseModel):
    """One job: the JD and the base CV the job agent recommends (read only, never changed).
    `jd_text` is always there; `jd_file` names the file it was read from, if any."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    jd_text: str = Field(min_length=1)
    base_cv: str = Field(min_length=1, description="Path to the CV_Test_*.pdf (read only)")
    jd_file: str | None = None
    jd_url: str | None = None
    degree_first: bool | None = None  # None: decided from the JD (order.wants_masters), the worker may set it
    target_score: int | None = Field(default=None, ge=1, le=100)  # None: the config's target_score
    notes: str = ""
    tool: ToolPick | None = None  # the CV Tool's pick; None: the user picks in its tab 2
    reply_to: str = ""  # the agent that asked (cv.task's caller): told by agent id when the user submits

    @field_validator("base_cv")
    @classmethod
    def _pdf(cls, value: str) -> str:
        if not BASE_CV_NAME.fullmatch(PureWindowsPath(value).name):
            raise ValueError(f"base_cv must be a CV_Test_*.pdf, not {PureWindowsPath(value).name}")
        return value


class SkillRef(BaseModel):
    """One rule file the module loaded into a job's task (`job_skills`): its path and sha256."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)


class CvJob(BaseModel):
    """What the module set up in code when a `CvRequest` arrived (`JobStart`), before the worker
    saw the task: the job's own folder, the copy of the base CV in it, the JD as a file, and the
    rules loaded into the task. The worker works on `base_cv_copy`, never on `base_cv`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    work_dir: str = Field(min_length=1)
    base_cv: str = Field(min_length=1)  # the original in cv_dir: read only, never opened by a script
    base_cv_copy: str = Field(min_length=1)
    base_cv_sha256: str = Field(min_length=64, max_length=64)  # the original's and the copy's (checked equal)
    jd_file: str = Field(min_length=1)  # jd.txt in work_dir
    skills: list[SkillRef] = Field(default_factory=list)
    created: bool = False  # the folder was made now (False: an earlier start of this job made it)


class ResumeRef(BaseModel):
    """A Rezi resume this run created: its name and id."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    id: str = Field(min_length=1)


class CvResult(BaseModel):
    """The job's outcome: the new CV as a PDF with what was learned on the way. `ready`: everything
    but your Submit (a one-page PDF, `approved_by_user` still false); cv_agent ends its task with it
    before you submit, and the cv module delivers your Submit itself (design A, 2026-11-10).
    `approved` (kept for older results) only with your yes and a one-page PDF. `scores` are the
    rounds' scores (filled from `rounds` when left out); `compare` is `cv.compare`'s value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ready", "approved", "stopped"]
    stop_reason: str = ""
    pdf_path: str | None = None  # the exact PDF that passed Rezi's check, in the job's folder (no .odt comes out)
    report_path: str | None = None  # cv.report's report.md
    rezi_resume: ResumeRef | None = None
    check_copy: ResumeRef | None = None  # "<Company> – check", the PDF imported back into Rezi
    target_score: int | None = Field(default=None, ge=1, le=100)  # None: the config's
    rounds: list[Round] = Field(default_factory=list)  # each score round, in order
    scores: list[int] = Field(default_factory=list)  # the Rezi Score after each round
    missing_keywords: list[str] = Field(default_factory=list)  # Rezi's still missing at the end
    keywords_left_out: list[str] = Field(default_factory=list)  # terms you don't have, so not added
    recommendations: list[str] = Field(default_factory=list)  # what Rezi or the worker suggests, not done
    match_ok: bool = False
    compare: dict[str, Any] | None = None
    one_page: bool = False
    section_order: list[str] = Field(default_factory=list)
    order_reason: str = ""
    approved_by_user: bool = False

    @model_validator(mode="before")
    @classmethod
    def _scores_from_rounds(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("rounds") and not value.get("scores"):
            rounds = value["rounds"]
            value = dict(value, scores=[r.score if isinstance(r, Round) else r.get("score") for r in rounds
                                        if isinstance(r, (Round, dict))])  # fmt: skip
        return value

    @field_validator("compare")
    @classmethod
    def _compare(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        from assistant.modules.cv.compare import Comparison

        return Comparison.from_value(value).as_value()

    @field_validator("scores")
    @classmethod
    def _scores(cls, value: list[int]) -> list[int]:
        if any(not 0 <= s <= 100 for s in value):
            raise ValueError("scores are 0 to 100")
        return value

    @field_validator("section_order")
    @classmethod
    def _order(cls, value: list[str]) -> list[str]:
        return check_sections(value, "section_order")

    @model_validator(mode="after")
    def _consistent(self) -> CvResult:
        if self.rounds and [r.score for r in self.rounds] != self.scores:
            raise ValueError(f"scores {self.scores} aren't the rounds' {[r.score for r in self.rounds]}")
        if self.compare is not None and self.match_ok and not self.compare["match_ok"]:
            raise ValueError(f"match_ok, but the compare found {self.compare['summary']}")
        if self.status in ("ready", "approved"):
            # Rezi's match is no longer needed: the CV Tool's own page is the final PDF (no Rezi import check)
            needs = (("one page", self.one_page), ("the PDF", bool(self.pdf_path)))
            if self.status == "approved":
                needs = (("your yes", self.approved_by_user), *needs)
            elif self.approved_by_user:
                raise ValueError("ready is before the user's Submit: approved_by_user must be false")
            missing = [name for name, ok in needs if not ok]
            if missing:
                raise ValueError(f"{self.status} needs {', '.join(missing)}")
        elif not self.stop_reason.strip():
            raise ValueError("stopped needs a stop_reason")
        return self

    @property
    def still_missing(self) -> list[str]:
        """Rezi's missing keywords at the end: `missing_keywords`, else the last round's."""
        return self.missing_keywords or (self.rounds[-1].missing if self.rounds else [])

    @property
    def score(self) -> int | None:
        """The last Rezi Score, None before the first round."""
        return self.scores[-1] if self.scores else None
