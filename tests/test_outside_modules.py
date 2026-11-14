"""Module layout step 2: add-ons in a folder outside the repo (`[core] module_folders`).

docs/next-steps/module-layout-step2-checklist.md. A fake add-on in a `tmp_path` folder (never the
repo's, never a real add-on moved) is found, its app imports, it starts, it's reloaded and added; its
agent's folder, its docs and the rule that add-ons don't assume they're in the repo are checked. A
module id in two folders is refused. Nothing configured: exactly today's folders.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import sys
import tomllib
import uuid
from pathlib import Path

import pytest

from assistant.contracts import AddModule, InvokeTool, ReloadModule
from assistant.core import App, LoadError, configured_module_folders, find_modules, loader
from assistant.infra import (
    MODULES_FOLDER,
    REPO_FOLDER,
    access_items,
    in_module_folder,
    module_folder,
    module_folder_of,
    module_roots,
)
from assistant.testkit import make_config

MODULE = '''
from assistant.contracts import IToolProvider, Manifest, ModuleProtocol, Result, ToolSpec
from {app} import FROM_APP

VERSION = {version!r}


class Probe(ModuleProtocol, IToolProvider):
    manifest = Manifest(id={id!r}, description="An add-on outside the repo", provides=(IToolProvider,))

    async def init(self, ctx):
        self.ctx = ctx
        ctx.provide(IToolProvider, self)

    def tools(self):
        return [ToolSpec(name={id!r} + ".version", description="Which code runs")]

    async def invoke(self, name, args):
        return Result.ok(f"{{VERSION}}-{{FROM_APP}}{{self.ctx.config.get('suffix', '')}}")
'''


def plant(folder: Path, module_id: str, version: str = "v1") -> Path:
    """A fake add-on `module_id` in `folder`: its code, its app/ package, module.toml and docs."""
    home = folder / module_id
    app = home / "app" / f"{module_id}_app"
    (home / "docs").mkdir(parents=True, exist_ok=True)
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text('FROM_APP = "app"\n', encoding="utf-8")
    (home / "__init__.py").write_text(MODULE.format(id=module_id, app=f"{module_id}_app", version=version),
                                      encoding="utf-8")  # fmt: skip
    (home / "module.toml").write_text('needs = []\npackages = []\nsuffix = "-outside"\n', encoding="utf-8")
    (home / "docs" / "docs.toml").write_text('group = "add-on"\n', encoding="utf-8")
    for page in ("README.md", "architecture.md", "tools.md"):
        (home / "docs" / page).write_text(f"# {module_id} {page}\n", encoding="utf-8")
    return home


@pytest.fixture
def outside(tmp_path, monkeypatch):
    """An empty outside folder; the modules package's path and sys.path restored afterwards, and the
    fake add-ons' packages dropped."""
    package = importlib.import_module(loader.MODULES_PACKAGE)
    monkeypatch.setattr(package, "__path__", list(package.__path__))
    monkeypatch.setattr(sys, "path", list(sys.path))
    folder = tmp_path / "AddOns"
    folder.mkdir()
    yield folder
    for name in [n for n in sys.modules if re.match(r"(assistant\.modules\.)?probe_[0-9a-f]{8}", n)]:
        del sys.modules[name]


def probe_id() -> str:
    return f"probe_{uuid.uuid4().hex[:8]}"


# Item 1: nothing configured changes nothing.


def test_nothing_configured_is_todays_layout() -> None:
    default = tomllib.loads((REPO_FOLDER / "config" / "default.toml").read_text(encoding="utf-8"))
    assert default["core"]["module_folders"] == []
    assert configured_module_folders(default) == [] and configured_module_folders({}) == []
    package = importlib.import_module(loader.MODULES_PACKAGE)
    before = list(package.__path__)
    assert loader.add_module_folders([]) == [] and list(package.__path__) == before
    assert module_roots()[0] == MODULES_FOLDER


def test_a_bad_setting_is_refused(tmp_path) -> None:
    for value in ("C:/AddOns", [1], ["AddOns"], ["./AddOns"]):
        with pytest.raises(LoadError):
            configured_module_folders({"core": {"module_folders": value}})
    assert configured_module_folders({"core": {"module_folders": [str(tmp_path)]}}) == [tmp_path.resolve()]
    with pytest.raises(LoadError, match="not a folder"):
        loader.add_module_folders([tmp_path / "missing"])


# Item 2: found, started, reloaded, added; a module found twice refused.


async def test_an_outside_add_on_is_found_started_and_reloaded(outside) -> None:
    probe = probe_id()
    home = plant(outside, probe)
    found = {cls.manifest.id: cls for cls in find_modules(folders=[outside])}
    assert probe in found and {"talker", "agent_hub"} <= set(found)  # the repo's modules still found
    assert outside.resolve() in module_roots() and module_roots()[0] == MODULES_FOLDER
    assert home / "app" in loader.app_folders()  # its app/ folder is on the import path
    cls = found[probe]
    assert cls.__module__ == f"assistant.modules.{probe}" and loader.module_folder(cls) == home.resolve()

    app = App([cls], make_config(probe))
    await app.start()
    try:
        assert (await app.router.send(InvokeTool(name=f"{probe}.version"))).value == "v1-app-outside"
        plant(outside, probe, version="v2")  # new code in the outside folder
        assert (await app.router.send(ReloadModule(module_id=probe))).is_ok
        assert (await app.router.send(InvokeTool(name=f"{probe}.version"))).value == "v2-app-outside"

        other = probe_id()
        plant(outside, other)  # a brand-new add-on dropped into the outside folder
        added = await app.router.send(AddModule(package=f"assistant.modules.{other}"))
        assert added.is_ok and added.value == other, added.error
        assert (await app.router.send(InvokeTool(name=f"{other}.version"))).value == "v1-app-outside"
    finally:
        await app.stop()


def test_a_module_in_two_folders_is_refused(outside, tmp_path) -> None:
    package = importlib.import_module(loader.MODULES_PACKAGE)
    before = list(package.__path__)
    (outside / "cv").mkdir()
    (outside / "cv" / "__init__.py").write_text("", encoding="utf-8")  # the repo has cv too
    with pytest.raises(LoadError, match="'cv' is in two folders"):
        find_modules(folders=[outside])
    assert list(package.__path__) == before  # nothing added

    probe, second = probe_id(), tmp_path / "More"
    (outside / "cv" / "__init__.py").unlink()
    (outside / "cv").rmdir()
    plant(outside, probe)
    plant(second, probe)  # two outside folders with the same id
    with pytest.raises(LoadError, match="two folders"):
        loader.add_module_folders([outside, second])
    assert loader.add_module_folders([outside]) == []  # the first one stayed added; again: once only
    assert [Path(p) for p in package.__path__].count(outside.resolve()) == 1


# Item 3: agent_access gives the right folder.


def test_an_outside_add_ons_agent_gets_its_own_folder(outside) -> None:
    probe = probe_id()
    home = plant(outside, probe).resolve()
    assert module_folder(probe) is None  # not added yet: no such module
    loader.add_module_folders([outside])
    assert module_folder(probe) == home and module_folder("cv") == MODULES_FOLDER / "cv"
    assert in_module_folder(probe, "workspace") == home / "workspace"
    writes = [i.target for i in access_items({"workspace": str(home / "workspace")}, probe) if i.kind.value == "write"]
    assert writes == [str(home)]  # its own folder, never the outside folder itself
    assert module_folder_of(home / "workspace" / "x") == home and module_folder_of(home) == home
    assert module_folder_of(outside) is None and module_folder_of(outside.parent) is None
    assert module_folder_of(MODULES_FOLDER / "cv" / "x") == MODULES_FOLDER / "cv"


# Item 4: the docs build picks up an outside add-on's docs.


def build_docs():
    spec = importlib.util.spec_from_file_location("build_docs", REPO_FOLDER / "scripts" / "build_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_docs_build_finds_an_outside_add_ons_docs(outside) -> None:
    probe = probe_id()
    home = plant(outside, probe).resolve()
    loader.add_module_folders([outside])
    docs = build_docs()
    assert docs.module_dirs()[0] == MODULES_FOLDER and outside.resolve() in docs.module_dirs()
    assert docs.module_doc_folders()[probe] == home / "docs" and "cv" in docs.module_doc_folders()
    docs.check_module_tabs()  # its standard pages and group are checked like any module's
    assert docs.module_tabs()[probe]["group"] == "add-on"
    assert docs.out_path(home / "docs" / "README.md") == docs.OUT / "modules" / probe / "index.html"
    tabs = {t["name"]: t for t in docs.nav_data(docs.OUT)["tabs"]}
    assert f"modules/{probe}/index.html" in tabs[probe]["home"]
    link = docs.readme_link(probe)
    assert (docs.DOCS / "architecture" / link).resolve() == home / "docs" / "README.md"
    assert f"| [`{probe}`]({link}) |" in docs.library_block()
    assert probe in [c.manifest.id for c in docs.module_classes()]


def test_rel_path_falls_back_to_the_absolute_path_across_drives() -> None:
    docs = build_docs()
    if os.name == "nt":
        other = Path("Z:/AddOns/x/docs/README.md") if not str(REPO_FOLDER).upper().startswith("Z") else Path("Y:/x.md")
        assert docs.rel_path(other, docs.DOCS) == other.as_posix()
    assert docs.rel_path(docs.DOCS / "api" / "x.md", docs.DOCS) == "api/x.md"


# Item 6: add-ons don't assume they're in the repo (the prompt's part is in main_assistant's own tests).

_UP = re.compile(r"Path\(__file__\)(?:\.resolve\(\))?(\.parents\[(\d+)\]|(?:\.parent(?!s))+)")
_REPO_PATH = re.compile(r"""(?:Path|open)\(\s*["']src[\\/]+assistant[\\/]+modules""")


def climbs_out(folder: Path) -> list[str]:
    """Each line of a module's Python code that reaches above its own folder from its own path
    (`Path(__file__).parents[n]` or a `.parent` chain), or opens a `src/assistant/modules/...` path:
    both break once the module lives outside the repo."""
    bad = []
    for file in folder.rglob("*.py"):
        rel = file.relative_to(folder)
        if {"__pycache__", "workspace"} & set(rel.parts):
            continue
        depth = len(rel.parts) - 1  # the highest parents[n] still inside the module's folder
        for n, line in enumerate(file.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            code = line.split("#", 1)[0]
            for match in _UP.finditer(code):
                up = int(match.group(2)) if match.group(2) is not None else match.group(1).count(".parent") - 1
                if up > depth:
                    bad.append(f"{rel.as_posix()}:{n}: {match.group(0)}")
            if _REPO_PATH.search(code):
                bad.append(f"{rel.as_posix()}:{n}: a src/assistant/modules path")
    return sorted(bad)


def _add_ons() -> list[Path]:
    found = []
    for root in module_roots():
        for p in root.iterdir():
            docs = p / "docs" / "docs.toml"
            if (p / "__init__.py").is_file() and docs.is_file():
                if tomllib.loads(docs.read_text(encoding="utf-8")).get("group") == "add-on":
                    found.append(p)
    return found


def test_no_add_on_assumes_it_is_in_the_repo() -> None:
    add_ons = _add_ons()
    assert {"cv", "job_search", "html_viewer"} <= {p.name for p in add_ons}
    found = {p.name: climbs_out(p) for p in add_ons}
    assert not any(found.values()), {m: f for m, f in found.items() if f}


def test_the_tripwire_catches_a_planted_climb(tmp_path) -> None:
    folder = tmp_path / "addon"
    (folder / "tests").mkdir(parents=True)
    (folder / "module.py").write_text("HERE = Path(__file__).resolve().parent\n"
                                      "REPO = Path(__file__).resolve().parents[4]\n", encoding="utf-8")  # fmt: skip
    (folder / "tests" / "test_x.py").write_text("OWN = Path(__file__).resolve().parents[1]\n"
                                                "UP = Path(__file__).parent.parent.parent\n"
                                                'P = Path("src/assistant/modules/addon/page.html")\n'
                                                "# Path(__file__).parents[9] in a comment is fine\n",
                                                encoding="utf-8")  # fmt: skip
    assert climbs_out(folder) == ["module.py:2: Path(__file__).resolve().parents[4]",
                                  "tests/test_x.py:2: Path(__file__).parent.parent.parent",
                                  "tests/test_x.py:3: a src/assistant/modules path"]  # fmt: skip

