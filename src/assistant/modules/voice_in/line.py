"""The live line with two passes: the live engine's rough words, with the pieces the final engine
cleaned so far settled at the front.

The service sends the live words (`partial`, all words so far) and, per piece, `cleaned`: live words
`[start, end)` are replaced by the final engine's text, or keep their own words on a fallback.
Spans settle in order from word 0, so the settled part is always the start of the line.
Pure: no I/O, no events. Design: docs/architecture/voice.md#the-voice_in-module.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .cleanup import _END_MARKS, clean_text


@dataclass(frozen=True)
class Segment:
    """A run of the line: its raw `text`, and whether it's `settled` (cleaned, or given up on)."""

    text: str
    settled: bool = True


class LiveLine:
    """The latest live words and the spans settled so far."""

    def __init__(self) -> None:
        self._words: list[str] = []
        self._spans: list[tuple[int, int, str | None]] = []  # (start, end, cleaned text or None: keeps its words)

    def set_live(self, text: str) -> None:
        """The live engine's text so far (a `partial`, or the live final in `refining`)."""
        self._words = text.split()

    def settle(self, start: int, end: int, text: str = "", fallback: str = "") -> None:
        """A `cleaned` message: words `[start, end)` become `text`, or keep their words when `fallback` is set."""
        self._spans.append((start, end, None if fallback else text))

    def segments(self) -> list[Segment]:
        """The settled spans in order, then the rough tail (the live words after the last span)."""
        out = []
        for start, end, text in self._spans:
            out.append(Segment(" ".join(self._words[start:end]) if text is None else text))
        settled_to = self._spans[-1][1] if self._spans else 0
        out.append(Segment(" ".join(self._words[settled_to:]), settled=False))
        return out


def render(
    segments: Sequence[Segment], terms: Iterable[str] = (), *, final: bool = False, cleanup: bool = True
) -> tuple[str, int]:
    """The line's text and its `settled_chars`. Each segment is cleaned on its own (`clean_text`):
    the final engine's cased text is kept, all-caps text gets sentence case, capitalized only where
    a sentence starts. `final` gives the last segment its end mark."""
    terms = tuple(terms)
    texts: list[str] = []
    settled = 0
    last = len(segments) - 1
    for i, segment in enumerate(segments):
        text = " ".join(segment.text.split())
        if cleanup:
            starts = not texts or texts[-1][-1] in _END_MARKS
            text = clean_text(text, terms, final=final and i == last, capitalize=starts)
        if text:
            texts.append(text)
        if segment.settled:
            settled = len(" ".join(texts))
    return " ".join(texts), settled
