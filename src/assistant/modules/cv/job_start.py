"""The job start, in code: a new job gets its own folder, a copy of the base CV and its rules
before the worker sees the task.

`JobStart.prepare` turns a `CvRequest` into a `CvJob`. It makes `<work_dir>/<date>_<Company>_<Role>`,
copies the base CV into it as `base_<its name>` (sha256 checked, never overwriting; the prefix keeps
anyone from taking it for a tailored CV), writes the JD as `jd.txt`, and
reads each rule file in `job_skills`. It takes any .pdf base CV as given and refuses a missing or empty
one, and a missing or empty rule file. `start_block` is what the worker gets under its task: the
`CV_JOB:` line, one rule, and each rule file's full text.

`JobStartAgent` is the `ITaskAgent` the module provides for its worker. It holds the worker's
`SessionTaskAgent` and passes every call through, but a task (or a message to a task not set up
yet) with a `CV_REQUEST:` line is set up first. If the set-up fails, the task is refused, so no job
starts without its folder and rules. Tasks without a `CV_REQUEST:` line pass unchanged.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from assistant.contracts import AgentInfo, AgentState, ITaskAgent, PermissionMode, Result, Task
from assistant.infra.session_agent import default_context
from assistant.modules.cv.data import CvJob, CvRequest, SkillRef
from assistant.modules.cv.handoff import has_request, job_line, read_request

COMPANY_WORDS = 3  # "Example Corp Inc" → ExampleCorpInc
ROLE_WORDS = 4  # "Staff Engineer, Widget Design & Testing" → StaffEngineerWidgetDesign
_PART_CHARS = 40  # one name part at most, so a long title can't make a too-long path
_WORD = re.compile(r"[A-Za-z0-9]+")
BASE_COPY_PREFIX = "base_"  # the job folder's copy of the base CV: base_CV_Test_ExampleCorp.pdf, never a tailored CV


class JobStartError(ValueError):
    """A job can't start: the reason, for the caller."""


def name_part(text: str, max_words: int, fallback: str) -> str:
    """Folder-safe words: accents dropped, only letters and digits, each word's first letter upper
    case and the rest kept, joined (`"Example corp, Inc."` → `ExampleCorpInc`). `fallback` if none."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = _WORD.findall(plain)[:max_words]
    return "".join(w[0].upper() + w[1:] for w in words)[:_PART_CHARS] or fallback


def job_folder_name(company: str, role: str, day: date) -> str:
    """`YYYY-MM-DD_Company_Role`, e.g. `2026-11-09_ExampleCorp_StaffEngineerWidgetDesign`."""
    return f"{day.isoformat()}_{name_part(company, COMPANY_WORDS, 'Company')}_{name_part(role, ROLE_WORDS, 'Role')}"


@dataclass(frozen=True)
class Skill:
    """One loaded rule file."""

    path: Path
    text: str
    sha256: str


class JobStart:
    """Sets up one job's folder and rules. `work_dir` must not be inside `cv_dir` (the config
    check makes sure); `skills` are the rule files every job loads."""

    def __init__(self, work_dir: str | Path, cv_dir: str | Path, skills: Sequence[str | Path],
                 today: Callable[[], date] = date.today, rules_dir: str | Path = "") -> None:  # fmt: skip
        self.work_dir = Path(work_dir)
        self.cv_dir = Path(cv_dir)
        self.skills = tuple(Path(s) for s in skills)
        self.rules_dir = Path(rules_dir) if str(rules_dir) else None
        self._today = today

    def rule_files(self) -> list[Path]:
        """The cv module's general rules: `rules_dir/SKILL.md`, then every `rules_dir/rules/*.md`,
        listed at each job (a new rule file needs no reload). JobStartError without SKILL.md."""
        if self.rules_dir is None:
            return []
        skill = self.rules_dir / "SKILL.md"
        if not skill.is_file():
            raise JobStartError(f"the cv rules' SKILL.md is missing in {self.rules_dir}")
        return [skill, *sorted((self.rules_dir / "rules").glob("*.md"))]

    def load_skills(self) -> list[Skill]:
        """Every rule file's text: the rules folder's, then `job_skills` (e.g. the confirmed facts).
        JobStartError if one is missing or empty."""
        loaded = []
        for path in (*self.rule_files(), *self.skills):
            if not path.is_file():
                raise JobStartError(f"the job's rule file is missing: {path}")
            data = path.read_bytes()
            text = data.decode("utf-8", errors="replace").strip()
            if not text:
                raise JobStartError(f"the job's rule file is empty: {path}")
            loaded.append(Skill(path, text, _sha(data)))
        return loaded

    def folder_for(self, company: str, role: str) -> Path:
        """The job's folder, as its set-up today makes it: `work_dir/YYYY-MM-DD_Company_Role`."""
        return self.work_dir / job_folder_name(company, role, self._today())

    def prepare(self, request: CvRequest) -> tuple[CvJob, str]:
        """Make the job's folder, copy the base CV and the JD into it, load the rules: the job and
        the block for the task. The base CV is only read. JobStartError with the reason."""
        base = Path(request.base_cv)  # any .pdf, used as given (CvRequest checks the .pdf)
        if not base.is_file():
            raise JobStartError(f"base_cv not found: {base}")
        source = base.read_bytes()  # read once: copied and hashed from the same bytes
        if not source:
            raise JobStartError(f"base_cv is empty (0 bytes), so there's nothing to copy: {base}")
        skills = self.load_skills()  # before anything is made: a missing rule makes nothing

        folder = self.folder_for(request.company, request.role)
        created = not folder.exists()
        folder.mkdir(parents=True, exist_ok=True)
        copy = _place(folder, BASE_COPY_PREFIX + base.name, source)
        if _sha(copy.read_bytes()) != _sha(source):
            raise JobStartError(f"the copy of the base CV doesn't match it: {copy}")
        jd = _place(folder, "jd.txt", request.jd_text.encode("utf-8"))
        job = CvJob(work_dir=str(folder), base_cv=str(base), base_cv_copy=str(copy), base_cv_sha256=_sha(source),
                    jd_file=str(jd), skills=[SkillRef(path=str(s.path), sha256=s.sha256) for s in skills],
                    created=created)  # fmt: skip
        now = datetime.now(UTC).isoformat(timespec="seconds")
        record = {"started": read_record(folder).get("started") or now, "set_up": now,
                  "job": job.model_dump(mode="json"),
                  "request": request.model_dump(mode="json", exclude={"jd_text"})}  # fmt: skip
        write_record(folder, record)  # one record per job: a second set-up replaces it (its newest reply_to)
        return job, start_block(job, skills, self.cv_dir)


def read_record(folder: Path) -> dict:
    """The job's `job_start.json`, or {} if there's none or it can't be read."""
    try:
        record = json.loads((Path(folder) / "job_start.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def write_record(folder: Path, record: dict) -> None:
    """`record` as the job's `job_start.json`, whole or not at all (written beside it, then moved)."""
    path = Path(folder) / "job_start.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def job_notes(key: str) -> str:
    """What a fresh session needs to pick a cv job up again when your answer comes: for a job
    folder, its `job_start.json` in brief (company, role, folder, files, the reply) and its handoff
    notes; for any other key, the default (that key as the handoff note)."""
    folder = Path(key) if key else None
    if folder is None or not (folder / "job_start.json").is_file():
        return default_context(key)
    record = read_record(folder)
    request, job = record.get("request") or {}, record.get("job") or {}
    lines = [f"The cv job for {request.get('company', '?')} ({request.get('role', '?')}) is in {folder}."]
    for name in ("base_cv_copy", "jd_file"):
        if job.get(name):
            lines.append(f"{name}: {job[name]}")
    files = sorted(p.name for p in folder.iterdir() if p.is_file())
    lines.append(f"Files there now: {', '.join(files)}")
    if replied := record.get("replied"):
        lines.append(f"The result went to {replied.get('to')} ({replied.get('how')}) at {replied.get('submitted_at')}.")
    notes = sorted(folder.glob("*handoff*.md"))
    lines += [f"Read your handoff note first: {p}" for p in notes] or ["Read job_start.json and the drafts there first."]
    return "\n".join(lines)


def start_block(job: CvJob, skills: Sequence[Skill], cv_dir: str | Path) -> str:
    """What the worker reads under its task: the job line, the rule, each rule file in full."""
    parts = [
        job_line(job),
        f"The cv module set up this job in code before you got it: its folder is {job.work_dir}, with a "
        f"copy of the base CV ({job.base_cv_copy}; the {BASE_COPY_PREFIX} prefix marks it as the untouched base, "
        f"never a tailored CV) and the JD ({job.jd_file}). Work only in that folder: "
        f"keep every draft there, and never run a script or command on a file in {cv_dir}. When the user "
        f"tells you to start, cv.open_tool with job_dir={job.work_dir} opens this job in the CV Tool; the "
        f"final PDF comes from the user's Submit there (cv.tool_result). "
        f"The job's rules and the confirmed facts, loaded for you, follow in full; they hold for the whole job:",
    ]
    for skill in skills:
        parts += [f"--- {skill.path} ---", skill.text, f"--- end of {skill.path.name} ---"]
    return "\n".join(parts)


def _place(folder: Path, name: str, data: bytes) -> Path:
    """`data` as `folder/name`, never overwriting: a file already there with the same bytes is
    kept, a different one gets `stem_2`, `stem_3`, ... beside it."""
    path, stem, n = folder / name, Path(name).stem, 1
    while path.exists():
        if path.is_file() and path.read_bytes() == data:
            return path
        n += 1
        path = folder / f"{stem}_{n}{Path(name).suffix}"
    with path.open("xb") as f:  # "x": never over a file that appeared meanwhile
        f.write(data)
    return path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class JobStartAgent(ITaskAgent):
    """The worker as the Hub sees it: every call goes to the worker's own agent, after a job's set-up.
    Until `attach`, it reports active and refuses tasks (the worker is starting). It remembers each
    task's job folder: that is the key of a question the task asks (`question_key`, for `job_notes`)."""

    def __init__(self, start: JobStart, agent_id: str, description: str, log: logging.Logger | None = None) -> None:
        self._start = start
        self._agent_id = agent_id
        self._description = description
        self._log = log
        self._inner: ITaskAgent | None = None
        self._jobs: dict[str, str] = {}  # task id -> its job's folder (the tasks whose job is set up)

    def attach(self, inner: ITaskAgent) -> None:
        self._inner = inner

    def question_key(self, task_id: str) -> str:
        """A question's context key: its task's job folder ("" if it has none)."""
        return self._jobs.get(task_id, "")

    def info(self) -> AgentInfo:
        if self._inner is None:
            return AgentInfo(agent_id=self._agent_id, description=self._description, state=AgentState.ACTIVE)
        return self._inner.info()

    async def assign(self, task: Task) -> Result:
        inner = self._inner
        if inner is None:
            return Result.not_available(f"{self._agent_id} is starting")
        # Active: it refuses the task itself, and nothing is set up for a task it won't take. An
        # answer to a question goes as it is: its job is set up already.
        if inner.info().active or task.question_key is not None:
            return await inner.assign(task)
        try:
            text, folder = await self._set_up(task.text)
        except JobStartError as exc:
            return Result.failed(f"{self._agent_id}: the job can't start: {exc}")
        result = await inner.assign(task.model_copy(update={"text": text}))
        if result.is_ok and folder:
            self._jobs[task.id] = folder
        return result

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        inner = self._inner
        if inner is None:
            return Result.not_available(f"{self._agent_id} is starting")
        if task_id not in self._jobs and has_request(text):  # a job given after the task started
            try:
                text, folder = await self._set_up(text)
            except JobStartError as exc:
                return Result.failed(f"{self._agent_id}: the job can't start: {exc}")
            self._jobs[task_id] = folder
        return await inner.message(task_id, text, resume)

    async def _set_up(self, text: str) -> tuple[str, str]:
        """`text` with the job's block under it and the job's folder, if it holds a job; else
        `text` and ""."""
        if not has_request(text):
            return text, ""
        try:
            request = read_request(text)
        except ValueError as exc:
            raise JobStartError(f"the CV_REQUEST line isn't a valid job: {exc}") from exc
        try:
            job, block = await asyncio.to_thread(self._start.prepare, request)
        except OSError as exc:
            raise JobStartError(f"the job's folder couldn't be set up: {exc}") from exc
        if self._log is not None:
            self._log.info("cv job set up in %s (copy %s, %d rule file(s))", job.work_dir, Path(job.base_cv_copy).name, len(job.skills))  # fmt: skip
        return f"{text}\n\n{block}", job.work_dir

    async def cancel(self, task_id: str) -> Result:
        return await self._call(lambda a: a.cancel(task_id))

    async def answer_permission(self, task_id: str, allow: bool) -> Result:
        return await self._call(lambda a: a.answer_permission(task_id, allow))

    async def set_permission_mode(self, mode: PermissionMode) -> Result:
        return await self._call(lambda a: a.set_permission_mode(mode))

    async def request_approval(self, action: str, run: Callable[[], Awaitable[Result]]) -> Result:
        return await self._call(lambda a: a.request_approval(action, run))

    def note(self, text: str) -> None:
        if self._inner is not None:
            self._inner.note(text)

    async def _call(self, call: Callable[[ITaskAgent], Awaitable[Result]]) -> Result:
        if self._inner is None:
            return Result.not_available(f"{self._agent_id} is starting")
        return await call(self._inner)
