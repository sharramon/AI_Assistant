"""The handler's guardrails, kept in the protected zone so no agent can edit them.

`PROTECTED`: the paths no agent is ever granted to write (the repo-zones table in
docs/architecture/permissions.md mirrors it; if they disagree, this code wins). `protected_paths`
adds the grants file in use and the app's config folder (a folder ASSISTANT_CONFIG_DIR names is
protected like the repo's config/). `refusals` takes
them off a list; `rule_warnings` gives the fixed, predictable warnings shown on every card.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePath

from assistant.contracts import AccessItem, AccessKind, AccessNote
from assistant.core.permissions.store import OLD_GRANTS

REPO = Path(__file__).resolve().parents[4]

# Relative to the repo. Folders cover everything under them. `config` holds the saved grants
# (config/permissions.toml); the old grants file stays protected too.
PROTECTED = (
    "src/assistant/core/permissions",
    OLD_GRANTS,
    "config",
    ".claude/settings.json",
    ".claude/settings.local.json",
)

FIXED_RULES = (
    "Never submit or send anything: a rule in its prompt that you can't trim. Chrome can't be limited "
    "to some actions, so this depends on the model following it; it isn't enforced in code.",
    "Protected paths (the permissions handler, its grants, the config folder (config/, or the one "
    "ASSISTANT_CONFIG_DIR names), .claude/settings*) are never granted.",
    "Sessions start in Manual: anything outside this list asks you with a card; Auto stays your button.",
)

WRITES = (AccessKind.WORKSPACE, AccessKind.WRITE)


def protected_paths(grants_file: Path, config_dir: Path | None = None) -> tuple[Path, ...]:
    """The protected paths, resolved, with the grants file actually in use and, when given, the
    config folder in use (`App._config_dir`: an ASSISTANT_CONFIG_DIR folder outside the repo is
    protected like `config/`; writes refused, reads allowed). Duplicates are dropped."""
    extra = [Path(config_dir).resolve()] if config_dir is not None else []
    return tuple(dict.fromkeys([*(REPO / p for p in PROTECTED), grants_file, *extra]).keys())


def _norm(path: str | Path) -> PurePath:
    return PurePath(os.path.normcase(str(Path(path).resolve())))


def _within(child: PurePath, parent: PurePath) -> bool:
    return child == parent or parent in child.parents


def refusals(items: Iterable[AccessItem], protected: Sequence[Path]) -> dict[str, str]:
    """Item key -> why it's refused: a folder it would write that is in the protected zone, or
    holds part of it (writing the repo's root would reach config/). Reading is never refused."""
    zone = [(p, _norm(p)) for p in protected]
    refused: dict[str, str] = {}
    for item in items:
        if item.kind not in WRITES:
            continue
        folder = _norm(item.target)
        hit = next((p for p, n in zone if _within(folder, n) or _within(n, folder)), None)
        if hit is not None:
            refused[item.key] = f"Refused: {item.label} reaches the protected {hit}; never granted."
    return refused


def rule_warnings(items: Sequence[AccessItem]) -> list[AccessNote]:
    """The fixed warnings, each with the items it's about: writing plus Chrome, reading outside
    the working folder plus Chrome, and Python."""
    notes: list[AccessNote] = []
    chrome = [i for i in items if i.kind is AccessKind.CHROME]
    writes = [i for i in items if i.kind in WRITES]
    workspaces = [_norm(i.target) for i in items if i.kind is AccessKind.WORKSPACE]
    outside = [i for i in items if i.kind is AccessKind.READ and not any(_within(_norm(i.target), w) for w in workspaces)]
    if chrome and writes:
        folders = ", ".join(i.target for i in writes)
        notes.append(AccessNote(
            text=f"It can change files in {folders} and put them on a website (for example your CV).",
            items=tuple(i.key for i in (*writes, *chrome)),
        ))  # fmt: skip
    if chrome and outside:
        folders = ", ".join(i.target for i in outside)
        notes.append(AccessNote(
            text=f"It can read {folders} and paste what it reads into a website.",
            items=tuple(i.key for i in (*outside, *chrome)),
        ))  # fmt: skip
    for item in items:
        if item.kind is AccessKind.PYTHON:
            notes.append(AccessNote(
                text="Python with any arguments can run any code, so it can do anything your account can.",
                items=(item.key,),
            ))  # fmt: skip
    return notes
