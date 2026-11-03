"""A TOML file plus its local override, deep-merged."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def load_layered(base: str | Path, local: str | Path | None = None) -> dict[str, Any]:
    """Load the TOML file `base`, then deep-merge `local` over it if that file exists.

    `local` defaults to `base` with `.local` before the suffix (`voice.toml` → `voice.local.toml`).
    Tables merge key by key; other values, lists included, are replaced.
    Raises `FileNotFoundError` if `base` is missing, `tomllib.TOMLDecodeError` for invalid TOML.
    """
    base = Path(base)
    local = Path(local) if local is not None else base.with_name(f"{base.stem}.local{base.suffix}")
    config = _read(base)
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
