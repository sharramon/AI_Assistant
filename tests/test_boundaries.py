"""The boundary tests (restructuring R1, decision D7): the line between the core and the modules, checked
before anything moves.

- Rule 1: a module's code imports only `assistant.contracts`, `assistant.infra`, `app_kit`, the standard
  library, third-party packages, its own package and its own `app/` packages. Never `assistant.core`, the
  test kit (outside its `tests/`), another module, or another module's companion app.
- Rule 2: the core's settings (`config/default.toml`) and every core module's `module.toml` never name an
  add-on (the code side is `test_no_core_code_names_an_add_on` in `test_module_folders.py`).
- Rule 3: a core module `needs` only core modules, and no module's `needs` makes a cycle.

Module layout step 1 (docs/next-steps/module-layout-step1-checklist.md, item 1) makes the line hard
with two more:

- Rule 1, the other way: the shared code (`assistant.core`, `assistant.contracts`, `assistant.infra`,
  `app_kit`) imports no module package at all, core group included; the core finds modules by folder.
- The core starts without any add-on: the core group alone resolves (needs, required contracts), and the
  shipped on-list (`config/modules.toml`) turns on no add-on.

Module layout step 2 (docs/next-steps/module-layout-step2-checklist.md, item 5): the add-ons may live
in folders outside the repo (`[core] module_folders`), so every rule runs over every module root, and two
more hold:

- A module outside the repo is an add-on: the core group stays in the repo.
- No module id is in two roots (the loader refuses it at startup too).

Each rule is a function over a folder, so a planted bad tree in `tmp_path` proves it catches a break.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from assistant.contracts import IVoice, Manifest, ModuleProtocol
from assistant.core import StartupError, loader
from assistant.core.registry import resolve_modules
from assistant.modules import __path__ as _modules_path

MODULES = Path(next(iter(_modules_path)))
REPO = MODULES.parents[2]
# Every folder holding modules: the repo's first, then the ones [core] module_folders names (the conftest adds them).
ROOTS = [Path(p) for p in _modules_path]
SHARED_CODE = (REPO / "src" / "assistant" / "core", REPO / "src" / "assistant" / "contracts",
               REPO / "src" / "assistant" / "infra", REPO / "src" / "app_kit")  # fmt: skip
ALLOWED = ("assistant.contracts", "assistant.infra")
SKIPPED = {"__pycache__", "workspace", "tests", "app", ".venv"}  # tests use the test kit; app/ never imports assistant


def _toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def module_ids(root: Path) -> list[str]:
    """The module folders under `root` (each holds a module.toml)."""
    return sorted(p.name for p in root.iterdir() if (p / "module.toml").is_file())


def groups(root: Path) -> dict[str, str]:
    """Each module's group (`core` or `add-on`), from its docs/docs.toml."""
    return {m: _toml(root / m / "docs" / "docs.toml").get("group", "") for m in module_ids(root)}


def app_packages(root: Path) -> dict[str, str]:
    """Every companion app package under `root`'s `<id>/app/`, mapped to its module id."""
    found = {}
    for m in module_ids(root):
        app = root / m / "app"
        if app.is_dir():
            found |= {p.name: m for p in app.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))}
    return found


def import_violations(root: Path, prefix: str = "assistant.modules") -> list[str]:
    """Rule 1 over every module folder in `root` (whose package is `prefix`): each import that crosses the line."""
    apps = app_packages(root)
    bad = []
    for m in module_ids(root):
        own = f"{prefix}.{m}"
        for file in (root / m).rglob("*.py"):
            rel = file.relative_to(root)
            if SKIPPED & set(rel.parts[1:-1]):
                continue
            package = list(rel.parts[:-1])  # the package this file's relative imports start from
            for node in ast.walk(ast.parse(file.read_text(encoding="utf-8-sig"))):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level:
                    if node.level > len(package):  # climbs out of its own package
                        bad.append(f"{rel.as_posix()}:{node.lineno}: relative import out of {m}")
                    continue
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    top = name.split(".")[0]
                    if top == "assistant":
                        if not (name.startswith(ALLOWED) or name == own or name.startswith(own + ".")):
                            bad.append(f"{rel.as_posix()}:{node.lineno}: {name}")
                    elif apps.get(top, m) != m:
                        bad.append(f"{rel.as_posix()}:{node.lineno}: {name} (the {apps[top]} module's app)")
    return bad


def _strings(value: object) -> list[str]:
    """Every key and string value in a parsed TOML table (comments are not in it)."""
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (k, *_strings(v))]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return [value] if isinstance(value, str) else []


def naming_add_ons(files: list[Path], add_ons: list[str]) -> list[str]:
    """Rule 2: each key or value in `files` that names an add-on id."""
    words = [re.compile(r"(?<![\w.])" + re.escape(a) + r"(?![\w])") for a in add_ons]
    return [f"{f.name}: {s!r}" for f in files for s in _strings(_toml(f)) if any(w.search(s) for w in words)]


def needs(root: Path) -> dict[str, list[str]]:
    """Each module's `needs`, from its module.toml."""
    return {m: list(_toml(root / m / "module.toml").get("needs", [])) for m in module_ids(root)}


def needs_violations(graph: dict[str, list[str]], group: dict[str, str]) -> list[str]:
    """Rule 3: a core module needing a non-core one, an unknown module, or a cycle."""
    bad = [f"{m} (core) needs {n} ({group.get(n) or 'unknown'})"
           for m, ns in graph.items() if group.get(m) == "core" for n in ns if group.get(n) != "core"]  # fmt: skip
    state: dict[str, int] = {}  # 1 on the path, 2 done

    def walk(m: str, path: list[str]) -> None:
        state[m] = 1
        for n in graph.get(m, []):
            if state.get(n) == 1:
                bad.append("cycle: " + " -> ".join([*path[path.index(n) :], n]))
            elif not state.get(n):
                walk(n, [*path, n])
        state[m] = 2

    for m in graph:
        if not state.get(m):
            walk(m, [m])
    return bad


def module_imports(folders: Sequence[Path], src: Path, package: str = "assistant.modules") -> list[str]:
    """Rule 1, the other way: each import of `package` (or anything in it) in the code under `folders`,
    relative imports resolved from each file's package under `src`."""
    bad = []
    for folder in folders:
        for file in folder.rglob("*.py"):
            if "__pycache__" in file.parts:
                continue
            here = list(file.relative_to(src).parts[:-1])
            for node in ast.walk(ast.parse(file.read_text(encoding="utf-8-sig"))):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = here[: len(here) - node.level + 1] if node.level else []
                    module = ".".join([*base, *([node.module] if node.module else [])])
                    names = [module] + [f"{module}.{a.name}" for a in node.names]
                bad += [f"{file.relative_to(src).as_posix()}:{node.lineno}: {n}" for n in names
                        if n == package or n.startswith(package + ".")]  # fmt: skip
    return sorted(set(bad))


def all_groups(roots: Sequence[Path]) -> dict[str, str]:
    """Each module's group over every root."""
    return {m: g for root in roots for m, g in groups(root).items()}


def all_needs(roots: Sequence[Path]) -> dict[str, list[str]]:
    """Each module's `needs` over every root."""
    return {m: n for root in roots for m, n in needs(root).items()}


def outside_core(roots: Sequence[Path], repo: Path) -> list[str]:
    """Step 2: each module in a root outside `repo` whose group isn't `add-on` (the core stays in the repo)."""
    return [f"{root / m}: group {g!r}" for root in roots if not root.resolve().is_relative_to(repo.resolve())
            for m, g in groups(root).items() if g != "add-on"]  # fmt: skip


def ids_twice(roots: Sequence[Path]) -> list[str]:
    """Step 2: each module id found in more than one root."""
    seen: dict[str, list[Path]] = {}
    for root in roots:
        for m in module_ids(root):
            seen.setdefault(m, []).append(root)
    return [f"{m}: {', '.join(map(str, where))}" for m, where in sorted(seen.items()) if len(where) > 1]


def core_alone(available: Sequence[type[ModuleProtocol]], enabled: Sequence[str]) -> str | None:
    """The core starts without any add-on: why `resolve_modules` refuses the core group's classes
    (`available`) with `enabled` on, or None when they resolve."""
    try:
        resolve_modules(available, enabled)
    except StartupError as exc:
        return str(exc)
    return None


# The real tree.


def test_rule_1_modules_import_only_contracts_infra_and_their_own() -> None:
    assert sum(len(module_ids(root)) for root in ROOTS) >= 10
    found = [v for root in ROOTS for v in import_violations(root)]
    assert not found, found


def test_rule_2_core_settings_name_no_add_on() -> None:
    group = all_groups(ROOTS)
    add_ons = sorted(m for m, g in group.items() if g == "add-on")
    assert {"html_viewer", "cv", "job_search"} <= set(add_ons)
    files = [REPO / "config" / "default.toml"] + [MODULES / m / "module.toml" for m, g in group.items() if g == "core"]
    assert not naming_add_ons(files, add_ons)


def test_rule_3_core_needs_only_core_and_no_cycle() -> None:
    group = all_groups(ROOTS)
    assert set(group.values()) <= {"core", "add-on"}, group
    assert not needs_violations(all_needs(ROOTS), group)


def test_step_2_the_core_stays_in_the_repo_and_no_id_is_found_twice() -> None:
    assert ROOTS[0] == MODULES  # the repo's folder first, the outside ones after
    assert not outside_core(ROOTS, REPO), outside_core(ROOTS, REPO)
    assert not ids_twice(ROOTS), ids_twice(ROOTS)


def test_rule_1_the_shared_code_imports_no_module() -> None:
    assert all(folder.is_dir() for folder in SHARED_CODE)
    found = module_imports(SHARED_CODE, REPO / "src")
    assert not found, f"the shared code imports a module (find it by folder or use a contract): {found}"


def test_the_core_starts_without_any_add_on() -> None:
    group = groups(MODULES)
    core = [cls for cls in loader.find_modules() if group.get(cls.manifest.id) == "core"]
    assert {cls.manifest.id for cls in core} == {m for m, g in group.items() if g == "core"}
    shipped = _toml(REPO / "config" / "modules.toml")["enabled"]
    assert not [m for m in shipped if group.get(m) != "core"], f"the shipped on-list turns on an add-on: {shipped}"
    assert core_alone(core, shipped) is None
    assert core_alone(core, [cls.manifest.id for cls in core]) is None  # every core module on at once


# Planted bad trees: each rule catches a break.


def _plant(root: Path, module: str, group: str, files: dict[str, str], needs_: list[str] | None = None) -> None:
    folder = root / module
    (folder / "docs").mkdir(parents=True)
    (folder / "module.toml").write_text(f"needs = {needs_ or []!r}\n".replace("'", '"'), encoding="utf-8")
    (folder / "docs" / "docs.toml").write_text(f'group = "{group}"\n', encoding="utf-8")
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")


def test_rule_1_catches_a_planted_bad_import(tmp_path) -> None:
    _plant(tmp_path, "good", "core", {
        "__init__.py": "from assistant.contracts import Manifest\nimport assistant.infra.config\nimport httpx\n",
        "sub/x.py": "from .. import good\nfrom . import y\nfrom assistant.modules.good.sub import y\nimport good_app\n",
        "app/good_app/__init__.py": "", "tests/test_x.py": "from assistant.testkit import make_config\n",
    })  # fmt: skip
    _plant(tmp_path, "bad", "add-on", {
        "__init__.py": "from assistant.core import App\nfrom assistant.modules.good import x\n",
        "deep.py": "from .. import good\nimport good_app.server\nimport assistant\nfrom assistant.testkit import FAKE\n",
    })  # fmt: skip
    found = import_violations(tmp_path)
    assert sorted(found) == sorted([
        "bad/__init__.py:1: assistant.core", "bad/__init__.py:2: assistant.modules.good",
        "bad/deep.py:1: relative import out of bad", "bad/deep.py:2: good_app.server (the good module's app)",
        "bad/deep.py:3: assistant", "bad/deep.py:4: assistant.testkit",
    ]), found  # fmt: skip


def test_rule_2_catches_a_planted_add_on_name(tmp_path) -> None:
    file = tmp_path / "default.toml"
    file.write_text('# html_viewer in a comment is fine\n[core]\nreviewer = "cv"\nport_html_viewer = 1\n'
                    'x = "cvs"\n', encoding="utf-8")  # fmt: skip
    assert naming_add_ons([file], ["cv", "html_viewer"]) == ["default.toml: 'cv'"]


def test_rule_3_catches_planted_needs(tmp_path) -> None:
    _plant(tmp_path, "core_a", "core", {}, ["addon_b"])
    _plant(tmp_path, "addon_b", "add-on", {}, ["addon_c"])
    _plant(tmp_path, "addon_c", "add-on", {}, ["addon_b"])
    found = needs_violations(needs(tmp_path), groups(tmp_path))
    assert "core_a (core) needs addon_b (add-on)" in found
    assert any(f.startswith("cycle: addon_b -> addon_c -> addon_b") for f in found), found


def test_step_2_rules_catch_a_planted_outside_folder(tmp_path) -> None:
    repo, outside = tmp_path / "repo", tmp_path / "AddOns"
    _plant(repo / "modules", "talker_x", "core", {})
    _plant(repo / "modules", "cv_x", "add-on", {})
    _plant(outside, "cv_x", "add-on", {})  # the same id in two roots
    _plant(outside, "hub_x", "core", {})  # a core module outside the repo
    _plant(outside, "jobs_x", "add-on", {"__init__.py": "from assistant.modules.cv_x import y\n"}, ["talker_x"])
    roots = [repo / "modules", outside]
    assert outside_core(roots, repo) == [f"{outside / 'hub_x'}: group 'core'"]
    assert ids_twice(roots) == [f"cv_x: {repo / 'modules'}, {outside}"]
    assert import_violations(outside) == ["jobs_x/__init__.py:1: assistant.modules.cv_x"]  # rule 1 there too
    assert not needs_violations(all_needs(roots), all_groups(roots))  # an add-on outside may need a core module
    assert not outside_core([repo / "modules"], repo) and not ids_twice([repo / "modules"])


def test_rule_1_other_way_catches_a_planted_module_import(tmp_path) -> None:
    core = tmp_path / "assistant" / "core"
    core.mkdir(parents=True)
    (core / "ok.py").write_text("from assistant.contracts import Manifest\nfrom . import registry\n"
                                'MODULES = "assistant.modules"\n', encoding="utf-8")  # a string is finding by folder
    (core / "bad.py").write_text("import assistant.modules.talker\nfrom assistant import modules\n"
                                 "from ..modules.cv import CvModule\n", encoding="utf-8")  # fmt: skip
    found = module_imports([core], tmp_path)
    assert found == ["assistant/core/bad.py:1: assistant.modules.talker", "assistant/core/bad.py:2: assistant.modules",
                     "assistant/core/bad.py:3: assistant.modules.cv", "assistant/core/bad.py:3: assistant.modules.cv.CvModule"]  # fmt: skip


class PlantedCore(ModuleProtocol):
    manifest = Manifest(id="planted_core", requires=(IVoice,))  # in this planted tree, only an add-on provides it

    async def init(self, ctx) -> None:
        pass


class PlantedAddOn(PlantedCore):
    manifest = Manifest(id="planted_add_on", provides=(IVoice,))


def test_core_alone_catches_a_core_module_that_requires_an_add_on() -> None:
    assert core_alone([PlantedCore, PlantedAddOn], ["planted_core", "planted_add_on"]) is None  # with the add-on, it starts
    assert "IVoice" in (core_alone([PlantedCore], ["planted_core"]) or "")  # the core group alone: refused
