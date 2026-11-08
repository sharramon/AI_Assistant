"""Step 6's check: does what Rezi read from the PDF hold the same content as the edited CV?

`FieldCompare.diff(edited, parsed)` compares section by section; `diff_text(edited, text)` checks
every edited line against one plain text (the PDF's text from `cv.build`, or text copied from
Rezi). Rezi splits an entry line into fields in its own order (title, company, dates), so each
line is split at `|` and each part checked on its own. A part is found when at least `min_cover`
of its words (counted, in any order: Rezi may reorder a field) are in the other side, and every
number on it is there too: a lost date or figure is never waved through.

Issues, all parse problems (the worker goes back to step 5):
- `missing_section`: Rezi has nothing under a section the CV has;
- `missing`: a line Rezi didn't read anywhere;
- `moved`: a line Rezi read under another section (`found_in`);
- `extra`: a line Rezi shows that isn't on the CV (sections only).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from assistant.modules.cv.content import SECTIONS, CvContent

KINDS = ("missing_section", "missing", "moved", "extra")

_SAME = str.maketrans({"–": "-", "—": "-", "‑": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "\xa0": " "})


def words(text: str) -> list[str]:
    """A line's words for comparing: lower case, dashes and quotes made plain, `&` as "and",
    punctuation dropped (`C++`, `C#` and `30%` kept whole)."""
    text = text.translate(_SAME).lower().replace("&", " and ")
    return re.findall(r"[a-z0-9]+[+#%]*", text)


def _numbers(tokens: Iterable[str]) -> set[str]:
    return {t for t in tokens if any(c.isdigit() for c in t)}


@dataclass(frozen=True)
class Issue:
    """One difference: its kind, the section, the line, and where Rezi put it (`moved` only)."""

    kind: str
    section: str
    line: str = ""
    found_in: str = ""

    def as_value(self) -> dict[str, str]:
        value = {"kind": self.kind, "section": self.section, "line": self.line}
        if self.found_in:
            value["found_in"] = self.found_in
        return value

    def describe(self) -> str:
        if self.kind == "missing_section":
            return f"{self.section}: Rezi read nothing under it"
        if self.kind == "moved":
            return f"{self.section}: read under {self.found_in}: {self.line}"
        where = "not read by Rezi" if self.kind == "missing" else "Rezi shows this, not on the CV"
        return f"{self.section}: {where}: {self.line}"


@dataclass(frozen=True)
class Comparison:
    """The compare's outcome: every issue, and how many lines were checked."""

    issues: tuple[Issue, ...] = ()
    checked: int = 0
    mode: str = "sections"  # or "text"

    @property
    def match_ok(self) -> bool:
        return not self.issues

    def summary(self) -> str:
        if self.match_ok:
            return f"same content: all {self.checked} lines found"
        n = {k: sum(1 for i in self.issues if i.kind == k) for k in KINDS}
        parts = [f"{n[k]} {k.replace('_', ' ')}" for k in KINDS if n[k]]
        return f"{len(self.issues)} issue(s) in {self.checked} lines: {', '.join(parts)}"

    def as_value(self) -> dict[str, Any]:
        return {"match_ok": self.match_ok, "mode": self.mode, "checked": self.checked,
                "summary": self.summary(), "issues": [i.as_value() for i in self.issues]}  # fmt: skip

    @classmethod
    def from_value(cls, value: dict[str, Any]) -> Comparison:
        """Back from `as_value` (what `cv.report` is given). ValueError if it isn't one."""
        if not isinstance(value, dict) or not isinstance(value.get("issues", []), list):
            raise ValueError("compare must be cv.compare's value (match_ok, issues, ...)")
        issues = []
        for item in value.get("issues", []):
            if not isinstance(item, dict) or item.get("kind") not in KINDS or item.get("section") not in SECTIONS:
                raise ValueError(f"compare: not an issue {item!r}; kinds {list(KINDS)}")
            issues.append(Issue(item["kind"], item["section"], str(item.get("line", "")), str(item.get("found_in", ""))))
        checked = value.get("checked", 0)
        comparison = cls(tuple(issues), checked if isinstance(checked, int) else 0, str(value.get("mode", "sections")))
        if "match_ok" in value and bool(value["match_ok"]) != comparison.match_ok:
            raise ValueError("compare: match_ok doesn't agree with its issues")
        return comparison


class FieldCompare:
    """Compares the edited CV with what Rezi read. `min_cover`: the share of a part's words that
    must be found, in order (numbers always all)."""

    def __init__(self, min_cover: float = 0.9) -> None:
        if not 0 < min_cover <= 1:
            raise ValueError("min_cover is above 0 and at most 1")
        self.min_cover = min_cover

    def found(self, line: str, pool: list[str]) -> bool:
        """Whether every `|` part of `line` is in `pool` (a word list)."""
        if not pool:
            return not words(line)
        have = Counter(pool)
        for part in line.split("|"):
            tokens = Counter(words(part))
            if not tokens:
                continue
            if any(have[t] == 0 for t in _numbers(tokens)):
                return False
            if sum((tokens & have).values()) < self.min_cover * sum(tokens.values()):
                return False
        return True

    def diff(self, edited: CvContent, parsed: CvContent) -> Comparison:
        """Section by section: missing sections, missing, moved and extra lines."""
        pools = {name: [w for line in parsed.lines(name) for w in words(line)] for name in parsed.names()}
        mine = {name: [w for line in edited.lines(name) for w in words(line)] for name in edited.names()}
        issues: list[Issue] = []
        checked = 0
        for name in edited.names():
            if name not in pools:
                issues.append(Issue("missing_section", name))
            for line in _real(edited.lines(name)):
                checked += 1
                if self.found(line, pools.get(name, [])):
                    continue
                elsewhere = next((other for other in pools if other != name and self.found(line, pools[other])), "")
                issues.append(Issue("moved", name, line, elsewhere) if elsewhere else Issue("missing", name, line))
        everything = [w for name in edited.names() for w in mine[name]]
        for name in parsed.names():
            for line in _real(parsed.lines(name)):
                if not self.found(line, mine.get(name, [])) and not self.found(line, everything):
                    issues.append(Issue("extra", name, line))
        return Comparison(tuple(issues), checked, "sections")

    def diff_text(self, edited: CvContent, text: str) -> Comparison:
        """Every edited line against one plain text: only missing lines (a text has no sections)."""
        pool = words(text)
        issues: list[Issue] = []
        checked = 0
        for name in edited.names():
            for line in _real(edited.lines(name)):
                checked += 1
                if not self.found(line, pool):
                    issues.append(Issue("missing", name, line))
        return Comparison(tuple(issues), checked, "text")


def _real(lines: tuple[str, ...]) -> list[str]:
    """Lines with words in them (a line of only punctuation isn't content)."""
    return [line for line in lines if words(line)]
