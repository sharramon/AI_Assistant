"""WhisperEngine: whisper through faster-whisper (CTranslate2), text on send.

Whisper gives no live text, so `live_partials` is False: a stream only buffers the audio, and
`finish` transcribes it all at once (the wait after the mic stops). faster-whisper and numpy are
imported only in `load` / `finish`. The model is read from a local folder only, never downloaded
while running (`python -m voice_service download whisper`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import WhisperConfig
from . import EngineError, SttEngine, SttStream

HINT = "run: python -m voice_service download whisper"


class WhisperEngine(SttEngine):
    name = "whisper"
    live_partials = False

    def __init__(self, model_dir: Path, config: WhisperConfig) -> None:
        self.model_dir = Path(model_dir)
        self.config = config
        self._model: Any = None

    def load(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise EngineError(f"faster-whisper is not installed ({exc}); run: pip install -e .[voice]") from exc
        if not (self.model_dir / "model.bin").is_file():
            raise EngineError(f"speech model not installed: {self.model_dir} has no model.bin; {HINT}")
        self._model = WhisperModel(
            str(self.model_dir),
            device=self.config.device,
            compute_type=self.config.compute_type,
            cpu_threads=self.config.cpu_threads,
            local_files_only=True,
        )

    def new_stream(self) -> SttStream:
        if self._model is None:
            raise EngineError("the whisper model isn't loaded")
        return _WhisperStream(self._model, self.config.beam_size)


class _WhisperStream(SttStream):
    def __init__(self, model: Any, beam_size: int) -> None:
        self._model = model
        self._beam_size = beam_size
        self._audio = bytearray()  # PCM16 at 16 kHz: 32 KB/s, about 4 MB for two minutes
        self._prompt = ""
        self._cancelled = False

    def accept(self, pcm: bytes) -> None:
        self._audio += pcm

    def partial(self) -> str:
        return ""

    def set_prompt(self, text: str) -> None:
        self._prompt = text.strip()

    def cancel(self) -> None:
        # A running decode can't be killed: faster-whisper decodes a 30 s window at once, so for a
        # piece (at most 20 s) this only throws the text away. Checked before and between segments.
        self._cancelled = True

    def finish(self) -> str:
        if not self._audio or self._cancelled:
            return ""
        import numpy as np

        samples = np.frombuffer(bytes(self._audio), dtype=np.int16).astype(np.float32) / 32768.0
        options: dict[str, Any] = {"language": "en", "beam_size": self._beam_size, "vad_filter": True}
        if self._prompt:
            options["initial_prompt"] = self._prompt  # the previous piece: whisper carries on in its style
        # The built-in VAD skips silence, which also stops whisper inventing words on empty audio.
        segments, _info = self._model.transcribe(samples, **options)
        texts = []
        for segment in segments:  # decoded lazily, one segment at a time
            if self._cancelled:
                return ""
            texts.append(segment.text.strip())
        return " ".join(texts).strip()
