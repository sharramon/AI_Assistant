"""Audio sources: where a session's PCM16, 16 kHz mono chunks come from.

`MicSource` is the real mic (sounddevice, imported only in `start`). `FileSource` reads a
16 kHz mono WAV, for transcribing recordings (`transcribe.py`) or feeding the service as if
it were a mic. `FakeSource` feeds chunks from a list, for tests. A remote recorder
(`/ws/audio`, later) becomes another `AudioSource`.
"""

from __future__ import annotations

import threading
import time
import wave
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

SAMPLE_RATE = 16000
OnChunk = Callable[[bytes], None]
OnLost = Callable[[str], None]


class MicUnavailable(RuntimeError):
    """The source couldn't be opened (no mic, blocked, busy). The message names the device and the reason."""


class AudioSource(ABC):
    """Calls `on_chunk(pcm)` for every chunk from `start` until `stop`, and `on_lost(reason)` if it ends by itself.

    `on_chunk` is called from the source's own thread and must not block.
    """

    @abstractmethod
    def start(self, on_chunk: OnChunk, on_lost: OnLost) -> None:
        """Open the source. Raises `MicUnavailable` if it can't."""

    @abstractmethod
    def stop(self) -> None:
        """Close the source; no `on_chunk` call happens after it returns."""


class MicSource(AudioSource):
    """The mic, through a sounddevice `RawInputStream`: int16, 16 kHz, mono, `chunk_ms` per callback.

    PortAudio reads the device list once. After a mic is lost, the next `start` reloads it, so a
    replugged or other mic can open (`stale_devices`).
    """

    stale_devices = False  # set when any MicSource is lost; the next start refreshes PortAudio

    @staticmethod
    def _refresh_devices(sd: Any) -> None:
        terminate, initialize = getattr(sd, "_terminate", None), getattr(sd, "_initialize", None)
        if terminate is None or initialize is None:
            return
        try:
            terminate()
            initialize()
        except Exception:  # keep the old list; the open below reports any real problem
            pass

    def __init__(self, device: str | int = "", chunk_ms: int = 32) -> None:
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        self.device = device if device != "" else None
        self.frames = SAMPLE_RATE * chunk_ms // 1000
        self._stream: Any = None
        self._stopping = False
        self._last_audio = 0.0

    def start(self, on_chunk: OnChunk, on_lost: OnLost) -> None:
        name = self.device if self.device is not None else "the default mic"
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise MicUnavailable(f"{name}: sounddevice is not available ({exc})") from exc

        def callback(indata, frames, time_info, status) -> None:  # PortAudio's thread: copy and queue, nothing else
            self._last_audio = time.monotonic()
            on_chunk(bytes(indata))

        def finished() -> None:
            if not self._stopping:
                MicSource.stale_devices = True
                on_lost(f"{name} stopped (unplugged or turned off)")

        if MicSource.stale_devices:
            self._refresh_devices(sd)
        self._last_audio = time.monotonic()
        try:
            self._stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=self.frames,
                device=self.device,
                channels=1,
                dtype="int16",
                callback=callback,
                finished_callback=finished,
            )
            self._stream.start()
            MicSource.stale_devices = False
        except Exception as exc:
            self._stream = None
            raise MicUnavailable(f"{name}: {exc}") from exc

    def stop(self) -> None:
        self._stopping = True
        stream, self._stream = self._stream, None
        if stream is not None:
            if time.monotonic() - self._last_audio > 1.0:  # stopped while it had gone quiet: likely unplugged
                MicSource.stale_devices = True
            stream.stop()
            stream.close()


class _ChunkFeeder(AudioSource):
    """Feeds a list of chunks on its own thread, `interval` seconds apart, then stays open until `stop`.

    `lose_after=N` ends it after N chunks as if the mic was unplugged.
    """

    def __init__(self, chunks: Sequence[bytes] = (), *, interval: float = 0.0, lose_after: int | None = None) -> None:
        self.chunks = list(chunks)
        self.interval = interval
        self.lose_after = lose_after
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, on_chunk: OnChunk, on_lost: OnLost) -> None:
        self._thread = threading.Thread(target=self._feed, args=(on_chunk, on_lost), name="chunk-feeder", daemon=True)
        self._thread.start()

    def _feed(self, on_chunk: OnChunk, on_lost: OnLost) -> None:
        for i, chunk in enumerate(self.chunks):
            if self.lose_after is not None and i >= self.lose_after:
                break
            if self._stopped.is_set():
                return
            on_chunk(chunk)
            if self.interval:
                time.sleep(self.interval)
        if self.lose_after is not None and not self._stopped.is_set():
            on_lost("fake mic: unplugged")

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)


class FileSource(_ChunkFeeder):
    """A 16 kHz mono PCM16 WAV file, in chunks of `chunk_ms`.

    Read whole with `chunks` (what `transcribe` does), or `start`ed like a mic: fed at the speed
    of speech with `realtime=True`, as fast as taken otherwise. Any other format raises `ValueError`.
    """

    def __init__(self, path: str | Path, *, chunk_ms: int = 32, realtime: bool = False) -> None:
        self.path = Path(path)
        with wave.open(str(self.path), "rb") as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
                raise ValueError(
                    f"{self.path}: needs 16 kHz mono 16-bit WAV, got {wav.getframerate()} Hz, "
                    f"{wav.getnchannels()} channel(s), {8 * wav.getsampwidth()}-bit"
                )
            data = wav.readframes(wav.getnframes())
        size = SAMPLE_RATE * chunk_ms // 1000 * 2
        super().__init__([data[i : i + size] for i in range(0, len(data), size)], interval=chunk_ms / 1000 if realtime else 0.0)
        self.seconds = len(data) / 2 / SAMPLE_RATE  # the recording's length


class FakeSource(_ChunkFeeder):
    """Feeds `chunks` on its own thread, `interval` seconds apart, then stays open until `stop`.

    `fail_on_open` makes `start` raise `MicUnavailable`; `lose_after=N` ends it after N chunks
    as if the mic was unplugged.
    """

    def __init__(
        self,
        chunks: Sequence[bytes] = (),
        *,
        interval: float = 0.0,
        fail_on_open: bool = False,
        lose_after: int | None = None,
    ) -> None:
        super().__init__(chunks, interval=interval, lose_after=lose_after)
        self.fail_on_open = fail_on_open

    @classmethod
    def from_wav(cls, path: str | Path, *, chunk_ms: int = 32, realtime: bool = True) -> FakeSource:
        """Chunks from a 16 kHz mono 16-bit WAV file (read by `FileSource`), fed at the speed of speech if `realtime`."""
        return cls(FileSource(path, chunk_ms=chunk_ms).chunks, interval=chunk_ms / 1000 if realtime else 0.0)

    def start(self, on_chunk: OnChunk, on_lost: OnLost) -> None:
        if self.fail_on_open:
            raise MicUnavailable("fake mic: failed to open")
        super().start(on_chunk, on_lost)
