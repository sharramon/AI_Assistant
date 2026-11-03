"""Read the tags agents write in their text, the same way everywhere.

- `<<NAME: argument>>` tags (the Talker's WORK, ASK, SHOW..., anyone's SHOW): `find_tags`
- a SHOW tag's argument, `path | "quote" | heading`: `parse_show`
- a last line like `NEED: <question>` or `HANDOFF: <note>`: `last_line`
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from typing import NamedTuple

# Paths never contain quotes, so every quote mark around one goes.
_PATH_QUOTES = "\"'“”‘’"
# A quote is the page's exact words: only one matching pair around it goes, so an
# apostrophe or quote mark that belongs to the page's text stays.
_PAIRS = {'"': '"', "'": "'", "“": "”", "”": "”", "‘": "’"}
# An unclosed double quote mark at one end is dropped; apostrophes are kept (`users'`).
_STRAY = "\"“”"


class Tag(NamedTuple):
    """One `<<NAME: argument>>` in a text; `start`/`end` slice it out of that text."""

    name: str
    argument: str
    start: int
    end: int


class ShowTag(NamedTuple):
    """A SHOW argument: the file, and optionally a quote of its text and the heading it's under."""

    path: str
    quote: str | None = None
    heading: str | None = None


@lru_cache(maxsize=16)
def _pattern(names: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(map(re.escape, names))
    return re.compile(rf"<<\s*({alternatives})\s*(?::(.*?))?>>", re.DOTALL)


def find_tags(text: str, names: Iterable[str]) -> list[Tag]:
    """Every `<<NAME>>` or `<<NAME: argument>>` in `text` whose NAME is in `names`, in order.

    The argument is stripped (empty when there is none). Names are case-sensitive; a tag
    without its closing `>>`, or with no colon before its argument, isn't a tag.
    """
    names = tuple(sorted(set(names), key=lambda n: (-len(n), n)))
    if not names:
        return []
    return [
        Tag(m.group(1), (m.group(2) or "").strip(), m.start(), m.end())
        for m in _pattern(names).finditer(text)
    ]


def parse_show(argument: str) -> ShowTag:
    """A SHOW argument, `path` or `path | "quote" | heading`, as a `ShowTag`.

    Quotes around the path go; around the quote and heading only one matching pair goes.
    An empty quote or heading is None.
    """
    path, *rest = argument.split("|", 2)
    quote = _unquote(rest[0]) if rest else None
    heading = _unquote(rest[1]) if len(rest) > 1 else None
    return ShowTag(path.strip().strip(_PATH_QUOTES).strip(), quote, heading)


def last_line(text: str, prefix: str) -> str | None:
    """What follows `prefix` if the last non-empty line starts with it, else None.

    For `NEED: <question>` and `HANDOFF: <note>`. The prefix is matched case-insensitively,
    and markdown emphasis or backticks around the line are ignored.
    """
    lines = [line.strip().strip("*`").strip() for line in text.splitlines() if line.strip()]
    if lines and lines[-1].upper().startswith(prefix.upper()):
        return lines[-1][len(prefix):].strip().strip("`").strip()
    return None


def _unquote(part: str) -> str | None:
    part = part.strip()
    if not part:
        return None
    if len(part) >= 2 and _PAIRS.get(part[0]) == part[-1]:
        part = part[1:-1]
    elif part[:1] in _STRAY and part[0] not in part[1:] and _PAIRS[part[0]] not in part[1:]:
        part = part[1:]
    elif part[-1:] in _STRAY and part[-1] not in part[:-1]:
        part = part[:-1]
    return part.strip() or None
