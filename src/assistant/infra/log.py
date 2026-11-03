"""Logging setup, and the log handler that owns where one app launch's logs go."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO


def setup_logging(settings: dict[str, Any], extra: Sequence[logging.Handler] = ()) -> None:
    """Configure root logging from the `[logging]` config section.

    Logs go to `file` by default, not the terminal, so they don't interleave
    with console input/output. Set `stderr = true` to also log to the terminal.
    `extra` handlers (e.g. a `LogSession.handler`) are added with the same format.
    """
    handlers: list[logging.Handler] = list(extra)
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


def theme_slug(text: str, max_words: int = 5) -> str:
    """A folder-safe theme: lowercase ASCII words joined by hyphens, at most `max_words`."""
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    return "-".join(words[:max_words])


class LogSink:
    """One log file of a `LogSession`. Holds what's written in memory until the session's
    folder exists, then writes it there, and everything after it directly. Thread-safe."""

    def __init__(self) -> None:
        self._held: list[str] = []
        self._path: Path | None = None
        self._file: TextIO | None = None
        self._lock = threading.Lock()

    def write(self, text: str) -> None:
        with self._lock:
            if self._path is None:
                self._held.append(text)
            else:
                self._write(text)

    def _write(self, text: str) -> None:
        if self._file is None:
            self._file = self._path.open("a", encoding="utf-8")
        self._file.write(text)
        self._file.flush()

    def held(self) -> str:
        """What's been written while the folder didn't exist yet."""
        with self._lock:
            return "".join(self._held)

    def close(self) -> None:
        """Close the file. A later `write` opens it again."""
        with self._lock:
            if self._file:
                self._file.close()
                self._file = None

    def _open(self, path: Path) -> None:
        with self._lock:
            self._path = path
            if self._held:
                self._write("".join(self._held))
                self._held = []


class _SinkHandler(logging.Handler):
    """A logging handler writing to a `LogSink`; remembers the worst level it saw."""

    def __init__(self, sink: LogSink):
        super().__init__()
        self.sink = sink
        self.worst = logging.NOTSET

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.sink.write(self.format(record) + "\n")
            self.worst = max(self.worst, record.levelno)
        except Exception:
            self.handleError(record)


class LogSession:
    """Owns where one app launch's logs go: `root/<start time>_<theme>/`, created only once
    the first message has its theme. Until then everything is held in memory, so a launch
    without a chat leaves no folder.

    Writes nothing itself: the app log goes through `handler`, and transcripts are
    pointed at `sink(name)` by the composition root.
    """

    NO_CHAT = "no-chat.log"

    def __init__(self, root: str | Path = "logs", now: datetime | None = None, app_log: str = "assistant.log"):
        self.root = Path(root)
        self._stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
        self.path: Path | None = None
        self._sinks: dict[str, LogSink] = {}
        self.handler = _SinkHandler(self.sink(app_log))

    def sink(self, name: str) -> LogSink:
        """The sink for the log file `name` in the session folder (one per name)."""
        if name not in self._sinks:
            self._sinks[name] = LogSink()
            if self.path:
                self._sinks[name]._open(self.path / name)
        return self._sinks[name]

    def folder(self) -> Path:
        """The session folder once it exists, else the logs root."""
        return self.path or self.root

    def set_theme(self, text: str) -> None:
        """Create the session folder, named by start time and theme, and write what's been held.
        The first usable theme wins."""
        theme = theme_slug(text)
        if self.path or not theme:
            return
        path, n = self.root / f"{self._stamp}_{theme}", 1
        while path.exists():
            n += 1
            path = self.root / f"{self._stamp}-{n}_{theme}"
        path.mkdir(parents=True)
        self.path = path
        for name, sink in self._sinks.items():
            sink._open(path / name)

    def finish(self) -> Path | None:
        """Close the files. Without a chat, nothing is kept, unless the app log has a warning or
        an error: then that log is appended to `root/no-chat.log`. Never raises."""
        for sink in self._sinks.values():
            sink.close()
        if self.path or self.handler.worst < logging.WARNING:
            return self.path
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / self.NO_CHAT).open("a", encoding="utf-8") as file:
                file.write(f"--- {self._stamp}: no chat ---\n{self.handler.sink.held()}")
        except OSError:
            pass
        return None
