"""The hand-off between the job agent and `cv_agent`: one job in, one result out, as task text.

A Hub task is plain text, so each side is one marked line of JSON:
- **In:** the job agent calls `cv.task` with the job's fields; it checks them (`CvRequest`, the
  base CV: any .pdf that exists) and starts `cv_agent` on the task's `text` itself (a `StartTask`, the
  caller's open task as its parent). The text holds a line `CV_REQUEST: <json>` that the worker reads. On the way
  in, the module (`job_start.JobStartAgent`) makes the job's folder and adds a `CV_JOB: <json>`
  line (a `CvJob`) with the job's rules under it.
- **Out:** the worker ends its task with a line `CV_RESULT: <json>` (a `CvResult`). The module
  then publishes the named event `cv.job_finished` (`job_finished` builds its data); the asker's
  module hears it and wakes its agent. The agent can read the whole result with
  `cv.read_result task_id=…` (`read_result`, then `result_view`:
  the new CV's PDF and report, the score per round against the target, the keywords, the recommendations,
  the one-page check and the compare).
Each JSON is on one line (newlines in the JD are escaped), and the last marked line counts.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from assistant.modules.cv.data import CvJob, CvRequest, CvResult

REQUEST = "CV_REQUEST:"
JOB = "CV_JOB:"  # added by the module (JobStart) under the request: the folder, the copy, the rules
RESULT = "CV_RESULT:"


def task_text(request: CvRequest, agent_id: str = "cv_agent") -> str:
    """The `hub.start` text for one job."""
    return (f"Tailor the CV for {request.role} at {request.company} ({agent_id}: the 5 CV Tool steps, one clean "
            f"page, the user's Submit). The job, as JSON:\n{_line(REQUEST, request)}")  # fmt: skip


def result_line(result: CvResult) -> str:
    """The worker's last line: the result, as JSON."""
    return _line(RESULT, result)


def read_request(text: str) -> CvRequest:
    """The job in a task's text. ValueError if there's none or it isn't a valid `CvRequest`."""
    return CvRequest.model_validate(_last(text, REQUEST))


def has_request(text: str) -> bool:
    """The text has a `CV_REQUEST:` line (valid or not)."""
    return _has(text, REQUEST)


def job_line(job: CvJob) -> str:
    """The `CV_JOB:` line the module adds to a job's task."""
    return _line(JOB, job)


def read_job(text: str) -> CvJob:
    """The set-up job in a task's text. ValueError if there's none or it isn't a valid `CvJob`."""
    return CvJob.model_validate(_last(text, JOB))


def read_result(text: str, tool: str | None = None) -> CvResult:
    """The result in a task's result text. ValueError if there's none or it isn't a valid `CvResult`.
    `tool`: the job's pick (its request's), used when the line doesn't name one."""
    value = _last(text, RESULT)
    if tool and not str(value.get("tool") or "").strip():
        value = dict(value, tool=tool)
    try:
        return CvResult.model_validate(value)
    except ValidationError as exc:  # one short line per field, not pydantic's dump
        raise ValueError(f"the {RESULT.rstrip(':')} line isn't a valid CvResult: "
                         + "; ".join(_why(error) for error in exc.errors())) from None  # fmt: skip


def _why(error: Any) -> str:
    """One pydantic error as `field: message`."""
    where = ".".join(str(part) for part in error.get("loc", ()))
    message = str(error.get("msg", "")).removeprefix("Value error, ")
    return f"{where}: {message}" if where else message


def request_tool(text: str) -> str | None:
    """The pick in a job task's `CV_REQUEST` line, or None (no valid line, or no pick named)."""
    try:
        return read_request(text).tool
    except ValueError:
        return None


JOB_FINISHED = "cv.job_finished"  # the named event cv publishes when cv_agent's job task ends


def job_finished(agent_id: str, task_id: str, state: str, parent_task_id: str | None, folder: str, record: dict,
                 text: str) -> dict[str, Any]:  # fmt: skip
    """The data of `cv.job_finished`: who asked (`reply_to`, from the job's `job_start.json`
    `record`), the task, the job, the parsed `CV_RESULT` (None if the text has no valid one) and a
    one-line `summary` of it."""
    request = record.get("request") or {}
    result: CvResult | None = None
    why = ""
    try:
        result = read_result(text, request.get("tool"))
    except ValueError as exc:
        why = str(exc) if _has(text, RESULT) else ""  # a line that isn't valid, not a missing one
    return {"reply_to": str(request.get("reply_to") or ""), "agent_id": agent_id, "task_id": task_id,
            "parent_task_id": parent_task_id, "state": state, "job_dir": folder,
            "company": request.get("company") or "", "role": request.get("role") or "",
            "cv_result": result.model_dump(mode="json") if result else None,
            "summary": finish_summary(result, why, task_id)}  # fmt: skip


def finish_summary(result: CvResult | None, why: str = "", task_id: str = "") -> str:
    """One line on a job's result: its status (and why it stopped), the PDF and the last score.
    With no result: `why` is the reason its line isn't valid (empty: the text has no line)."""
    if result is None:
        name = RESULT.rstrip(":")
        if not why:
            return f"No {name} line in its last message."
        show = f" cv.read_result task_id={task_id} shows it." if task_id else ""
        return f"Its {name} line isn't valid: {why.removeprefix(f'the {name} line ')}.{show}"
    why = f" ({result.stop_reason})" if result.stop_reason else ""
    score = result.score if result.score is not None else "(none)"
    return f"{RESULT} status {result.status}{why}; PDF: {result.pdf_path or '(none)'}; last score: {score}."


JD_SUFFIXES = (".txt", ".md", ".html", ".htm")


class _Text(HTMLParser):
    """An HTML page's visible text, one block per line (scripts and styles skipped)."""

    BLOCKS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def read_jd_file(path: str | Path) -> str:
    """A JD file's text: `.txt` and `.md` as they are, `.html`/`.htm` as visible text.
    ValueError for another kind of file, a missing one, or one with no text."""
    path = Path(path)
    if path.suffix.lower() not in JD_SUFFIXES:
        raise ValueError(f"jd_file must be one of {list(JD_SUFFIXES)}, not {path.name}")
    if not path.is_file():
        raise ValueError(f"jd_file not found: {path}")
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        parser = _Text()
        parser.feed(raw)
        raw = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    text = "\n".join(line for line in lines if line).strip()
    if not text:
        raise ValueError(f"jd_file has no text: {path}")
    return text


def result_view(result: CvResult, target_score: int) -> dict[str, Any]:
    """What `cv.read_result` returns: the new CV's PDF with its metadata, grouped.
    `target_score`: the config's, used when the result doesn't name its own."""
    target = result.target_score or target_score
    last = result.score

    def exists(path: str | None) -> bool:
        return bool(path) and Path(path).is_file()

    return {
        "status": result.status,
        "stop_reason": result.stop_reason,
        "approved_by_user": result.approved_by_user,
        "files": {
            "pdf_path": result.pdf_path, "pdf_exists": exists(result.pdf_path),
            "report_path": result.report_path, "report_exists": exists(result.report_path),
        },
        "tool": result.tool,
        "rezi": {
            "resume": result.rezi_resume.model_dump() if result.rezi_resume else None,
            "check_copy": result.check_copy.model_dump() if result.check_copy else None,
        },
        "score": {
            "target": target, "last": last, "reached": last is not None and last >= target,
            "rounds": [{"round": n, "score": s, "vs_target": s - target,
                        **({"added": r.added, "missing": r.missing, "note": r.note} if r else {})}
                       for n, (s, r) in enumerate(zip(result.scores, _padded(result), strict=True), 1)],
        },
        "keywords": {"missing": result.still_missing, "left_out": result.keywords_left_out},
        "recommendations": result.recommendations,
        "page": {"one_page": result.one_page, "section_order": result.section_order,
                 "order_reason": result.order_reason},
        "compare": result.compare if result.compare is not None else {"match_ok": result.match_ok},
    }  # fmt: skip


def _padded(result: CvResult) -> list[Any]:
    """The rounds beside the scores: each round, or None where only the score is known."""
    return list(result.rounds) if result.rounds else [None] * len(result.scores)


def _line(marker: str, model: BaseModel) -> str:
    return f"{marker} {json.dumps(model.model_dump(mode='json', exclude_defaults=True), ensure_ascii=False)}"


def _marked(text: str, marker: str) -> list[str]:
    lines = [line.strip().strip("`").strip() for line in text.splitlines()]
    return [line[len(marker):].strip() for line in lines if line.startswith(marker)]


def _has(text: str, marker: str) -> bool:
    return bool(_marked(text, marker))


def _last(text: str, marker: str) -> dict:
    found = _marked(text, marker)
    if not found:
        raise ValueError(f"no {marker} line in the text")
    try:
        value = json.loads(found[-1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"the {marker} line isn't JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"the {marker} line isn't a JSON object")
    return value
