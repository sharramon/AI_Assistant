"""Sentence case for the speech engine's text: cheap rules, no model.

The Zipformer gives all capitals and no punctuation. `clean_text` lowercases it, capitalizes the
first letter and the word "I" (with I'm, I'll, I've, I'd), restores the configured terms, and gives
a final text one end mark. It doesn't split sentences or add commas.
Text that already has lowercase letters (whisper writes its own case and punctuation) is kept as it
is: only the spaces are collapsed and the terms restored.
Design: docs/next-steps/voice-text-cleanup.md, docs/next-steps/voice-layers-whisper.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# A final starting with one of these gets "?", any other a ".".
QUESTION_WORDS = frozenset(
    "what what's how how's why when where where's who who's whom whose which "
    "can could can't couldn't do does did don't doesn't didn't is isn't are aren't was wasn't were weren't "
    "will won't would wouldn't should shouldn't shall may might must have has haven't hasn't am".split()
)
_END_MARKS = ".?!"
_I = re.compile(r"(?<![\w'])i(?=$|[^\w']|'(?:m|ll|ve|d)\b)")


def _restore_terms(text: str, terms: Iterable[str]) -> str:
    """One pass over the text, longest term first, so "USD" can't re-match inside "usd prim"."""
    by_key = {" ".join(t.split()).lower(): " ".join(t.split()) for t in terms if t.strip()}
    if not by_key:
        return text
    alternatives = "|".join(re.escape(k) for k in sorted(by_key, key=len, reverse=True))
    pattern = re.compile(rf"(?<![\w'])(?:{alternatives})(?!\w)", re.IGNORECASE)  # "unity's" → "Unity's"
    return pattern.sub(lambda m: by_key[m.group(0).lower()], text)


def clean_text(raw: str, terms: Iterable[str] = (), final: bool = False, capitalize: bool = True) -> str:
    """`raw` in sentence case. `terms` are written back as given (longest first); `final` adds the end mark.
    Already cased text (any lowercase letter) keeps its case and punctuation; only the terms change.
    `capitalize=False`: the text carries on a sentence (a part after another), so its first letter stays small."""
    text = " ".join(raw.split())  # one space between words, so terms match on single spaces
    if any(c.islower() for c in text):
        return _restore_terms(text, terms)
    text = text.lower()
    if not text:
        return ""
    if capitalize:
        text = text[0].upper() + text[1:]
    text = _I.sub("I", text)
    text = _restore_terms(text, terms)
    if final and text[-1] not in _END_MARKS:
        first = text.split(" ", 1)[0].lower()
        text += "?" if first in QUESTION_WORDS else "."
    return text
