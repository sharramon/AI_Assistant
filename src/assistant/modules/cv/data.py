"""What a job sends in (`CvRequest`) and gets back (`CvResult`): plain, serializable data.

A caller (later the job agent) sends one job to `cv_agent` through the Hub (`cv.task`, then `hub.start`); the
worker reads it as a `CvRequest` and ends the task with a `CvResult` (`cv.read_result` checks it).
Fields as on the module's Tools page.
"""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from assistant.modules.cv.content import check_sections


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
    base_cv: str = Field(min_length=1, description="Path to the CV_Test_*.odt (read only)")
    jd_file: str | None = None
    jd_url: str | None = None
    degree_first: bool | None = None  # None: decided from the JD (order.wants_masters), the worker may set it
    target_score: int | None = Field(default=None, ge=1, le=100)  # None: the config's target_score
    notes: str = ""

    @field_validator("base_cv")
    @classmethod
    def _odt(cls, value: str) -> str:
        if PureWindowsPath(value).suffix.lower() != ".odt":
            raise ValueError("base_cv must be an .odt file (the CV_Test_*.odt the job agent recommends)")
        return value


class ResumeRef(BaseModel):
    """A Rezi resume this run created: its name and id."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    id: str = Field(min_length=1)


class CvResult(BaseModel):
    """The job's outcome: the new CV and PDF with what was learned on the way. `approved` only with
    your yes, a one-page PDF and Rezi reading the same content. `scores` are the rounds' scores
    (filled from `rounds` when left out); `compare` is `cv.compare`'s value from step 6."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["approved", "stopped"]
    stop_reason: str = ""
    pdf_path: str | None = None  # the exact PDF that passed Rezi's check
    odt_path: str | None = None
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
        if self.status == "approved":
            missing = [name for name, ok in (("your yes", self.approved_by_user), ("one page", self.one_page),
                                             ("Rezi's match", self.match_ok), ("the PDF", bool(self.pdf_path)))
                       if not ok]  # fmt: skip
            if missing:
                raise ValueError(f"approved needs {', '.join(missing)}")
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
