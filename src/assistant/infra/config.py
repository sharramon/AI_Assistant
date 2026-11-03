"""Loads the main app's TOML configuration: a thin wrapper around `app_kit.load_layered`."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app_kit import load_layered


def load_config(config_dir: str | Path | None = None) -> dict[str, Any]:
    """Load `default.toml`, then deep-merge `local.toml` over it if it exists.

    The directory is `config_dir`, else the ASSISTANT_CONFIG_DIR environment
    variable, else `./config`.
    """
    directory = Path(config_dir or os.environ.get("ASSISTANT_CONFIG_DIR", "config"))
    return load_layered(directory / "default.toml", directory / "local.toml")
