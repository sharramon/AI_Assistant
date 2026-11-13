"""Selects the enabled modules and validates their dependency graph before anything starts."""

from __future__ import annotations

from collections.abc import Sequence

from assistant.contracts import Contract, ModuleProtocol
from assistant.core.container import allows_another, is_shared_contract
from assistant.core.loader import LoadError, apply_needs


class StartupError(Exception):
    """The configured modules can't be started together."""


def resolve_modules(available: Sequence[type[ModuleProtocol]], enabled: Sequence[str]) -> list[type[ModuleProtocol]]:
    """Return the enabled modules in start order: providers before the modules that use them, and
    needed modules (`Manifest.needs`, read from each `module.toml`) before the modules that need them.
    A needed module that isn't in `enabled` is added: turning a module on turns on what it needs.

    Raises StartupError for unknown or duplicate ids, a needed module that doesn't exist (named),
    non-shared contracts, missing required contracts, too many providers of a single-provider
    contract, or circular dependencies.
    """
    by_id: dict[str, type[ModuleProtocol]] = {}
    for cls in available:
        try:
            apply_needs(cls)
        except LoadError as exc:
            raise StartupError(str(exc)) from exc
        if cls.manifest.id in by_id:
            raise StartupError(f"Two modules use the id {cls.manifest.id!r}")
        by_id[cls.manifest.id] = cls

    unknown = [module_id for module_id in enabled if module_id not in by_id]
    if unknown:
        raise StartupError(f"Enabled modules not found: {', '.join(unknown)}")
    selected = [by_id[module_id] for module_id in dict.fromkeys(enabled)]
    for cls in selected:  # grows as needed modules are added, so their own needs are added too
        for needed in cls.manifest.needs:
            if needed not in by_id:
                raise StartupError(f"{cls.manifest.id!r} needs the module {needed!r}, which doesn't exist")
            if by_id[needed] not in selected:
                selected.append(by_id[needed])

    providers: dict[type[Contract], list[type[ModuleProtocol]]] = {}
    for cls in selected:
        m = cls.manifest
        for contract in (*m.provides, *m.requires, *m.optional, *m.uses):
            if not is_shared_contract(contract):
                raise StartupError(f"{m.id!r} lists {contract!r}, which is not a contract from assistant.contracts")
        for contract in m.provides:
            providers.setdefault(contract, []).append(cls)

    for contract, owners in providers.items():
        if not allows_another(contract, owners[1:]):
            ids = ", ".join(cls.manifest.id for cls in owners)
            raise StartupError(f"{contract.__name__} allows one provider but is provided by: {ids}")

    for cls in selected:
        for contract in cls.manifest.requires:
            if contract not in providers:
                raise StartupError(f"{cls.manifest.id!r} requires {contract.__name__}, which no enabled module provides")

    deps = {
        cls: {
            provider
            for contract in (*cls.manifest.requires, *cls.manifest.optional)
            for provider in providers.get(contract, [])
            if provider is not cls
        }
        | {by_id[needed] for needed in cls.manifest.needs}
        for cls in selected
    }
    order: list[type[ModuleProtocol]] = []
    remaining = list(selected)
    while remaining:
        ready = [cls for cls in remaining if deps[cls] <= set(order)]
        if not ready:
            ids = ", ".join(cls.manifest.id for cls in remaining)
            raise StartupError(f"Circular dependency among modules: {ids}")
        for cls in ready:
            order.append(cls)
            remaining.remove(cls)
    return order
