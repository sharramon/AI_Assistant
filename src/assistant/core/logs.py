"""The `ctx.logs` port: modules reach the launch's log folder and files through it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from assistant.contracts import ModuleLogs


class _Session(Protocol):
    """What the core needs from the log handler (`assistant.infra.LogSession`)."""

    def folder(self) -> Path: ...
    def sink(self, name: str) -> Any: ...


class SessionLogs(ModuleLogs):
    """`ModuleLogs` backed by the launch's `LogSession`, or by plain paths under `root`
    when the app runs without one (tests). One instance serves every module."""

    def __init__(self, session: _Session | None = None, root: str | Path = "logs"):
        self._session = session
        self._root = Path(root)

    def folder(self) -> Path:
        return Path(self._session.folder()) if self._session else self._root

    def sink(self, name: str) -> Any:
        return self._session.sink(name) if self._session else self._root / name
