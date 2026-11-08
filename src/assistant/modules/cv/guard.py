"""The resume guard: `rezi.write_resume` may change only a Rezi resume this module created.

Every resume already in your Rezi account is protected, and there's no fixed base resume: a write
with no id makes a new resume (allowed, and its id is remembered), and a write with an id is
allowed only for an id remembered here. A reload hands the ids over (`as_value` / `from_value`);
a restart forgets them, so after a restart the worker makes a new resume rather than touching one
it can no longer prove it made.
"""

from __future__ import annotations

from typing import Any

# Keys that name a resume inside the fields sent: the id goes in `resume_id` only, so it is checked.
ID_KEYS = ("resume_id", "resumeid", "id", "_id")


class GuardRefused(ValueError):
    """A write the guard refuses (an item gives `invalid_arguments`)."""


def _plain_key(key: str) -> str:
    return "".join(c for c in key.lower() if c.isalnum() or c == "_")


class ResumeGuard:
    """The ids of the Rezi resumes this module created, with their names."""

    def __init__(self, created: dict[str, str] | None = None) -> None:
        self._created: dict[str, str] = dict(created or {})

    def check_write(self, resume_id: str | None, fields: dict[str, Any]) -> None:
        """Refuses an update of a resume not created here, and an id hidden in the fields."""
        hidden = [k for k in fields if _plain_key(k) in ID_KEYS]
        if hidden:
            raise GuardRefused(f"the resume's id goes in resume_id, not in the fields ({hidden})")
        if resume_id is None:
            return  # a new resume
        if resume_id not in self._created:
            raise GuardRefused(
                f"resume {resume_id!r} wasn't created by this module, so it's protected; "
                "write without resume_id to make a new one"
            )

    def created(self, resume_id: str, name: str = "") -> None:
        """Remembers a resume this module just made."""
        if not resume_id:
            raise ValueError("a created resume needs its id")
        self._created[str(resume_id)] = name or self._created.get(str(resume_id), "")

    def owns(self, resume_id: str) -> bool:
        return resume_id in self._created

    def as_value(self) -> dict[str, Any]:
        return {"created": [{"id": i, "name": n} for i, n in self._created.items()]}

    @classmethod
    def from_value(cls, value: Any) -> ResumeGuard:
        """Back from `as_value` (a reload's handover); anything else is an empty guard."""
        items = value.get("created", []) if isinstance(value, dict) else []
        return cls({str(i["id"]): str(i.get("name", "")) for i in items if isinstance(i, dict) and i.get("id")})
