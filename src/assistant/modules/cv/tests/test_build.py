"""cv's own tests (chunk 2): the `.odt` writer and reader (inside the build only: no item takes or
gives an `.odt`), the PDF check, the fit to one page, and the `cv.build` item, which takes a
`CV_Test_*.pdf` or sections and exports the PDF. LibreOffice is faked except in the one test
marked for it (skipped when it isn't installed)."""

import json
import tomllib
import zipfile
from datetime import date
from pathlib import Path

import pytest

from assistant.contracts import InvokeTool, Status
from assistant.core import App
from assistant.modules.cv import CvModule
from assistant.modules.cv.build import build_cv
from assistant.modules.cv.content import CvContent
from assistant.modules.cv.module import output_path
from assistant.modules.cv.odt import LAYOUTS, OdtWriter, heading_section, line_kind, read_odt
from assistant.modules.cv.order import SectionOrder
from assistant.modules.cv.pdf import PageCheck, PageReport, PdfExport, assess
from assistant.modules.cv.tests.pdf_fixture import write_pdf

DEFAULTS = tomllib.loads((Path(__file__).parents[1] / "module.toml").read_text(encoding="utf-8"))
ORDER = SectionOrder.from_config(DEFAULTS)
SOFFICE = Path(DEFAULTS["soffice"])

CV = CvContent(sections={
    "contact": ("Ada Lovelace", "Engineer", "ada@example.com | London"),
    "summary": ("Builds engines that compute.",),
    "skills": ("Languages: Python, C++",),
    "experience": ("Engineer, Analytical Engines | Jan 2020 – Present", "• Wrote the first program.",
                   "• Kept notes & tables <clean>."),
    "education": ("B.Sc. Mathematics | 2015",),
    "awards": ("• Best Paper",),
    "publications": ("• Notes on the Engine",),
})  # fmt: skip

_NS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
       'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
       'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"')  # fmt: skip


def odt_with(tmp_path: Path, body: str, name: str = "CV_Test_Test.odt") -> Path:
    """A minimal `.odt` holding this body XML (what a word processor would write)."""
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as odt:
        odt.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        odt.writestr("content.xml", f'<office:document-content {_NS}><office:body><office:text>{body}'
                                    "</office:text></office:body></office:document-content>")  # fmt: skip
    return path


# --- reading ----------------------------------------------------------------------------------------------

def test_reading_maps_the_cvs_headings_tables_tabs_and_lists(tmp_path):
    path = odt_with(tmp_path, (
        "<text:p>Ada <text:span>Lovelace</text:span></text:p><text:p>ada@example.com<text:line-break/>London</text:p>"
        '<text:h text:outline-level="1">Introduction</text:h><text:p>Builds  engines.</text:p>'
        "<text:h>Relevant Experience</text:h>"
        "<table:table><table:table-row><table:table-cell><text:p>Engineer, Engines</text:p></table:table-cell>"
        "<table:table-cell><text:p>2020 – Now</text:p></table:table-cell></table:table-row></table:table>"
        "<text:list><text:list-item><text:p>Wrote the first program.</text:p></text:list-item>"
        "<text:list-item><text:h>Additional Experience</text:h></text:list-item></text:list>"
        "<text:p>Tutor<text:tab/>2018</text:p>"
        "<text:h>Accomplishments &amp; Publications</text:h><text:list><text:list-item><text:p>Best Paper</text:p>"
        "</text:list-item></text:list>"
    ))  # fmt: skip
    cv = read_odt(path)
    assert cv.sections == {
        "contact": ("Ada Lovelace", "ada@example.com", "London"),
        "summary": ("Builds engines.",),
        "experience": ("Engineer, Engines | 2020 – Now", "• Wrote the first program.", "Tutor | 2018"),
        "awards": ("• Best Paper",),
    }


def test_an_unknown_heading_or_a_non_odt_is_refused_by_name(tmp_path):
    with pytest.raises(ValueError, match="Hobbies"):
        read_odt(odt_with(tmp_path, "<text:p>Ada</text:p><text:h>Hobbies</text:h><text:p>chess</text:p>"))
    bad = tmp_path / "cv.odt"
    bad.write_text("not a zip")
    with pytest.raises(ValueError, match="not an .odt"):
        read_odt(bad)
    assert heading_section("Honors  &  Awards") == "awards" and heading_section("Hobbies") is None


def test_what_the_writer_writes_reads_back_the_same(tmp_path):
    path = OdtWriter("letter").write(CV, ORDER.usual, tmp_path / "out" / "CV.odt")
    again = read_odt(path)
    assert again.sections == {name: CV.lines(name) for name in ORDER.usual if name in CV.sections}
    with zipfile.ZipFile(path) as odt:
        assert odt.namelist()[0] == "mimetype" and odt.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        content, styles = odt.read("content.xml").decode(), odt.read("styles.xml").decode()
    assert "table:table" not in content and "draw:" not in content  # one column: paragraphs only
    assert "&lt;clean&gt;" in content and 'fo:page-width="8.5in"' in styles


def test_the_writer_knows_the_papers_and_the_line_kinds(tmp_path):
    a4 = OdtWriter("a4", LAYOUTS[-1]).write(CV, ORDER.usual, tmp_path / "a4.odt")
    with zipfile.ZipFile(a4) as odt:
        assert 'fo:page-width="8.27in"' in odt.read("styles.xml").decode()
    with pytest.raises(ValueError, match="paper"):
        OdtWriter("legal")
    assert [line_kind("contact", 0, "Ada"), line_kind("contact", 1, "a | b"), line_kind("experience", 0, "x | 2020"),
            line_kind("skills", 0, "a | b"), line_kind("awards", 0, "• prize")] == [
            "name", "contact", "entry", "body", "bullet"]  # fmt: skip
    assert LAYOUTS[0].font_pt > LAYOUTS[-1].font_pt and LAYOUTS[0].margin_in > LAYOUTS[-1].margin_in


# --- the PDF check ----------------------------------------------------------------------------------------

LETTER = [(612.0, 792.0)]


def test_assess_finds_what_is_wrong_with_a_page():
    text = "Ada Lovelace\nSummary\nSkills"
    assert assess(LETTER, text, "letter", ["Summary", "Skills"], "Ada Lovelace") == []
    assert "not a4" in assess(LETTER, text, "a4")[0]
    assert assess(LETTER, "  ", "letter") == ["no text in the PDF (only images?)"]
    assert "Education" in assess(LETTER, text, "letter", ["Education"])[0]
    assert "name" in assess(LETTER, text, "letter", name="Grace Hopper")[0]
    assert "unreadable" in assess(LETTER, text + "\ufffd", "letter")[0]
    assert PageReport(pages=2, text="").one_page is False


def test_no_libreoffice_is_said_plainly(tmp_path):
    export = PdfExport(tmp_path / "missing" / "soffice.exe")
    assert not export.available()
    with pytest.raises(FileNotFoundError, match="soffice"):
        export.export(tmp_path / "CV.odt")


# --- the fit to one page ----------------------------------------------------------------------------------

class FakeExport:
    """Writes a PDF of `CV` next to the .odt (the fixture's own text PDF, no LibreOffice)."""

    def __init__(self, cv: CvContent | None = None) -> None:
        self.cv, self.made = cv or CV, []

    def export(self, odt):
        self.made.append(Path(odt))
        return write_pdf(self.cv, ORDER.usual, Path(odt).with_suffix(".pdf"))


class FakeCheck(PageCheck):
    """One page once the layout is at most `font_pt` and `dropped` sections are gone; else two."""

    def __init__(self, fits) -> None:
        self.fits, self.seen = fits, []

    def read(self, pdf, paper, titles=(), name=""):
        self.seen.append(tuple(titles))
        return PageReport(pages=1 if self.fits(len(self.seen), tuple(titles)) else 2, text=name)


def fit(fits, **kw):
    check = FakeCheck(fits)
    return build_cv(CV, ORDER, Path("out/CV.pdf"), FakeExport(), check=check, **kw), check


def test_the_roomiest_layout_that_fits_is_kept(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    built, _ = fit(lambda n, titles: n == 2)
    assert built.one_page and built.tries == 2 and built.layout == LAYOUTS[1] and built.choice.dropped == ()
    assert built.as_value()["pages"] == 1 and built.as_value()["layout"] == LAYOUTS[1].describe()
    assert "odt_path" not in built.as_value()


def test_only_the_pdf_comes_out_the_odt_stays_in_a_temp_folder(tmp_path):
    export = FakeExport()
    built = build_cv(CV, ORDER, tmp_path / "job" / "CV_Test_Acme.pdf", export, check=FakeCheck(lambda n, t: True))
    assert built.pdf_path == tmp_path / "job" / "CV_Test_Acme.pdf" and built.pdf_path.read_bytes()[:5] == b"%PDF-"
    assert sorted(p.name for p in (tmp_path / "job").iterdir()) == ["CV_Test_Acme.pdf"]  # no .odt beside it
    assert export.made and not any(p.is_relative_to(tmp_path) for p in export.made)
    assert not any(p.exists() or p.parent.exists() for p in export.made)  # the temp folder is gone
    with pytest.raises(ValueError, match=r"must be a \.pdf"):
        build_cv(CV, ORDER, tmp_path / "CV.odt", FakeExport())


def test_publications_then_awards_go_when_no_layout_fits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    built, check = fit(lambda n, titles: "Awards" not in titles)
    assert built.one_page and built.choice.dropped == ("awards", "publications") and built.tries == 7
    assert "Publications" not in check.seen[3] and "Awards" in check.seen[3]  # Publications went first
    never, _ = fit(lambda n, titles: False)
    assert not never.one_page and never.tries == 9 and never.layout == LAYOUTS[-1] and never.report.pages == 2
    kept, _ = fit(lambda n, titles: False, auto_drop=False)
    assert kept.tries == 3 and kept.choice.dropped == ()
    asked, _ = fit(lambda n, titles: True, drop=1)
    assert asked.choice.dropped == ("publications",) and asked.tries == 1


def test_a_cv_without_contact_is_refused(tmp_path):
    with pytest.raises(ValueError, match="contact"):
        build_cv(CvContent(sections={"skills": ("Python",)}), ORDER, tmp_path / "CV.pdf", FakeExport())


def test_the_output_goes_in_a_dated_folder_per_company():
    path = output_path("C:/out", "Acme Robotics, Inc.", date(2026, 11, 6))
    # named like the job's work folder (job_start.name_part), so both read the same
    assert path == Path("C:/out/2026-11-06_AcmeRoboticsInc/CV_Test_AcmeRoboticsInc.pdf")
    assert output_path("C:/out", "ExampleCorp", date(2026, 11, 9)).parent.name == "2026-11-09_ExampleCorp"
    assert output_path("C:/out", "???", date(2026, 11, 6)).name == "CV_Test_Company.pdf"


# --- the cv.build item ------------------------------------------------------------------------------------

async def call(tmp_path: Path, soffice: str, export=None, **args):
    section = {"output_dir": str(tmp_path / "out"), "soffice": soffice, "work_dir": str(tmp_path / "work")}
    app = App([CvModule], {"modules": {"enabled": ["cv"], "cv": section | {"agent": {"enabled": False}}}, "core": {}})
    await app.start()
    try:
        if export is not None:
            app._lifecycle._active["cv"][0]._export = export
        return await app.router.send(InvokeTool(name="cv.build", args=args, caller="cv_agent"))
    finally:
        await app.stop()


SECTIONS_ARG = {name: list(lines) for name, lines in CV.sections.items()}


async def test_cv_build_checks_its_arguments(tmp_path):
    assert "cv.build" in CvModule.menu.names()
    missing = str(tmp_path / "no" / "soffice.exe")
    odt = OdtWriter().write(CV, ORDER.usual, tmp_path / "CV_Test_Base.odt")  # a real .odt: refused all the same
    for args in ({"company": "Acme"}, {"company": "Acme", "base_cv": "x.pdf", "sections": SECTIONS_ARG},
                 {"company": "Acme", "base_cv": str(odt)}, {"company": "Acme", "base_cv": str(tmp_path / "gone.pdf")},
                 {"company": "Acme", "sections": {"hobbies": ["chess"]}}, {"company": "Acme", "sections": {"skills": "x"}},
                 {"company": "Acme", "sections": SECTIONS_ARG, "drop": -1}, {"company": ""},
                 {"company": "Acme", "sections": SECTIONS_ARG, "job_dir": str(tmp_path / "out")},
                 {"company": "Acme", "sections": SECTIONS_ARG, "job_dir": str(tmp_path / "work")},
                 {"company": "Acme", "sections": SECTIONS_ARG, "job_dir": str(tmp_path / "work" / "gone")}):  # fmt: skip
        result = await call(tmp_path, missing, **args)
        assert result.status is Status.INVALID_ARGUMENTS, (args, result.error)
    refused = await call(tmp_path, missing, company="Acme", base_cv=str(odt))
    assert ".odt isn't read" in refused.error
    result = await call(tmp_path, missing, company="Acme", sections=SECTIONS_ARG)
    assert result.status is Status.NOT_AVAILABLE and "LibreOffice" in result.error


async def test_cv_build_exports_the_pdf_into_the_jobs_folder_never_over_its_base_copy(tmp_path):
    job = tmp_path / "work" / "2026-11-09_Acme_Engineer"
    base = write_pdf(CV, ORDER.usual, tmp_path / "CV" / "CV_Test_Base.pdf")
    copy = job / "CV_Test_Acme.pdf"  # the job's copy of a base CV that happens to share the name
    copy.parent.mkdir(parents=True)
    copy.write_bytes(base.read_bytes())
    (job / "job_start.json").write_text(json.dumps({"job": {"base_cv_copy": str(copy)}}), encoding="utf-8")
    missing = str(tmp_path / "no" / "soffice.exe")
    result = await call(tmp_path, missing, FakeExport(), company="Acme", base_cv=str(copy), job_dir=str(job))
    assert result.status is Status.OK, result.error
    value = result.value
    assert Path(value["pdf_path"]) == job / "CV_Test_Acme_tailored.pdf" and Path(value["pdf_path"]).is_file()
    assert value["one_page"] and value["problems"] == [] and "odt_path" not in value
    assert copy.read_bytes() == base.read_bytes()  # the job's base copy is only read
    assert sorted(p.suffix for p in job.iterdir()) == [".json", ".pdf", ".pdf"]  # no .odt in the job's folder
    assert not (tmp_path / "out").exists()  # with job_dir, nothing goes to output_dir

    other = await call(tmp_path, missing, FakeExport(), company="Beta", sections=SECTIONS_ARG, job_dir=str(job))
    assert other.is_ok and Path(other.value["pdf_path"]) == job / "CV_Test_Beta.pdf"
    plain = await call(tmp_path, missing, FakeExport(), company="Beta", sections=SECTIONS_ARG)
    assert plain.is_ok and Path(plain.value["pdf_path"]).parent.parent == tmp_path / "out"


@pytest.mark.skipif(not SOFFICE.is_file(), reason="LibreOffice is not installed")
async def test_cv_build_makes_one_clean_page_with_libreoffice(tmp_path):
    base = write_pdf(CV, ORDER.usual, tmp_path / "CV" / "CV_Test_Base.pdf")
    before = base.read_bytes()
    result = await call(tmp_path, str(SOFFICE), company="Acme", base_cv=str(base),
                        jd_text="An M.S. in Computer Science is preferred.")  # fmt: skip
    assert result.status is Status.OK, result.error
    value = result.value
    assert value["one_page"] and value["problems"] == [] and value["paper"] == "letter"
    assert value["section_order"].index("education") == value["section_order"].index("skills") + 1
    pdf = Path(value["pdf_path"])
    assert pdf.is_file() and pdf.parent.parent == tmp_path / "out" and "odt_path" not in value
    assert [p.suffix for p in pdf.parent.iterdir()] == [".pdf"]  # only the PDF comes out
    assert "Ada Lovelace" in value["text"] and "Present" in value["text"]
    assert base.read_bytes() == before  # the base CV is only read
