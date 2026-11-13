"""Initializes, starts, and stops modules: all at once at startup and shutdown, or one at a time at runtime."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import Any

from assistant.contracts import (
    AccessDenied,
    AccessPending,
    Contract,
    Manifest,
    Menu,
    ModuleInfo,
    ModuleProtocol,
    ModuleState,
    Result,
)
from assistant.core import loader
from assistant.core.container import allows_another, is_shared_contract
from assistant.core.context import ScopedContext
from assistant.core.registry import StartupError

log = logging.getLogger(__name__)


class LifecycleManager:
    def __init__(
        self,
        available: Sequence[type[ModuleProtocol]],
        start_order: list[type[ModuleProtocol]],
        make_context: Callable[..., ScopedContext],  # (manifest, handover=None)
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
        self._active: dict[str, tuple[ModuleProtocol, ScopedContext]] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Init every startup module, then start every one, both in dependency order.

        A failing module is skipped unless it provides a contract that another
        module requires and nothing else provides, in which case StartupError
        is raised.
        """
        async with self._lock:
            initialized: list[tuple[ModuleProtocol, ScopedContext]] = []
            for cls in self._start_order:
                self._set(cls.manifest.id, ModuleState.STARTING)
                try:
                    self._check_needs(cls.manifest)
                    module, ctx = await self._init_one(cls)
                except Exception as exc:
                    self._skip(cls.manifest, "initialize", exc)
                    continue
                initialized.append((module, ctx))
                self._active[cls.manifest.id] = (module, ctx)

            for module, ctx in initialized:
                try:
                    self._check_needs(module.manifest)
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
                description=cls.manifest.description,
                provides=tuple(c.__name__ for c in cls.manifest.provides),
                requires=tuple(c.__name__ for c in cls.manifest.requires),
            )
            for module_id, cls in self._classes.items()
        ]

    def module_class(self, module_id: str) -> type:
        """The module's current class (on or off; the new one after a reload). KeyError if unknown."""
        return self._classes[module_id]

    def menu(self, module_id: str) -> Menu | None:
        """The module's `Menu`, read from its current class (on or off). KeyError if unknown."""
        return self._classes[module_id].menu

    async def activate(self, module_id: str) -> Result:
        """Activate a module at runtime, first activating the sole provider of each contract it requires."""
        async with self._lock:
            return await self._activate(module_id, ())

    async def deactivate(self, module_id: str, with_dependents: bool = False) -> Result:
        """Deactivate a module at runtime. Refused while an active module requires it, unless `with_dependents`."""
        async with self._lock:
            return await self._deactivate(module_id, with_dependents)

    async def reload(self, module_id: str, now: bool = False, idle_timeout: float = 300.0) -> Result:
        """Swap a module's code: stop it (and modules that require it), import its package fresh,
        start the new code with what the old instance exported. If the new code fails, the old
        code is put back and started. Waits while the module is busy, unless `now`."""
        if not now and (reason := await self._wait_idle(module_id, idle_timeout)):
            return Result.failed(
                f"{module_id!r} is still busy ({reason}) after {idle_timeout:g}s; reload with now to cut in"
            )
        async with self._lock:
            old_cls = self._classes.get(module_id)
            if old_cls is None:
                return Result.invalid_arguments(f"No module called {module_id!r}")
            package = loader.package_of(old_cls)
            try:
                loader.check_reloadable(package)
            except loader.LoadError as exc:
                return Result.failed(str(exc))

            was_active = module_id in self._active
            before = list(self._active)
            state = None
            if was_active:
                for dependent in reversed(self._dependents(module_id)):
                    await self._deactivate(dependent, True)
                module, ctx = self._active.pop(module_id)
                self._set(module_id, ModuleState.RELOADING)
                state = self._export(module)
                await self._stop_one(module, ctx)
            else:
                self._set(module_id, ModuleState.RELOADING)
            stopped = [m for m in before if m not in self._active and m != module_id]

            removed = loader.drop(package)
            try:
                self._classes[module_id] = loader.find_module_class(loader.import_fresh(package), module_id)
            except Exception as exc:
                log.error("Reloading %s failed; keeping the old code", module_id, exc_info=exc)
                return await self._roll_back(module_id, old_cls, package, removed, was_active, stopped, exc, state)

            if was_active:
                result = await self._activate(module_id, (), state)
                if not result.is_ok:
                    return await self._roll_back(
                        module_id, old_cls, package, removed, True, stopped, result.error, state
                    )
                await self._restart(stopped)
            else:
                self._set(module_id, ModuleState.INACTIVE)
            log.info("Reloaded %s", module_id)
            return Result.ok()

    async def add(self, package: str, activate: bool = True) -> Result:
        """Load a module that wasn't available at launch. Result value: its id."""
        async with self._lock:
            try:
                loader.check_reloadable(package)
                if any(loader.package_of(cls) == package for cls in self._classes.values()):
                    raise loader.LoadError(f"{package!r} is already loaded; use ReloadModule")
                loader.drop(package)
                cls = loader.find_module_class(loader.import_fresh(package))
                loader.check_folder(cls, package)
            except Exception as exc:
                log.error("Adding %s failed", package, exc_info=exc)
                return Result.failed(f"Couldn't load {package!r}: {exc}")
            module_id = cls.manifest.id
            if module_id in self._classes:
                return Result.failed(f"A module called {module_id!r} already exists")
            self._classes[module_id] = cls
            self._set(module_id, ModuleState.INACTIVE)
            log.info("Added %s from %s", module_id, package)
            if activate:
                result = await self._activate(module_id, ())
                if not result.is_ok:
                    return result
            return Result.ok(module_id)

    async def remove(self, module_id: str, enabled: Sequence[str] = ()) -> Result:
        """Take a module out of this run: off if it's on, then out of the module list (until `add`).
        Refused while another module needs it: an active one (`needs`, or a sole provider it
        requires), or one in `enabled` whose `needs` lists it. Its package stays imported; `add`
        imports it fresh."""
        async with self._lock:
            if module_id not in self._classes:
                return Result.invalid_arguments(f"No module called {module_id!r}")
            needers = self._dependents(module_id) if module_id in self._active else []
            needers += [
                other
                for other in enabled
                if other != module_id
                and other not in needers
                and other in self._classes
                and module_id in self._classes[other].manifest.needs
            ]
            if needers:
                return Result.failed(
                    f"{module_id!r} is needed by {', '.join(needers)}; remove or turn them off first"
                )
            result = await self._deactivate(module_id, False)
            if not result.is_ok:
                return result
            del self._classes[module_id]
            del self._states[module_id]
            log.info("Removed %s from this run", module_id)
            return Result.ok()

    async def _roll_back(self, module_id, old_cls, package, removed, was_active, stopped, error, state) -> Result:
        loader.restore(package, removed)
        self._classes[module_id] = old_cls
        message = f"New code for {module_id!r} failed: {error}"
        if was_active:
            back = await self._activate(module_id, (), state)
            await self._restart(stopped)
            if back.is_ok:
                return Result.failed(f"{message}; the old code is running again")
            return Result.failed(f"{message}; the old code failed too: {back.error}")
        self._set(module_id, ModuleState.INACTIVE)
        return Result.failed(message)

    async def _wait_idle(self, module_id: str, timeout: float) -> str | None:
        """Wait until the active module's `busy()` is None; returns its last reason on timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            entry = self._active.get(module_id)
            reason = self._ask(entry[0], "busy") if entry else None
            if not reason or loop.time() >= deadline:
                return reason
            await asyncio.sleep(0.2)

    def _export(self, module: ModuleProtocol) -> Any:
        return self._ask(module, "export_state")

    @staticmethod
    def _ask(module: ModuleProtocol, hook: str) -> Any:
        """Call a module's `busy` or `export_state`; a failing hook counts as None."""
        try:
            return getattr(module, hook)()
        except Exception:
            log.exception("%s.%s raised; treating it as None", module.manifest.id, hook)
            return None

    async def _restart(self, module_ids: list[str]) -> None:
        for other in module_ids:
            result = await self._activate(other, ())
            if not result.is_ok:
                log.error("Couldn't restart %s after a reload: %s", other, result.error)

    async def _activate(self, module_id: str, chain: tuple[str, ...], handover: Any = None) -> Result:
        cls = self._classes.get(module_id)
        if cls is None:
            return Result.invalid_arguments(f"No module called {module_id!r}")
        if module_id in self._active:
            return Result.ok()
        if module_id in chain:
            return Result.failed(f"Circular dependency: {' -> '.join((*chain, module_id))}")

        manifest = cls.manifest
        for contract in (*manifest.provides, *manifest.requires, *manifest.optional, *manifest.uses):
            if not is_shared_contract(contract):
                return Result.failed(f"{module_id!r} lists {contract!r}, which is not a contract from assistant.contracts")
        for contract in manifest.provides:
            other = self._active_provider(contract)
            if not allows_another(contract, other):
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

        for needed in manifest.needs:  # the modules it needs, by id: turned on first
            if needed not in self._classes:
                return Result.not_available(f"{module_id!r} needs the module {needed!r}, which doesn't exist")
            result = await self._activate(needed, (*chain, module_id))
            if not result.is_ok:
                return Result.failed(f"{module_id!r} needs {needed!r}: {result.error}")

        self._set(module_id, ModuleState.STARTING)
        try:
            module, ctx = await self._init_one(cls, handover)
        except Exception as exc:
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

    async def _init_one(self, cls: type[ModuleProtocol], handover: Any = None) -> tuple[ModuleProtocol, ScopedContext]:
        """The one init path, at startup and at runtime: a context (with what the old copy
        exported, on a reload), a new instance, `init`, its menu linked. On failure the context
        is closed and the error raised for the caller to report."""
        ctx = self._make_context(cls.manifest, handover)
        module = cls()
        try:
            await module.init(ctx)
            ctx.link_menu(module)
        except Exception:
            ctx.close()
            raise
        return module, ctx

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
        """Active modules that need `module_id` (`needs`) or require something only it provides,
        in activation order."""
        provided = self._classes[module_id].manifest.provides
        return [
            other
            for other in self._active
            if other != module_id
            and (
                module_id in self._classes[other].manifest.needs
                or any(
                    contract in provided and not self._active_provider(contract, excluding=module_id)
                    for contract in self._classes[other].manifest.requires
                )
            )
        ]

    def _check_needs(self, manifest: Manifest) -> None:
        """At startup: raise if a module it needs didn't come up (failed or skipped), so it's skipped too."""
        missing = [needed for needed in manifest.needs if needed not in self._active]
        if missing:
            raise RuntimeError(f"it needs {', '.join(map(repr, missing))}, which didn't start")

    async def _stop_one(self, module: ModuleProtocol, ctx: ScopedContext) -> None:
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
        _log_failure(f"{module_id} failed to {phase}", exc)
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
        _log_failure(f"{manifest.id} failed to {phase}; skipping it", exc)

    def _set(self, module_id: str, state: ModuleState) -> None:
        self._states[module_id] = state
        if self._on_change:
            self._on_change(module_id, state)


def _log_failure(what: str, exc: Exception) -> None:
    """A module that waits for (or was denied) its access card isn't broken: one info line."""
    if isinstance(exc, (AccessPending, AccessDenied)):
        log.info("%s: %s", what, exc)
    else:
        log.error("%s", what, exc_info=exc)
