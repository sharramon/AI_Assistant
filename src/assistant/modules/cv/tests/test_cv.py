"""cv's own tests (chunk 1): its defaults, the section order rules, the CV content, the request and
result data, and that the module loads, turns off and on, and swaps in place. No Rezi, Chrome or LibreOffice."""

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from assistant.contracts import ActivateModule, DeactivateModule, ListModules, ModuleState, ReloadModule
from assistant.core import App
from assistant.modules.cv import CvModule
from assistant.modules.cv.content import SECTIONS, CvContent
from assistant.modules.cv.data import CvRequest, CvResult, ResumeRef
from assistant.modules.cv.module import settings, with_defaults
from assistant.modules.cv.order import SectionOrder, wants_masters

DEFAULTS = tomllib.loads((Path(__file__).parents[1] / "module.toml").read_text(encoding="utf-8"))
ORDER = SectionOrder.from_config(DEFAULTS)
FULL = CvContent(sections={name: (f"{name} line",) for name in SECTIONS})


# --- defaults ---------------------------------------------------------------------------------------------

def test_the_defaults_are_the_workflows():
    assert ORDER.usual == SECTIONS == (
        "contact", "summary", "skills", "experience", "projects", "education", "awards", "publications")
    assert ORDER.degree_first == (
        "contact", "summary", "skills", "education", "experience", "projects", "awards", "publications")
    assert ORDER.drop_first == ("publications", "awards")
    checked = settings(DEFAULTS)
    assert (checked["paper"], checked["target_score"], checked["max_rounds"]) == ("letter", 90, 5)
    assert checked["soffice"].endswith("soffice.exe") and checked["output_dir"]


def test_cv_fills_in_its_own_defaults_when_the_app_passes_only_its_section():
    # An app started before the core merged module.toml passes only [modules.cv] (first real run).
    assert with_defaults({}) == DEFAULTS
    assert with_defaults(DEFAULTS) == DEFAULTS
    merged = with_defaults({"target_score": 95, "agent": {"enabled": False}})
    assert merged["target_score"] == 95 and merged["degree_first_order"] == DEFAULTS["degree_first_order"]
    assert merged["agent"] == {**DEFAULTS["agent"], "enabled": False}
    assert settings(with_defaults({}))["order"] == ORDER


@pytest.mark.parametrize("change, problem", [
    ({"section_order": list(SECTIONS[:-1])}, "must list each"),
    ({"section_order": [*SECTIONS, "contact"]}, "listed twice"),
    ({"degree_first_order": [*SECTIONS[:-1], "hobbies"]}, "unknown sections"),
    ({"drop_first": ["certificates"]}, "unknown sections"),
    ({"drop_first": ["contact"]}, "never dropped"),
    ({"paper": "legal"}, "paper"),
    ({"target_score": 0}, "target_score"),
    ({"max_rounds": 0}, "max_rounds"),
])
def test_a_bad_config_is_refused_with_the_reason(change, problem):
    with pytest.raises(ValueError, match=problem):
        settings(DEFAULTS | change)


# --- section order ----------------------------------------------------------------------------------------

def test_education_moves_under_skills_only_for_a_masters():
    assert ORDER.choose(FULL, degree_first=False).order == ORDER.usual
    choice = ORDER.choose(FULL, degree_first=True)
    assert choice.order.index("education") == choice.order.index("skills") + 1
    assert "master's" in choice.reason


def test_publications_then_awards_drop_first():
    assert ORDER.choose(FULL, False, drop=1).dropped == ("publications",)
    two = ORDER.choose(FULL, False, drop=2)
    assert two.dropped == ("awards", "publications") and "awards" not in two.order and "left out" in two.reason
    assert ORDER.choose(FULL, False, drop=9).order == ORDER.usual[:-2]  # nothing else is ever dropped
    with pytest.raises(ValueError):
        ORDER.drop(ORDER.usual, -1)


def test_a_cv_without_publications_loses_awards_first_and_keeps_its_own_sections_only():
    cv = CvContent(sections={"skills": ("Python",), "contact": ("me",), "awards": ("prize",), "summary": ("",)})
    assert cv.names() == ["skills", "contact", "awards"]  # an empty section counts as missing
    assert ORDER.choose(cv, False).order == ("contact", "skills", "awards")
    assert ORDER.choose(cv, False, drop=1).order == ("contact", "skills")


@pytest.mark.parametrize("jd, wanted", [
    ("Master's degree in Computer Science preferred.", True),
    ("Masters in Robotics required", True),
    ("MS in Mechanical Engineering or equivalent", True),
    ("BS/MS in a related field", True),
    ("M.S. or Ph.D. in Electrical Engineering", True),
    ("MSc in Data Science a plus", True),
    ("Master of Science in Physics", True),
    ("Bachelor's degree required.", False),
    ("Proficient in MS Office and MS Excel", False),
    ("Keep latency under 10 ms", False),
    ("Certified Scrum Master", False),
    ("", False),
])
def test_wants_masters_reads_the_jd(jd, wanted):
    assert wants_masters(jd) is wanted


# --- content and data -------------------------------------------------------------------------------------

def test_cv_content_knows_only_the_standard_sections():
    with pytest.raises(ValidationError, match="unknown sections"):
        CvContent(sections={"hobbies": ("chess",)})
    assert [name for name, _ in FULL.ordered(ORDER.degree_first)] == list(ORDER.degree_first)
    assert FULL.lines("skills") == ("skills line",) and CvContent(sections={}).lines("skills") == ()


def request(**change) -> dict:
    return {"company": "Acme", "role": "Engineer", "jd_text": "Build robots.",
            "base_cv": r"C:\Chang\Jobs\CV\CV_Test_Acme.pdf"} | change


def test_a_request_needs_the_job_and_a_pdf_base_cv():
    req = CvRequest(**request(target_score=95))
    assert req.degree_first is None and CvRequest.model_validate_json(req.model_dump_json()) == req
    assert CvRequest(**request(base_cv=r"C:\Chang\Jobs\CV\CV_Test_Acme.PDF")).base_cv.endswith(".PDF")
    for any_pdf in ("cv.pdf", r"D:\elsewhere\My Resume.pdf", "/tmp/resume.PDF"):  # any name, any folder, as given
        assert CvRequest(**request(base_cv=any_pdf)).base_cv == any_pdf
    for bad in (request(company=""), request(target_score=101), request(extra=1)):
        with pytest.raises(ValidationError):
            CvRequest(**bad)
    for not_pdf in (r"C:\Chang\Jobs\CV\CV_Test_Acme.odt", "resume.docx", "resume", "resume.pdf.txt"):
        with pytest.raises(ValidationError, match=r"base_cv must be a \.pdf file"):
            CvRequest(**request(base_cv=not_pdf))


def test_a_result_is_approved_only_with_your_yes_one_page_and_rezis_match():
    ok = CvResult(status="approved", pdf_path="out/CV.pdf", approved_by_user=True,
                  one_page=True, match_ok=True, scores=[78, 91], section_order=list(ORDER.usual),
                  rezi_resume=ResumeRef(name="Acme – Engineer", id="r1"))
    assert ok.score == 91 and CvResult.model_validate_json(ok.model_dump_json()) == ok
    assert "odt_path" not in ok.model_dump()
    with pytest.raises(ValidationError, match="odt_path"):  # dropped: no .odt comes out
        CvResult(status="stopped", stop_reason="x", odt_path="out/CV.odt")
    with pytest.raises(ValidationError, match="your yes"):
        CvResult(status="approved", pdf_path="x.pdf", one_page=True, match_ok=True)
    with pytest.raises(ValidationError, match="stop_reason"):
        CvResult(status="stopped")
    with pytest.raises(ValidationError):
        CvResult(status="stopped", stop_reason="rounds used up", scores=[101])
    with pytest.raises(ValidationError, match="unknown sections"):
        CvResult(status="stopped", stop_reason="x", section_order=["hobbies"])
    assert CvResult(status="stopped", stop_reason="rounds used up").score is None


def test_a_results_section_order_ignores_case_as_the_worker_may_write_it():
    """Fake job 3: cv_agent wrote "Summary", "Skills" …; the result must still read."""
    result = CvResult(status="stopped", stop_reason="x", section_order=["Summary", " Skills ", "EXPERIENCE"])
    assert result.section_order == ["summary", "skills", "experience"]
    with pytest.raises(ValidationError, match="listed twice"):
        CvResult(status="stopped", stop_reason="x", section_order=["summary", "Summary"])


def test_a_ready_result_is_everything_but_the_submit_and_the_job_agent_is_told_so():
    from assistant.modules.cv.handoff import read_result, result_line, result_view
    from assistant.modules.cv.reply import reply_text
    from assistant.modules.cv.report import ReportWriter

    ready = CvResult(status="ready", pdf_path="out/CV.pdf", one_page=True, scores=[80, 92])
    assert read_result(result_line(ready)) == ready
    assert result_view(ready, target_score=90)["status"] == "ready"
    assert "**Ready** for your Submit" in ReportWriter().render(ready, "Acme")
    with pytest.raises(ValidationError, match="ready needs one page, the PDF"):
        CvResult(status="ready")
    with pytest.raises(ValidationError, match="before the user's Submit"):
        CvResult(status="ready", pdf_path="out/CV.pdf", one_page=True, approved_by_user=True)
    with pytest.raises(ValidationError):
        CvResult(status="submitted", stop_reason="x")
    told = reply_text({"role": "Engineer", "company": "Acme", "submitted_at": "2026-11-10T03:00:00"})
    assert told.endswith('cv_agent\'s own CV_RESULT line has status "ready" (everything but this Submit); '
                         "nothing more comes from it.")
    assert "follows when its task ends" not in told


# --- the module in the app --------------------------------------------------------------------------------

def config(section: dict | None = None) -> dict:
    return {"modules": {"enabled": ["cv"], "cv": (section or {}) | {"agent": {"enabled": False}}}, "core": {}}


async def state(app: App) -> ModuleState:
    return {m.id: m.state for m in (await app.router.send(ListModules())).value}["cv"]


async def test_it_loads_turns_off_and_on_and_swaps_in_place():
    assert CvModule.manifest.id == "cv" and "cv.build" in CvModule.menu.names()
    app = App([CvModule], config())
    await app.start()
    try:
        assert await state(app) is ModuleState.ACTIVE
        assert (await app.router.send(DeactivateModule(module_id="cv"))).is_ok
        assert await state(app) is not ModuleState.ACTIVE
        assert (await app.router.send(ActivateModule(module_id="cv"))).is_ok
        assert await state(app) is ModuleState.ACTIVE
        reloaded = await app.router.send(ReloadModule(module_id="cv", now=True))
        assert reloaded.is_ok, reloaded.error
        assert await state(app) is ModuleState.ACTIVE
    finally:
        await app.stop()


async def test_a_bad_override_keeps_it_off():
    app = App([CvModule], config({"paper": "legal"}))
    await app.start()
    try:
        assert await state(app) is not ModuleState.ACTIVE
    finally:
        await app.stop()
