"""Loads the main app's TOML configuration from `config/`: the core's settings, which modules are on,
and your own choices, one file per module. Built on `app_kit.load_layered` and `merge`."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from app_kit import load_layered, local_path, merge

# Files in config/ that are not one module's choices: the core's settings, the old local overrides,
# the on/off list, the saved grants, and the voice service's own settings.
NOT_MODULE_FILES = frozenset({"default", "local", "modules", "permissions", "voice_service"})


def load_config(config_dir: str | Path | None = None) -> dict[str, Any]:
    """The app's config, merged in this order (each over the one before, key by key):

    1. `default.toml`: the core's settings (`[core]`, `[logging]`); no module's defaults.
    2. `modules.toml` then `modules.local.toml` into `[modules]`: which modules are on (`enabled`).
    3. For each module id: `<id>.toml` then `<id>.local.toml` into `[modules.<id>]`: your choices for
       it (top-level keys are its settings). Either file may be missing.
    4. `local.toml` last, as before (`[modules] enabled`, `[modules.<id>]`, anything else).

    A module's own defaults (its `module.toml`) go under all of these: the core merges them in
    (`App._config_of`). The directory is `config_dir`, else ASSISTANT_CONFIG_DIR, else `./config`.
    """
    directory = Path(config_dir or os.environ.get("ASSISTANT_CONFIG_DIR", "config"))
    config = _read(directory / "default.toml")
    modules = merge(config.get("modules", {}), _layer(directory, "modules"))
    for module_id in module_config_ids(directory):
        modules = merge(modules, {module_id: _layer(directory, module_id)})
    config["modules"] = modules
    local = directory / "local.toml"
    return merge(config, _read(local)) if local.exists() else config


def module_config_ids(directory: str | Path) -> list[str]:
    """The module ids with a choices file in `directory` (`<id>.toml` or `<id>.local.toml`),
    leaving out the files that are not a module's (`NOT_MODULE_FILES`)."""
    names = {p.name.removesuffix(".toml").removesuffix(".local") for p in Path(directory).glob("*.toml")}
    return sorted(n for n in names if n.isidentifier() and n not in NOT_MODULE_FILES)


def _layer(directory: Path, name: str) -> dict[str, Any]:
    """`<name>.toml` with `<name>.local.toml` over it; {} when neither exists."""
    base = directory / f"{name}.toml"
    if base.exists():
        return load_layered(base)
    local = local_path(base)
    return _read(local) if local.exists() else {}


def _read(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)
