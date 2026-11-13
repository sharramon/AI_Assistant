"""Finds the modules by folder, and imports a module's package fresh, so new code runs
without restarting the app.

Generic: knows nothing about which modules exist. A module is its folder under
`assistant.modules`, named with its manifest id. A module's package is the package its class
lives in (e.g. `assistant.modules.voice_in`); on a reload everything under it is dropped from
`sys.modules` and imported again. The shared parts every module holds (core, contracts, infra,
app_kit) are never reloaded: their classes must stay the same objects.
"""

from __future__ import annotations

import dataclasses
import importlib
import logging
import pkgutil
import shutil
import sys
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

from assistant.contracts import ModuleProtocol

log = logging.getLogger(__name__)

# Where the modules live: one sub-folder (package) per module, named with its manifest id.
MODULES_PACKAGE = "assistant.modules"
# A module's own config defaults, in its folder; its `[modules.<id>]` section in the app's config
# is merged over them.
MODULE_DEFAULTS = "module.toml"

# A module's companion app lives in its folder as `app/<the app's package>/` (`app/` is no package),
# so the app keeps its own import name and never imports the module (`add_app_folders`).
APP_FOLDER = "app"

# Packages whose classes are shared by every module. Reloading them (or anything inside them)
# would break isinstance checks and contract identity, so they still need a restart.
SHARED = ("assistant.core", "assistant.contracts", "assistant.infra", "assistant.testkit", "app_kit")
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


def module_folder(cls: type) -> Path | None:
    """The folder of the package a module class lives in (where its own config defaults and docs are),
    None if it can't be found (a class defined in `__main__`, say)."""
    try:
        package = sys.modules.get(package_of(cls)) or importlib.import_module(package_of(cls))
    except (ImportError, ValueError):
        return None
    file = getattr(package, "__file__", None)
    if file:
        return Path(file).parent
    paths = list(getattr(package, "__path__", ()))
    return Path(paths[0]) if paths else None


def module_defaults(cls: type) -> dict[str, Any]:
    """The module's own config defaults: `module.toml` in its folder, read fresh each time (so a reload
    picks up new defaults). {} if it has none; an unreadable file is logged and counts as none."""
    folder = module_folder(cls)
    path = folder / MODULE_DEFAULTS if folder else None
    if path is None or not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("Ignoring %s: %s", path, exc)
        return {}


#: The `module.toml` keys the core puts on the manifest, each a list of strings, with what they hold.
MANIFEST_KEYS = {"needs": "module ids", "packages": "pip requirements"}


def apply_module_toml(cls: type[ModuleProtocol]) -> type[ModuleProtocol]:
    """Put the manifest keys (`MANIFEST_KEYS`) from the module's `module.toml` on its manifest:
    `needs = [...]` (`Manifest.needs`) and `packages = [...]` (`Manifest.packages`), so the module
    declares them in one place. A key the file doesn't have leaves that field as it is.
    Returns `cls`; LoadError if a value isn't a list of strings, or the manifest refuses it."""
    defaults = module_defaults(cls)
    found = {}
    for key, what in MANIFEST_KEYS.items():
        if key not in defaults:
            continue
        value = defaults[key]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise LoadError(f"{cls.manifest.id!r}: {key} in its {MODULE_DEFAULTS} must be a list of {what}, "
                            f"not {value!r}")  # fmt: skip
        found[key] = tuple(value)
    if found:
        try:
            cls.manifest = dataclasses.replace(cls.manifest, **found)
        except ValueError as exc:
            raise LoadError(str(exc)) from exc
    return cls


def app_folders(root: str = MODULES_PACKAGE) -> list[Path]:
    """Every module's `app/` folder under `root`, found by folder (no names), sorted: the folders
    that hold the modules' companion apps' packages."""
    found = []
    for base in importlib.import_module(root).__path__:
        found += [p for p in Path(base).glob(f"*/{APP_FOLDER}") if p.is_dir() and not p.parent.name.startswith("_")]
    return sorted(p.resolve() for p in found)


def add_app_folders(root: str = MODULES_PACKAGE) -> list[Path]:
    """Put every module's `app/` folder on `sys.path` (appended, once each), so a companion app's
    package imports by its own name (`cv_tool`). Called at startup by `find_modules`, before a
    reload or add (`import_fresh`), and by the test setup. Returns the folders added now."""
    present = {str(Path(p).resolve()).lower() for p in sys.path if p}
    added = [p for p in app_folders(root) if str(p).lower() not in present]
    sys.path.extend(str(p) for p in added)
    if added:
        importlib.invalidate_caches()
    return added


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
    """Import `package` from source. Translates a missing contract into a 'needs a restart' error.
    A new module's `app/` folder goes on the import path first (`add_app_folders`)."""
    add_app_folders()
    importlib.invalidate_caches()
    try:
        return importlib.import_module(package)
    except ImportError as exc:
        if (exc.name or "").startswith("assistant.contracts") or "assistant.contracts" in str(exc):
            raise LoadError(
                f"{package!r} needs a contract the running app doesn't have ({exc}); new contracts need a restart"
            ) from exc
        raise


def find_module_class(package: ModuleType, module_id: str | None = None) -> type[ModuleProtocol]:
    """The `ModuleProtocol` subclass defined in `package` (with manifest id `module_id`, if given)."""
    prefix = package.__name__
    found = {
        value
        for value in vars(package).values()
        if isinstance(value, type)
        and issubclass(value, ModuleProtocol)
        and getattr(value, "manifest", None) is not None
        and (value.__module__ == prefix or value.__module__.startswith(f"{prefix}."))
        and (module_id is None or value.manifest.id == module_id)
    }
    if len(found) != 1:
        what = f"module {module_id!r}" if module_id else "a module"
        raise LoadError(f"{prefix!r} must export exactly one class for {what}; found {len(found)}")
    return apply_module_toml(found.pop())


def check_folder(cls: type[ModuleProtocol], package: str, root: str = MODULES_PACKAGE) -> None:
    """Raise LoadError if a module folder under `root` isn't named with its module's id."""
    parent, _, folder = package.rpartition(".")
    if parent == root and cls.manifest.id != folder:
        raise LoadError(
            f"{package!r} holds the module {cls.manifest.id!r}; a module's folder must be named with its id"
        )


def find_modules(root: str = MODULES_PACKAGE) -> list[type[ModuleProtocol]]:
    """Every module under `root`, sorted by folder: one per sub-folder with an `__init__.py`
    that exports exactly one `ModuleProtocol` class whose id is the folder's name.

    A folder that fails to import, has no module class (or two), or a different id is skipped
    and logged; the rest still load. Folders starting with `_` are ignored. Every module's `app/`
    folder goes on the import path first (`add_app_folders`).
    """
    add_app_folders(root)
    found = []
    for info in sorted(pkgutil.iter_modules(importlib.import_module(root).__path__), key=lambda i: i.name):
        if not info.ispkg or info.name.startswith("_"):
            continue
        package = f"{root}.{info.name}"
        try:
            cls = find_module_class(importlib.import_module(package))
            check_folder(cls, package, root)
        except Exception as exc:
            log.warning("Skipping the module folder %s: %s", package, exc, exc_info=not isinstance(exc, LoadError))
            continue
        found.append(cls)
    return found
