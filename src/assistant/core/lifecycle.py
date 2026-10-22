"""Initializes, starts, and stops modules: all at once at startup and shutdown, or one at a time at runtime."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

from assistant.contracts import Contract, Manifest, Module, ModuleInfo, ModuleState, Result
from assistant.core.container import is_shared_contract
from assistant.core.context import ScopedContext
from assistant.core.registry import StartupError

log = logging.getLogger(__name__)


class LifecycleManager:
    def __init__(
        self,
        available: Sequence[type[Module]],
        start_order: list[type[Module]],
        make_context: Callable[[Manifest], ScopedContext],
        stop_timeout: float = 5.0,
        on_change: Callable[[str, ModuleState], None] | None = None,
    ):
        """`available` is every module that may run; `start_order` the validated ones active at startup."""
        self._classes = {cls.manifest.id: cls for cls in available}
        self._start_order = start_order
        self._make_context = make_context
        self._stop_timeout = stop_timeout
        self._on_change = on_change
        self._states = {module_id: ModuleState.INACTIVE for module_id in self._classes}
        # Insertion order is activation order, so stopping in reverse stops dependents first.
        self._active: dict[str, tuple[Module, ScopedContext]] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Init every startup module, then start every one, both in dependency order.

        A failing module is skipped unless it provides a contract that another
        module requires and nothing else provides, in which case StartupError
        is raised.
        """
        async with self._lock:
            initialized: list[tuple[Module, ScopedContext]] = []
            for cls in self._start_order:
                self._set(cls.manifest.id, ModuleState.STARTING)
                ctx = self._make_context(cls.manifest)
                module = cls()
                try:
                    await module.init(ctx)
                except Exception as exc:
                    ctx.close()
                    self._skip(cls.manifest, "initialize", exc)
                    continue
                initialized.append((module, ctx))
                self._active[cls.manifest.id] = (module, ctx)

            for module, ctx in initialized:
                try:
                    await module.start()
                except Exception as exc:
                    del self._active[module.manifest.id]
                    await self._stop_one(module, ctx)
                    self._skip(module.manifest, "start", exc)
                    continue
                self._set(module.manifest.id, ModuleState.ACTIVE)
            log.info("Running modules: %s", ", ".join(self._active) or "none")

    async def stop(self) -> None:
        """Stop active modules in reverse activation order, then remove their registrations."""
        async with self._lock:
            while self._active:
                module_id, (module, ctx) = self._active.popitem()
                self._set(module_id, ModuleState.STOPPING)
                await self._stop_one(module, ctx)
                self._set(module_id, ModuleState.INACTIVE)

    def modules(self) -> list[ModuleInfo]:
        """Every available module and its current state."""
        return [
            ModuleInfo(
                id=module_id,
                state=self._states[module_id],
                provides=tuple(c.__name__ for c in cls.manifest.provides),
                requires=tuple(c.__name__ for c in cls.manifest.requires),
            )
            for module_id, cls in self._classes.items()
        ]

    async def activate(self, module_id: str) -> Result:
        """Activate a module at runtime, first activating the sole provider of each contract it requires."""
        async with self._lock:
            return await self._activate(module_id, ())

    async def deactivate(self, module_id: str, with_dependents: bool = False) -> Result:
        """Deactivate a module at runtime. Refused while an active module requires it, unless `with_dependents`."""
        async with self._lock:
            return await self._deactivate(module_id, with_dependents)

    async def _activate(self, module_id: str, chain: tuple[str, ...]) -> Result:
        cls = self._classes.get(module_id)
        if cls is None:
            return Result.invalid_arguments(f"No module called {module_id!r}")
        if module_id in self._active:
            return Result.ok()
        if module_id in chain:
            return Result.failed(f"Circular dependency: {' -> '.join((*chain, module_id))}")

        manifest = cls.manifest
        for contract in (*manifest.provides, *manifest.requires, *manifest.optional):
            if not is_shared_contract(contract):
                return Result.failed(f"{module_id!r} lists {contract!r}, which is not a contract from assistant.contracts")
        for contract in manifest.provides:
            other = self._active_provider(contract)
            if not contract.multiple and other:
                return Result.failed(f"{other!r} already provides {contract.__name__}; deactivate it first")

        for contract in manifest.requires:
            if self._active_provider(contract):
                continue
            candidates = [c.manifest.id for c in self._classes.values() if contract in c.manifest.provides]
            if not candidates:
                return Result.not_available(f"{module_id!r} requires {contract.__name__}, which no module provides")
            if len(candidates) > 1:
                return Result.failed(
                    f"{module_id!r} requires {contract.__name__}; activate one of {', '.join(candidates)} first"
                )
            result = await self._activate(candidates[0], (*chain, module_id))
            if not result.is_ok:
                return Result.failed(f"{module_id!r} requires {contract.__name__}: {result.error}")

        self._set(module_id, ModuleState.STARTING)
        ctx = self._make_context(manifest)
        module = cls()
        try:
            await module.init(ctx)
        except Exception as exc:
            ctx.close()
            return self._fail(module_id, "initialize", exc)
        try:
            await module.start()
        except Exception as exc:
            await self._stop_one(module, ctx)
            return self._fail(module_id, "start", exc)
        self._active[module_id] = (module, ctx)
        self._set(module_id, ModuleState.ACTIVE)
        log.info("Activated %s", module_id)
        return Result.ok()

    async def _deactivate(self, module_id: str, with_dependents: bool) -> Result:
        if module_id not in self._classes:
            return Result.invalid_arguments(f"No module called {module_id!r}")
        if module_id not in self._active:
            return Result.ok()

        dependents = self._dependents(module_id)
        if dependents and not with_dependents:
            return Result.failed(f"{module_id!r} is required by {', '.join(dependents)}; deactivate them first")
        for dependent in reversed(dependents):
            await self._deactivate(dependent, True)

        module, ctx = self._active.pop(module_id)
        self._set(module_id, ModuleState.STOPPING)
        await self._stop_one(module, ctx)
        self._set(module_id, ModuleState.INACTIVE)
        log.info("Deactivated %s", module_id)
        return Result.ok()

    def _active_provider(self, contract: type[Contract], excluding: str | None = None) -> str | None:
        for module_id in self._active:
            if module_id != excluding and contract in self._classes[module_id].manifest.provides:
                return module_id
        return None

    def _dependents(self, module_id: str) -> list[str]:
        """Active modules that require something only `module_id` provides, in activation order."""
        provided = self._classes[module_id].manifest.provides
        return [
            other
            for other in self._active
            if other != module_id
            and any(
                contract in provided and not self._active_provider(contract, excluding=module_id)
                for contract in self._classes[other].manifest.requires
            )
        ]

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

    def _fail(self, module_id: str, phase: str, exc: Exception) -> Result:
        self._set(module_id, ModuleState.FAILED)
        log.error("%s failed to %s", module_id, phase, exc_info=exc)
        return Result.failed(f"{module_id!r} failed to {phase}: {exc}")

    def _skip(self, manifest: Manifest, phase: str, exc: Exception) -> None:
        self._set(manifest.id, ModuleState.FAILED)
        healthy = [cls.manifest for cls in self._start_order if self._states[cls.manifest.id] is not ModuleState.FAILED]
        for contract in manifest.provides:
            needed = any(contract in m.requires for m in healthy)
            replaced = any(contract in m.provides for m in healthy)
            if needed and not replaced:
                raise StartupError(
                    f"{manifest.id!r} failed to {phase}, and other modules require its {contract.__name__}"
                ) from exc
        log.error("%s failed to %s; skipping it", manifest.id, phase, exc_info=exc)

    def _set(self, module_id: str, state: ModuleState) -> None:
        self._states[module_id] = state
        if self._on_change:
            self._on_change(module_id, state)
