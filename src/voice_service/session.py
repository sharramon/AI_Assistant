"""One mic session: its audio source, chunk queue, and engine thread. Plus the background model load.

Threads (docs/architecture/voice.md#the-voice-service-threads-and-audio-flow): the source's thread
only queues chunks; the engine thread accepts them and hands messages to the asyncio loop with
`call_soon_threadsafe`; the loop calls `start`, `stop` and `abort` (through `asyncio.to_thread`).
A lost mic is reopened from the engine thread, with a fresh source from the factory.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Callable

from .audio import AudioSource
from .config import ServiceConfig
from .engines import EngineError, SttEngine, SttStream
from .protocol import Error, ErrorCode, Final, MicBack, MicDropped, Partial

log = logging.getLogger("voice_service.session")

DONE = object()  # the last item on a session's outbox: the engine thread has ended


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


class ListenSession:
    """Mic on until `stop`, a long silence, a lost mic that doesn't come back, or `abort`.

    Results come out of `outbox`, then `DONE`. `source_factory` makes the first source, and a
    fresh one for each try to reopen a lost mic (for `mic_recovery_seconds`).
    """

    retry_seconds = 1.0  # how often a lost mic is tried again

    def __init__(
        self,
        loader: EngineLoader,
        source_factory: Callable[[], AudioSource],
        config: ServiceConfig,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        audio = config.audio
        self.outbox: asyncio.Queue = asyncio.Queue()
        self._loader = loader
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

    @property
    def stopping(self) -> bool:
        return self._stopping.is_set()

    def start(self) -> None:
        """Open the source and start the engine thread. Raises what the source raises (`MicUnavailable`)."""
        self._started_at = time.monotonic()
        self._open_source()
        self._thread = threading.Thread(target=self._run, name="voice-engine", daemon=True)
        self._thread.start()
        log.info("session started")

    def stop(self) -> None:
        """Close the mic; the engine thread drains the queue and posts the final."""
        if self._stopping.is_set():
            return
        self._stop_time = time.monotonic()
        self._close_source()
        self._stopping.set()

    def abort(self) -> None:
        """Drop everything: mic closed, engine thread ended, no final."""
        self._abort.set()
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
            latency_ms = int((time.monotonic() - self._stop_time) * 1000)
            self._post(Final(text=text, latency_ms=latency_ms, complete=self._lost is None, ended_by=ended_by))
            log.info(
                "final: %d chars in %d ms, %.1f s of audio, %d ms dropped, %d mic drops, ended by %s%s: %r",
                len(text), latency_ms, self._accepted * self._chunk_ms / 1000, self._dropped * self._chunk_ms,
                self._drops, ended_by, ", mic lost" if self._lost else "", text,
            )  # fmt: skip
            if self._lost is not None:
                self._post(Error(reason=ErrorCode.MIC_LOST, detail=self._lost))
        except Exception as exc:
            if not self._abort.is_set():
                detail = str(exc) if isinstance(exc, EngineError) else f"speech engine error: {type(exc).__name__}: {exc}"
                log.error("session failed: %s", detail)
                self._post(Error(reason=ErrorCode.ENGINE_FAILED, detail=detail))
        finally:
            self._close_source()
            self._post(DONE)

    def _listen(self, stream: SttStream) -> str | None:
        """Accept chunks and post partials until a stop, a lost mic that doesn't come back, or a long
        silence; then drain the queue.

        Returns `ended_by` ("stop" or "silence"), or None if aborted.
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
                    stream.accept(pcm)
                    self._accepted += 1
                    text = stream.partial()
                    if text != last_text:
                        last_text, last_change, pending = text, now, True
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
                stream.accept(self._chunks.get_nowait())
            except queue.Empty:
                return ended_by
            self._accepted += 1

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
