"""Speech to text from a file, straight through an engine: no server, no mic, no session thread.

    text = transcribe_file("talk.wav", "whisper")

The layer for utilities (and the engine comparison) that want text without the voice service.
Imports neither the server nor sounddevice.
"""

from __future__ import annotations

import time
from pathlib import Path

from .audio import FileSource
from .config import ServiceConfig, load_service_config
from .engines import SttEngine, load_engine


def transcribe(engine: SttEngine, source: FileSource, *, load: bool = True, timings: dict | None = None) -> str:
    """Run one stream of `engine` over all of `source`'s chunks and return the final text.

    `load=False` for an engine that's already loaded. `timings`, if given, gets `audio_seconds`,
    `load_seconds`, `accept_seconds` (feeding the audio) and `finish_seconds` (the wait after the
    audio ends: what you'd wait after stopping the mic).
    """
    began = time.perf_counter()
    if load:
        engine.load()
    loaded = time.perf_counter()
    stream = engine.new_stream()
    for pcm in source.chunks:
        stream.accept(pcm)
    fed = time.perf_counter()
    text = stream.finish()
    done = time.perf_counter()
    if timings is not None:
        timings.update(audio_seconds=source.seconds, load_seconds=loaded - began, accept_seconds=fed - loaded,
                       finish_seconds=done - fed)  # fmt: skip
    return text


def transcribe_file(
    path: str | Path, engine_name: str | None = None, config: ServiceConfig | None = None, *, timings: dict | None = None
) -> str:
    """The text of a 16 kHz mono WAV, with the engine `engine_name` (default: the config's) loaded for it."""
    config = config or load_service_config()
    engine = load_engine(engine_name or config.engine.name, config)
    return transcribe(engine, FileSource(path, chunk_ms=config.audio.chunk_ms), timings=timings)
