"""Logging setup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


def setup_logging(settings: dict[str, Any]) -> None:
    """Configure root logging from the `[logging]` config section.

    Logs go to `file` by default, not the terminal, so they don't interleave
    with console input/output. Set `stderr = true` to also log to the terminal.
    """
    handlers: list[logging.Handler] = []
    if file := settings.get("file"):
        path = Path(file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    if settings.get("stderr", False):
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=settings.get("level", "INFO"),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers or [logging.NullHandler()],
        force=True,
    )
