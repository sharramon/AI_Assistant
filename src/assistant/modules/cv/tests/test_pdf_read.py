"""The CV PDF reader (`pdf_read.py`): how lines become sections, the read check, and real PDFs read
back (the fixture's text PDF, and the module's own writer through LibreOffice, skipped without it)."""

import tomllib
from pathlib import Path

import pytest

from assistant.modules.cv.content import CvContent
from assistant.modules.cv.odt import OdtWriter
from assistant.modules.cv.order import SectionOrder
from assistant.modules.cv.pdf import PdfExport
from assistant.modules.cv.pdf_read import Line, Run, _line, _small_caps, _unread, place, read_pdf
from assistant.modules.cv.tests.pdf_fixture import write_pdf

DEFAULTS = tomllib.loads((Path(__file__).parents[1] / "module.toml").read_text(encoding="utf-8"))
ORDER = SectionOrder.from_config(DEFAULTS)
SOFFICE = Path(DEFAULTS["soffice"])
LEFT, RIGHT = 50.0, 500.0


def ln(text: str, x0: float = LEFT, x1: float = RIGHT - 5, size: float = 10.0, first_word: float = 20.0,
       bullet: bool = False) -> Line:  # fmt: skip
    """A line as `_lines` makes it, on a page from LEFT to RIGHT."""
    return Line(runs=[Run(x0, x1, 700.0, size, text)], text=text, bullet=bullet, x0=x0, x1=x1, size=size,
                first_word=first_word, right=RIGHT, left=LEFT)  # fmt: skip


NAME = ln("Ada Lovelace", x1=150, size=18)


def head(title: str) -> Line:
    return ln(title, x1=110, size=12)


# --- place: lines into sections ---------------------------------------------------------------------------


def test_a_wrapped_line_joins_the_one_above_and_a_short_one_doesnt():
    read = place([NAME, head("Summary"),
                  ln("Builds engines that"), ln("compute.", x1=100, first_word=40),  # no room for "compute." above
                  ln("Short line.", x1=200), ln("Next item.", x1=150)])  # room left above: its own item  # fmt: skip
    assert read.content.lines("summary") == ("Builds engines that compute.", "Short line.", "Next item.")
    assert read.content.lines("contact") == ("Ada Lovelace",)


def test_a_line_broken_at_a_hyphen_joins_without_a_space():
    read = place([NAME, head("Summary"), ln("Builds real-"), ln("time engines.", x1=120, first_word=60)])
    assert read.content.lines("summary") == ("Builds real-time engines.",)


def test_a_centered_wrap_joins_when_the_word_wouldnt_fit_the_whole_width():
    above = ln("Builds engines that compute and more", x0=100, x1=460)  # center 280
    below = ln("words here", x0=230, x1=330, first_word=100)  # center 280
    assert place([NAME, head("Summary"), above, below]).content.lines("summary") == (
        "Builds engines that compute and more words here",)  # fmt: skip
    narrow = ln("words here", x0=255, x1=305, first_word=20)  # it would have fit: a line of its own
    assert len(place([NAME, head("Summary"), above, narrow]).content.lines("summary")) == 2


def test_a_label_line_never_joins_the_line_above():
    read = place([NAME, head("Skills"), ln("Languages: Python, C++, C#, Java, JavaScript, MATLAB, SQL"),
                  ln("Tools: Git, Docker", x1=150, first_word=40)])  # fmt: skip
    assert read.content.lines("skills") == ("Languages: Python, C++, C#, Java, JavaScript, MATLAB, SQL", "Tools: Git, Docker")


def test_an_entrys_next_line_is_its_left_part_and_bullets_stay_items():
    read = place([NAME, head("Experience"), ln("Engineer, Engines | Jan 2020 – Present"),
                  ln("Analytical Lab", x1=120), ln("Wrote the first program.", x1=200, bullet=True),
                  ln("Kept the notes.", x1=180, bullet=True)])  # fmt: skip
    assert read.content.lines("experience") == (
        "Engineer, Engines Analytical Lab | Jan 2020 – Present", "• Wrote the first program.", "• Kept the notes.")
    assert read.complete


def test_text_under_a_heading_it_doesnt_know_is_unplaced_once():
    lines = [NAME, head("Summary"), ln("Builds engines.", x1=150), ln("Hobbies", x1=100, size=14), ln("chess", x1=90)]
    read = place(lines, "Ada Lovelace Summary Builds engines. Hobbies chess")
    assert read.unplaced == ("Hobbies", "chess") and not read.complete
    assert read.content.lines("summary") == ("Builds engines.",)
    with_hidden = place(lines[:3], "Ada Lovelace Summary Builds engines. secret")  # text the lines didn't hold
    assert with_hidden.unplaced == ("secret",)


def test_the_read_check_counts_each_word():
    assert _unread("Python Python C++ Rust", ["Python, C++"]) == ["Python", "Rust"]
    assert _unread("Ada", ["ada"]) == []


# --- runs into a line -------------------------------------------------------------------------------------


def test_small_caps_are_lower_cased_and_real_capitals_kept():
    runs = _small_caps([Run(50, 58, 700, 10, "C"), Run(58, 80, 700, 8, "HANG"), Run(84, 92, 700, 10, "H"),
                        Run(92, 108, 700, 8, "UR")])  # fmt: skip
    assert [r.text for r in runs] == ["C", "hang", "H", "ur"]
    kept = _small_caps([Run(50, 80, 700, 10, "NASA"), Run(84, 110, 700, 10, "JPL")])  # same size: capitals
    assert [r.text for r in kept] == ["NASA", "JPL"]


def test_a_bullet_glyph_marks_the_line_and_a_wide_gap_is_the_entrys_bar():
    bullet = _line([Run(50, 200, 700, 10, "• Wrote it")])
    assert bullet is not None and bullet.bullet and bullet.text == "Wrote it" and bullet.x0 > 50
    alone = _line([Run(50, 55, 700, 10, "▪"), Run(62, 200, 700, 10, "Kept notes")])
    assert alone is not None and alone.bullet and alone.text == "Kept notes" and alone.x0 == 62
    entry = _line([Run(50, 150, 700, 10, "Engineer"), Run(470, 500, 700, 10, "2020")])
    assert entry is not None and entry.text == "Engineer | 2020" and entry.entry
    spaced = _line([Run(50, 100, 700, 10, "Ada"), Run(103, 150, 700, 10, "Lovelace")])
    assert spaced is not None and spaced.text == "Ada Lovelace"
    assert _line([Run(50, 60, 700, 10, "  ")]) is None


# --- real PDFs --------------------------------------------------------------------------------------------

CV = CvContent(sections={
    "contact": ("Ada Lovelace", "ada@example.com | London"),
    "summary": ("Builds engines that compute.",),
    "skills": ("Languages: Python, C++", "Tools: Git"),
    "experience": ("Engineer, Analytical Engines | Jan 2020 – Present", "• Wrote the first program.",
                   "• Kept notes & tables."),
    "education": ("B.Sc. Mathematics | 2015",),
    "awards": ("• Best Paper",),
})  # fmt: skip


def test_a_text_pdf_reads_back_to_its_sections(tmp_path):
    read = read_pdf(write_pdf(CV, ORDER.usual, tmp_path / "CV_Test_Test.pdf"))
    assert read.complete and read.pages == 1 and read.content.sections == CV.sections
    # sections, not the models: a reload test elsewhere may import a fresh copy of the class
    assert CvContent.from_pdf(tmp_path / "CV_Test_Test.pdf").sections == CV.sections


def test_from_pdf_refuses_text_it_cant_place_and_a_broken_pdf(tmp_path):
    odd = write_pdf(CV, ORDER.usual, tmp_path / "CV_Test_Odd.pdf", extra=((14.0, "Hobbies"), (10.0, "chess")))
    with pytest.raises(ValueError, match=r"2 piece\(s\) of text couldn't be placed.*'Hobbies'"):
        CvContent.from_pdf(odd)
    broken = tmp_path / "CV_Test_Broken.pdf"
    broken.write_bytes(b"%PDF-1.4 not really")
    with pytest.raises(ValueError, match="not a readable PDF|no text"):
        read_pdf(broken)


@pytest.mark.skipif(not SOFFICE.is_file(), reason="LibreOffice is not installed")
def test_the_modules_own_page_reads_back_through_libreoffice(tmp_path):
    odt = OdtWriter("letter").write(CV, ORDER.usual, tmp_path / "CV.odt")
    read = read_pdf(PdfExport(SOFFICE).export(odt))
    assert read.complete, read.unplaced
    assert read.content.sections == CV.sections
