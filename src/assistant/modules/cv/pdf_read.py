"""Reading a CV PDF into plain sections: the base CV comes in as a `CV_Test_*.pdf`.

The lines come out with the same two marks `odt.py` uses (`• text` a bullet, `left | dates` an
entry line; the first Contact line is the name), and the headings map to the eight sections the
same way (`odt.heading_section`). How the page is read back:
- **Runs:** each piece of text with its start and end on the line, its baseline and its size
  (pypdf's layout reader, `_runs`). A run in capitals at about 0.8 of the size of the run beside it
  is small caps: lower case on the page's source, so it's lower-cased (`J`+`ANE` → `Jane`).
- **Lines:** runs on the same baseline (the dates sit a little off it), joined left to right: a
  wide gap is the entry's ` | `, a small one a space.
- **Paragraphs:** a line goes on the one above when it starts where that one's text starts and
  its first word wouldn't have fit at the end of the line above (so it was wrapped there); a line
  under an entry, starting where the entry starts, is the rest of the entry's left part.
- **The read check:** every word pypdf's plain text has must be in what was read (`unplaced`
  lists the ones that aren't, with the text under a heading it doesn't know). Anything unplaced
  stops the worker, who asks you.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from assistant.modules.cv.content import CvContent
from assistant.modules.cv.odt import BULLET, ENTRY_SECTIONS, heading_section

# Bullet glyphs the CVs' PDFs use: Symbol's and Wingdings' private-use ones and the plain ones.
BULLET_GLYPHS = frozenset("•▪●◦■‣⁃")
_SMALL_CAPS = (0.72, 0.88)  # a small-caps run's size against the run beside it
_ENTRY_GAP = 2.5  # a gap this many font sizes wide is the entry's " | " (the tab to the dates)
_SPACE_GAP = 0.15  # a gap this many font sizes wide is a space
_SAME_LINE = 0.45  # runs this many font sizes apart in height are on one line
_HEADING_SIZE = 1.25  # a short line this much bigger than the body text is a heading
_WORD_WIDE = 1.1  # a word's share of its run's width by characters, made up to its real width
_WORD = re.compile(r"[^\W_]+")
_LABEL = re.compile(r"[A-Z][\w&/+-]*(?: [\w&/+-]+){0,2}:(?:\s|$)")  # a line's label: "Skills:", "AI Development:"


@dataclass(frozen=True)
class Run:
    """One piece of text on the page: from `x0` to `x1` on baseline `y`, at `size` pt."""

    x0: float
    x1: float
    y: float
    size: float
    text: str


@dataclass
class Line:
    """One line of the page: its runs left to right, joined into `text`."""

    runs: list[Run]
    text: str = ""
    bullet: bool = False
    x0: float = 0.0  # where the text starts (after a bullet glyph)
    x1: float = 0.0
    size: float = 0.0
    first_word: float = 0.0  # how wide its first word is
    right: float = 0.0  # the page's right edge: where the widest line ends
    left: float = 0.0  # the page's left edge: where the leftmost line starts

    @property
    def entry(self) -> bool:
        return " | " in self.text


@dataclass(frozen=True)
class PdfCv:
    """A CV read from a PDF: its sections, and the words the read check couldn't place."""

    content: CvContent
    unplaced: tuple[str, ...] = field(default=())
    pages: int = 1

    @property
    def complete(self) -> bool:
        return not self.unplaced


def read_pdf(path: str | Path) -> PdfCv:
    """The CV in a PDF as plain sections, with the read check (read only). ValueError: not a
    readable PDF, or no text in it."""
    from pypdf import PdfReader  # imported on use: only the PDF parts need it
    from pypdf.errors import PdfReadError

    path = Path(path)
    try:
        reader = PdfReader(str(path))
        pages = list(reader.pages)
        plain = "\n".join(page.extract_text() or "" for page in pages)
        lines = [line for page in pages for line in _lines(_runs(page))]
    except (PdfReadError, OSError, KeyError, TypeError) as exc:
        raise ValueError(f"{path.name}: not a readable PDF ({exc})") from exc
    if not lines:
        raise ValueError(f"{path.name}: no text in the PDF (only images?)")
    return place(lines, plain, len(pages))


def place(lines: list[Line], plain: str = "", pages: int = 1) -> PdfCv:
    """The lines as sections, and the read check against `plain` (the PDF's plain text)."""
    body = _body_size(lines)
    sections: dict[str, list[str]] = {}
    last: dict[str, Line] = {}  # the line each section's last item came from
    unplaced: list[str] = []
    current: str | None = "contact"
    seen_heading = False
    for line in lines:
        name = None if line.bullet or line.entry else heading_section(line.text)
        if name is not None:
            current, seen_heading = name, True
            continue
        if seen_heading and not line.bullet and line.size >= body * _HEADING_SIZE and len(line.text) <= 60:
            current = None  # a heading it doesn't know: what's under it can't be placed
            unplaced.append(line.text)
            continue
        if current is None:
            unplaced.append(line.text)
            continue
        items = sections.setdefault(current, [])
        above = last.get(current)
        if items and above is not None and current != "contact" and _goes_on(above, line, current):
            items[-1] = _join(items[-1], line, above)
        else:
            items.append(BULLET + line.text if line.bullet else line.text)
        last[current] = line
    content = CvContent(sections={n: tuple(v) for n, v in sections.items() if v})
    # the lines already named as unplaced count as read here, so each piece is named once
    missing = _unread(plain, [*(line for v in content.sections.values() for line in v), *_headings(lines), *unplaced])
    return PdfCv(content=content, unplaced=tuple(unplaced) + tuple(missing), pages=pages)


def _goes_on(above: Line, line: Line, section: str) -> bool:
    """`line` continues the item `above` ended: the rest of an entry's left part, or a wrapped line."""
    if line.bullet or line.entry:
        return False
    if above.entry:
        return section in ENTRY_SECTIONS and abs(line.x0 - above.x0) <= 2.0
    if _LABEL.match(line.text):  # "Skills: …" starts an item of its own
        return False
    space = _SPACE_GAP * 2 * max(above.size, 1.0)
    word = line.first_word * _WORD_WIDE
    right = above.right or above.x1
    if abs(line.x0 - above.x0) <= 2.0:  # left aligned or justified: room left at the end of the line above
        return above.x1 + space + word > right - 1.0
    if abs((line.x0 + line.x1) - (above.x0 + above.x1)) <= 4.0:  # centered: room in the whole width
        return (above.x1 - above.x0) + space + word > right - min(above.left, line.left) - 1.0
    return False


def _join(item: str, line: Line, above: Line) -> str:
    if above.entry:  # the entry's left part goes on; the dates stay at the end
        left, right = item.rsplit(" | ", 1)
        return f"{left} {line.text} | {right}"
    if re.search(r"[A-Za-z]-$", item):  # broken at a hyphen: "real-" + "time"
        return item + line.text
    return f"{item} {line.text}"


def _headings(lines: Iterable[Line]) -> list[str]:
    return [line.text for line in lines if not line.bullet and heading_section(line.text) is not None]


def _unread(plain: str, read: Iterable[str]) -> list[str]:
    """The words of `plain` not in `read` (as many times as they're missing), in page order."""
    have = Counter(w.lower() for text in read for w in _WORD.findall(text))
    out = []
    for word in _WORD.findall(plain):
        key = word.lower()
        if have[key] > 0:
            have[key] -= 1
        else:
            out.append(word)
    return out


def _body_size(lines: Iterable[Line]) -> float:
    """The size most of the text is set in."""
    sizes: Counter[float] = Counter()
    for line in lines:
        for run in line.runs:
            sizes[round(run.size, 1)] += len(run.text.strip())
    return sizes.most_common(1)[0][0] if sizes else 10.0


# --- runs and lines ---------------------------------------------------------------------------------------

def _runs(page: object) -> list[Run]:
    """The page's text runs with their place and size, from pypdf's layout reader (its own
    `_layout_mode`, which the `layout` text mode uses). RuntimeError if pypdf changed it."""
    try:
        from pypdf._text_extraction import _layout_mode
        from pypdf.generic import ArrayObject, ContentStream, StreamObject

        contents = page.get("/Contents")  # type: ignore[attr-defined]
        if contents is None:
            return []
        contents = contents.get_object()
        if not isinstance(contents, (ArrayObject, StreamObject)):
            return []
        fonts = page._layout_mode_fonts()  # type: ignore[attr-defined]
        ops = iter(ContentStream(contents, page.pdf, "bytes").operations)  # type: ignore[attr-defined]
        groups = _layout_mode.text_show_operations(ops, fonts, True, None)
        return [Run(float(g["tx"]), float(g["displaced_tx"]), float(g["ty"]), float(g["font_size"]), str(g["text"]))
                for g in groups if g["text"]]  # fmt: skip
    except (ImportError, AttributeError, KeyError) as exc:
        raise RuntimeError(f"pypdf's layout reader isn't what the cv module reads PDFs with: {exc!r}") from exc


def _lines(runs: list[Run]) -> list[Line]:
    """The runs grouped into lines, top to bottom, each joined left to right."""
    rows: list[list[Run]] = []
    for run in sorted(runs, key=lambda r: (-r.y, r.x0)):
        if rows and abs(rows[-1][0].y - run.y) <= _SAME_LINE * max(run.size, rows[-1][0].size):
            rows[-1].append(run)
        else:
            rows.append([run])
    lines = [line for row in rows if (line := _line(sorted(row, key=lambda r: r.x0))) is not None]
    right = max((line.x1 for line in lines), default=0.0)
    left = min((line.x0 for line in lines), default=0.0)
    for line in lines:
        line.right, line.left = right, left
    return lines


def _line(runs: list[Run]) -> Line | None:
    runs = _small_caps(runs)
    shown = [r for r in runs if r.text.strip()]
    if not shown:
        return None
    bullet = False
    first = shown[0].text.lstrip()
    if first[:1] in BULLET_GLYPHS:
        bullet = True
        rest = first[1:].lstrip()
        if rest:
            shown[0] = Run(shown[0].x1 - _width(shown[0], rest), shown[0].x1, shown[0].y, shown[0].size, rest)
        else:
            shown = shown[1:]
            if not shown:
                return None
    parts: list[str] = []
    for i, run in enumerate(shown):
        if i:
            before = shown[i - 1]
            gap = run.x0 - before.x1
            if gap > max(_ENTRY_GAP * run.size, 18.0):
                parts.append(" | ")
            elif gap > _SPACE_GAP * run.size and not before.text.endswith(" ") and not run.text.startswith(" "):
                parts.append(" ")
        parts.append(run.text)
    text = " | ".join(" ".join(part.split()) for part in "".join(parts).replace("\xa0", " ").split(" | "))
    text = text.strip(" |")
    if not text:
        return None
    return Line(runs=shown, text=text, bullet=bullet, x0=shown[0].x0, x1=max(r.x1 for r in shown),
                size=max(r.size for r in shown), first_word=_first_word(shown))  # fmt: skip


def _small_caps(runs: list[Run]) -> list[Run]:
    """Runs in capitals set at about 0.8 of the size of the run beside them, lower-cased."""
    out = []
    for i, run in enumerate(runs):
        letters = [c for c in run.text if c.isalpha()]
        if letters and all(c.isupper() for c in letters):
            near = [runs[j] for j in (i - 1, i + 1) if 0 <= j < len(runs)
                    and min(abs(runs[j].x0 - run.x1), abs(run.x0 - runs[j].x1)) < 1.5]  # touching it
            if any(n.size and _SMALL_CAPS[0] <= run.size / n.size <= _SMALL_CAPS[1] for n in near):
                run = Run(run.x0, run.x1, run.y, run.size, run.text.lower())
        out.append(run)
    return out


def _width(run: Run, text: str) -> float:
    """About how wide `text` (part of `run`) is: the run's width shared out by characters,
    each weighted by about how wide it is in a sans font (capitals wide, i/l/t narrow)."""
    return (run.x1 - run.x0) * _weight(text) / max(_weight(run.text), 1e-6)


def _weight(text: str) -> float:
    return sum(_NARROW if c in _NARROW_CHARS else _CAP if c.isupper() or c in "mwMW&%@" else 1.0 for c in text)


_NARROW_CHARS = frozenset(" iljtfrI.,:;'!|()[]-/")
_NARROW, _CAP = 0.5, 1.3  # against a lower-case letter's width


def _first_word(runs: list[Run]) -> float:
    """How wide the line's first word is, from where the line starts."""
    started = False
    for run in runs:
        for k, ch in enumerate(run.text):
            if ch.isspace():
                if started:
                    return run.x0 + _width(run, run.text[:k]) - runs[0].x0
            else:
                started = True
    return runs[-1].x1 - runs[0].x0
