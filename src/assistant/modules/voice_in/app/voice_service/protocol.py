"""The `/ws/listen` protocol: one JSON object per WebSocket text frame.

Shared by the service and every Python client (`voice_in`), so the two can't drift.
Names no models and nothing about the assistant; depends on pydantic only.
Spec: src/assistant/modules/voice_in/docs/voice-service.md#the-protocol.
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
    MIC_LOST = "mic_lost"  # the mic went away mid-session (and didn't come back within mic_recovery_seconds)
    ENGINE_FAILED = "engine_failed"  # the model didn't load, or the engine crashed
    BAD_MESSAGE = "bad_message"  # unknown or malformed message


class ProtocolError(ValueError):
    """A frame that isn't a valid message for this direction (`bad_message`)."""


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True)


# app → service


class Start(_Message):
    """Open the mic and start transcribing.

    `partials: false` asks for no live text even from an engine that gives it (the text on send).
    """

    type: Literal["start"] = "start"
    partials: bool = True


class Stop(_Message):
    """Close the mic; the final text follows."""

    type: Literal["stop"] = "stop"


# service → app


class Started(_Message):
    """The mic is open. `partials` says whether live text will come this session (false: only the final).

    `clean_pieces`: the live text is cleaned piece by piece (`cleaned` messages), `refining` comes
    after stop, and the final is the cleaned text. False: one engine, as before.
    """

    type: Literal["started"] = "started"
    partials: bool = True
    clean_pieces: bool = False


class Partial(_Message):
    """The text so far; replaces the previous partial."""

    type: Literal["partial"] = "partial"
    text: str


Fallback = Literal["", "failed", "empty", "timed_out"]


class Cleaned(_Message):
    """Piece `piece` is done: the live words `[start, end)` (split on spaces, counted from the session's
    start) are replaced by `text`.

    With `fallback` set, `text` is empty and the span keeps its live words: `failed` (the final
    engine raised), `empty` (it heard nothing where the live engine had words), `timed_out` (not
    done within the timeout after stop). Sent in piece order; spans run back to back from word 0.
    Only sent when `started.clean_pieces` and `partials` are both true.
    """

    type: Literal["cleaned"] = "cleaned"
    piece: int
    start: int
    end: int
    text: str = ""
    fallback: Fallback = ""


class Refining(_Message):
    """After stop, when `clean_pieces`: the live engine's final `text` (empty with `partials` off),
    and how many pieces are still being cleaned. `final` follows."""

    type: Literal["refining"] = "refining"
    text: str = ""
    pending: int = 0


class MicDropped(_Message):
    """The mic went away mid-session; the service tries to reopen it for `wait_seconds`.

    The session stays open and keeps its text. `mic_back` follows if a mic opens in time;
    otherwise `final` (`complete: false`) then `error mic_lost`. Never sent when the
    service's `mic_recovery_seconds` is 0.
    """

    type: Literal["mic_dropped"] = "mic_dropped"
    detail: str = ""
    wait_seconds: float


class MicBack(_Message):
    """A mic opened again after `mic_dropped`; listening carries on with the same text."""

    type: Literal["mic_back"] = "mic_back"


class FinalPart(_Message):
    """One piece of a two-pass final: its `text`, and whether it's the final engine's (`cleaned`) or
    kept its live words (`fallback` says why)."""

    text: str
    cleaned: bool = True
    fallback: Fallback = ""


class Final(_Message):
    """The finished text after a stop; empty if nothing was heard.

    `complete` is False when the session ended early (mic lost). `ended_by` is
    `"stop"` (the app sent stop) or `"silence"` (the service stopped itself). `parts`: with
    `clean_pieces`, each piece's text in order (`text` is them joined with spaces); empty otherwise.
    """

    type: Literal["final"] = "final"
    text: str
    latency_ms: int
    complete: bool = True
    ended_by: Literal["stop", "silence"] = "stop"
    parts: tuple[FinalPart, ...] = ()


class Error(_Message):
    """`reason` is a fixed code; `detail` is a sentence for the log."""

    type: Literal["error"] = "error"
    reason: ErrorCode
    detail: str = ""


ClientMessage = Start | Stop
ServiceMessage = Started | Partial | Cleaned | Refining | MicDropped | MicBack | Final | Error

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
