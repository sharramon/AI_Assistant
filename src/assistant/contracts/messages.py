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
    """User input from any source (console, voice, remote client)."""

    text: str
    source: str
    conversation_id: str | None = None


class ResponseReady(Event):
    """A reply to present. `correlation_id` is the id of the input it answers."""

    text: str
    conversation_id: str | None = None


class ShutdownRequested(Event):
    """Asks the host to shut down cleanly."""

    reason: str = ""
