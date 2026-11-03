"""The viewer's document model: document state, commands, and the HTML document handler.

State is the file's own text with an id on every element (`data-hv-id`), so the view and
commands can point at the same element. An edit replaces one element's content in that
text; nothing else in the file is touched, and saving strips the ids again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ID_ATTR = "data-hv-id"
_ID = re.compile(rf' {ID_ATTR}="\d+"')
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _Scanner(HTMLParser):
    """Where each start tag is, and for elements with an end tag, where their content is."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self._lines = [0] + [m.end() for m in re.finditer("\n", text)]
        self.starts: list[tuple[int, int]] = []  # (start, end) of each start tag
        self.content: dict[str, tuple[int, int]] = {}  # element id -> (content start, content end)
        self._open: list[tuple[str, str | None, int]] = []  # (tag, id, content start)
        self.feed(text)
        self.close()

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._lines[line - 1] + column

    def _start(self, attrs: list[tuple[str, str | None]]) -> tuple[int, str | None]:
        start = self._offset()
        end = start + len(self.get_starttag_text() or "")
        self.starts.append((start, end))
        return end, dict(attrs).get(ID_ATTR)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        end, element_id = self._start(attrs)
        if tag not in VOID:
            self._open.append((tag, element_id, end))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(attrs)

    def handle_endtag(self, tag: str) -> None:
        # Elements closed implicitly (a <p> without </p>) get no content span: they can't be edited.
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i][0] == tag:
                _, element_id, start = self._open[i]
                if element_id is not None:
                    self.content[element_id] = (start, self._offset())
                del self._open[i:]
                return


def add_ids(text: str) -> str:
    """`text` with a `data-hv-id` on every start tag that doesn't have one."""
    out, last = [], 0
    for n, (start, end) in enumerate(_Scanner(text).starts):
        tag = text[start:end]
        if ID_ATTR in tag:
            continue
        cut = end - 2 if tag.endswith("/>") else end - 1
        out += [text[last:cut], f' {ID_ATTR}="{n}"']
        last = cut
    out.append(text[last:])
    return "".join(out)


class HtmlDocument:
    """Document state for one open HTML file."""

    def __init__(self, text: str) -> None:
        self.source = add_ids(text)  # what the view shows

    @property
    def text(self) -> str:
        """The file's text, without the ids: what saving writes."""
        return _ID.sub("", self.source)

    def content(self, element_id: str) -> str:
        start, end = self._span(element_id)
        return self.source[start:end]

    def replace_content(self, element_id: str, html: str) -> str:
        """Replace one element's content; returns the old content."""
        start, end = self._span(element_id)
        old = self.source[start:end]
        self.source = self.source[:start] + html + self.source[end:]
        return old

    def _span(self, element_id: str) -> tuple[int, int]:
        span = _Scanner(self.source).content.get(element_id)
        if span is None:
            raise KeyError(f"No editable element {element_id!r}")
        return span


@dataclass(frozen=True)
class EditText:
    """A command: replace one element's content. It knows how to reverse itself."""

    element_id: str
    old: str
    new: str

    def do(self, doc: HtmlDocument) -> None:
        doc.replace_content(self.element_id, self.new)

    def undo(self, doc: HtmlDocument) -> None:
        doc.replace_content(self.element_id, self.old)


class HtmlHandler:
    """The document handler for HTML: loads a file into state and writes state back.

    `supports` tells the page which tools can work on the file.
    """

    suffixes = (".html", ".htm")
    supports = ("render", "anchor", "edit", "save")

    def load(self, path: Path) -> HtmlDocument:
        # newline="" and surrogateescape: saving writes back exactly the bytes it didn't edit.
        with open(path, encoding="utf-8", errors="surrogateescape", newline="") as file:
            return HtmlDocument(file.read())

    def save(self, doc: HtmlDocument, path: Path) -> None:
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as file:
            file.write(doc.text)


HANDLERS = [HtmlHandler()]


def handler_for(path: Path) -> HtmlHandler | None:
    return next((h for h in HANDLERS if path.suffix.lower() in h.suffixes), None)
