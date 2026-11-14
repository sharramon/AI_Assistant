"""Install every module's own pip packages: the `packages = [...]` list in each module's `module.toml`
(`Manifest.packages`), for every folder holding modules (the repo's, then the outside ones
`[core] module_folders` names), into the Python that runs this script.

The app's own packages are in `pyproject.toml`; install those first (`pip install -e ".[dev]"`).
CI runs this after that, so every module's tests can import what the module needs.

    python scripts/install_module_packages.py          # install them
    python scripts/install_module_packages.py --list   # only print them, one per line
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

MODULE_TOML = "module.toml"


def module_dirs() -> tuple[Path, ...]:
    """The folders holding module folders, as the app finds them (the same as `build_docs.module_dirs`)."""
    from assistant.core.loader import LoadError, add_module_folders, configured_module_folders
    from assistant.infra import load_config, module_roots

    try:
        add_module_folders(configured_module_folders(load_config()))
    except LoadError as exc:
        raise SystemExit(f"[core] module_folders: {exc}") from exc
    return tuple(module_roots())


def module_packages(roots: Iterable[Path]) -> list[str]:
    """Every `packages` entry of every `<root>/<id>/module.toml`, in folder order, each once.
    SystemExit naming the file if one can't be read or its `packages` isn't a list of strings."""
    found: list[str] = []
    for root in roots:
        for path in sorted(Path(root).glob(f"*/{MODULE_TOML}")):
            try:
                with path.open("rb") as f:
                    packages = tomllib.load(f).get("packages", [])
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise SystemExit(f"{path}: {exc}") from exc
            if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
                raise SystemExit(f"{path}: packages must be a list of pip requirements, not {packages!r}")
            found += [p for p in packages if p not in found]
    return found


def main(argv: list[str]) -> int:
    packages = module_packages(module_dirs())
    if "--list" in argv:
        print("\n".join(packages))
        return 0
    if not packages:
        print("No module packages to install.")
        return 0
    print("Installing the modules' packages:", ", ".join(packages), flush=True)
    return subprocess.call([sys.executable, "-m", "pip", "install", *packages])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
