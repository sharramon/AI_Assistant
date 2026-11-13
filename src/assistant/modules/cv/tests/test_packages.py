"""Every pip package cv's code imports is in its module.toml's `packages` (so a fresh environment gets it).

pypdf and mcp were installed by hand once and never listed (found 2026-11-13); this keeps it from happening again.
"""
import ast
import sys
import tomllib
from pathlib import Path

CV = Path(__file__).resolve().parents[1]
# The app's own packages (pyproject.toml) and the dev extra: not cv's to list.
APP_OWN = {"pydantic", "markdown", "pytest", "httpx", "pytest_asyncio"}
FIRST_PARTY = {"assistant", "app_kit", "tests"}
PIP_NAME = {"fitz": "pymupdf"}  # an import name that isn't its pip name


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names.add(node.module.split(".")[0])
    return names


def _local(folder: Path) -> set[str]:
    """Modules and packages beside a file, imported by their own name (the CV Tool's own files)."""
    return {p.stem for p in folder.glob("*.py")} | {p.name for p in folder.iterdir() if (p / "__init__.py").is_file()}


def test_every_imported_package_is_listed() -> None:
    listed = {p.split("<")[0].split(">")[0].split("=")[0].split("[")[0].strip().lower()
              for p in tomllib.loads((CV / "module.toml").read_text(encoding="utf-8"))["packages"]}  # fmt: skip
    apps = {p.name for p in (CV / "app").iterdir() if p.is_dir()}
    missing = {}
    for path in CV.rglob("*.py"):
        if "workspace" in path.relative_to(CV).parts or "__pycache__" in path.parts:
            continue
        own = FIRST_PARTY | apps | _local(path.parent) | APP_OWN | set(sys.stdlib_module_names)
        for name in _imports(path) - own:
            if PIP_NAME.get(name, name).lower() not in listed:
                missing.setdefault(PIP_NAME.get(name, name), []).append(path.relative_to(CV).as_posix())
    assert not missing, f"cv imports packages its module.toml doesn't list: {missing}"
