"""Finding modules by folder: a module is its folder, named with its manifest id."""

import logging
import sys
import uuid
from pathlib import Path

import pytest

from assistant.core import App, find_modules
from assistant.core.loader import LoadError, check_folder, find_module_class
from assistant.testkit import make_config

ROOT = Path(__file__).resolve().parents[1]

GOOD = """
from assistant.contracts import Manifest, ModuleProtocol


class Good(ModuleProtocol):
    manifest = Manifest(id={id!r}, description="A module found by its folder")

    async def init(self, ctx):
        pass
"""


@pytest.fixture
def root(tmp_path):
    """A throwaway modules folder `found_<hex>` with a `folder(name, code)` helper."""
    top = f"found_{uuid.uuid4().hex[:8]}"
    (tmp_path / top).mkdir()
    (tmp_path / top / "__init__.py").write_text("")

    def folder(name, code):
        (tmp_path / top / name).mkdir()
        (tmp_path / top / name / "__init__.py").write_text(code)

    sys.path.insert(0, str(tmp_path))
    yield top, folder
    sys.path.remove(str(tmp_path))
    for name in [n for n in sys.modules if n == top or n.startswith(f"{top}.")]:
        del sys.modules[name]


def test_finds_the_module_in_each_folder_and_skips_bad_ones(root, caplog):
    top, folder = root
    folder("good", GOOD.format(id="good"))
    folder("broken", "raise RuntimeError('boom')\n")
    folder("empty", "")
    folder("misnamed", GOOD.format(id="other_name"))
    folder("_private", GOOD.format(id="private"))

    with caplog.at_level(logging.WARNING, logger="assistant.core.loader"):
        found = find_modules(top)

    assert [cls.manifest.id for cls in found] == ["good"]
    skipped = " ".join(record.getMessage() for record in caplog.records)
    for name in ("broken", "empty", "misnamed"):
        assert f"{top}.{name}" in skipped
    assert "_private" not in skipped


def test_a_folder_must_be_named_with_its_module_id(root):
    top, folder = root
    folder("misnamed", GOOD.format(id="other_name"))
    import importlib

    cls = find_module_class(importlib.import_module(f"{top}.misnamed"))
    with pytest.raises(LoadError, match="named with its id"):
        check_folder(cls, f"{top}.misnamed", top)
    check_folder(cls, "elsewhere.misnamed", top)  # outside the modules folder: any name


def test_every_real_module_folder_is_found():
    folders = sorted(
        p.name for p in (ROOT / "src" / "assistant" / "modules").iterdir() if (p / "__init__.py").is_file()
    )
    assert [cls.manifest.id for cls in find_modules()] == folders


def test_the_app_runs_from_what_it_found():
    App(find_modules(), make_config("echo_orchestrator", "console_io"))  # validates without raising
