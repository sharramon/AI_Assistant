"""Saved grants: one section per module and subject in `data/permissions.toml` (protected zone).

A subject is a kind of agent: a module's own agent (`job_search_agent`), or a kind of helper
(`helper`, whose copies `helper_2`, ... share its grant). Changed only through the handler's
calls, never by hand. Each section holds the fingerprint of the list that was asked for, the
asked and granted item keys, whether it was denied, and the date.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from assistant.contracts import AccessItem

HEADER = ("# Saved grants of the permissions handler (one section per module and subject).\n"
          "# Changed only through its calls (permissions.grant / permissions.revoke, or a card), never by hand.\n")  # fmt: skip


def fingerprint(items: Iterable[AccessItem]) -> str:
    """A hash of an access list: the same items in any order give the same fingerprint."""
    text = "\n".join(sorted({i.key for i in items}))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Grant:
    module_id: str
    subject: str
    fingerprint: str
    asked: tuple[str, ...]
    granted: tuple[str, ...] = ()
    denied: bool = False
    date: str = ""
    added: tuple[str, ...] = ()  # items its agent asked for itself (`permissions.request`), beyond its config list

    def granted_items(self) -> tuple[AccessItem, ...]:
        return tuple(AccessItem.from_key(k) for k in self.granted)

    def asked_items(self) -> tuple[AccessItem, ...]:
        return tuple(AccessItem.from_key(k) for k in self.asked)

    def with_granted(self, keys: Iterable[str], denied: bool = False) -> Grant:
        """This grant now holding `keys` (asked, then added, in their order), dated today."""
        keep = set(keys)
        return replace(self, granted=tuple(k for k in (*self.asked, *self.added) if k in keep), denied=denied,
                       date=date.today().isoformat())  # fmt: skip

    def with_added(self, keys: Iterable[str]) -> Grant:
        """This grant with `keys` among its added items (those not on its list already); the
        fingerprint stays the config list's, so an unchanged config still matches."""
        known = {*self.asked, *self.added}
        return replace(self, added=(*self.added, *(k for k in dict.fromkeys(keys) if k not in known)))


class GrantStore:
    """The grants file, read once and written whole on each change (atomically)."""

    def __init__(self, path: Path, log: logging.Logger | None = None) -> None:
        self.path = path
        self._log = log or logging.getLogger(__name__)
        self._grants: dict[tuple[str, str], Grant] = self._load()

    def get(self, module_id: str, subject: str) -> Grant | None:
        return self._grants.get((module_id, subject))

    def of(self, module_id: str) -> list[Grant]:
        return [g for (m, _), g in self._grants.items() if m == module_id]

    def all(self) -> list[Grant]:
        return list(self._grants.values())

    def put(self, grant: Grant) -> None:
        self._grants[(grant.module_id, grant.subject)] = grant
        self._save()

    def remove(self, module_id: str, subject: str) -> None:
        if self._grants.pop((module_id, subject), None) is not None:
            self._save()

    def _load(self) -> dict[tuple[str, str], Grant]:
        if not self.path.exists():
            return {}
        try:
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            self._log.error("Can't read the grants in %s (%s); every list asks again", self.path, exc)
            return {}
        grants: dict[tuple[str, str], Grant] = {}
        for module_id, subjects in data.items():
            for subject, s in (subjects or {}).items():
                grants[(module_id, subject)] = Grant(
                    module_id=module_id, subject=subject, fingerprint=str(s.get("fingerprint", "")),
                    asked=tuple(s.get("asked", ())), granted=tuple(s.get("granted", ())),
                    denied=bool(s.get("denied", False)), date=str(s.get("date", "")),
                    added=tuple(s.get("added", ())),
                )  # fmt: skip
        return grants

    def _save(self) -> None:
        q = json.dumps  # TOML basic strings take JSON's escapes
        lines = [HEADER]
        for g in sorted(self._grants.values(), key=lambda g: (g.module_id, g.subject)):
            lines += [
                f"\n[{q(g.module_id)}.{q(g.subject)}]",
                f"fingerprint = {q(g.fingerprint)}",
                f"asked = [{', '.join(q(k) for k in g.asked)}]",
                f"granted = [{', '.join(q(k) for k in g.granted)}]",
                f"denied = {'true' if g.denied else 'false'}",
                f"date = {q(g.date)}",
                *([f"added = [{', '.join(q(k) for k in g.added)}]"] if g.added else []),
            ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".toml.tmp")
        temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temp.replace(self.path)
