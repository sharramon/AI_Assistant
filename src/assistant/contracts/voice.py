"""Voice input: the voice contract (`IVoice`) other modules require, the commands any UI sends
to turn the mic on and off, and the events `voice_in` publishes.
Design: docs/architecture/voice.md#the-voice_in-module.

`VoiceState` and `VoiceTranscript` carry `correlation_id` = the session id (the
`StartListening` command's id, or the id given to `IVoice.listen`), so a module follows
only its own session and drops a stale one's updates.
"""

from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum

from assistant.contracts.messages import Command, Event, Result
from assistant.contracts.module import Contract


class VoiceDestination(StrEnum):
    """Where a voice session's final text goes."""

    TALKER = "talker"  # also to the Talker, as InputReceived(source="voice")
    CALLER = "caller"  # only the VoiceTranscript events, for the module that asked


class IVoice(Contract):
    """Speech to text from the one mic, in sessions that each belong to their caller.

    Provided by `voice_in`; a module that needs the mic (voice notes) lists it in `requires`,
    so the core turns voice input on first. Look it up at each call (`ctx.get_one(IVoice)`),
    never keep it: a reload swaps the provider.

    One mic, one session at a time; the second `listen` wins. The session it ends gets
    `VoiceState(idle, reason="taken_over")` and an empty final `VoiceTranscript`.
    """

    @abstractmethod
    async def listen(self, session_id: str, destination: VoiceDestination = VoiceDestination.CALLER) -> Result:
        """Open a session under `session_id`, which the caller makes (e.g. `uuid4().hex`), so it can
        follow its events from the first one. Result value: `{"session_id": ...}`."""

    @abstractmethod
    async def finish(self, session_id: str, discard: bool = False) -> Result:
        """End that session only; another caller's session is never touched. Result value:
        `{"text": ...}` with the final text. `discard=True` throws the words away. A session that
        already ended (taken over, failed, a silence stop) gives `{"text": "", "ended": True}`."""


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

    `agent_id`: the agent tab the stop was pressed in. The final text goes to that tab's Talker
    (`InputReceived.agent_id`), even if you switch tabs while it is still being cleaned. None:
    the tab in focus when the text arrives (also a stop by a long silence).
    """

    discard: bool = False
    agent_id: str | None = None


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
