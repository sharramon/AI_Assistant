"""Finding a highlight's text in a page: the viewer program's half of `viewer.highlight`.

A highlight is a short quote of the page's words, optionally narrowed to the section under
a heading. The page (`page.html`, `findQuote`) draws it with the same rules: page text only
(no scripts, styles, SVG, or Mermaid), the quote's words in order with any whitespace (or
none) between them, case ignored; a heading narrows the search to that heading's section,
up to the next heading of the same or a higher level, and is ignored if no heading matches.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

SKIP = {"script", "style", "svg", "noscript", "template"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


def pattern(quote: str) -> re.Pattern[str] | None:
    """The quote's words in order, any whitespace between them, case ignored."""
    words = quote.split()
    return re.compile(r"\s*".join(map(re.escape, words)), re.IGNORECASE) if words else None


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


class _PageText(HTMLParser):
    """The page's visible text, in order, with where each heading starts."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.headings: list[tuple[int, int, list[str]]] = []  # (level, chunk index, its text)
        self._skip: tuple[str, int] | None = None  # (tag, nesting) while inside skipped content
        self._heading: list[str] | None = None
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip is not None:
            if tag == self._skip[0]:
                self._skip = (tag, self._skip[1] + 1)
            return
        classes = (dict(attrs).get("class") or "").split()
        if tag in SKIP or "mermaid" in classes:
            self._skip = (tag, 1)
        elif tag in HEADINGS:
            self._heading = []
            self.headings.append((HEADINGS[tag], len(self.chunks), self._heading))

    def handle_endtag(self, tag: str) -> None:
        if self._skip is not None:
            if tag == self._skip[0]:
                depth = self._skip[1] - 1
                self._skip = (tag, depth) if depth else None
            return
        if tag in HEADINGS:
            self._heading = None

    def handle_data(self, data: str) -> None:
        if self._skip is None:
            self.chunks.append(data)
            if self._heading is not None:
                self._heading.append(data)


def count(source: str, quote: str, heading: str | None = None) -> int:
    """How many times the quote occurs in the page (in the heading's section, if one matches)."""
    found = pattern(quote)
    if found is None:
        return 0
    page = _PageText(source)
    start, end = 0, len(page.chunks)
    if heading and heading.strip():
        wanted = _norm(heading)
        for i, (level, at, text) in enumerate(page.headings):
            if wanted in _norm("".join(text)):
                start = at
                end = next((a for lv, a, _ in page.headings[i + 1:] if lv <= level), len(page.chunks))
                break
    return len(found.findall("".join(page.chunks[start:end])))
