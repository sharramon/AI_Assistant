"""The voice service's config: built-in defaults, then the TOML file and its `.local` override, then flags.

Spec: docs/architecture/voice.md#the-voice-service-config.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app_kit import load_layered

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "voice_service.toml"
WHISPER_PREFIX = "faster-whisper-"  # whisper model folders: faster-whisper-<size>, e.g. faster-whisper-small.en


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServerConfig(_Section):
    host: str = "127.0.0.1"
    port: int = 8767


class AudioConfig(_Section):
    device: str | int = ""  # "" = the system's default mic; or a device name or index
    chunk_ms: int = Field(32, gt=0)  # rate and format are fixed: 16 kHz mono PCM16
    queue_seconds: float = Field(10.0, gt=0)
    silence_stop_seconds: float = 120.0  # 0 or less: never stop on silence
    mic_recovery_seconds: float = 15.0  # a lost mic: try to reopen it this long; 0 or less: end the session at once
    stall_seconds: float = 2.0  # no audio at all for this long counts as a lost mic (an unplug Windows didn't report); 0: off
    speech_rms: float = 300.0  # a chunk this loud (RMS, int16 scale) counts as speech, for the silence stop when the engine gives no live text


class ZipformerConfig(_Section):
    model: str = "sherpa-onnx-streaming-zipformer-en-2023-06-26"  # folder under models_dir
    num_threads: int = 2
    decoding: str = "greedy_search"
    int8: bool = True  # False: the full-precision model files


class WhisperConfig(_Section):
    model: str = "faster-whisper-small.en"  # folder under models_dir (`python -m voice_service download whisper`)
    device: str = "cpu"  # "cuda" later
    compute_type: str = "int8"
    beam_size: int = 5
    cpu_threads: int = 8


class FakeConfig(_Section):
    text: str = "hello from the fake engine"


EngineName = Literal["zipformer", "whisper", "fake"]


class EngineConfig(_Section):
    name: EngineName = "zipformer"  # the live engine: listens, fills the live line. Changing it restarts a running service
    final: EngineName | Literal[""] = "whisper"  # the final engine: cleans each piece; "" (or the same as name) = one engine
    final_timeout_seconds: float = Field(20.0, gt=0)  # after stop: pieces not cleaned by then keep their live words
    models_dir: str = ""  # "" = %LOCALAPPDATA%\AI_Assistant\voice_models; env VOICE_SERVICE_MODELS overrides
    partial_interval_ms: int = 100
    zipformer: ZipformerConfig = ZipformerConfig()
    whisper: WhisperConfig = WhisperConfig()
    fake: FakeConfig = FakeConfig()


class PiecesConfig(_Section):
    """Where the live audio is cut into pieces for the final engine. Read per session (a save applies to the next one)."""

    pause_seconds: float = Field(0.7, gt=0)  # this long below speech_rms, after speech, ends a piece
    min_seconds: float = Field(4.0, ge=0)  # a pause before this doesn't cut
    max_seconds: float = Field(20.0, gt=0)  # this much after the piece's first speech with no pause: cut at the quietest chunk
    cut_search_seconds: float = Field(3.0, gt=0)  # a forced cut looks this far back for the quietest chunk
    prompt_previous: bool = True  # give the final engine the previous piece's text, so the joins read on


class LoggingConfig(_Section):
    level: str = "INFO"
    file: str = ""  # "" = stderr only


class ServiceConfig(_Section):
    server: ServerConfig = ServerConfig()
    audio: AudioConfig = AudioConfig()
    engine: EngineConfig = EngineConfig()
    pieces: PiecesConfig = PiecesConfig()
    logging: LoggingConfig = LoggingConfig()


def final_engine_name(config: ServiceConfig) -> str:
    """The final engine's name, or "" for one engine (`final` empty or the same as `name`)."""
    final = config.engine.final
    return "" if final == config.engine.name else final


def load_service_config(
    path: str | Path | None = None, *, host: str | None = None, port: int | None = None
) -> ServiceConfig:
    """Defaults, then `path` (default `config/voice_service.toml`) and its `.local.toml`, then `host` / `port`.

    A missing default file means the built-in defaults; a missing `path` raises `FileNotFoundError`.
    """
    if path is None:
        data = load_layered(DEFAULT_CONFIG) if DEFAULT_CONFIG.exists() else {}
    else:
        data = load_layered(path)
    config = ServiceConfig.model_validate(data)
    if host is not None:
        config.server.host = host
    if port is not None:
        config.server.port = port
    return config


def models_dir(config: ServiceConfig) -> Path:
    """Where model folders live: env `VOICE_SERVICE_MODELS`, else `[engine] models_dir`, else the user's app data."""
    if env := os.environ.get("VOICE_SERVICE_MODELS"):
        return Path(env)
    if config.engine.models_dir:
        return Path(config.engine.models_dir)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "AI_Assistant" / "voice_models"


def whisper_folder(model: str) -> str:
    """A whisper model's folder name under models_dir: `small.en` → `faster-whisper-small.en` (a folder name stays)."""
    model = model.replace("/", "--")  # a Hugging Face repo id
    return model if model.startswith(WHISPER_PREFIX) else WHISPER_PREFIX + model
