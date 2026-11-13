"""ZipformerEngine: Streaming Zipformer EN through sherpa-onnx's OnlineRecognizer.

sherpa-onnx is imported only in `load`, after the model files are found, so a missing
model gives a clear error and the rest of the service runs without it. No numpy:
sherpa-onnx takes a plain sequence of floats.
"""

from __future__ import annotations

from array import array
from pathlib import Path
from typing import Any

from ..config import ZipformerConfig
from . import EngineError, SttEngine, SttStream

SAMPLE_RATE = 16000
_TAIL_PADDING_SECONDS = 0.66  # silence fed after the last chunk so the model emits its last words


class ZipformerEngine(SttEngine):
    name = "zipformer"

    def __init__(self, model_dir: Path, config: ZipformerConfig) -> None:
        self.model_dir = Path(model_dir)
        self.config = config
        self._recognizer: Any = None

    def model_files(self) -> dict[str, Path]:
        """The tokens and the encoder, decoder and joiner files (int8 or full precision, per config)."""
        hint = "run: python -m voice_service download zipformer"
        if not self.model_dir.is_dir():
            raise EngineError(f"speech model not installed: {self.model_dir} is missing; {hint}")
        files = {"tokens": self.model_dir / "tokens.txt"}
        for part in ("encoder", "decoder", "joiner"):
            found = sorted(p for p in self.model_dir.glob(f"{part}-*.onnx") if p.name.endswith(".int8.onnx") == self.config.int8)
            if not found:
                kind = "int8" if self.config.int8 else "full-precision"
                raise EngineError(f"no {kind} {part} model in {self.model_dir}; {hint}")
            files[part] = found[0]
        if not files["tokens"].is_file():
            raise EngineError(f"tokens.txt missing in {self.model_dir}; {hint}")
        return files

    def load(self) -> None:
        files = self.model_files()
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise EngineError(f"sherpa-onnx is not installed ({exc}); run: pip install the packages in voice_in's module.toml") from exc
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(files["tokens"]),
            encoder=str(files["encoder"]),
            decoder=str(files["decoder"]),
            joiner=str(files["joiner"]),
            num_threads=self.config.num_threads,
            sample_rate=SAMPLE_RATE,
            feature_dim=80,
            decoding_method=self.config.decoding,
            enable_endpoint_detection=False,
        )

    def new_stream(self) -> SttStream:
        if self._recognizer is None:
            raise EngineError("the Zipformer model isn't loaded")
        return _ZipformerStream(self._recognizer)


class _ZipformerStream(SttStream):
    def __init__(self, recognizer: Any) -> None:
        self._rec = recognizer
        self._stream = recognizer.create_stream()

    def _feed(self, samples: list[float]) -> None:
        self._stream.accept_waveform(SAMPLE_RATE, samples)
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)

    def accept(self, pcm: bytes) -> None:
        self._feed([s / 32768.0 for s in array("h", pcm)])  # PCM16 little-endian (Windows, Linux) to [-1, 1]

    def partial(self) -> str:
        result = self._rec.get_result(self._stream)
        return (result if isinstance(result, str) else result.text).strip()

    def finish(self) -> str:
        self._feed([0.0] * int(_TAIL_PADDING_SECONDS * SAMPLE_RATE))
        self._stream.input_finished()
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)
        return self.partial()
