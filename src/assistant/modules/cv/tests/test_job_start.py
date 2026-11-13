"""The job start in code: a CV_REQUEST gets its own folder, a copy of the base CV and its rules
before the worker sees the task. The base CV is any `.pdf`. Everything is written in
tmp_path."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from app_kit.config import merge
from assistant.contracts import AgentInfo, AgentState, ITaskAgent, PermissionMode, Result, Status, Task
from assistant.modules.cv.data import CvRequest
from assistant.modules.cv.handoff import read_job, read_request, task_text
from assistant.modules.cv.job_start import JobStart, JobStartAgent, JobStartError, job_folder_name, name_part
from assistant.modules.cv.module import settings
from assistant.modules.cv.order import SectionOrder
from assistant.modules.cv.tests.pdf_fixture import write_pdf
from assistant.modules.cv.tests.test_handoff import finished, use
from assistant.modules.cv.tests.test_worker import CV, DEFAULTS, SKILL_TEXT, app_with, cv_module

DAY = date(2026, 11, 9)
ROLE = "Staff Engineer, Widget Design & Testing"


def hashes(folder: Path) -> dict[str, tuple[str, float]]:
    return {str(p.relative_to(folder)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime)
            for p in sorted(folder.rglob("*")) if p.is_file()}  # fmt: skip


def rules(tmp_path: Path) -> list[Path]:
    a, b = tmp_path / "rules" / "SKILL.md", tmp_path / "memory" / "never-script.md"
    for path, text in ((a, "# CV writing\nNo semicolons."), (b, "Never run a script on a file in the CV folder.")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return [a, b]


def base_cv(tmp_path: Path, name: str = "CV_Test_ExampleCorp.pdf", folder: str = "CV") -> Path:
    return write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / folder / name)


def request(base: Path, company: str = "ExampleCorp", role: str = ROLE) -> CvRequest:
    return CvRequest(company=company, role=role, jd_text="Isaac Sim, C#, Python\nSim-to-real", base_cv=str(base))


def starter(tmp_path: Path, skills: list[Path] | None = None) -> JobStart:
    return JobStart(tmp_path / "work", tmp_path / "CV", skills if skills is not None else rules(tmp_path), lambda: DAY)


# --- the folder's name ----------------------------------------------------------------------------------


def test_the_folder_is_named_from_the_date_the_company_and_the_role():
    assert job_folder_name("ExampleCorp", ROLE, DAY) == "2026-11-09_ExampleCorp_StaffEngineerWidgetDesign"
    assert name_part("Example corp, Inc.", 3, "Company") == "ExampleCorpInc"
    assert name_part("Société Générale", 3, "Company") == "SocieteGenerale"  # accents dropped
    assert name_part(r"..\..\CV:*?<>|", 3, "Company") == "CV"  # no path or reserved characters
    assert name_part("???", 3, "Company") == "Company"
    assert len(name_part("A" * 100, 4, "Role")) == 40
    assert job_folder_name("", "", DAY) == "2026-11-09_Company_Role"


# --- JobStart.prepare -----------------------------------------------------------------------------------


def test_a_job_gets_its_folder_a_checked_copy_the_jd_and_its_rules(tmp_path):
    base = base_cv(tmp_path)
    original = hashes(base.parent)
    job, block = starter(tmp_path).prepare(request(base))

    folder = tmp_path / "work" / "2026-11-09_ExampleCorp_StaffEngineerWidgetDesign"
    assert Path(job.work_dir) == folder and job.created
    copy = Path(job.base_cv_copy)
    assert copy == folder / "base_CV_Test_ExampleCorp.pdf" and copy.read_bytes() == base.read_bytes()
    assert job.base_cv_sha256 == hashlib.sha256(base.read_bytes()).hexdigest()
    assert Path(job.jd_file).read_text(encoding="utf-8") == "Isaac Sim, C#, Python\nSim-to-real"
    record = json.loads((folder / "job_start.json").read_text(encoding="utf-8"))
    assert record["job"]["base_cv_copy"] == str(copy) and record["request"]["company"] == "ExampleCorp"
    assert hashes(base.parent) == original  # the base CV is only read

    # the block: the job line, the rule, both rule files in full
    assert read_job(block) == job
    assert [Path(s.path).name for s in job.skills] == ["SKILL.md", "never-script.md"]
    for needed in ("No semicolons.", "Never run a script on a file in the CV folder.", "Work only in that folder",
                   f"never run a script or command on a file in {tmp_path / 'CV'}"):  # fmt: skip
        assert needed in block, needed


def test_a_second_start_reuses_the_folder_and_never_overwrites_a_copy(tmp_path):
    base = base_cv(tmp_path)
    start = starter(tmp_path)
    first, _ = start.prepare(request(base))
    again, _ = start.prepare(request(base))
    assert again.work_dir == first.work_dir and not again.created
    assert again.base_cv_copy == first.base_cv_copy  # the same bytes: the same copy

    Path(first.base_cv_copy).write_bytes(b"edited by hand")  # the copy changed in the folder
    third, _ = start.prepare(request(base))
    assert Path(third.base_cv_copy).name == "base_CV_Test_ExampleCorp_2.pdf"
    assert Path(first.base_cv_copy).read_bytes() == b"edited by hand"  # kept
    assert sorted(p.name for p in Path(first.work_dir).glob("job_start*.json")) == ["job_start.json"]  # one per job
    record = json.loads((Path(first.work_dir) / "job_start.json").read_text(encoding="utf-8"))
    assert record["job"]["base_cv_copy"] == third.base_cv_copy and record["started"] <= record["set_up"]


def test_a_pdf_anywhere_with_any_name_is_taken_as_given(tmp_path):
    base = base_cv(tmp_path, "My Resume.pdf", "elsewhere")  # no prefix, outside cv_dir
    job, _ = starter(tmp_path).prepare(request(base))
    assert job.base_cv == str(base) and Path(job.base_cv_copy).name == "base_My Resume.pdf"
    assert Path(job.base_cv_copy).read_bytes() == base.read_bytes()


@pytest.mark.parametrize("problem", ["missing", "empty", "no_rule", "empty_rule"])
def test_a_job_that_cant_start_safely_makes_nothing(tmp_path, problem):
    base = base_cv(tmp_path)
    skills = rules(tmp_path)
    if problem == "missing":
        base = tmp_path / "CV" / "CV_Test_Gone.pdf"
    elif problem == "empty":
        base.write_bytes(b"")  # the 2026-11-08 incident: a 0-byte CV
    elif problem == "no_rule":
        skills[1].unlink()
    else:
        skills[0].write_text("  \n", encoding="utf-8")
    with pytest.raises(JobStartError):
        starter(tmp_path, skills).prepare(request(base))
    assert not (tmp_path / "work").exists()


# --- the config -----------------------------------------------------------------------------------------


def test_the_work_folder_and_the_rules_come_from_the_config(tmp_path):
    checked = settings(DEFAULTS)
    home = Path("C:/Chang/Jobs/CV_Module")
    assert Path(checked["work_dir"]) == (home / "work").resolve()
    assert [Path(s) for s in checked["job_skills"]] == [home / "data" / "confirmed_facts.json"]
    assert Path(checked["rules_dir"]) == home / ".claude" / "skills" / "cv-writing"
    assert checked["tool"] | {"rules_dir": ""} == {"host": "127.0.0.1", "port": 8771, "data_dir": str(home / "cv_tool"),
                                                  "facts": str(home / "data" / "confirmed_facts.json"),
                                                  "cv_dir": "C:/Chang/Jobs/CV", "rules_dir": "",
                                                  "cv_prefix": "CV_Test_"}  # fmt: skip
    assert checked["cv_prefix"] == "CV_Test_"  # the repo default; the real one is in the local config
    with pytest.raises(ValueError, match="cv_prefix"):
        settings(DEFAULTS | {"cv_prefix": "../CV"})

    workspace = tmp_path / "cv_agent"
    own = {"cv_dir": str(tmp_path / "CV"), "agent": {"workspace": str(workspace)}}
    assert Path(settings(merge(DEFAULTS, own))["work_dir"]) == (workspace / "work").resolve()
    for bad, reason in ((tmp_path / "CV" / "work", "outside your CV folder"), (tmp_path / "elsewhere", "workspace")):
        with pytest.raises(ValueError, match=reason):
            settings(merge(DEFAULTS, own | {"work_dir": str(bad)}))
    for skills in ([], "SKILL.md", [""]):
        with pytest.raises(ValueError, match="job_skills"):
            settings(merge(DEFAULTS, own | {"job_skills": skills}))


# --- JobStartAgent, the gate ----------------------------------------------------------------------------


class Inner(ITaskAgent):
    """A worker's agent that keeps what it's given."""

    def __init__(self, busy: bool = False) -> None:
        self.busy, self.tasks, self.messages = busy, [], []

    def info(self) -> AgentInfo:
        return AgentInfo(agent_id="cv_agent", description="the worker",
                         state=AgentState.ACTIVE if self.busy else AgentState.IDLE)

    async def assign(self, task: Task) -> Result:
        if self.busy:
            return Result.not_available("busy")
        self.tasks.append(task)
        return Result.ok()

    async def message(self, task_id: str, text: str, resume: bool = True) -> Result:
        self.messages.append((task_id, text))
        return Result.ok()

    async def cancel(self, task_id: str) -> Result:
        return Result.ok("cancelled")

    async def answer_permission(self, task_id: str, allow: bool) -> Result:
        return Result.ok(allow)

    async def set_permission_mode(self, mode: PermissionMode) -> Result:
        return Result.ok(mode.value)


async def test_the_gate_sets_up_a_job_and_passes_everything_else_through(tmp_path):
    base = base_cv(tmp_path)
    gate, inner = JobStartAgent(starter(tmp_path), "cv_agent", "the worker"), Inner()
    assert gate.info().active and (await gate.assign(Task(id="t0", text="x"))).status is Status.NOT_AVAILABLE
    gate.attach(inner)

    assert (await gate.assign(Task(id="t1", text="Fix the docs"))).is_ok  # no job: unchanged, nothing made
    assert inner.tasks[-1].text == "Fix the docs" and not (tmp_path / "work").exists()

    text = task_text(request(base))
    assert (await gate.assign(Task(id="t2", text=text))).is_ok
    sent = inner.tasks[-1].text
    assert sent.startswith(text) and read_request(sent) == request(base) and "No semicolons." in sent
    assert Path(read_job(sent).base_cv_copy).is_file()
    folder = read_job(sent).work_dir
    assert gate.question_key("t2") == folder and gate.question_key("t1") == ""  # the key of a question it asks

    # the answer to a question is the same task given back: passed on as it is, no second set-up
    answer = Task(id="t2", text="Answer to your question in task t2 (...): yes " + text, question_key=folder)
    assert (await gate.assign(answer)).is_ok and inner.tasks[-1] == answer

    # a job given in a message to a task that has none yet is set up once
    assert (await gate.message("t1", text)).is_ok
    assert "CV_JOB:" in inner.messages[-1][1]
    assert (await gate.message("t1", text)).is_ok
    assert "CV_JOB:" not in inner.messages[-1][1]

    assert (await gate.cancel("t2")).value == "cancelled"
    assert (await gate.set_permission_mode(PermissionMode.AUTO)).value == "auto"
    assert (await gate.answer_permission("t2", True)).value is True


async def test_the_gate_refuses_a_job_it_cant_set_up_and_leaves_a_busy_worker_alone(tmp_path):
    base = base_cv(tmp_path)
    gate, inner = JobStartAgent(starter(tmp_path), "cv_agent", "the worker"), Inner()
    gate.attach(inner)
    empty = base.with_name("CV_Test_Empty.pdf")
    empty.write_bytes(b"")
    refused = await gate.assign(Task(id="t1", text=task_text(request(empty))))
    assert refused.status is Status.FAILED and "0 bytes" in refused.error and not inner.tasks
    broken = await gate.assign(Task(id="t2", text='CV_REQUEST: {"company": "Acme"}'))
    assert broken.status is Status.FAILED and "isn't a valid job" in broken.error

    inner.busy = True
    assert (await gate.assign(Task(id="t3", text=task_text(request(base))))).status is Status.NOT_AVAILABLE
    assert not (tmp_path / "work").exists()  # nothing set up for a task the worker won't take


# --- through the Hub ------------------------------------------------------------------------------------


async def test_a_job_through_the_hub_gets_its_folder_before_the_worker_sees_it(tmp_path):
    base = base_cv(tmp_path)
    app = app_with(tmp_path)
    await app.start()
    try:
        module = cv_module(app)
        assert module.gate is not None and module.gate.info().agent_id == "cv_agent"
        job = await use(app, "cv.task", company="ExampleCorp", role=ROLE, jd_text="Isaac Sim", base_cv=str(base))
        assert job.is_ok, job.error  # cv.task started cv_agent on it
        echoed = (await finished(app, job.value["task_id"])).result  # the fake claude echoes what it got
        made = read_job(echoed)
        today = date.today().isoformat()
        assert Path(made.work_dir) == (tmp_path / "cv_agent" / "work" /
                                       f"{today}_ExampleCorp_StaffEngineerWidgetDesign").resolve()
        assert Path(made.base_cv_copy).read_bytes() == base.read_bytes() and SKILL_TEXT in echoed
        assert Path(made.base_cv_copy).name == "base_CV_Test_ExampleCorp.pdf"  # never taken for a tailored CV
        read = await use(app, "cv.read", caller="cv_agent", pdf=made.base_cv_copy)  # the copy is readable
        assert read.is_ok and read.value["complete"], read.error
        assert read.value["sections"]["experience"] == list(CV.lines("experience"))
        built = await use(app, "cv.build", caller="cv_agent", company="ExampleCorp", base_cv=made.base_cv_copy,
                          job_dir=made.work_dir)  # the PDF goes to the job's folder, never over its copy
        if built.is_ok:  # LibreOffice installed
            assert Path(built.value["pdf_path"]).parent == Path(made.work_dir)
            assert Path(built.value["pdf_path"]).name == "CV_Test_ExampleCorp.pdf"  # the copy is base_…: no clash
            assert Path(made.base_cv_copy).read_bytes() == base.read_bytes()
        else:
            assert built.status is Status.NOT_AVAILABLE, built.error

        plain = await use(app, "hub.start", caller="main_assistant", text="Check the docs build", agent_id="cv_agent")
        passed = (await finished(app, plain.value)).result  # a task with no job passes as it is
        assert passed.strip().endswith("Check the docs build") and "CV_JOB:" not in passed

        base.write_bytes(b"")
        refused = await use(app, "hub.start", caller="main_assistant", text=job.value["text"], agent_id="cv_agent")
        assert refused.status is Status.FAILED and "can't start" in refused.error
    finally:
        await app.stop()
