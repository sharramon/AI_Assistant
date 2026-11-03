"""The `/ws/listen` protocol: one JSON object per WebSocket text frame.

Shared by the service and every Python client (`voice_in`), so the two can't drift.
Names no models and nothing about the assistant; depends on pydantic only.
Spec: docs/architecture/voice.md#the-protocol.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class ErrorCode(StrEnum):
    """Fixed `error` reasons. After any but `BAD_MESSAGE` the session is over."""

    BUSY = "busy"  # another app is listening
    MIC_UNAVAILABLE = "mic_unavailable"  # no mic, or it couldn't be opened
    MIC_LOST = "mic_lost"  # the mic went away mid-session
    ENGINE_FAILED = "engine_failed"  # the model didn't load, or the engine crashed
    BAD_MESSAGE = "bad_message"  # unknown or malformed message


class ProtocolError(ValueError):
    """A frame that isn't a valid message for this direction (`bad_message`)."""


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True)


# app → service


class Start(_Message):
    """Open the mic and start transcribing."""

    type: Literal["start"] = "start"


class Stop(_Message):
    """Close the mic; the final text follows."""

    type: Literal["stop"] = "stop"


# service → app


class Started(_Message):
    """The mic is open."""

    type: Literal["started"] = "started"


class Partial(_Message):
    """The text so far; replaces the previous partial."""

    type: Literal["partial"] = "partial"
    text: str


class Final(_Message):
    """The finished text after a stop; empty if nothing was heard.

    `complete` is False when the session ended early (mic lost). `ended_by` is
    `"stop"` (the app sent stop) or `"silence"` (the service stopped itself).
    """

    type: Literal["final"] = "final"
    text: str
    latency_ms: int
    complete: bool = True
    ended_by: Literal["stop", "silence"] = "stop"


class Error(_Message):
    """`reason` is a fixed code; `detail` is a sentence for the log."""

    type: Literal["error"] = "error"
    reason: ErrorCode
    detail: str = ""


ClientMessage = Start | Stop
ServiceMessage = Started | Partial | Final | Error

_client = TypeAdapter(Annotated[ClientMessage, Field(discriminator="type")])
_service = TypeAdapter(Annotated[ServiceMessage, Field(discriminator="type")])


def _parse(adapter: TypeAdapter, raw: str | bytes) -> _Message:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("not a JSON object")
    try:
        return adapter.validate_python(data)
    except ValidationError as exc:
        raise ProtocolError(f"invalid message: {exc.errors()[0]['msg']}") from exc


def parse_client_message(raw: str | bytes) -> ClientMessage:
    """A frame the app sent to the service. Raises `ProtocolError`."""
    return _parse(_client, raw)


def parse_service_message(raw: str | bytes) -> ServiceMessage:
    """A frame the service sent to the app. Raises `ProtocolError`."""
    return _parse(_service, raw)


def dump(message: _Message) -> str:
    """One message as a JSON text frame."""
    return message.model_dump_json()
