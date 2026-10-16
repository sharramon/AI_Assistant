"""Initializes, starts, and stops modules in dependency order."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from assistant.contracts import Manifest, Module
from assistant.core.context import ScopedContext
from assistant.core.registry import StartupError

log = logging.getLogger(__name__)


class LifecycleManager:
    def __init__(
        self,
        modules: list[type[Module]],
        make_context: Callable[[Manifest], ScopedContext],
        stop_timeout: float = 5.0,
    ):
        self._modules = modules
        self._make_context = make_context
        self._stop_timeout = stop_timeout
        self._active: list[tuple[Module, ScopedContext]] = []
        self._failed: set[str] = set()

    async def start(self) -> None:
        """Init every module, then start every module, both in dependency order.

        A failing module is skipped unless it provides a contract that another
        module requires and nothing else provides, in which case StartupError
        is raised.
        """
        for cls in self._modules:
            ctx = self._make_context(cls.manifest)
            module = cls()
            try:
                await module.init(ctx)
            except Exception as exc:
                ctx.close()
                self._skip(cls.manifest, "initialize", exc)
                continue
            self._active.append((module, ctx))

        for module, ctx in list(self._active):
            try:
                await module.start()
            except Exception as exc:
                self._active.remove((module, ctx))
                await self._stop_one(module, ctx)
                self._skip(module.manifest, "start", exc)
        log.info("Running modules: %s", ", ".join(m.manifest.id for m, _ in self._active) or "none")

    async def stop(self) -> None:
        """Stop active modules in reverse order, then remove their registrations."""
        while self._active:
            await self._stop_one(*self._active.pop())

    async def _stop_one(self, module: Module, ctx: ScopedContext) -> None:
        try:
            async with asyncio.timeout(self._stop_timeout):
                await module.stop()
        except TimeoutError:
            log.warning("%s did not stop within %ss", module.manifest.id, self._stop_timeout)
        except Exception:
            log.exception("%s raised while stopping", module.manifest.id)
        finally:
            ctx.close()

    def _skip(self, manifest: Manifest, phase: str, exc: Exception) -> None:
        self._failed.add(manifest.id)
        healthy = [cls.manifest for cls in self._modules if cls.manifest.id not in self._failed]
        for contract in manifest.provides:
            needed = any(contract in m.requires for m in healthy)
            replaced = any(contract in m.provides for m in healthy)
            if needed and not replaced:
                raise StartupError(
                    f"{manifest.id!r} failed to {phase}, and other modules require its {contract.__name__}"
                ) from exc
        log.error("%s failed to %s; skipping it", manifest.id, phase, exc_info=exc)
