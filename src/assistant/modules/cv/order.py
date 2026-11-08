"""The section order of the one page, and what goes first when it's too long.

The rules, from the CV workflow:
- The usual order: Contact, Summary, Skills, Experience, Projects, Education, Awards, Publications.
- Education moves up, right under Skills, only when the job requires or prefers a master's.
- When space is tight, Publications goes first, then Awards (then older bullets are tightened,
  which is the worker's edit, not an order rule).

All three lists come from the module's config (`module.toml`), checked once when the module starts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from assistant.modules.cv.content import SECTIONS, CvContent, check_sections

# A master's degree in a job description. "MS" only in capitals (lower case "ms" is milliseconds),
# and not when it names a Microsoft product.
_MASTERS = re.compile(r"\bmaster['’]?s\b|\bmaster of (?:science|engineering|arts|business)\b"
                      r"|\bm\.\s?s\.|\bm\.?sc\b|\bm\.?eng\b|\bmba\b", re.IGNORECASE)  # fmt: skip
_MS = re.compile(r"\bMS\b(?!\s*(?:Office|Excel|Word|Teams|SQL|Access|Project|Dynamics|Azure|Windows|Outlook"
                 r"|PowerPoint|365))")  # fmt: skip


def wants_masters(jd_text: str) -> bool:
    """True if the job description mentions a master's degree (required or preferred).

    A first guess for the worker, who reads the JD itself and may set `degree_first` either way."""
    text = jd_text or ""
    return bool(_MASTERS.search(text) or _MS.search(text))


@dataclass(frozen=True)
class OrderChoice:
    """The order picked for one CV, and why (for the result and the report)."""

    order: tuple[str, ...]
    degree_first: bool
    dropped: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class SectionOrder:
    """The usual order, the degree-first order and the drop list, each checked against `SECTIONS`."""

    usual: tuple[str, ...]
    degree_first: tuple[str, ...]
    drop_first: tuple[str, ...]

    def __post_init__(self) -> None:
        for what, names in (("section_order", self.usual), ("degree_first_order", self.degree_first)):
            if sorted(check_sections(names, what)) != sorted(SECTIONS):
                raise ValueError(f"{what}: must list each of {list(SECTIONS)} once")
        check_sections(self.drop_first, "drop_first")
        if "contact" in self.drop_first:
            raise ValueError("drop_first: contact is never dropped")

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> SectionOrder:
        """From the module's config: `section_order`, `degree_first_order`, `drop_first`."""
        return cls(
            usual=tuple(config.get("section_order", SECTIONS)),
            degree_first=tuple(config.get("degree_first_order", ())),
            drop_first=tuple(config.get("drop_first", ())),
        )

    def pick(self, degree_first: bool) -> tuple[str, ...]:
        """The degree-first order if the job requires or prefers a master's, else the usual one."""
        return self.degree_first if degree_first else self.usual

    def drop(self, order: Iterable[str], n: int) -> tuple[str, ...]:
        """`order` without the first `n` sections of the drop list that are in it (n beyond the list: all of them)."""
        order = tuple(order)
        if n < 0:
            raise ValueError("n must be 0 or more")
        gone = [name for name in self.drop_first if name in order][:n]
        return tuple(name for name in order if name not in gone)

    def choose(self, content: CvContent, degree_first: bool, drop: int = 0) -> OrderChoice:
        """The order for this CV: picked, cut to the sections it has, then `drop` sections taken off.

        The drop count only counts sections the CV has, so a CV with no Publications loses Awards first."""
        picked = tuple(name for name in self.pick(degree_first) if name in content.names())
        order = self.drop(picked, drop)
        dropped = tuple(name for name in picked if name not in order)
        reason = "Education under Skills: the job requires or prefers a master's" if degree_first else "the usual order"
        if dropped:
            reason += f"; left out for space: {', '.join(dropped)}"
        return OrderChoice(order=order, degree_first=degree_first, dropped=dropped, reason=reason)
