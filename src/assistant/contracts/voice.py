"""Voice input: the commands any UI sends to turn the mic on and off, and the events
`voice_in` publishes. Design: docs/architecture/voice.md#the-voice_in-module.

`VoiceState` and `VoiceTranscript` carry `correlation_id` = the session id (the
`StartListening` command's id), so a UI can drop a stale session's updates.
"""

from __future__ import annotations

from enum import StrEnum

from assistant.contracts.messages import Command, Event


class ListeningState(StrEnum):
    """Where the mic is, for the button."""

    IDLE = "idle"  # mic off, nothing happening
    STARTING = "starting"  # clicked; the service may be launching, the mic opening
    LISTENING = "listening"  # mic open, text coming
    FAILED = "failed"  # went wrong; `reason` and `detail` say what


class StartListening(Command):
    """Turn the mic on. With `send_as_input=False` the text goes only to
    `VoiceTranscript` subscribers, never to the Talker."""

    send_as_input: bool = True


class StopListening(Command):
    """Turn the mic off; the result carries the final text."""


class VoiceState(Event):
    """The mic's state changed.

    `reason`: the service's error code, `"service_stopped"`, or `"silence"` on an
    idle after a silence stop. `detail`: a short sentence for the button.
    """

    state: ListeningState
    reason: str | None = None
    detail: str | None = None


class VoiceTranscript(Event):
    """Live text: each partial (`final=False`), then once the final text
    (`final=True`; empty clears the line)."""

    session_id: str
    text: str
    final: bool = False
