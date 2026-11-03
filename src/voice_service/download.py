"""Fetch an engine's model files once into `models_dir`. Never called while the service runs."""

from __future__ import annotations

import logging
import shutil
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .config import ServiceConfig, models_dir

log = logging.getLogger("voice_service.download")

ZIPFORMER_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{model}.tar.bz2"

Fetch = Callable[[str, Path], None]


def download_model(engine: str, config: ServiceConfig, *, fetch: Fetch | None = None) -> Path:
    """Download and extract `engine`'s model (as named in `config`) into `models_dir`; returns its folder.

    Does nothing if the folder is already there. Raises `ValueError` for an engine with no download.
    """
    if engine != "zipformer":
        raise ValueError(f"no download for engine {engine!r}; only 'zipformer'")
    model = config.engine.zipformer.model
    root = models_dir(config)
    target = root / model
    if target.is_dir():
        log.info("already downloaded: %s", target)
        return target
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        archive = Path(tmp) / f"{model}.tar.bz2"
        (fetch or _fetch)(ZIPFORMER_URL.format(model=model), archive)
        extract(archive, root)
    if not target.is_dir():
        raise RuntimeError(f"the archive didn't contain {model}/")
    return target


def extract(archive: Path, dest: Path) -> None:
    """Extract a tar archive with tarfile's safe `data` filter (no paths outside `dest`, no links out, no devices)."""
    with tarfile.open(archive, "r:*") as tar:
        tar.extractall(dest, filter="data")


def _fetch(url: str, dest: Path) -> None:
    log.info("downloading %s", url)
    with urllib.request.urlopen(url, timeout=60) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    log.info("downloaded %.0f MB", dest.stat().st_size / 1e6)
