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
    DROPPED = "dropped"  # the mic went away mid-session; waiting for it to come back (then listening, or failed)
    FINISHING = "finishing"  # mic off; the last piece is being cleaned (two passes), then idle with the text
    FAILED = "failed"  # went wrong; `reason` and `detail` say what


class StartListening(Command):
    """Turn the mic on. With `send_as_input=False` the text goes only to
    `VoiceTranscript` subscribers, never to the Talker."""

    send_as_input: bool = True


class StopListening(Command):
    """Turn the mic off; the result carries the final text.

    With `discard=True` (a clear button) the session is thrown away instead: nothing goes to
    the Talker, an empty final `VoiceTranscript` clears the live line, and the state is
    `idle` with reason `"cleared"`. A UI that wants to carry on sends `StartListening` next.
    """

    discard: bool = False


class VoiceState(Event):
    """The mic's state changed.

    `reason`: the service's error code (`busy`, `mic_unavailable`, `mic_lost`,
    `engine_failed`), one of the app's own (`not_allowed`, `service_unavailable`,
    `service_stopped`, `timed_out`), `"mic_dropped"` on a dropped state, or
    `"silence"` on an idle after a silence stop. `detail`: a short sentence for the button.
    """

    state: ListeningState
    reason: str | None = None
    detail: str | None = None


class VoiceTranscript(Event):
    """Live text: each partial (`final=False`), then once the final text
    (`final=True`; empty clears the line).

    `settled_chars`: how many characters from the start of `text` are settled (cleaned by the
    final engine, or given up on); the rest is rough live text. 0 with one engine.
    """

    session_id: str
    text: str
    final: bool = False
    settled_chars: int = 0
