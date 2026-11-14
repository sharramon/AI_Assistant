"""scripts/install_module_packages.py: it finds every module's `packages`, each once, and refuses a bad list."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def script():
    spec = importlib.util.spec_from_file_location(
        "install_module_packages", ROOT / "scripts" / "install_module_packages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(folder: Path, text: str) -> None:
    folder.mkdir(parents=True)
    (folder / "module.toml").write_text(text, encoding="utf-8")


def test_packages_from_every_root_each_once(tmp_path):
    write(tmp_path / "a" / "one", 'packages = ["fastapi>=0.110", "uvicorn"]')
    write(tmp_path / "a" / "two", "packages = []")
    write(tmp_path / "a" / "three", 'needs = ["one"]')
    write(tmp_path / "b" / "four", 'packages = ["uvicorn", "mcp>=2"]')
    found = script().module_packages([tmp_path / "a", tmp_path / "b"])
    assert found == ["fastapi>=0.110", "uvicorn", "mcp>=2"]


def test_a_bad_packages_list_is_refused(tmp_path):
    write(tmp_path / "one", 'packages = "fastapi"')
    with pytest.raises(SystemExit, match="packages must be a list"):
        script().module_packages([tmp_path])


def test_the_repo_modules_packages_are_found():
    """The packages CI installs include the ones the cv and voice_in tests import."""
    found = script().module_packages([ROOT / "src" / "assistant" / "modules"])
    for name in ("httpx2", "mcp", "fastapi", "uvicorn"):
        assert any(p.startswith(name) for p in found), name
