"""One mic session: its audio source, chunk queue, engine thread, and (two passes) its piece cleaner.
Plus the background model load.

Threads (src/assistant/modules/voice_in/docs/voice-service.md#the-voice-service-threads-and-audio-flow): the source's thread
only queues chunks; the engine thread accepts them and hands messages to the asyncio loop with
`call_soon_threadsafe`; the loop calls `start`, `stop` and `abort` (through `asyncio.to_thread`).
A lost mic is reopened from the engine thread, with a fresh source from the factory. With a final
engine, the engine thread also cuts the audio into pieces (`PieceCutter`) and the `voice-clean`
thread sends them to the final engine in order (`_Cleaner`).
"""

from __future__ import annotations

import asyncio
import logging
import math
import queue
import threading
import time
from array import array
from collections.abc import Callable
from dataclasses import dataclass

from .audio import SAMPLE_RATE, AudioSource
from .config import ServiceConfig
from .engines import EngineError, SttEngine, SttStream
from .pieces import PieceCutter
from .protocol import Cleaned, Error, ErrorCode, Final, FinalPart, MicBack, MicDropped, Partial, Refining

log = logging.getLogger("voice_service.session")

DONE = object()  # the last item on a session's outbox: the engine thread has ended


def rms(pcm: bytes) -> float:
    """The level of a PCM16 chunk (root mean square, int16 scale: 0 to 32768)."""
    samples = array("h", pcm[: len(pcm) // 2 * 2])
    return math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0


class EngineLoader:
    """Loads the engine's model once, in the background; `ready` and `error` are for `/health`."""

    def __init__(self, engine: SttEngine) -> None:
        self.engine = engine
        self.done = threading.Event()
        self.error: str | None = None

    @property
    def ready(self) -> bool:
        return self.done.is_set() and self.error is None

    def load(self) -> None:
        started = time.monotonic()
        try:
            self.engine.load()
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, EngineError) else f"{type(exc).__name__}: {exc}"
            log.error("the %s model failed to load: %s", self.engine.name, self.error)
        else:
            log.info("the %s model loaded in %.1f s", self.engine.name, time.monotonic() - started)
        finally:
            self.done.set()


@dataclass
class Piece:
    """A cut piece of audio and the span of live words it covers (`words` are those live words).

    `speech` is False for a piece with no chunk at or above `speech_rms` (the last piece after a
    stop, or a mic-drop piece): its live words are only the live engine catching up on the piece
    before, so if the final engine hears nothing they're dropped, not kept.
    """

    index: int
    audio: bytes
    start: int
    end: int
    words: list[str]
    speech: bool = True

    @property
    def seconds(self) -> float:
        return len(self.audio) / (2 * SAMPLE_RATE)  # PCM16: two bytes a sample


class _Cleaner:
    """The `voice-clean` thread: sends pieces to the final engine one at a time, in order.

    Each result is kept as a `FinalPart` and, if `on_cleaned` is set, posted as `Cleaned`.
    `finish(deadline)` waits for the queue to empty; what isn't done by then keeps its live words
    (`timed_out`). `cancel()` drops the queue and stops the running piece.
    """

    def __init__(self, loader: EngineLoader, on_cleaned: Callable[[Cleaned], None] | None, *, prompt: bool) -> None:
        self._loader = loader
        self._on_cleaned = on_cleaned
        self._prompt = prompt
        self._queue: queue.Queue[Piece | None] = queue.Queue()
        self._lock = threading.Lock()  # guards the parts, the running stream, and `_closed`
        self._closed = False  # cancelled or timed out: later results are thrown away
        self._parts: dict[int, FinalPart] = {}
        self._pieces: list[Piece] = []
        self._stream: SttStream | None = None
        self._previous = ""  # the last piece's cleaned text, the next one's prompt
        self._thread = threading.Thread(target=self._run, name="voice-clean", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def put(self, piece: Piece) -> None:
        self._pieces.append(piece)
        self._queue.put(piece)
        waiting = self._queue.qsize()
        log.info(
            "piece %d cut: %.1f s of audio, live words %d to %d, %d waiting%s",
            piece.index, piece.seconds, piece.start, piece.end, waiting, " (whisper is behind)" if waiting > 1 else "",
        )  # fmt: skip

    @property
    def given(self) -> int:
        """Pieces given so far (the next piece's index)."""
        return len(self._pieces)

    @property
    def pending(self) -> int:
        """Pieces given but not done yet."""
        with self._lock:
            return len(self._pieces) - len(self._parts)

    def finish(self, deadline: float) -> list[FinalPart]:
        """Wait (until `deadline`, a `time.monotonic()`) for every piece given; the parts in piece order."""
        self._queue.put(None)
        self._thread.join(max(0.0, deadline - time.monotonic()))
        with self._lock:
            self._closed = True
            if self._stream is not None:
                self._stream.cancel()
            for piece in self._pieces:
                if piece.index not in self._parts:
                    log.warning("piece %d timed out: it keeps its %d live words", piece.index, len(piece.words))
                    self._settle(piece, FinalPart(text=" ".join(piece.words), cleaned=False, fallback="timed_out"))
            return [self._parts[p.index] for p in self._pieces]

    def cancel(self) -> None:
        with self._lock:
            self._closed = True
            if self._stream is not None:
                self._stream.cancel()
        self._queue.put(None)

    def _settle(self, piece: Piece, part: FinalPart) -> None:
        """Keep a piece's part and post it. Under `_lock`, so posts stay in piece order."""
        self._parts[piece.index] = part
        if self._on_cleaned is not None:
            text = part.text if part.cleaned else ""
            self._on_cleaned(Cleaned(piece=piece.index, start=piece.start, end=piece.end, text=text, fallback=part.fallback))

    def _run(self) -> None:
        while (piece := self._queue.get()) is not None:
            while not self._loader.done.wait(0.05):  # pieces wait while the final engine loads
                if self._closed:
                    return
            if self._closed:
                return
            part = self._clean(piece)
            with self._lock:
                if self._closed:
                    return
                self._settle(piece, part)

    def _clean(self, piece: Piece) -> FinalPart:
        began = time.monotonic()
        live = " ".join(piece.words)
        try:
            if self._loader.error:
                raise EngineError(self._loader.error)
            stream = self._loader.engine.new_stream()
            if self._prompt and self._previous:
                stream.set_prompt(self._previous)
            with self._lock:
                if self._closed:
                    return FinalPart(text=live, cleaned=False, fallback="timed_out")
                self._stream = stream
            stream.accept(piece.audio)
            text = stream.finish().strip()
        except Exception as exc:
            log.error("piece %d failed (%s: %s): it keeps its live words", piece.index, type(exc).__name__, exc)
            self._previous = ""
            return FinalPart(text=live, cleaned=False, fallback="failed")
        finally:
            with self._lock:
                self._stream = None
        took = time.monotonic() - began
        if not text and piece.words and not piece.speech:
            # The live engine lags: the words are the previous piece's last ones, already cleaned there.
            log.info("piece %d: no speech and the final engine heard nothing; its lagging live words %r are dropped", piece.index, live)
            return FinalPart(text="")
        if not text and piece.words:
            log.warning("piece %d: the final engine heard nothing in %.2f s; it keeps its live words %r", piece.index, took, live)
            self._previous = ""
            return FinalPart(text=live, cleaned=False, fallback="empty")
        log.info("piece %d cleaned in %.2f s (%.1f s of audio): %r → %r", piece.index, took, piece.seconds, live, text)
        self._previous = text
        return FinalPart(text=text)


class ListenSession:
    """Mic on until `stop`, a long silence, a lost mic that doesn't come back, or `abort`.

    Results come out of `outbox`, then `DONE`. `source_factory` makes the first source, and a
    fresh one for each try to reopen a lost mic (for `mic_recovery_seconds`).

    `partials` (whether live text goes to the client) is true only if the engine gives live text
    and the client asked for it. A forced on-send session on a live engine still reads the engine's
    text to tell speech from silence; with an engine that gives none, a chunk at or above
    `speech_rms` counts as speech.

    `final_loader` (two passes): the final engine. `clean_pieces` is true when it's given, didn't
    fail to load, and the live engine gives live text. Then the audio is cut into pieces at pauses,
    each piece is cleaned in the background, and the final is the cleaned pieces joined.
    """

    retry_seconds = 1.0  # how often a lost mic is tried again

    def __init__(
        self,
        loader: EngineLoader,
        source_factory: Callable[[], AudioSource],
        config: ServiceConfig,
        loop: asyncio.AbstractEventLoop,
        *,
        partials: bool = True,
        final_loader: EngineLoader | None = None,
    ) -> None:
        audio = config.audio
        self.outbox: asyncio.Queue = asyncio.Queue()
        self._loader = loader
        self._live = loader.engine.live_partials  # the engine gives text while you speak
        self.partials = partials and self._live
        self._speech_rms = audio.speech_rms
        self._factory = source_factory
        self._source: AudioSource | None = None
        self._loop = loop
        self._chunk_ms = audio.chunk_ms
        self._chunks: queue.Queue[bytes] = queue.Queue(max(1, int(audio.queue_seconds * 1000 / audio.chunk_ms)))
        self._silence = audio.silence_stop_seconds
        self._recovery = audio.mic_recovery_seconds
        self._stall = audio.stall_seconds
        self._last_chunk = 0.0  # when the source last delivered a chunk (the stall watchdog)
        self._interval = config.engine.partial_interval_ms / 1000
        self._abort = threading.Event()
        self._stopping = threading.Event()
        self._lost: str | None = None
        self._drops = 0
        self._source_lock = threading.Lock()
        self._started_at = 0.0
        self._stop_time = 0.0
        self._accepted = 0
        self._dropped = 0
        self._thread: threading.Thread | None = None
        # Two passes: the cutter, the current piece's chunks with the live word count after each, the cleaner.
        self.clean_pieces = final_loader is not None and final_loader.error is None and self._live
        self._final_timeout = config.engine.final_timeout_seconds
        self._cutter: PieceCutter | None = None
        self._cleaner: _Cleaner | None = None
        self._piece_chunks: list[bytes] = []
        self._piece_counts: list[int] = []
        self._span_start = 0  # the live words before this belong to pieces already cut
        self._words: list[str] = []  # the live words so far
        if self.clean_pieces:
            self._cutter = PieceCutter.from_config(config.pieces, chunk_ms=audio.chunk_ms, speech_rms=audio.speech_rms)
            self._cleaner = _Cleaner(
                final_loader, self._post if self.partials else None, prompt=config.pieces.prompt_previous
            )

    @property
    def stopping(self) -> bool:
        return self._stopping.is_set()

    def start(self) -> None:
        """Open the source and start the engine thread. Raises what the source raises (`MicUnavailable`)."""
        self._started_at = time.monotonic()
        self._open_source()
        if self._cleaner is not None:
            self._cleaner.start()
        self._thread = threading.Thread(target=self._run, name="voice-engine", daemon=True)
        self._thread.start()
        mode = "live text" if self.partials else "text on send"
        log.info("session started (%s%s)", mode, ", pieces cleaned" if self.clean_pieces else "")

    def stop(self) -> None:
        """Close the mic; the engine thread drains the queue and posts the final."""
        if self._stopping.is_set():
            return
        self._stop_time = time.monotonic()
        self._close_source()
        self._stopping.set()

    def abort(self) -> None:
        """Drop everything: mic closed, engine thread ended, pieces dropped, no final."""
        self._abort.set()
        if self._cleaner is not None:
            self._cleaner.cancel()
        self._close_source()
        self.join()
        log.info("session aborted")

    def join(self, timeout: float = 5.0) -> None:
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    # --- the source's thread ---

    def _on_chunk(self, pcm: bytes) -> None:
        self._last_chunk = time.monotonic()
        try:
            self._chunks.put_nowait(pcm)
        except queue.Full:
            self._dropped += 1

    def _on_lost(self, reason: str) -> None:
        self._lost = reason or "the microphone stopped"

    # --- the source ---

    def _open_source(self) -> None:
        """A fresh source from the factory, started. Raises what its `start` raises."""
        source = self._factory()
        self._last_chunk = time.monotonic()
        source.start(self._on_chunk, self._on_lost)
        with self._source_lock:
            self._source = source

    def _close_source(self) -> None:
        with self._source_lock:
            source, self._source = self._source, None
        if source is None:
            return
        try:
            source.stop()
        except Exception:
            log.exception("closing the audio source failed")

    # --- the engine thread ---

    def _post(self, item: object) -> None:
        try:
            self._loop.call_soon_threadsafe(self.outbox.put_nowait, item)
        except RuntimeError:  # the loop is closed: the service is shutting down
            pass

    def _run(self) -> None:
        try:
            while not self._loader.done.wait(0.05):  # a start during the model load buffers in the queue
                if self._abort.is_set():
                    return
            if self._loader.error:
                raise EngineError(self._loader.error)
            stream = self._loader.engine.new_stream()
            ended_by = self._listen(stream)
            if ended_by is None:
                return
            text = stream.finish()
            parts: tuple[FinalPart, ...] = ()
            if self._cleaner is not None:
                if self._lost is None:
                    parts = self._finish_pieces(text)
                    text = " ".join(p.text for p in parts if p.text)
                else:
                    self._cleaner.cancel()  # the session ended early: voice_in drops its text anyway
            latency_ms = int((time.monotonic() - self._stop_time) * 1000)
            final = Final(text=text, latency_ms=latency_ms, complete=self._lost is None, ended_by=ended_by, parts=parts)
            self._post(final)
            log.info(
                "final: %d chars in %d ms, %.1f s of audio, %d ms dropped, %d mic drops, %d pieces, ended by %s%s: %r",
                len(text), latency_ms, self._accepted * self._chunk_ms / 1000, self._dropped * self._chunk_ms,
                self._drops, len(parts), ended_by, ", mic lost" if self._lost else "", text,
            )  # fmt: skip
            if self._lost is not None:
                self._post(Error(reason=ErrorCode.MIC_LOST, detail=self._lost))
        except Exception as exc:
            if not self._abort.is_set():
                detail = str(exc) if isinstance(exc, EngineError) else f"speech engine error: {type(exc).__name__}: {exc}"
                log.error("session failed: %s", detail)
                self._post(Error(reason=ErrorCode.ENGINE_FAILED, detail=detail))
        finally:
            if self._cleaner is not None and self._abort.is_set():
                self._cleaner.cancel()
            self._close_source()
            self._post(DONE)

    def _accept(self, stream: SttStream, pcm: bytes) -> str | None:
        """Feed one chunk to the live engine (and, two passes, to the current piece). The live text, if read."""
        stream.accept(pcm)
        self._accepted += 1
        text = stream.partial() if self._live else None
        if self._cutter is not None:
            if text is not None:
                self._words = text.split()
            self._piece_chunks.append(pcm)
            self._piece_counts.append(len(self._words))
            if not self._stopping.is_set() and (cut := self._cutter.feed(rms(pcm))) is not None:
                self._cut(cut)
        return text

    def _cut(self, length: int, *, speech: bool = True) -> None:
        """The current piece's first `length` chunks are a piece: queue it; the rest starts the next one.

        `speech` is whether the piece had speech (a pause or forced cut always has)."""
        if length <= 0:
            return
        end = max(self._span_start, self._piece_counts[length - 1])
        piece = Piece(
            index=self._cleaner.given,
            audio=b"".join(self._piece_chunks[:length]),
            start=self._span_start,
            end=end,
            words=self._words[self._span_start : end],
            speech=speech,
        )
        del self._piece_chunks[:length], self._piece_counts[:length]
        self._span_start = end
        self._cleaner.put(piece)

    def _finish_pieces(self, text: str) -> tuple[FinalPart, ...]:
        """After stop: the last piece (the audio since the last cut), then wait for every piece."""
        self._words = text.split()
        end = max(self._span_start, len(self._words))
        last = bool(self._piece_chunks) and (self._cutter.speech or end > self._span_start)
        self._post(Refining(text=text if self.partials else "", pending=self._cleaner.pending + int(last)))
        if last:
            self._piece_counts = [end] * len(self._piece_counts)  # the last piece takes every word left
            self._cut(len(self._piece_chunks), speech=self._cutter.speech)
        parts = self._cleaner.finish(self._stop_time + self._final_timeout)
        log.info("pieces done %.2f s after stop", time.monotonic() - self._stop_time)
        return tuple(parts)

    def _listen(self, stream: SttStream) -> str | None:
        """Accept chunks and post partials until a stop, a lost mic that doesn't come back, or a long
        silence; then drain the queue.

        Speech (for the silence stop) is the engine's text changing, or, with an engine that gives
        no live text, a chunk at or above `speech_rms`. Returns `ended_by` ("stop" or "silence"),
        or None if aborted.
        """
        last_text, last_change, last_sent, pending = "", self._started_at, float("-inf"), False
        ended_by = "stop"
        while True:
            # A lost mic: first take what it already queued, so the text so far is up to date.
            while not self._stopping.is_set() and (self._lost is None or not self._chunks.empty()):
                if self._abort.is_set():
                    return None
                try:
                    pcm = self._chunks.get(timeout=0.05)
                except queue.Empty:
                    pcm = None
                now = time.monotonic()
                if pcm is not None:
                    text = self._accept(stream, pcm)
                    if text is not None:
                        if text != last_text:
                            last_text, last_change, pending = text, now, self.partials
                    elif rms(pcm) >= self._speech_rms:
                        last_change = now
                if pending and now - last_sent >= self._interval:
                    self._post(Partial(text=last_text))
                    last_sent, pending = now, False
                if self._silence > 0 and now - last_change >= self._silence:
                    log.info("no speech for %.0f s: stopping", self._silence)
                    self._stop_time = now
                    self._close_source()
                    ended_by = "silence"
                    break
                if self._stall > 0 and self._lost is None and now - self._last_chunk >= self._stall:
                    # No chunks at all (silence still sends them): an unplug Windows didn't report.
                    self._lost = f"no audio from the mic for {self._stall:g} s"
                    log.warning("%s: treating it as a lost mic", self._lost)
            if ended_by == "silence" or self._stopping.is_set() or self._abort.is_set():
                break
            if pending:  # the mic was lost: show the text so far before the drop
                self._post(Partial(text=last_text))
                last_sent, pending = time.monotonic(), False
            if self._cutter is not None and (self._cutter.speech or len(self._words) > self._span_start):
                self._cut(len(self._piece_chunks), speech=self._cutter.speech)  # a mic drop ends a piece with speech; the next starts when the mic is back
                self._cutter.reset()
            if not self._recover():
                break
            last_change = time.monotonic()  # the silence timer starts again after a drop
        if self._lost is not None and not self._stopping.is_set():
            self._stop_time = time.monotonic()
            self._close_source()
        while True:
            if self._abort.is_set():
                return None
            try:
                pcm = self._chunks.get_nowait()
            except queue.Empty:
                return ended_by
            self._accept(stream, pcm)

    def _recover(self) -> bool:
        """The mic was lost: keep the session and try a fresh source until `mic_recovery_seconds` pass.

        True if one opened (`mic_back` was posted); False on a timeout, a stop, or an abort.
        """
        if self._recovery <= 0:
            return False
        detail = self._lost or "the microphone stopped"
        self._close_source()
        self._drops += 1
        self._post(MicDropped(detail=detail, wait_seconds=self._recovery))
        log.warning("mic dropped (%s): trying to reopen it for %.0f s", detail, self._recovery)
        deadline = time.monotonic() + self._recovery
        while (left := deadline - time.monotonic()) > 0:
            if self._stopping.wait(min(self.retry_seconds, left)) or self._abort.is_set():
                return False
            try:
                self._open_source()
            except Exception as exc:
                log.debug("the mic didn't reopen: %s", exc)
                continue
            if self._stopping.is_set() or self._abort.is_set():
                self._close_source()
                return False
            self._lost = None
            self._post(MicBack())
            log.info("the mic is back")
            return True
        log.warning("the mic didn't come back within %.0f s", self._recovery)
        return False
