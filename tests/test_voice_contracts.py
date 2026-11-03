"""Voice contracts (assistant.contracts.voice) and the service protocol (voice_service.protocol)."""

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import assistant.contracts as contracts
from assistant.contracts import (
    Command,
    Event,
    ListeningState,
    StartListening,
    StopListening,
    VoiceState,
    VoiceTranscript,
)
from voice_service import protocol
from voice_service.protocol import (
    Error,
    ErrorCode,
    Final,
    Partial,
    ProtocolError,
    Start,
    Started,
    Stop,
    dump,
    parse_client_message,
    parse_service_message,
)

# --- contracts ---


def test_exported_from_contracts():
    for name in ("ListeningState", "StartListening", "StopListening", "VoiceState", "VoiceTranscript"):
        assert name in contracts.__all__


def test_kinds_and_defaults():
    assert issubclass(StartListening, Command) and issubclass(StopListening, Command)
    assert issubclass(VoiceState, Event) and issubclass(VoiceTranscript, Event)
    assert StartListening().send_as_input is True
    t = VoiceTranscript(session_id="s1", text="hi", correlation_id="s1")
    assert t.final is False and t.correlation_id == "s1"
    s = VoiceState(state=ListeningState.IDLE)
    assert s.reason is None and s.detail is None


def test_listening_state_values():
    assert [m.value for m in ListeningState] == ["idle", "starting", "listening", "failed"]


def test_voice_state_accepts_plain_string_and_rejects_unknown():
    assert VoiceState(state="listening").state is ListeningState.LISTENING
    with pytest.raises(ValidationError):
        VoiceState(state="sleeping")
    assert json.loads(VoiceState(state="failed", reason="busy").model_dump_json())["state"] == "failed"


def test_contracts_are_frozen():
    with pytest.raises(ValidationError):
        StartListening().send_as_input = False
    with pytest.raises(ValidationError):
        VoiceTranscript(session_id="s", text="a").text = "b"


# --- protocol ---


@pytest.mark.parametrize(
    ("message", "wire"),
    [
        (Start(), {"type": "start"}),
        (Stop(), {"type": "stop"}),
    ],
)
def test_client_messages_round_trip(message, wire):
    assert json.loads(dump(message)) == wire
    assert parse_client_message(dump(message)) == message


@pytest.mark.parametrize(
    ("message", "wire"),
    [
        (Started(), {"type": "started"}),
        (Partial(text="hel"), {"type": "partial", "text": "hel"}),
        (
            Final(text="hello", latency_ms=120),
            {"type": "final", "text": "hello", "latency_ms": 120, "complete": True, "ended_by": "stop"},
        ),
        (
            Final(text="", latency_ms=5, complete=False, ended_by="silence"),
            {"type": "final", "text": "", "latency_ms": 5, "complete": False, "ended_by": "silence"},
        ),
        (
            Error(reason=ErrorCode.BUSY, detail="another app"),
            {"type": "error", "reason": "busy", "detail": "another app"},
        ),
    ],
)
def test_service_messages_round_trip(message, wire):
    assert json.loads(dump(message)) == wire
    assert parse_service_message(dump(message)) == message


def test_parse_accepts_bytes_and_minimal_fields():
    assert parse_service_message(b'{"type": "error", "reason": "mic_lost"}') == Error(reason=ErrorCode.MIC_LOST)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1, 2]",
        '{"type": "shout"}',
        '{"text": "no type"}',
        '{"type": "partial"}',
        '{"type": "final", "text": "x"}',
        '{"type": "final", "text": "x", "latency_ms": 1, "ended_by": "timeout"}',
        '{"type": "error", "reason": "unknown_code"}',
    ],
)
def test_service_parser_rejects_bad_frames(raw):
    with pytest.raises(ProtocolError):
        parse_service_message(raw)


def test_parsers_refuse_the_other_direction():
    with pytest.raises(ProtocolError):
        parse_client_message(dump(Started()))
    with pytest.raises(ProtocolError):
        parse_service_message(dump(Start()))


def test_error_codes_are_fixed():
    assert {c.value for c in ErrorCode} == {"busy", "mic_unavailable", "mic_lost", "engine_failed", "bad_message"}


def test_protocol_never_imports_assistant():
    for path in Path(protocol.__file__).parent.rglob("*.py"):  # the whole voice_service package
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(n == "assistant" or n.startswith("assistant.") for n in names), path
