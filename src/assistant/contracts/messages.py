"""Message types shared by all modules.

Commands, events, and results are plain, immutable data so they can later cross
process or network boundaries (e.g. to remote clients) unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """Base for commands and events."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    correlation_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Command(Message):
    """A request for exactly one handler to do something. Sent with `ModuleContext.send`."""


class Event(Message):
    """A notification that something happened. Published with `ModuleContext.publish`."""


class Status(StrEnum):
    OK = "ok"
    INVALID_ARGUMENTS = "invalid_arguments"
    NOT_AVAILABLE = "not_available"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class Result(BaseModel):
    """Outcome of a command. Every command returns exactly one."""

    model_config = ConfigDict(frozen=True)

    status: Status
    value: Any = None
    error: str | None = None
    retryable: bool = False

    @property
    def is_ok(self) -> bool:
        return self.status is Status.OK

    @classmethod
    def ok(cls, value: Any = None) -> Result:
        return cls(status=Status.OK, value=value)

    @classmethod
    def invalid_arguments(cls, error: str) -> Result:
        return cls(status=Status.INVALID_ARGUMENTS, error=error)

    @classmethod
    def not_available(cls, error: str) -> Result:
        return cls(status=Status.NOT_AVAILABLE, error=error)

    @classmethod
    def failed(cls, error: str, retryable: bool = False) -> Result:
        return cls(status=Status.FAILED, error=error, retryable=retryable)

    @classmethod
    def timed_out(cls, error: str) -> Result:
        return cls(status=Status.TIMED_OUT, error=error, retryable=True)

    @classmethod
    def cancelled(cls, error: str = "Cancelled") -> Result:
        return cls(status=Status.CANCELLED, error=error)


class InputReceived(Event):
    """User input from any source (console, voice, remote client). `agent_id`: the agent tab it
    was typed in; None (voice, terminal 1) means the tab in focus."""

    text: str
    source: str
    conversation_id: str | None = None
    agent_id: str | None = None


class ResponseReady(Event):
    """A reply to present. `correlation_id` is the id of the input it answers. `agent_id`: the
    agent tab whose chat it belongs to; None means the tab in focus."""

    text: str
    conversation_id: str | None = None
    agent_id: str | None = None


class ShutdownRequested(Event):
    """Asks the host to shut down cleanly. With `restart`, the launcher starts the app again."""

    reason: str = ""
    restart: bool = False


class SessionTheme(Event):
    """A few words about what this app session is about, for its log folder name."""

    text: str


class ModuleEvent(Event):
    """A module-owned event, matched by its name rather than its class, so a new one needs no
    restart and either side reloads on its own. Published with `ctx.publish_named`, heard with
    `ctx.subscribe_named`; never built by hand. Shared events (the core's, the Hub's, ones
    several modules agree on) stay typed classes; a named event that becomes widely used gets
    a typed class at the next planned restart."""

    #: `<module_id>.<what>`, e.g. `cv.job_finished`; only that module may publish it.
    name: str
    #: The publishing module's id, set by the core.
    source: str
    #: Plain JSON values only (no classes, so nothing breaks on a reload).
    data: dict[str, Any] = Field(default_factory=dict)


class ViewerTabsChanged(Event):
    """The HTML viewer's open tabs changed: a tab opened, closed, or was switched to.

    `tabs` are the open files' full paths, in tab order; `active` is the one shown.
    `highlights` are `(path, quoted text)` for each highlight on an open page.
    """

    tabs: tuple[str, ...] = ()
    active: str | None = None
    highlights: tuple[tuple[str, str], ...] = ()


MAX_SNIPS = 3  # snips sent with one message: the Talker keeps and the temp UI shows at most this many
PASTED_FILE = "(pasted)"  # ViewerClip.file of an image pasted into a chat box, not snipped from a page


class ViewerClip(Event):
    """You snipped part of a page in the HTML viewer: an image for the assistant.

    `image_path` is the PNG (in the launch's log folder); `file` the page it's from;
    `heading` the nearest heading above the box, if any. `id` names it, e.g. to drop it.
    """

    id: str
    image_path: str
    file: str
    heading: str | None = None


class ViewerClipDropped(Event):
    """You dropped a snip before sending it (the × on its thumbnail in the chat)."""

    id: str
