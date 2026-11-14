"""Access lists and the messages of the core's permissions handler (its first piece).

A task-agent module asks for its whole access list in one request, `ctx.permissions.request_set`.
The core's permissions handler (always on, part of the core) answers from a saved grant when the
list is unchanged, and otherwise asks you on one card (`PermissionRequested` →
`AnswerPermissionRequest` → `PermissionChanged`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from assistant.contracts.messages import Command, Event


class AccessKind(StrEnum):
    WORKSPACE = "workspace"  # its working folder, read and write; kept whenever the list is allowed
    READ = "read"  # a folder it may read
    WRITE = "write"  # a folder it may write
    PYTHON = "python"  # a Python it may run, with any arguments
    COMMAND = "command"  # a shell command it may run, with any arguments
    CHROME = "chrome"  # the Claude in Chrome tools
    MESSAGE = "message"  # messaging another agent (target: its id); saved under agent_hub, per sender kind


class AccessItem(BaseModel):
    """One line of an access list. `target`: the resolved folder, the Python's path or the
    command; empty for Chrome. `key` (`kind:target`) names it in answers and saved grants."""

    model_config = ConfigDict(frozen=True)

    kind: AccessKind
    target: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind.value}:{self.target}" if self.target else self.kind.value

    @classmethod
    def from_key(cls, key: str) -> AccessItem:
        """The item a `key` names. Raises ValueError for an unknown kind."""
        kind, _, target = key.partition(":")
        return cls(kind=AccessKind(kind), target=target)

    @property
    def trimmable(self) -> bool:
        """Whether a card offers a tick box for it (the working folder comes with the agent)."""
        return self.kind is not AccessKind.WORKSPACE

    @property
    def label(self) -> str:
        t = self.target
        return {
            AccessKind.WORKSPACE: f"read and write {t} (its working folder)",
            AccessKind.READ: f"read {t}",
            AccessKind.WRITE: f"write {t}",
            AccessKind.PYTHON: f"run {t} (any arguments)",
            AccessKind.COMMAND: f"run `{t}` (any arguments)",
            AccessKind.CHROME: "use Chrome",
            AccessKind.MESSAGE: f"message {t}",
        }[self.kind]


class AccessNote(BaseModel):
    """A line on the card about some items (`items`: their keys). `source`: `rule` (a fixed
    warning rule), `review` (the Main Assistant's note) or `refused` (taken off the list)."""

    model_config = ConfigDict(frozen=True)

    text: str
    items: tuple[str, ...] = ()
    source: Literal["rule", "review", "refused"] = "rule"


class AccessDenied(Exception):
    """You denied the access list, or didn't answer in time."""


class AccessPending(Exception):
    """The list waits for your answer on a card. Raised by `request_set(wait=False)`, so a
    module's start ends at once with this reason; on Allow the handler turns the module on."""


class PermissionRequested(Event):
    """A card for you. `action`: `access` (a module's list), `grant` / `revoke` (an agent's
    call, `caller`, waiting for your yes), or `message` (agent `caller` wants to message the
    agent in its one item; answered Allow once, Always allow or Deny), or `confirm` (a risky step
    `caller` asks for: a reload, an add, a remove, a restart; `reason` says what; no items; Allow
    or Deny, and Auto never skips it). `items`: the lines offered, each with a tick box when
    `trimmable`. `notes`: refused items, rule warnings, then the review's notes. `reviewed`:
    True or False for an access list (False shows "not reviewed"), None for no review step.
    `rules`: the fixed rules, one line each."""

    request_id: str
    module_id: str
    subject: str = ""
    action: Literal["access", "grant", "revoke", "message", "confirm"] = "access"
    reason: str = ""
    items: tuple[AccessItem, ...] = ()
    notes: tuple[AccessNote, ...] = ()
    reviewed: bool | None = None
    rules: tuple[str, ...] = ()
    caller: str = ""


class AnswerPermissionRequest(Command):
    """Your answer to a `PermissionRequested` card. `keep`: the keys of the ticked items
    (None: all of them); ignored on Deny. `remember`: for a `message` card, False is Allow
    once (nothing saved), True is Always allow; other cards ignore it. `invalid_arguments` if
    the card isn't open."""

    request_id: str
    allow: bool
    keep: tuple[str, ...] | None = None
    remember: bool = True


class PermissionChanged(Event):
    """A grant was saved, denied or revoked. `request_id`: the card it closes, if any (UIs drop
    it). `granted`: what the module or subject holds now. `text`: what happened, for you."""

    module_id: str
    subject: str = ""
    granted: tuple[AccessItem, ...] = ()
    request_id: str = ""
    text: str = ""


class ReviewAccessList(Command):
    """The core asks for a review of an access list before its card shows (D6: the reviewer is a
    listener; the core never starts a task). Handled by the module that runs reviews (the Agent
    Hub, on agent `reviewer`). Its result says only whether a review started (`not_available`:
    no reviewer, or it's busy); the notes come back as `AddCardNotes` within `timeout` seconds,
    else the card shows "not reviewed". `who`: how the card names the list; `warnings`: the
    notes already on the card."""

    request_id: str
    reviewer: str
    who: str
    reason: str = ""
    items: tuple[str, ...] = ()  # the items' labels
    warnings: tuple[str, ...] = ()
    timeout: float = 90.0


class AddCardNotes(Command):
    """A review's outcome for a card waiting on `ReviewAccessList` (handled by the core).
    `notes`: one line per risk (the core keeps at most a few); `reviewed=False`: the review
    didn't finish (the card says "not reviewed"). `invalid_arguments` if no review waits."""

    request_id: str
    notes: tuple[str, ...] = ()
    reviewed: bool = True
