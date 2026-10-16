"""Loads TOML configuration."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


def load_config(config_dir: str | Path | None = None) -> dict[str, Any]:
    """Load `default.toml`, then deep-merge `local.toml` over it if it exists.

    The directory is `config_dir`, else the ASSISTANT_CONFIG_DIR environment
    variable, else `./config`.
    """
    directory = Path(config_dir or os.environ.get("ASSISTANT_CONFIG_DIR", "config"))
    config = _read(directory / "default.toml")
    local = directory / "local.toml"
    if local.exists():
        config = _merge(config, _read(local))
    return config


def _read(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged
