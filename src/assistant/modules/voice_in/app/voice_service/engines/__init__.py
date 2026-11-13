"""The engine interface and the one place that knows the engine names.

The server, the session, and the protocol see only `SttEngine` / `SttStream`. An engine works
by itself, with no mic and no server (`voice_service.transcribe`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import ServiceConfig, models_dir, whisper_folder


class EngineError(RuntimeError):
    """The engine can't be used: unknown name, model missing, library missing. The message is for the log."""


class SttStream(ABC):
    """One session's recognition state. Called from the session's engine thread only."""

    @abstractmethod
    def accept(self, pcm: bytes) -> None:
        """Feed PCM16, 16 kHz mono audio."""

    @abstractmethod
    def partial(self) -> str:
        """The text so far. Never called when the engine's `live_partials` is False."""

    @abstractmethod
    def finish(self) -> str:
        """No more audio: flush the model and return the final text."""

    def set_prompt(self, text: str) -> None:
        """Optional: the text said just before this audio, so the engine carries on in its style. Default: ignored."""

    def cancel(self) -> None:
        """Optional, from another thread: stop a running `finish` early; its result is thrown away. Default: nothing."""


class SttEngine(ABC):
    """A speech-to-text engine: the model, loaded once; one `SttStream` per session.

    `live_partials`: whether its streams give text while audio comes in. False (whisper): the
    text comes only from `finish`, so the session sends no partials and finds speech by level.
    """

    name: str = ""
    live_partials: bool = True

    def load(self) -> None:
        """Load the model. Blocking, called once in the background. Raises on failure."""

    @abstractmethod
    def new_stream(self) -> SttStream:
        """A fresh stream for one session. Only after `load` succeeded."""


def load_engine(name: str, config: ServiceConfig) -> SttEngine:
    """The engine called `name`, configured but not loaded yet. Raises `EngineError` for an unknown name."""
    if name == "fake":
        from .fake import FakeEngine

        return FakeEngine(config.engine.fake.text)
    if name == "zipformer":
        from .zipformer import ZipformerEngine

        zipformer = config.engine.zipformer
        return ZipformerEngine(models_dir(config) / zipformer.model, zipformer)
    if name == "whisper":
        from .whisper import WhisperEngine

        whisper = config.engine.whisper
        return WhisperEngine(models_dir(config) / whisper_folder(whisper.model), whisper)
    raise EngineError(f"unknown engine {name!r}; choose 'zipformer', 'whisper' or 'fake'")
