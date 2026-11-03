"""The engine interface and the one place that knows the engine names.

The server, the session, and the protocol see only `SttEngine` / `SttStream`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import ServiceConfig, models_dir


class EngineError(RuntimeError):
    """The engine can't be used: unknown name, model missing, library missing. The message is for the log."""


class SttStream(ABC):
    """One session's recognition state. Called from the session's engine thread only."""

    @abstractmethod
    def accept(self, pcm: bytes) -> None:
        """Feed PCM16, 16 kHz mono audio."""

    @abstractmethod
    def partial(self) -> str:
        """The text so far."""

    @abstractmethod
    def finish(self) -> str:
        """No more audio: flush the model and return the final text."""


class SttEngine(ABC):
    """A speech-to-text engine: the model, loaded once; one `SttStream` per session."""

    name: str = ""

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
    raise EngineError(f"unknown engine {name!r}; choose 'zipformer' or 'fake'")
