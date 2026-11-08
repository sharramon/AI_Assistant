"""The `.odt` side of the one page: read a CV_Test_*.odt into plain sections, write the one page.

Lines are plain text with two marks, the same both ways (reading a written page gives the same lines):
- `• text` is a bullet;
- `left | right` in Experience, Projects, Education, Awards or Publications is an entry line: the
  left part bold, the right part (the dates) at the right margin. In the source `.odt` this is a
  table row (cells) or a tab between two pieces of text.
The first Contact line is the name.

`read_odt` maps the CVs' heading names to the eight sections (`HEADINGS`: "Introduction" is the
summary, "Additional Experience" joins Experience, "Accomplishments & Publications" is Awards) and
refuses a heading it doesn't know, naming it. Text boxes, images and frames are skipped.

`OdtWriter` writes one column: standard headings, paragraphs only (no tables, text boxes or
images), so the PDF reads cleanly. The `Layout` (font size, margins, gaps) is what `build.py`
tightens to fit one page.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from assistant.modules.cv.content import CvContent

_NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
}
_T = f"{{{_NS['text']}}}"  # ElementTree's "{namespace}tag" prefixes
_TB = f"{{{_NS['table']}}}"
_O = f"{{{_NS['office']}}}"

# The one page's heading for each section (Contact has none).
TITLES = {
    "summary": "Summary", "skills": "Skills", "experience": "Experience", "projects": "Projects",
    "education": "Education", "awards": "Awards", "publications": "Publications",
}  # fmt: skip

# Heading names found on the CVs (lower case, "&" as "and") -> section. The titles above map back too.
HEADINGS = {
    **{title.lower(): name for name, title in TITLES.items()},
    "introduction": "summary", "professional summary": "summary", "profile": "summary", "objective": "summary",
    "technical skills": "skills", "core skills": "skills",
    "relevant experience": "experience", "work experience": "experience",
    "professional experience": "experience", "additional experience": "experience",
    "selected projects": "projects",
    "accomplishments": "awards", "accomplishments and publications": "awards", "honors": "awards",
    "awards and honors": "awards", "honors and awards": "awards",
}  # fmt: skip

ENTRY_SECTIONS = ("experience", "projects", "education", "awards", "publications")
BULLET = "• "
_BULLET_MARKS = ("• ", "- ", "* ", "•")

PAPER_SIZES_IN = {"letter": (8.5, 11.0), "a4": (8.27, 11.69)}


# --- reading ----------------------------------------------------------------------------------------------

def heading_section(heading: str) -> str | None:
    """The section a heading name stands for, or None if it isn't one the CVs use."""
    key = re.sub(r"\s+", " ", heading.replace("&", " and ")).strip().lower()
    return HEADINGS.get(key)


def read_odt(path: str | Path) -> CvContent:
    """The CV in an `.odt` as plain sections (read only). ValueError: not an .odt, or an unknown heading."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as odt:
            xml = odt.read("content.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(f"{path.name}: not an .odt document ({exc})") from exc
    body = ET.fromstring(xml).find(f"{_O}body/{_O}text")
    if body is None:
        raise ValueError(f"{path.name}: not a text document")
    sections: dict[str, list[str]] = {}
    current: str | None = "contact"
    unknown: list[str] = []
    for kind, el in _blocks(body):
        if kind == "heading":
            heading = _clean(_text(el))
            if not heading:
                continue
            current = heading_section(heading)
            if current is None:
                unknown.append(heading)
            continue
        if current is not None:
            sections.setdefault(current, []).extend(_lines(kind, el, header=current == "contact"))
    if unknown:
        raise ValueError(f"{path.name}: headings not known {unknown}; known: {sorted(HEADINGS)}")
    return CvContent(sections={name: tuple(lines) for name, lines in sections.items() if lines})


def _blocks(parent: Iterable[ET.Element]) -> Iterator[tuple[str, ET.Element]]:
    """(kind, element) in reading order: heading, paragraph, bullet or table. Lists are opened up,
    so a heading kept inside a list (the CVs' "Additional Experience") still counts as a heading."""
    for el in parent:
        if el.tag in (_T + "section", _T + "index-body"):
            yield from _blocks(el)
        elif el.tag == _T + "h":
            yield "heading", el
        elif el.tag == _T + "p":
            yield "paragraph", el
        elif el.tag == _TB + "table":
            yield "table", el
        elif el.tag == _T + "list":
            for item in el:
                for child in item:
                    if child.tag == _T + "h":
                        yield "heading", child
                    elif child.tag == _T + "p":
                        yield "bullet", child
                    elif child.tag == _T + "list":
                        yield from _blocks([child])


def _lines(kind: str, el: ET.Element, header: bool) -> list[str]:
    """One block's lines. In the header (Contact) every paragraph and line break is its own line."""
    if kind == "paragraph":
        return [line for line in (_clean(part) for part in _text(el).split("\n")) if line]
    if kind == "bullet":
        text = _clean(_text(el).replace("\n", " "))
        return [BULLET + text] if text else []
    if kind == "table":
        out: list[str] = []
        for row in el.iter(_TB + "table-row"):
            cells = [[p for p in cell.iter() if p.tag in (_T + "p", _T + "h")]
                     for cell in row.findall(_TB + "table-cell")]  # fmt: skip
            if header:
                out += [line for cell in cells for p in cell for line in _lines("paragraph", p, header=True)]
            else:
                texts = [_clean(" ".join(_text(p).replace("\n", " ") for p in cell)) for cell in cells]
                if any(texts):
                    out.append(" | ".join(t for t in texts if t))
        return out
    return []


def _text(el: ET.Element) -> str:
    """An element's text: spaces, tabs and line breaks kept; frames, shapes and notes skipped."""
    out = [el.text or ""]
    for child in el:
        tag = child.tag
        if tag == _T + "s":
            out.append(" " * int(child.get(_T + "c", "1")))
        elif tag == _T + "tab":
            out.append("\t")
        elif tag == _T + "line-break":
            out.append("\n")
        elif tag in (_T + "span", _T + "a"):
            out.append(_text(child))
        out.append(child.tail or "")
    return "".join(out)


def _clean(line: str) -> str:
    """Spaces collapsed; a tab between two pieces of text becomes ` | ` (an entry line's dates)."""
    parts = [re.sub(r"\s+", " ", part).strip() for part in line.replace("\xa0", " ").split("\t")]
    return " | ".join(part for part in parts if part)


# --- writing ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Layout:
    """How roomy the page is: body font size (pt), page margins (in), gap above headings (pt)."""

    font_pt: float
    margin_in: float
    gap_pt: float

    def describe(self) -> str:
        return f"{self.font_pt:g} pt, {self.margin_in:g} in margins"


# From roomy to tight; `build.py` takes the first that fits one page.
LAYOUTS = (Layout(10.5, 0.6, 6), Layout(10, 0.5, 4), Layout(9.5, 0.45, 3))


def line_kind(section: str, index: int, line: str) -> str:
    """How a line is set: name, contact, bullet, entry (left | right) or body."""
    if section == "contact":
        return "name" if index == 0 else "contact"
    if line.startswith(_BULLET_MARKS):
        return "bullet"
    if section in ENTRY_SECTIONS and " | " in line:
        return "entry"
    return "body"


class OdtWriter:
    """Writes the one page as an `.odt`: one column, standard headings, paragraphs only."""

    def __init__(self, paper: str = "letter", layout: Layout = LAYOUTS[0]) -> None:
        if paper not in PAPER_SIZES_IN:
            raise ValueError(f"paper must be one of {list(PAPER_SIZES_IN)}, not {paper!r}")
        self.paper, self.layout = paper, layout

    def write(self, content: CvContent, order: Iterable[str], path: str | Path) -> Path:
        """The sections in `order` (only those the CV has) written to `path`; returns the path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as odt:
            odt.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")  # first, stored
            odt.writestr("META-INF/manifest.xml", _MANIFEST, zipfile.ZIP_DEFLATED)
            odt.writestr("styles.xml", self._styles(), zipfile.ZIP_DEFLATED)
            odt.writestr("content.xml", self._content(content, order), zipfile.ZIP_DEFLATED)
        return path

    def _content(self, content: CvContent, order: Iterable[str]) -> str:
        parts: list[str] = []
        for section, lines in content.ordered(order):
            if section in TITLES:
                parts.append(f'<text:h text:style-name="CvHeading" text:outline-level="1">{TITLES[section]}</text:h>')
            for index, line in enumerate(line for line in lines if line.strip()):
                parts.append(_paragraph(line_kind(section, index, line), line))
        return (f'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-content {_xmlns()} office:version="1.3">'
                f"{_FONTS}<office:body><office:text>{''.join(parts)}</office:text></office:body>"
                "</office:document-content>")  # fmt: skip

    def _styles(self) -> str:
        width, height = PAPER_SIZES_IN[self.paper]
        lay = self.layout
        text_width = width - 2 * lay.margin_in
        size = f"{lay.font_pt:g}pt"

        def para(name: str, para_props: str, text_props: str = "", inner: str = "") -> str:
            return (f'<style:style style:name="{name}" style:family="paragraph" style:parent-style-name="CvBase">'
                    f"<style:paragraph-properties {para_props}>{inner}</style:paragraph-properties>"
                    f"<style:text-properties {text_props}/></style:style>")  # fmt: skip

        styles = "".join((
            '<style:style style:name="CvBase" style:family="paragraph"><style:paragraph-properties '
            'fo:margin-top="0in" fo:margin-bottom="0in" fo:line-height="110%"/>'
            f'<style:text-properties style:font-name="Arial" fo:font-size="{size}" fo:language="en" '
            'fo:country="US"/></style:style>',
            para("CvName", 'fo:text-align="center" fo:margin-bottom="0.02in"',
                 f'fo:font-size="{lay.font_pt + 7:g}pt" fo:font-weight="bold"'),
            para("CvContact", 'fo:text-align="center"'),
            para("CvHeading", f'fo:margin-top="{lay.gap_pt:g}pt" fo:margin-bottom="2pt" fo:keep-with-next="always" '
                              'fo:padding-bottom="1pt" fo:border-bottom="0.5pt solid #000000"',
                 f'fo:font-size="{lay.font_pt + 1.5:g}pt" fo:font-weight="bold"'),
            para("CvBody", 'fo:margin-bottom="1pt"'),
            para("CvEntry", 'fo:margin-top="2pt" fo:keep-with-next="always"', "",
                 f'<style:tab-stops><style:tab-stop style:position="{text_width - 0.01:.2f}in" '
                 'style:type="right"/></style:tab-stops>'),
            para("CvBullet", 'fo:margin-left="0.18in" fo:text-indent="-0.12in" fo:margin-bottom="1pt"'),
            '<style:style style:name="CvBold" style:family="text"><style:text-properties fo:font-weight="bold"/>'
            "</style:style>",
        ))  # fmt: skip
        return (f'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-styles {_xmlns()} office:version="1.3">'
                f"{_FONTS}<office:styles>{styles}</office:styles><office:automatic-styles>"
                f'<style:page-layout style:name="CvPage"><style:page-layout-properties fo:page-width="{width}in" '
                f'fo:page-height="{height}in" style:print-orientation="portrait" fo:margin-top="{lay.margin_in}in" '
                f'fo:margin-bottom="{lay.margin_in}in" fo:margin-left="{lay.margin_in}in" '
                f'fo:margin-right="{lay.margin_in}in"/></style:page-layout></office:automatic-styles>'
                '<office:master-styles><style:master-page style:name="Standard" style:page-layout-name="CvPage"/>'
                "</office:master-styles></office:document-styles>")  # fmt: skip


def _paragraph(kind: str, line: str) -> str:
    if kind == "bullet":
        text = next(line[len(mark):] for mark in _BULLET_MARKS if line.startswith(mark)).strip()
        return f'<text:p text:style-name="CvBullet">{escape(BULLET + text)}</text:p>'
    if kind == "entry":
        left, right = line.rsplit(" | ", 1)
        right = right.replace(" ", "\xa0")  # the dates stay on one line when the left part is long
        return (f'<text:p text:style-name="CvEntry"><text:span text:style-name="CvBold">{escape(left)}</text:span>'
                f"<text:tab/>{escape(right)}</text:p>")  # fmt: skip
    style = {"name": "CvName", "contact": "CvContact"}.get(kind, "CvBody")
    return f'<text:p text:style-name="{style}">{escape(line)}</text:p>'


def _xmlns() -> str:
    return " ".join(f'xmlns:{prefix}="{uri}"' for prefix, uri in _NS.items() if prefix != "manifest")


_FONTS = ('<office:font-face-decls><style:font-face style:name="Arial" svg:font-family="Arial" '
          'style:font-family-generic="swiss"/></office:font-face-decls>')  # fmt: skip

_MANIFEST = (f'<?xml version="1.0" encoding="UTF-8"?>\n<manifest:manifest xmlns:manifest="{_NS["manifest"]}" '
             'manifest:version="1.3">'
             '<manifest:file-entry manifest:full-path="/" manifest:version="1.3" '
             'manifest:media-type="application/vnd.oasis.opendocument.text"/>'
             '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
             '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
             "</manifest:manifest>")  # fmt: skip
