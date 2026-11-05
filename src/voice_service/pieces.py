"""PieceCutter: where the live audio is cut into pieces for the final engine, from each chunk's level.

Pure: no threads, no audio, just levels in and cut points out. Spec:
docs/architecture/voice.md#two-passes-pieces-cleaned-while-you-talk.
"""

from __future__ import annotations

import math


def _chunks(seconds: float, chunk_ms: int) -> int:
    return max(1, math.ceil(seconds * 1000 / chunk_ms - 1e-9))


class PieceCutter:
    """Feed each chunk's level (`rms`); `feed` says when the current piece ends.

    - **A pause cut:** `pause_seconds` of chunks in a row below `speech_rms`, after some speech in
      the piece, once the piece is at least `min_seconds` long. The quiet stays in the piece.
    - **A forced cut:** `max_seconds` after the piece's first speech with no pause: the cut goes
      after the quietest chunk of the last `cut_search_seconds`, and the chunks after it start the
      next piece. Counted from the first speech, so a quiet lead-in never forces a cut.
    - **Quiet with no speech** never cuts.

    `reset()` starts a new piece (a mic drop, the session's end).
    """

    def __init__(
        self,
        *,
        chunk_ms: int,
        speech_rms: float,
        pause_seconds: float,
        min_seconds: float,
        max_seconds: float,
        cut_search_seconds: float,
    ) -> None:
        self.speech_rms = speech_rms
        self._pause = _chunks(pause_seconds, chunk_ms)
        self._min = _chunks(min_seconds, chunk_ms) if min_seconds > 0 else 0
        self._max = _chunks(max_seconds, chunk_ms)
        self._search = min(_chunks(cut_search_seconds, chunk_ms), self._max)
        self.reset()

    @classmethod
    def from_config(cls, pieces, *, chunk_ms: int, speech_rms: float) -> PieceCutter:
        """From a `PiecesConfig`."""
        return cls(
            chunk_ms=chunk_ms,
            speech_rms=speech_rms,
            pause_seconds=pieces.pause_seconds,
            min_seconds=pieces.min_seconds,
            max_seconds=pieces.max_seconds,
            cut_search_seconds=pieces.cut_search_seconds,
        )

    @property
    def speech(self) -> bool:
        """Whether the current piece has had a chunk at or above `speech_rms`."""
        return self._speech_at is not None

    def reset(self) -> None:
        self._levels: list[float] = []
        self._speech_at: int | None = None  # the first loud chunk's index in the current piece
        self._quiet = 0  # quiet chunks in a row at the end

    def feed(self, level: float) -> int | None:
        """Add one chunk's level. Returns the finished piece's length in chunks, from the current
        piece's start, or None. Any chunks after that length begin the next piece."""
        self._levels.append(level)
        n = len(self._levels)
        if level >= self.speech_rms:
            if self._speech_at is None:
                self._speech_at = n - 1
            self._quiet = 0
        else:
            self._quiet += 1
        if self._speech_at is None:
            return None
        if self._quiet >= self._pause and n >= self._min:
            self.reset()
            return n
        if n - self._speech_at >= self._max:
            window = self._levels[n - self._search :]
            cut = n - self._search + min(range(len(window)), key=window.__getitem__) + 1
            rest = self._levels[cut:]
            self.reset()
            for value in rest:  # the rest starts the next piece (too short to cut again)
                self._levels.append(value)
                if value >= self.speech_rms:
                    self._speech_at = self._speech_at if self._speech_at is not None else len(self._levels) - 1
                    self._quiet = 0
                else:
                    self._quiet += 1
            return cut
        return None
