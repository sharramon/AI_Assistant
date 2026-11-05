"""Imports a module's package fresh, so new code runs without restarting the app.

Generic: knows nothing about which modules exist. A module's package is the package its class
lives in (e.g. `assistant.modules.voice_in`); everything under it is dropped from `sys.modules`
and imported again. The shared parts every module holds (core, contracts, infra, app_kit) are
never reloaded: their classes must stay the same objects.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path
from types import ModuleType

from assistant.contracts import Module

# Packages whose classes are shared by every module. Reloading them (or anything inside them)
# would break isinstance checks and contract identity, so they still need a restart.
SHARED = ("assistant.core", "assistant.contracts", "assistant.infra", "app_kit")
# Parents of modules' packages: reloading one of these would reload every module at once.
PARENTS = ("assistant", "assistant.modules")


class LoadError(Exception):
    """The package can't be (re)loaded; the message says why in plain words."""


def package_of(cls: type) -> str:
    """The package a module class lives in."""
    name = cls.__module__
    module = sys.modules.get(name)
    if module is not None and hasattr(module, "__path__"):
        return name
    return name.rpartition(".")[0]


def check_reloadable(package: str) -> None:
    """Raise LoadError unless `package` is a module's own package (at least `a.b`, not shared code)."""
    if "." not in package or package in PARENTS:
        raise LoadError(f"{package or 'its code'!r} is not a module's own package, so it can't be reloaded")
    for shared in SHARED:
        if package == shared or package.startswith(f"{shared}."):
            raise LoadError(f"{package!r} is shared code ({shared}); changing it needs a restart")


def drop(package: str) -> dict[str, ModuleType]:
    """Remove `package` and its submodules from `sys.modules`; returns them for `restore`."""
    names = [n for n in sys.modules if n == package or n.startswith(f"{package}.")]
    removed = {n: sys.modules.pop(n) for n in names}
    for module in removed.values():
        for folder in getattr(module, "__path__", ()):
            # Compiled caches are checked by source mtime and size only; drop them so an edit
            # within the same second is never missed. They're rebuilt on import.
            shutil.rmtree(Path(folder) / "__pycache__", ignore_errors=True)
    return removed


def restore(package: str, removed: dict[str, ModuleType]) -> None:
    """Put back what `drop` removed, discarding anything imported since."""
    drop(package)
    sys.modules.update(removed)
    parent, _, child = package.rpartition(".")
    if parent in sys.modules and package in removed:
        setattr(sys.modules[parent], child, removed[package])


def import_fresh(package: str) -> ModuleType:
    """Import `package` from source. Translates a missing contract into a 'needs a restart' error."""
    importlib.invalidate_caches()
    try:
        return importlib.import_module(package)
    except ImportError as exc:
        if (exc.name or "").startswith("assistant.contracts") or "assistant.contracts" in str(exc):
            raise LoadError(
                f"{package!r} needs a contract the running app doesn't have ({exc}); new contracts need a restart"
            ) from exc
        raise


def find_module_class(package: ModuleType, module_id: str | None = None) -> type[Module]:
    """The `Module` subclass defined in `package` (with manifest id `module_id`, if given)."""
    prefix = package.__name__
    found = {
        value
        for value in vars(package).values()
        if isinstance(value, type)
        and issubclass(value, Module)
        and getattr(value, "manifest", None) is not None
        and (value.__module__ == prefix or value.__module__.startswith(f"{prefix}."))
        and (module_id is None or value.manifest.id == module_id)
    }
    if len(found) != 1:
        what = f"module {module_id!r}" if module_id else "a module"
        raise LoadError(f"{prefix!r} must export exactly one class for {what}; found {len(found)}")
    return found.pop()
