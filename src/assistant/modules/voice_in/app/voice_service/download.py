"""Fetch an engine's model files once into `models_dir`. Never called while the service runs."""

from __future__ import annotations

import logging
import shutil
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .config import WHISPER_PREFIX, ServiceConfig, models_dir, whisper_folder

log = logging.getLogger("voice_service.download")

ZIPFORMER_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{model}.tar.bz2"

Fetch = Callable[[str, Path], None]
FetchWhisper = Callable[[str, Path], None]  # (size or repo id, output folder)


def download_model(
    engine: str, config: ServiceConfig, *, fetch: Fetch | None = None, model: str | None = None,
    fetch_whisper: FetchWhisper | None = None,
) -> Path:  # fmt: skip
    """Download `engine`'s model (as named in `config`, or `model` for whisper) into `models_dir`; returns its folder.

    Does nothing if the folder is already there. Raises `ValueError` for an engine with no download.
    """
    if engine == "whisper":
        return _download_whisper(config, model, fetch_whisper or _fetch_whisper)
    if engine != "zipformer":
        raise ValueError(f"no download for engine {engine!r}; only 'zipformer' and 'whisper'")
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


def _download_whisper(config: ServiceConfig, model: str | None, fetch: FetchWhisper) -> Path:
    """A CTranslate2 whisper model into `models_dir/faster-whisper-<size>`, through a temp folder so a
    broken download leaves nothing behind."""
    folder = whisper_folder(model or config.engine.whisper.model)
    root = models_dir(config)
    target = root / folder
    if target.is_dir():
        log.info("already downloaded: %s", target)
        return target
    root.mkdir(parents=True, exist_ok=True)
    size = folder.removeprefix(WHISPER_PREFIX).replace("--", "/")
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        fetched = Path(tmp) / folder
        fetch(size, fetched)
        if not (fetched / "model.bin").is_file():
            raise RuntimeError(f"the whisper download for {size!r} has no model.bin")
        fetched.rename(target)
    return target


def _fetch_whisper(size: str, dest: Path) -> None:
    try:
        from faster_whisper import download_model as fetch
    except ImportError as exc:
        raise RuntimeError(f"faster-whisper is not installed ({exc}); run: pip install the packages in voice_in's module.toml") from exc
    log.info("downloading whisper %s", size)
    fetch(size, output_dir=str(dest))


def extract(archive: Path, dest: Path) -> None:
    """Extract a tar archive with tarfile's safe `data` filter (no paths outside `dest`, no links out, no devices)."""
    with tarfile.open(archive, "r:*") as tar:
        tar.extractall(dest, filter="data")


def _fetch(url: str, dest: Path) -> None:
    log.info("downloading %s", url)
    with urllib.request.urlopen(url, timeout=60) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    log.info("downloaded %.0f MB", dest.stat().st_size / 1e6)
