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


class ZipformerConfig(_Section):
    model: str = "sherpa-onnx-streaming-zipformer-en-2023-06-26"  # folder under models_dir
    num_threads: int = 2
    decoding: str = "greedy_search"
    int8: bool = True  # False: the full-precision model files


class FakeConfig(_Section):
    text: str = "hello from the fake engine"


class EngineConfig(_Section):
    name: Literal["zipformer", "fake"] = "zipformer"
    models_dir: str = ""  # "" = %LOCALAPPDATA%\AI_Assistant\voice_models; env VOICE_SERVICE_MODELS overrides
    partial_interval_ms: int = 100
    zipformer: ZipformerConfig = ZipformerConfig()
    fake: FakeConfig = FakeConfig()


class LoggingConfig(_Section):
    level: str = "INFO"
    file: str = ""  # "" = stderr only


class ServiceConfig(_Section):
    server: ServerConfig = ServerConfig()
    audio: AudioConfig = AudioConfig()
    engine: EngineConfig = EngineConfig()
    logging: LoggingConfig = LoggingConfig()


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
