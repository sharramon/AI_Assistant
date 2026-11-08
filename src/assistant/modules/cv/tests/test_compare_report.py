"""cv's own tests (chunk 3): the step-6 compare (`FieldCompare`, `cv.compare`) and the step-8 report
(`ReportWriter`, `cv.report`)."""

from datetime import date
from pathlib import Path

import pytest

from assistant.contracts import InvokeTool, Status
from assistant.core import App
from assistant.modules.cv import CvModule
from assistant.modules.cv.compare import Comparison, FieldCompare, Issue, words
from assistant.modules.cv.content import CvContent
from assistant.modules.cv.data import CvResult, ResumeRef
from assistant.modules.cv.module import output_path
from assistant.modules.cv.odt import OdtWriter
from assistant.modules.cv.report import REPORT_NAME, ReportWriter, Round

EDITED = CvContent(sections={
    "contact": ("Ada Lovelace", "ada@example.com | London"),
    "summary": ("Builds engines that compute, in C++ and Python.",),
    "experience": ("Engineer, Analytical Engines | Jan 2020 – Present", "• Cut run time by 30% for 12 programs.",
                   "• Wrote the first program."),
    "education": ("B.Sc. Mathematics, University of London | 2015",),
    "awards": ("• Best Paper",),
})  # fmt: skip

# What Rezi might show after the import: fields split and reordered, dashes and case changed.
PARSED = CvContent(sections={
    "contact": ("Ada Lovelace", "London", "ada@example.com"),
    "summary": ("Builds engines that compute, in C++ and Python",),
    "experience": ("Jan 2020 - Present", "Engineer", "Analytical Engines", "Cut run time by 30% for 12 programs",
                   "wrote the first program"),
    "education": ("University of London", "B.Sc. Mathematics", "2015"),
    "awards": ("Best Paper",),
})  # fmt: skip


def with_lines(cv: CvContent, **changes: tuple[str, ...] | None) -> CvContent:
    sections = dict(cv.sections)
    for name, lines in changes.items():
        if lines is None:
            sections.pop(name, None)
        else:
            sections[name] = lines
    return CvContent(sections=sections)


# --- FieldCompare -----------------------------------------------------------------------------------------

def test_words_are_made_plain_for_comparing():
    assert words("C++ & C#: cut 30% – “fast”") == ["c++", "and", "c#", "cut", "30%", "fast"]


def test_the_same_content_in_rezis_fields_matches():
    comparison = FieldCompare().diff(EDITED, PARSED)
    assert comparison.match_ok, comparison.issues
    assert comparison.checked == 8 and comparison.summary() == "same content: all 8 lines found"


def test_a_lost_line_a_lost_number_and_a_lost_section_are_found():
    parsed = with_lines(PARSED, awards=None, experience=(
        "Jan 2020 - Present", "Engineer", "Analytical Engines", "Cut run time by 30% for 13 programs"))
    issues = FieldCompare().diff(EDITED, parsed).issues
    assert Issue("missing_section", "awards") in issues
    assert Issue("missing", "awards", "• Best Paper") in issues
    assert Issue("missing", "experience", "• Cut run time by 30% for 12 programs.") in issues  # 12 became 13
    assert Issue("missing", "experience", "• Wrote the first program.") in issues
    assert Issue("extra", "experience", "Cut run time by 30% for 13 programs") in issues


def test_a_line_under_another_section_is_moved_and_new_text_is_extra():
    parsed = with_lines(PARSED, awards=(), summary=("Builds engines that compute, in C++ and Python", "Best Paper"),
                        education=("University of London", "B.Sc. Mathematics", "2015", "Fluent in French"))
    comparison = FieldCompare().diff(EDITED, parsed)
    assert set(comparison.issues) == {
        Issue("missing_section", "awards"), Issue("moved", "awards", "• Best Paper", "summary"),
        Issue("extra", "education", "Fluent in French")}  # fmt: skip
    value = comparison.as_value()
    assert value["match_ok"] is False and value["mode"] == "sections"
    assert {"kind": "moved", "section": "awards", "line": "• Best Paper", "found_in": "summary"} in value["issues"]
    assert "1 moved" in value["summary"] and "1 extra" in value["summary"]


def test_the_compare_against_one_text_finds_only_missing_lines():
    text = "Ada Lovelace\nada@example.com · London\nSummary\nBuilds engines that compute, in C++ and Python.\n" \
           "Engineer, Analytical Engines   Jan 2020 – Present\n• Cut run time by 30% for 12 programs.\n" \
           "B.Sc. Mathematics, University of London 2015\nBest Paper\nNot on the CV at all"
    comparison = FieldCompare().diff_text(EDITED, text)
    assert comparison.mode == "text"
    assert comparison.issues == (Issue("missing", "experience", "• Wrote the first program."),)
    with pytest.raises(ValueError):
        FieldCompare(min_cover=0)


def test_a_comparison_comes_back_from_its_value():
    comparison = FieldCompare().diff(EDITED, with_lines(PARSED, awards=None))
    again = Comparison.from_value(comparison.as_value())
    assert again == comparison
    for bad in ({"issues": "x"}, {"issues": [{"kind": "lost", "section": "awards"}]},
                {"match_ok": True, "issues": [{"kind": "missing", "section": "awards"}]}):
        with pytest.raises(ValueError):
            Comparison.from_value(bad)


# --- ReportWriter -----------------------------------------------------------------------------------------

APPROVED = CvResult(
    status="approved", pdf_path="C:/out/2026-11-06_Acme/CV_Test_Acme.pdf",
    odt_path="C:/out/2026-11-06_Acme/CV_Test_Acme.odt", rezi_resume=ResumeRef(name="Acme – Engineer", id="r1"),
    check_copy=ResumeRef(name="Acme – check", id="r2"), scores=[78, 91], keywords_left_out=["Kubernetes", "Go"],
    match_ok=True, one_page=True, section_order=["contact", "summary", "skills", "experience", "education"],
    order_reason="usual order", approved_by_user=True,
)  # fmt: skip
ROUNDS = [Round(score=78, added=["CI/CD"], missing=["Kubernetes", "Go"]), Round(score=91, note="a | b")]


def test_the_report_says_what_came_out():
    text = ReportWriter(90).render(APPROVED, "Acme", "Engineer", ROUNDS, FieldCompare().diff(EDITED, PARSED),
                                   notes="Sent back to job_search.", today=date(2026, 11, 6))  # fmt: skip
    assert text.startswith("# CV report: Acme – Engineer\n\n2026-11-06 · **Approved** by you")
    assert "| PDF | C:/out/2026-11-06_Acme/CV_Test_Acme.pdf |" in text
    assert "| Rezi check copy | Acme – check (r2) |" in text
    assert "Last: **91**, target 90 (reached), 2 round(s)." in text
    assert "| 1 | 78 | CI/CD | Kubernetes, Go | – |" in text and "| 2 | 91 | – | – | a \\| b |" in text
    assert "- Kubernetes\n- Go" in text and "- One page: yes" in text and "- Your yes: yes" in text
    assert "same content: all 8 lines found" in text and text.rstrip().endswith("Sent back to job_search.")


def test_a_stopped_report_lists_the_compares_issues():
    stopped = CvResult(status="stopped", stop_reason="Rezi lost the awards", scores=[70])
    comparison = FieldCompare().diff(EDITED, with_lines(PARSED, awards=None))
    text = ReportWriter(90).render(stopped, "Acme", comparison=comparison)
    assert "**Stopped:** Rezi lost the awards" in text and "target 90 (not reached), 1 round(s)" in text
    assert "Scores by round: 70." in text and "  - awards: Rezi read nothing under it" in text
    assert "- none" in text  # no keywords left out


def test_a_report_that_contradicts_itself_is_refused(tmp_path):
    writer = ReportWriter()
    with pytest.raises(ValueError, match="scores"):
        writer.render(APPROVED, "Acme", rounds=[Round(score=91)])
    with pytest.raises(ValueError, match="same content"):
        writer.render(APPROVED, "Acme", comparison=FieldCompare().diff(EDITED, with_lines(PARSED, awards=None)))
    path = writer.write(tmp_path / "job", APPROVED, "Acme", rounds=ROUNDS)
    assert path == tmp_path / "job" / REPORT_NAME and "# CV report: Acme" in path.read_text(encoding="utf-8")


# --- the items --------------------------------------------------------------------------------------------

async def call(tmp_path: Path, name: str, **args):
    app = App([CvModule], {"modules": {"enabled": ["cv"], "cv": {"output_dir": str(tmp_path / "out"), "agent": {"enabled": False}}}, "core": {}})
    await app.start()
    try:
        return await app.router.send(InvokeTool(name=name, args=args, caller="test"))
    finally:
        await app.stop()


def plain(cv: CvContent) -> dict[str, list[str]]:
    return {name: list(lines) for name, lines in cv.sections.items()}


async def test_cv_compare_takes_the_built_odt_or_sections(tmp_path):
    assert CvModule.menu.names()[-3:] == ["cv.build", "cv.compare", "cv.report"]
    odt = OdtWriter().write(EDITED, EDITED.sections, tmp_path / "CV_Test_Acme.odt")
    result = await call(tmp_path, "cv.compare", edited_odt=str(odt), parsed=plain(PARSED))
    assert result.status is Status.OK and result.value["match_ok"], result.value
    result = await call(tmp_path, "cv.compare", edited=plain(EDITED), parsed_text="Ada Lovelace")
    assert result.status is Status.OK and result.value["mode"] == "text" and not result.value["match_ok"]
    for args in ({"parsed": plain(PARSED)}, {"edited": plain(EDITED)},
                 {"edited": plain(EDITED), "parsed": plain(PARSED), "parsed_text": "x"},
                 {"edited_odt": "cv.pdf", "parsed_text": "x"}, {"edited": plain(EDITED), "parsed": {"hobbies": ["chess"]}},
                 {"edited": plain(EDITED), "parsed": {"skills": "x"}}):  # fmt: skip
        result = await call(tmp_path, "cv.compare", **args)
        assert result.status is Status.INVALID_ARGUMENTS, (args, result.error)


async def test_cv_report_writes_report_md_in_the_jobs_folder(tmp_path):
    folder = output_path(tmp_path / "out", "Acme").parent
    result = APPROVED.model_dump() | {"pdf_path": str(folder / "CV_Test_Acme.pdf"),
                                      "odt_path": str(folder / "CV_Test_Acme.odt")}  # fmt: skip
    rounds = [r.model_dump() for r in ROUNDS]
    compare = FieldCompare().diff(EDITED, PARSED).as_value()
    done = await call(tmp_path, "cv.report", company="Acme", role="Engineer", result=result, rounds=rounds,
                      compare=compare, target_score=95)  # fmt: skip
    assert done.status is Status.OK, done.error
    assert Path(done.value["report_path"]) == folder / REPORT_NAME
    assert "target 95 (not reached)" in done.value["text"]
    stopped = {"status": "stopped", "stop_reason": "no yes yet"}
    done = await call(tmp_path, "cv.report", company="Acme Inc", result=stopped)
    assert Path(done.value["report_path"]).parent == output_path(tmp_path / "out", "Acme Inc").parent


async def test_cv_report_refuses_bad_input_and_folders_outside_the_output(tmp_path):
    outside = APPROVED.model_dump() | {"pdf_path": str(tmp_path / "CV" / "CV_Test_Base.pdf")}
    for args in ({"result": {"status": "approved"}}, {"result": outside},
                 {"result": APPROVED.model_dump(), "rounds": [{"score": 101}]},
                 {"result": {"status": "stopped", "stop_reason": "x"}, "compare": {"issues": [{"kind": "?"}]}},
                 {"result": {"status": "stopped", "stop_reason": "x"}, "target_score": 0},
                 {"result": {"status": "stopped", "stop_reason": "x"}, "rounds": [{"score": 50}], "role": "x",
                  "notes": "x", "compare": {"issues": []}, "target_score": 101}):  # fmt: skip
        result = await call(tmp_path, "cv.report", company="Acme", **args)
        assert result.status is Status.INVALID_ARGUMENTS, (args, result.error)
    assert not (tmp_path / "CV").exists()
