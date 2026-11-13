"""Write text edits in a page built from Markdown back into its Markdown source.

Pages built by `scripts/build_docs.py` say where they came from (`<!-- Generated from
docs/... -->`). An edited element is mapped back by text, never guessed: the one
Markdown block (heading, paragraph, list item, table cell) whose rendered text equals the
element's old text, and within it only the changed words, if they occur there exactly once.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

_SOURCE = re.compile(r"<!-- Generated from (\S+) by scripts/build_docs\.py")
_TAG = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")
_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
_TABLE_ROW = re.compile(r"^\s*\|")
_TABLE_RULE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+\.)[ \t]+")
_QUOTE = re.compile(r"^\s*>[ \t]?")
_CONTINUATION = re.compile(r"^\s*(?:>[ \t]?)?")
_MAX_CONTEXT = 40  # characters of unchanged text tried around an edit to place it uniquely


def find_source(page: Path) -> Path | None:
    """The Markdown file a built page came from, if it says so and the file exists."""
    try:
        head = page.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return None
    match = _SOURCE.search(head)
    if not match:
        return None
    for folder in page.resolve().parents:
        candidate = folder / match.group(1)
        if candidate.is_file():
            return candidate
    return None


def plain(markup: str) -> str:
    """The visible text of an HTML fragment, with whitespace collapsed."""
    return _SPACE.sub(" ", html.unescape(_TAG.sub("", markup))).strip()


@dataclass(frozen=True)
class Block:
    """One Markdown block that becomes one editable element: where its text is in the file."""

    start: int
    end: int
    cell: bool = False  # a table cell: `|` in new text gets escaped


def blocks(text: str) -> list[Block]:
    """The headings, paragraphs, list items, and table cells of a Markdown text."""
    found: list[Block] = []
    running: list[int] | None = None  # [start, end] of the paragraph or list item being read
    in_fence = False
    offset = 0

    def flush() -> None:
        nonlocal running
        if running is not None:
            found.append(Block(running[0], running[1]))
            running = None

    for line in text.split("\n"):
        start = offset
        offset += len(line) + 1
        body = line.rstrip("\r")
        end = start + len(body)
        if _FENCE.match(body):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        quote = _QUOTE.match(body)
        content = body[quote.end():] if quote else body
        lead = start + (quote.end() if quote else 0)
        if not content.strip():
            flush()
        elif heading := _HEADING.match(content):
            flush()
            found.append(Block(lead + heading.start(2), lead + heading.end(2)))
        elif _TABLE_ROW.match(content):
            flush()
            if not _TABLE_RULE.match(content):
                found += _cells(content, lead)
        elif item := _ITEM.match(content):
            flush()
            running = [lead + item.end(), end]
        elif running is not None:
            running[1] = end
        else:
            running = [lead + len(content) - len(content.lstrip()), end]
    flush()
    return found


def _cells(row: str, lead: int) -> list[Block]:
    cells, start = [], row.index("|") + 1
    for i in range(start, len(row) + 1):
        if i == len(row) or (row[i] == "|" and row[i - 1] != "\\"):
            cell = row[start:i]
            if cell.strip():
                left = start + len(cell) - len(cell.lstrip())
                cells.append(Block(lead + left, lead + start + len(cell.rstrip()), cell=True))
            start = i + 1
    return cells


class MarkdownSource:
    """A Markdown file's text, and the edits written back into it."""

    def __init__(self, text: str) -> None:
        import markdown  # the same renderer the docs build uses

        self.text = text
        self._md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
        self._rendered: dict[str, str] = {}

    def _plain_block(self, block: Block) -> str:
        raw = self.text[block.start:block.end]
        if raw not in self._rendered:
            lines = raw.replace("\r", "").split("\n")
            clean = "\n".join([lines[0]] + [_CONTINUATION.sub("", line, count=1) for line in lines[1:]])
            self._md.reset()
            self._rendered[raw] = plain(self._md.convert(clean).replace("\\|", "|"))
        return self._rendered[raw]

    def write_back(self, old_html: str, new_html: str) -> bool:
        """Write one element's edit into the text. False if it can't be placed unambiguously."""
        old, new = plain(old_html), plain(new_html)
        if old == new:
            return True
        matches = [b for b in blocks(self.text) if self._plain_block(b) == old]
        if len(matches) != 1:
            return False
        block = matches[0]
        raw = self.text[block.start:block.end]
        replaced = _replace_changed(raw, old, new, escape_pipes=block.cell)
        if replaced is None:
            return False
        self.text = self.text[:block.start] + replaced + self.text[block.end:]
        return True


def _replace_changed(raw: str, old: str, new: str, escape_pipes: bool) -> str | None:
    """`raw` with the part of `old` that changed replaced by its new version, or None."""
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]:
        p += 1
    s = 0
    while s < min(len(old), len(new)) - p and old[-1 - s] == new[-1 - s]:
        s += 1
    prefix, suffix = old[:p], old[len(old) - s:]
    old_mid, new_mid = old[p:len(old) - s], new[p:len(new) - s]
    if escape_pipes:
        new_mid = new_mid.replace("|", "\\|")
    # A change at the very end or start of the text goes at the block's edge, outside any markup.
    if not suffix and raw.endswith(old_mid):
        return raw[:len(raw) - len(old_mid)] + new_mid
    if not prefix and raw.startswith(old_mid):
        return new_mid + raw[len(old_mid):]
    # Grow the changed part with unchanged text on both sides until it occurs exactly once.
    for grow in range(_MAX_CONTEXT + 1):
        left, right = prefix[max(0, len(prefix) - grow):], suffix[:grow]
        find = left + old_mid + right
        if find and raw.count(find) == 1:
            at = raw.index(find)
            return raw[:at] + left + new_mid + right + raw[at + len(find):]
        if grow >= len(prefix) and grow >= len(suffix):
            break
    return None
