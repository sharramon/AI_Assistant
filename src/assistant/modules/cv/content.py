"""A CV as plain sections: the eight standard section ids, each with its lines of text.

The one page knows only these sections (`SECTIONS`); a CV holds any of them, in any order, and
the section order (`order.py`) decides where each goes. Readers: `from_odt` (the incoming
`CV_Test_*.odt`, in `odt.py`) and `from_rezi` (Rezi's resume JSON, in `rezi_json.py`).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

# Every section the one page can have, in the usual order.
SECTIONS: tuple[str, ...] = (
    "contact", "summary", "skills", "experience", "projects", "education", "awards", "publications",
)  # fmt: skip


def check_sections(names: Iterable[str], what: str) -> list[str]:
    """`names` as a list, if each is a known section and none repeats; else ValueError naming `what`."""
    names = list(names)
    unknown = [n for n in names if n not in SECTIONS]
    if unknown:
        raise ValueError(f"{what}: unknown sections {unknown}; known: {list(SECTIONS)}")
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise ValueError(f"{what}: sections listed twice {repeated}")
    return names


class CvContent(BaseModel):
    """One CV's text by section id (each a list of lines). Read only: a change makes a new one."""

    model_config = ConfigDict(frozen=True)

    sections: dict[str, tuple[str, ...]]

    @field_validator("sections")
    @classmethod
    def _known(cls, value: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        check_sections(value, "CV")
        return value

    @classmethod
    def from_odt(cls, path: str | Path) -> CvContent:
        """The CV in a `CV_Test_*.odt` (read only; `odt.read_odt`). ValueError: not an .odt, or an unknown heading."""
        from assistant.modules.cv.odt import read_odt  # odt.py builds on this module

        return read_odt(path)

    @classmethod
    def from_rezi(cls, data: object) -> CvContent:
        """The CV in Rezi's resume JSON (`rezi_json.read_rezi`; keys it can't place are left out).
        ValueError when nothing in it is a resume section."""
        from assistant.modules.cv.rezi_json import read_rezi  # rezi_json.py builds on this module

        return read_rezi(data)[0]

    def names(self) -> list[str]:
        """The sections this CV has, with at least one line, in the order they were given."""
        return [name for name, lines in self.sections.items() if any(line.strip() for line in lines)]

    def lines(self, name: str) -> tuple[str, ...]:
        """One section's lines; () if the CV doesn't have it."""
        return self.sections.get(name, ())

    def ordered(self, order: Iterable[str]) -> list[tuple[str, tuple[str, ...]]]:
        """(section, lines) in `order`, keeping only the sections this CV has."""
        have = set(self.names())
        return [(name, self.sections[name]) for name in order if name in have]
