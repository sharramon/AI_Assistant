"""The module-folders migration's tripwires (docs/next-steps/module-folders-checklist.md): one
test per finished item, so a done item can't slip back.

Item 1: every module can edit itself by default. A module's own agent asks for a write on its
own module folder only, and the Hub lets it work beside the Main Assistant's whole-repo grant,
while two agents on one module folder are still refused, with the folder named.

Item 2: a `needs` list. cv's module.toml declares `needs`, the core puts it on the manifest, and
the lifecycle turns needed modules on first and refuses to turn one off while a module needs it.

Item 3: cv's `[agent]` section is complete. cv_agent's `named_only = true` is in its own section,
not in agent_hub's config; the Hub reads it from the agent (`AgentInfo.named_only`).

Item 4: the CV Tool app is in cv's folder, `cv/app/cv_tool/`. No app is left in `src/<app>`; the core
finds every module's `app/` folder by folder and puts it on the import path, a launch passes it on
(`PYTHONPATH`), the app never imports `assistant`, and its defaults are in cv's workspace.

Item 5: cv's tests are in its module, on the public test kit. No module file imports `tests`; the
shared fakes and helpers are in `assistant.testkit`, which only tests import.

Item 6: cv's packages and ruff rule are in its folder. pyproject.toml names no module package, extra or
per-file ignore; cv's module.toml lists `packages` (on its manifest), and cv/ruff.toml extends the root.

Item 7: job_search's defaults, needs and tests are in its folder. Its module.toml holds its defaults and
`needs = ["cv"]`.

Item 8: html_viewer's app, events and tests are in its folder. The viewer app is `html_viewer/app/html_viewer/`
(launched by folder), its defaults and `needs` are in its module.toml, its three event types left the
contracts (its named events now, heard by name).

Item 9: voice_in's app, packages and tests are in its folder. The voice service is `voice_in/app/voice_service/`
(launched by folder) with its defaults `voice_service.toml` beside its code, voice_in's defaults and `packages`
are in its module.toml (the `voice` extra and the script entry left pyproject.toml), and no `tests/test_voice*` is left.

Item 10: voice_notes' defaults and `needs = ["voice_in"]` are in its module.toml, its tests in its folder.

Item 11 (first half): agent_hub, talker, main_assistant and task_agents (its kinds of helper too) have
their defaults in their module.toml, config/default.toml has no section of theirs, and their own tests
are in their folders; the tests that run them together stay in `tests/`.

Item 11 (second half): console_io, temp_ui, usage, assistant_view and echo_orchestrator have their
module.toml too, so every module folder has one; config/default.toml has no module's defaults left (only
the core's settings); and no central test file names only one module unless it's listed with its reason.

Item 12: config/ is your choices only. `config/modules.toml` says which modules are on (default.toml has no
`enabled` left), `config/<id>.toml` holds your choices for one module over its module.toml, `config/<id>.local.toml`
over that, and `[modules.<id>]` in config/local.toml last; the saved grants' file is never read as a module's.

Item 15: the needs arrows point one way, never core → add-on. No code of the core group's modules, the core,
contracts, infra or app_kit names an add-on's id or its menu items (docstrings and comments aside; an add-on's
named events may be heard by name, decision 9); pages open through the `IPageOpener` slot, which html_viewer fills.

Item 19: the rule holds for every add-on (each module whose docs/docs.toml group is "add-on"), one test per
add-on: no `src/<app>`, no package, extra, app or ruff rule of it in pyproject.toml, no section or file of it in
committed config/, no test of it in `tests/`, and its agent's workspace in its own folder. What items 4–10 checked
for one add-on each is checked there for all of them; the core group keeps its own checks here."""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_kit.companion import launch_env, package_root
from assistant.contracts import (
    AccessKind,
    ActivateModule,
    AgentInfo,
    DeactivateModule,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ModuleState,
    StartTask,
    Status,
)
from assistant.core import App, StartupError, loader
from assistant.infra import (
    MODULES_FOLDER,
    access_items,
    in_module_folder,
    module_folder,
    module_folder_of,
    request_access,
)
from assistant.infra.profile_agent import named_only
from assistant.modules.agent_hub.tasks import folders_clash
from assistant.modules.agent_hub.tests.test_agent_hub_parts import FakeAgent, Rig
from assistant.modules.cv import CvModule
from assistant.testkit import FAKE, FAKE_JOB_UI, make_config

REPO = MODULES_FOLDER.parents[2]
CV = MODULES_FOLDER / "cv"


def _toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _module_toml(module_id: str) -> dict:
    return _toml(MODULES_FOLDER / module_id / "module.toml")


def _module_class(module_id: str) -> type:
    """Module `module_id`'s class, its module.toml applied (as the core loads it)."""
    return loader.find_module_class(importlib.import_module(f"assistant.modules.{module_id}"), module_id)


def _writes(items) -> list[str]:
    return [i.target for i in items if i.kind is AccessKind.WRITE]


def test_module_agent_edits_its_own_folder(tmp_path) -> None:
    config = {"workspace": str(tmp_path / "w"), "write_dirs": [str(tmp_path / "out")]}
    # Item 1: the default list names the module's own folder, and only that one in the modules folder.
    writes = _writes(access_items(config, "cv"))
    assert writes == [str((tmp_path / "out").resolve()), str(CV)]
    inside_modules = [w for w in writes if module_folder_of(w) is not None]
    assert inside_modules == [str(CV)]  # never the modules folder, the repo or another module
    assert str(MODULES_FOLDER) not in writes and str(REPO) not in writes
    # No module id (task_agents' helpers), or no such module folder: nothing added.
    assert _writes(access_items(config)) == [str((tmp_path / "out").resolve())]
    assert module_folder("no_such_module") is None and module_folder("..") is None
    assert module_folder("job_search") == MODULES_FOLDER / "job_search"

    # request_access asks with it by default (from the asking module's id), and without on request.
    asked: list = []

    async def request_set(items, reason, subject, wait):
        asked.append(items)
        return items

    ctx = SimpleNamespace(module_id="cv", permissions=SimpleNamespace(request_set=request_set))
    granted = asyncio.run(request_access(ctx, config, subject="cv_agent"))
    assert granted["write_dirs"] == [str((tmp_path / "out").resolve()), str(CV)]
    asyncio.run(request_access(ctx, config, subject="helper", own_folder=False))
    assert str(CV) not in _writes(asked[-1])


async def test_a_module_agent_runs_beside_the_main_assistant() -> None:
    rig = Rig(FakeAgent("main", (str(REPO),)), FakeAgent("cv_agent", (str(CV),)))
    assert (await rig.board.start(StartTask(text="whole repo", agent_id="main"))).is_ok
    assert (await rig.board.start(StartTask(text="its own module", agent_id="cv_agent"))).is_ok
    # The other order too: the module agent first, then the whole-repo grant.
    rig = Rig(FakeAgent("main", (str(REPO),)), FakeAgent("cv_agent", (str(CV / "workspace"),)))
    assert (await rig.board.start(StartTask(text="its own module", agent_id="cv_agent"))).is_ok
    assert (await rig.board.start(StartTask(text="whole repo", agent_id="main"))).is_ok


async def test_two_agents_on_one_module_folder_are_refused_with_the_folder_named() -> None:
    rig = Rig(FakeAgent("main"), FakeAgent("a", (str(CV),)), FakeAgent("b", (str(CV),)))
    assert (await rig.board.start(StartTask(text="x", agent_id="a"))).is_ok
    refused = await rig.board.start(StartTask(text="y", agent_id="b"))
    assert refused.status is Status.NOT_AVAILABLE
    assert str(CV) in refused.error and "a's write grant" in refused.error and "the same folder" in refused.error


def test_the_folder_rule() -> None:
    assert folders_clash(str(CV), str(CV)) == "the same folder"
    # Inside one module folder: still a clash, either way round.
    assert folders_clash(str(CV), str(CV / "workspace")) == "one folder is inside the other"
    assert folders_clash(str(CV / "workspace"), str(CV)) == "one folder is inside the other"
    # A module's folder under a wider grant (the repo, src, the modules folder): no clash.
    for wider in (REPO, REPO / "src", MODULES_FOLDER):
        assert folders_clash(str(wider), str(CV)) is None and folders_clash(str(CV / "x"), str(wider)) is None
    # A folder in the repo that's no module's own still clashes with the whole repo.
    assert folders_clash(str(REPO), str(REPO / "scratch")) == "one folder is inside the other"
    assert folders_clash(str(REPO), str(MODULES_FOLDER)) == "one folder is inside the other"
    # Two modules side by side: no overlap.
    assert folders_clash(str(CV), str(MODULES_FOLDER / "job_search")) is None


# Item 2: a needs list.


class Base(ModuleProtocol):
    manifest = Manifest(id="base_part")

    async def init(self, ctx: ModuleContext) -> None:
        pass


class NeedsBase(Base):
    manifest = Manifest(id="needs_base", needs=("base_part",))


class NeedsMissing(Base):
    manifest = Manifest(id="needs_missing", needs=("no_such_part",))


def _states(app: App) -> dict[str, ModuleState]:
    return {info.id: info.state for info in app._lifecycle.modules()}


def test_cv_declares_needs(monkeypatch) -> None:
    toml = _module_toml("cv")
    assert toml["needs"] == []
    assert loader.apply_module_toml(CvModule).manifest.needs == ()
    # A module.toml's needs reach the manifest; a wrong value or the module's own id is refused.
    class FromToml(Base):
        manifest = Manifest(id="from_toml")

    monkeypatch.setattr(loader, "module_defaults", lambda cls: {"needs": ["base_part"]})
    assert loader.apply_module_toml(FromToml).manifest.needs == ("base_part",)
    for bad in ("base_part", ["from_toml"], [1]):
        monkeypatch.setattr(loader, "module_defaults", lambda cls, bad=bad: {"needs": bad})
        with pytest.raises(loader.LoadError):
            loader.apply_module_toml(FromToml)


async def test_turning_on_a_module_turns_on_what_it_needs() -> None:
    app = App([Base, NeedsBase], make_config())
    await app.start()
    assert (await app.router.send(ActivateModule(module_id="needs_base"))).is_ok
    assert _states(app) == {"base_part": ModuleState.ACTIVE, "needs_base": ModuleState.ACTIVE}
    assert list(app._lifecycle._active) == ["base_part", "needs_base"]
    await app.stop()
    # At startup too: enabling only the one that needs it starts both, the needed one first.
    app = App([NeedsBase, Base], make_config("needs_base"))
    await app.start()
    assert list(app._lifecycle._active) == ["base_part", "needs_base"]
    await app.stop()


async def test_turning_off_a_needed_module_is_refused() -> None:
    app = App([Base, NeedsBase], make_config("needs_base"))
    await app.start()
    refused = await app.router.send(DeactivateModule(module_id="base_part"))
    assert refused.status is Status.FAILED and "needs_base" in refused.error
    assert _states(app)["base_part"] is ModuleState.ACTIVE
    assert (await app.router.send(DeactivateModule(module_id="base_part", with_dependents=True))).is_ok
    assert _states(app) == {"base_part": ModuleState.INACTIVE, "needs_base": ModuleState.INACTIVE}
    await app.stop()


async def test_a_missing_needed_module_is_named() -> None:
    with pytest.raises(StartupError, match="no_such_part"):
        App([NeedsMissing], make_config("needs_missing"))
    app = App([NeedsMissing], make_config())
    await app.start()
    result = await app.router.send(ActivateModule(module_id="needs_missing"))
    assert result.status is Status.NOT_AVAILABLE and "no_such_part" in result.error
    await app.stop()


# Item 3: cv's [agent] section is complete.


def test_cv_agent_is_named_only_from_its_own_section() -> None:
    assert "cv_agent" not in (REPO / "config" / "default.toml").read_text(encoding="utf-8")
    toml = _module_toml("cv")
    assert toml["agent"]["agent_id"] == "cv_agent" and toml["agent"]["named_only"] is True
    # The flag reaches the agent's info() through ProfileAgent; a wrong value is refused.
    assert named_only("cv_agent", toml["agent"]) is True and named_only("helper", {}) is False
    with pytest.raises(ValueError, match="named_only"):
        named_only("helper", {"named_only": "yes"})


class NamedOnlyAgent(FakeAgent):
    def info(self) -> AgentInfo:
        return super().info().model_copy(update={"named_only": True})


async def test_a_free_pick_never_lands_on_a_named_only_agent() -> None:
    rig = Rig(NamedOnlyAgent("cv_agent"))
    assert (await rig.board.start(StartTask(text="anyone"))).status is Status.NOT_AVAILABLE
    # A normal free agent beside it is picked, whatever the order.
    rig = Rig(NamedOnlyAgent("cv_agent"), FakeAgent("helper"))
    started = await rig.board.start(StartTask(text="anyone"))
    assert started.is_ok and rig.board.get(started.value).agent_id == "helper"
    # Named, it still starts.
    assert (await rig.board.start(StartTask(text="for you", agent_id="cv_agent"))).is_ok


# Item 4: the CV Tool app in cv's folder.

# Where companion apps used to live, outside their module (src/voice_service is voice_in's, a core
# module; item 19 checks every add-on's src/<app> by its app/ folder).
OLD_APPS = ["src/cv_tool", "src/html_viewer", "src/voice_service"]
CV_APP = CV / "app"


def test_no_app_outside_its_module() -> None:
    for old in OLD_APPS:
        assert not (REPO / old).exists(), f"{old} is left outside its module"
    assert (CV_APP / "cv_tool" / "__main__.py").is_file() and (CV_APP / "cv_tool" / "cv_tool.toml").is_file()
    assert not (CV_APP / "__init__.py").exists()  # app/ is no package: the app keeps its own name
    # Found by folder, on the import path (the core at startup, the test setup), imported from there.
    assert CV_APP in loader.app_folders()
    loader.add_app_folders()
    assert loader.add_app_folders() == []  # once each
    assert any(p and Path(p).resolve() == CV_APP for p in sys.path)
    import cv_tool

    assert Path(cv_tool.__file__).parent == CV_APP / "cv_tool"
    # A launch passes the folder on, first on PYTHONPATH, keeping what was there.
    assert package_root("cv_tool") == CV_APP and package_root("no_such_app_package") is None
    assert launch_env("cv_tool", {"PYTHONPATH": "kept"})["PYTHONPATH"] == os.pathsep.join([str(CV_APP), "kept"])
    assert launch_env("no_such_app_package", {"A": "1"}) == {"A": "1"}
    base = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    child = subprocess.run([sys.executable, "-c", "import cv_tool; print(cv_tool.__file__)"], env=launch_env("cv_tool", base),
                           capture_output=True, text=True, timeout=60, check=True)  # fmt: skip
    assert Path(child.stdout.strip()).parent == CV_APP / "cv_tool"


def _imports(file: Path) -> list[str]:
    """The absolute imports of a Python file (`a.b` for `import a.b` and `from a.b import c`)."""
    names: list[str] = []
    for node in ast.walk(ast.parse(file.read_text(encoding="utf-8-sig"))):  # some files start with a BOM
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            names.append(node.module or "")
    return names


def test_every_module_app_never_imports_assistant() -> None:
    folders = loader.app_folders()
    assert CV_APP in folders
    for file in (f for folder in folders for f in folder.rglob("*.py")):
        assert not any(n.split(".")[0] == "assistant" for n in _imports(file)), file


def test_the_cv_tool_defaults_are_in_the_module_workspace(tmp_path) -> None:
    # No absolute folder of the user's in the app (Chrome's install folder is the one fixed path).
    for file in ("cv_tool.toml", "cvlib.py", "server.py"):
        text = (CV_APP / "cv_tool" / file).read_text(encoding="utf-8")
        found = re.findall(r"\b[A-Za-z]:[\\/][^\"'\n]*", text)
        assert all("Program Files" in path for path in found), (file, found)
    pytest.importorskip("pymupdf")
    from cv_tool import cvlib, server

    workspace = CV / "workspace"
    assert Path(cvlib.WORKSPACE) == workspace
    assert Path(cvlib.DEFAULT_DATA) == workspace / "cv_tool" and Path(cvlib.DEFAULT_CV_DIR) == workspace / "cvs"
    assert Path(cvlib.DEFAULT_RULES) == workspace / ".claude" / "skills" / "cv-writing"
    config = tmp_path / "cv_tool.toml"  # the committed defaults alone, without this machine's .local file
    config.write_text((CV_APP / "cv_tool" / "cv_tool.toml").read_text(encoding="utf-8"), encoding="utf-8")
    settings = server.settings(["--config", str(config)])
    assert Path(settings["data_dir"]) == workspace / "cv_tool" and Path(settings["cv_dir"]) == workspace / "cvs"


# Item 5: cv's tests in its module, on the public test kit (no cv test central: item 19).

TESTKIT = REPO / "src" / "assistant" / "testkit"
SKIPPED = {"__pycache__", "workspace", ".venv"}  # an agent's workspace holds its own files, not the app's


def _python_files(*folders: Path) -> list[Path]:
    return [f for folder in folders for f in folder.rglob("*.py") if not SKIPPED & set(f.relative_to(REPO).parts)]


def test_module_tests_use_only_the_testkit() -> None:
    files = _python_files(MODULES_FOLDER)
    assert any(f.parts[-2] == "tests" for f in files)  # the modules' own tests are in the walk
    for file in files:
        assert not any(n == "tests" or n.startswith("tests.") for n in _imports(file)), file


def test_only_tests_import_the_testkit() -> None:
    def a_test(file: Path) -> bool:
        parts = file.relative_to(REPO).parts
        return parts[0] == "tests" or "tests" in parts[:-1] or file.is_relative_to(TESTKIT) or file.name == "conftest.py"

    for file in _python_files(REPO / "src", REPO / "scripts", REPO / "tests") + list(REPO.glob("*.py")):
        if any(n.split(".")[:2] == ["assistant", "testkit"] for n in _imports(file)):
            assert a_test(file), f"{file} imports the test kit outside the tests"
    # The kit holds the shared fakes; the scripts run as subprocesses are found by path, and it needs no pytest.
    assert Path(FAKE[1]).parent == TESTKIT and Path(FAKE[1]).is_file() and Path(FAKE_JOB_UI).is_file()
    assert not list((REPO / "tests").glob("fake_*.py")) and not (REPO / "tests" / "support.py").exists()
    assert not any(n.split(".")[0] == "pytest" for f in _python_files(TESTKIT) for n in _imports(f))


# Item 6: a module's packages and ruff rules in its folder (every add-on: item 19; the core group here).


def _apps(folder: Path) -> list[str]:
    """The companion apps' package names in a module folder's app/ (none without one)."""
    app = folder / "app"
    if not app.is_dir():
        return []
    return sorted(p.name for p in app.iterdir() if (p / "__main__.py").is_file() or (p / "__init__.py").is_file())


def _package_names(module_id: str) -> list[str]:
    """The pip names of the packages in a module's module.toml (`pymupdf` for `pymupdf>=1.24`), lowercase."""
    return [re.split(r"[\s<>=!~\[;]", p, maxsplit=1)[0].lower() for p in _module_toml(module_id).get("packages", [])]


def _pyproject_leaks(module_id: str, *, by_id: bool = False) -> list[str]:
    """What of module `module_id` is still outside its folder in pyproject.toml: an extra named for it, a
    per-file ignore in its folder, one of its packages or its app's name (and its own id, `by_id`); and
    whether its own ruff.toml, if any, extends the root and ignores only files in its folder."""
    root = REPO / "pyproject.toml"
    text = root.read_text(encoding="utf-8").lower()
    pyproject = tomllib.loads(text)
    folder = MODULES_FOLDER / module_id
    leaks = []
    if module_id in pyproject["project"].get("optional-dependencies", {}):
        leaks.append(f"pyproject.toml: the {module_id!r} extra")
    ignores = pyproject["tool"]["ruff"]["lint"].get("per-file-ignores", {})
    leaks += [f"pyproject.toml: the per-file ignore {path!r}" for path in ignores if f"/{module_id}/" in path]
    words = [*_package_names(module_id), *_apps(folder), *([module_id] if by_id else [])]
    leaks += [f"pyproject.toml names {w!r}" for w in words if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", text)]
    ruff = folder / "ruff.toml"
    if ruff.is_file():
        own, name = _toml(ruff), ruff.relative_to(REPO).as_posix()
        if (folder / own.get("extend", "")).resolve() != root.resolve():
            leaks.append(f"{name} doesn't extend pyproject.toml")
        leaks += [f"{name}: the per-file ignore {path!r} is outside its folder"
                  for path in own.get("lint", {}).get("per-file-ignores", {})
                  if not Path(os.path.normpath(folder / path)).is_relative_to(folder)]  # fmt: skip
    return leaks


def test_no_core_module_package_in_pyproject() -> None:
    pyproject = _toml(REPO / "pyproject.toml")
    assert "voice" not in pyproject["project"].get("optional-dependencies", {})  # voice_in's old extra
    core = sorted(m for m, g in _groups().items() if g != "add-on")
    assert "voice_in" in core
    leaks = {m: found for m in core if (found := _pyproject_leaks(m))}
    assert not leaks, f"pyproject.toml holds what belongs in these core modules' folders: {leaks}"
    for module_id in core:  # each lists its packages in its module.toml, and they reach its manifest
        assert _module_class(module_id).manifest.packages == tuple(_module_toml(module_id)["packages"]), module_id
    assert any(p.startswith("websockets") for p in _module_toml("voice_in")["packages"])


def test_packages_come_from_module_toml(monkeypatch) -> None:
    class Packaged(Base):
        manifest = Manifest(id="packaged", needs=("base_part",))

    # One reader for both keys: packages arrive, and needs are left as they were when absent.
    monkeypatch.setattr(loader, "module_defaults", lambda cls: {"packages": ["somepkg>=1"]})
    manifest = loader.apply_module_toml(Packaged).manifest
    assert manifest.packages == ("somepkg>=1",) and manifest.needs == ("base_part",)
    for bad in ("somepkg", [""], ["  "], [1]):
        monkeypatch.setattr(loader, "module_defaults", lambda cls, bad=bad: {"packages": bad})
        with pytest.raises(loader.LoadError, match="packages"):
            loader.apply_module_toml(Packaged)
    with pytest.raises(ValueError, match="packages"):
        Manifest(id="x", packages=("",))


# Item 7: job_search's defaults, needs and tests in its folder (nothing of it outside: item 19).

JOB_SEARCH = MODULES_FOLDER / "job_search"


def test_job_search_has_its_module_toml() -> None:
    toml = _module_toml("job_search")
    assert toml["needs"] == ["cv"] and toml["packages"] == []
    assert toml["workspace"] and toml["transcript"] == "job_search_agent.jsonl"  # its defaults are here
    assert _module_class("job_search").manifest.needs == ("cv",)
    assert (JOB_SEARCH / "tests" / "test_job_search.py").is_file()


# Item 8: html_viewer's app, events and tests in its folder (nothing of it outside: item 19).

HTML_VIEWER = MODULES_FOLDER / "html_viewer"
VIEWER_TYPES = ("ViewerTabsChanged", "ViewerClip", "ViewerClipDropped")


def test_viewer_events_left_the_contracts() -> None:
    import assistant.contracts as contracts

    assert not any(hasattr(contracts, name) for name in VIEWER_TYPES)
    for file in (REPO / "src" / "assistant" / "contracts").rglob("*.py"):
        text = file.read_text(encoding="utf-8")
        assert "ViewerClip" not in text and "ViewerTabsChanged" not in text, file
    # Nowhere in the app either: the publisher and its listeners use the named events.
    for file in _python_files(REPO / "src"):
        assert not any(name in file.read_text(encoding="utf-8-sig") for name in VIEWER_TYPES), file
    from assistant.modules.html_viewer import HtmlViewerModule

    assert HtmlViewerModule.manifest.publishes_named == ("html_viewer.tabs_changed", "html_viewer.clip")


def test_html_viewer_app_defaults_and_tests_are_in_its_folder() -> None:
    toml = _module_toml("html_viewer")
    assert toml["needs"] == [] and toml["packages"] == []
    assert toml["port"] == 8766 and toml["start_on_use"] is True  # its defaults are here
    # The app in its folder, found by folder; a `python -m html_viewer` launch gets that folder on its path.
    app = HTML_VIEWER / "app"
    assert (app / "html_viewer" / "__main__.py").is_file() and not (app / "__init__.py").exists()
    loader.add_app_folders()
    assert package_root("html_viewer") == app
    base = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    child = subprocess.run([sys.executable, "-m", "html_viewer", "--help"], env=launch_env("html_viewer", base),
                           capture_output=True, text=True, timeout=60, check=True)  # fmt: skip
    assert "HTML viewer" in child.stdout
    assert (HTML_VIEWER / "tests" / "test_html_viewer.py").is_file()
    assert "html-viewer" not in (REPO / "pyproject.toml").read_text(encoding="utf-8")  # the old script entry


# Item 9: voice_in's app, packages and tests in its folder.

VOICE_IN = MODULES_FOLDER / "voice_in"


def test_voice_in_app_packages_and_tests_are_in_its_folder() -> None:
    toml = _module_toml("voice_in")
    assert toml["needs"] == [] and toml["port"] == 8767 and toml["terms"]  # its defaults are here
    assert any(p.startswith("websockets") for p in toml["packages"])
    default = _toml(REPO / "config" / "default.toml")
    assert "voice_in" not in default["modules"]
    # The service in its folder, its defaults beside its code, found by folder and launched from there.
    app = VOICE_IN / "app"
    assert (app / "voice_service" / "__main__.py").is_file() and not (app / "__init__.py").exists()
    assert (app / "voice_service" / "voice_service.toml").is_file()
    assert not (REPO / "config" / "voice_service.toml").exists()
    from voice_service.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG == app / "voice_service" / "voice_service.toml"
    assert app in loader.app_folders() and package_root("voice_service") == app
    base = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    child = subprocess.run([sys.executable, "-m", "voice_service", "--help"], env=launch_env("voice_service", base),
                           capture_output=True, text=True, timeout=60, check=True)  # fmt: skip
    assert "speech to text" in child.stdout.lower()
    # Its tests are in its folder (voice_notes' in voice_notes'), none left central; no script entry.
    assert (VOICE_IN / "tests" / "test_voice_in.py").is_file()
    assert (MODULES_FOLDER / "voice_notes" / "tests" / "test_voice_notes.py").is_file()
    assert not list((REPO / "tests").glob("test_voice*")) and not (REPO / "tests" / "voice_client.py").exists()
    assert "voice-service" not in (REPO / "pyproject.toml").read_text(encoding="utf-8")


# Item 10: voice_notes' defaults and needs in its module.toml, its page and tests in its folder
# (nothing of it outside: item 19).

VOICE_NOTES = MODULES_FOLDER / "voice_notes"


def test_voice_notes_has_its_module_toml() -> None:
    toml = _module_toml("voice_notes")
    assert toml["needs"] == ["voice_in"] and toml["packages"] == []
    assert toml["port"] == 8770 and toml["window"] == "app"  # its defaults are here
    assert _module_class("voice_notes").manifest.needs == ("voice_in",)
    assert (VOICE_NOTES / "page.html").is_file()
    assert (VOICE_NOTES / "tests" / "test_voice_notes.py").is_file()

# Item 11, first half: the core agent modules' defaults and tests in their folders.

CORE_AGENT_TESTS = {
    "agent_hub": ("test_agent_hub_parts.py",),
    "talker": ("test_talker.py", "test_talker_parts.py", "test_talker_prompt.py", "test_talker_snips.py"),
    "main_assistant": ("test_main_assistant.py",),
    "task_agents": ("test_task_agents.py",),
}


@pytest.mark.parametrize("module_id", sorted(CORE_AGENT_TESTS))
def test_core_agent_modules_have_their_module_toml_and_tests(module_id: str) -> None:
    folder = MODULES_FOLDER / module_id
    toml = _module_toml(module_id)
    assert toml["needs"] == [] and toml["packages"] == []  # a core module never needs an add-on
    assert _module_class(module_id).manifest.needs == ()
    default = _toml(REPO / "config" / "default.toml")
    assert module_id not in default["modules"]  # its defaults are in its module.toml, none here
    for name in CORE_AGENT_TESTS[module_id]:
        assert (folder / "tests" / name).is_file() and not (REPO / "tests" / name).exists(), name
    assert (folder / "tests" / "__init__.py").is_file()
    if module_id == "task_agents":  # its kinds of helper are its defaults
        assert {"helper", "rezi"} <= set(toml["agents"])

# Item 11, second half: the other core modules, then the whole item's rule for every module.

CORE_MODULE_TESTS = {
    "console_io": ("test_console_io.py",),
    "temp_ui": ("test_temp_ui.py", "test_temp_ui_snips.py", "test_taskbar_flash.py"),
    "usage": ("test_usage_module.py",),
    "echo_orchestrator": ("test_echo.py",),
    "assistant_view": (),  # no test of its own: it opens a console window (tests/test_swap_every_module.py swaps it)
}
LEFT_TESTS = ("test_temp_ui.py", "test_viewer_listeners.py", "test_taskbar_flash.py")  # moved out of tests/

# A central test file that names only one module, and why it stays central: it tests the core or a
# shared part, with that module as an example. Any other central file naming one module is module-only.
CENTRAL_ON_PURPOSE = {
    "test_app.py": "the core's App, with echo_orchestrator as the stand-in orchestrator",
    "test_directory.py": "the core's directory; modules.add loads echo_orchestrator's package",
    "test_edit_note.py": "the edit hook (scripts/hooks) and its env; one line of the worker's prompt",
    "test_menu.py": "the core's Menu part; html_viewer's menu as a real one",
    "test_permissions_handler.py": "the core's permissions handler; the Hub in two of its tests",
    "test_questions_as_messages.py": "the Hub's questions flow; cv's job notes as a module's notes",
    "test_reload.py": "the core's reload; voice_in named as a reloadable package",
}


def module_folders() -> list[Path]:
    return sorted(p for p in MODULES_FOLDER.iterdir() if (p / "__init__.py").is_file())


@pytest.mark.parametrize("module_id", sorted(CORE_MODULE_TESTS))
def test_the_other_core_modules_have_their_module_toml_and_tests(module_id: str) -> None:
    folder = MODULES_FOLDER / module_id
    toml = _module_toml(module_id)
    assert toml["needs"] == [] and toml["packages"] == []  # a core module never needs an add-on
    manifest = _module_class(module_id).manifest
    assert manifest.needs == () and manifest.packages == ()
    for name in CORE_MODULE_TESTS[module_id]:
        assert (folder / "tests" / name).is_file() and not (REPO / "tests" / name).exists(), name
    for name in LEFT_TESTS:
        assert not (REPO / "tests" / name).exists(), name


def test_every_module_folder_has_its_module_toml() -> None:
    missing = [p.name for p in module_folders() if not (p / "module.toml").is_file()]
    assert not missing, f"module folders without a module.toml: {missing}"
    assert len(module_folders()) >= 14


def test_config_default_toml_holds_no_module_defaults() -> None:
    default = _toml(REPO / "config" / "default.toml")
    left = sorted(k for k, v in default["modules"].items() if isinstance(v, dict) and v)
    assert not left, f"[modules.<id>] defaults still in config/default.toml (move them to module.toml): {left}"
    assert {"core", "logging"} <= set(default)  # the core's own settings stay


def _module_only_central_tests() -> dict[str, list[str]]:
    """The central test files (tests/test_*.py) that are one module's own, by its id: they name
    exactly that one module and aren't on CENTRAL_ON_PURPOSE."""
    ids = {p.name for p in module_folders()}
    found: dict[str, list[str]] = {}
    for path in sorted((REPO / "tests").glob("test_*.py")):
        named = set(re.findall(r"assistant\.modules\.(\w+)", path.read_text(encoding="utf-8"))) & ids
        if len(named) == 1 and path.name not in CENTRAL_ON_PURPOSE:
            found.setdefault(named.pop(), []).append(path.name)
    return found


def test_no_module_only_test_file_is_central() -> None:
    """A central test that names exactly one core module is that module's, unless it's listed with its
    reason (item 19's per-add-on test checks the add-ons)."""
    groups = _groups()
    module_only = {m: files for m, files in _module_only_central_tests().items() if groups[m] != "add-on"}
    assert not module_only, f"module-only tests under tests/ (move them into the module's tests/): {module_only}"
    assert all((REPO / "tests" / name).is_file() for name in CENTRAL_ON_PURPOSE)  # the list stays true


def _write(folder: Path, name: str, text: str) -> None:
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_config_modules_toml_holds_the_on_off_list() -> None:
    assert (REPO / "config" / "modules.toml").is_file()
    shipped = _toml(REPO / "config" / "modules.toml")
    assert "talker" in shipped["enabled"] and "agent_hub" in shipped["enabled"]
    default = _toml(REPO / "config" / "default.toml")
    assert "enabled" not in default.get("modules", {}), "the on/off list belongs in config/modules.toml"


def test_config_module_files_are_yours_and_ignored() -> None:
    def ignored(path: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO).returncode == 0

    assert ignored("config/temp_ui.toml") and ignored("config/temp_ui.local.toml") and ignored("config/permissions.toml")
    assert not ignored("config/modules.toml") and not ignored("config/default.toml")


def test_generated_is_ignored_and_set_in_the_core_config() -> None:
    """Item 14: generated/ is built by the core and the docs build, never committed."""
    assert subprocess.run(["git", "check-ignore", "-q", "generated/"], cwd=REPO).returncode == 0
    assert subprocess.run(["git", "check-ignore", "-q", "generated/modules.json"], cwd=REPO).returncode == 0
    default = _toml(REPO / "config" / "default.toml")
    assert default["core"]["generated_dir"] == "generated"


def test_a_modules_settings_load_from_its_config_file_over_its_module_toml(tmp_path) -> None:
    from assistant.infra.config import load_config, module_config_ids

    folder = tmp_path / "config"
    _write(folder, "default.toml", "[modules]\n[core]\ncommand_timeout = 7.0\n")
    _write(folder, "modules.toml", 'enabled = ["console_io"]\n')
    _write(folder, "temp_ui.toml", 'port = 9001\nwindow = "none"\n')
    _write(folder, "permissions.toml", '[grants]\nx = 1\n')  # the saved grants, never a module's file
    _write(folder, "voice_service.local.toml", "port = 1\n")
    cls = _module_class("temp_ui")

    def temp_ui_config() -> tuple[dict, dict]:
        config = load_config(folder)
        app = App([cls], {**config, "modules": {**config["modules"], "enabled": []}})  # only temp_ui is available
        return app._config_of("temp_ui"), config

    seen, config = temp_ui_config()
    assert seen["port"] == 9001 and seen["window"] == "none"  # config/temp_ui.toml over its module.toml
    assert seen["needs"] == []  # the rest still from module.toml
    assert config["modules"]["enabled"] == ["console_io"]  # config/modules.toml
    assert config["core"]["command_timeout"] == 7.0
    assert module_config_ids(folder) == ["temp_ui"]  # not permissions, voice_service, default, modules

    _write(folder, "temp_ui.local.toml", "port = 9002\n")
    _write(folder, "modules.local.toml", 'enabled = ["temp_ui"]\n')
    seen, config = temp_ui_config()
    assert seen["port"] == 9002 and seen["window"] == "none"  # .local over config/temp_ui.toml
    assert config["modules"]["enabled"] == ["temp_ui"]

    _write(folder, "local.toml", '[modules]\nenabled = ["talker"]\n[modules.temp_ui]\nport = 9003\n')
    seen, config = temp_ui_config()
    assert seen["port"] == 9003 and seen["window"] == "none"  # local.toml's section last
    assert config["modules"]["enabled"] == ["talker"]


def test_saved_grants_live_in_config_and_only_the_copy_names_the_old_file() -> None:
    """Item 13: the grants are in config/permissions.toml; the old data/ file is named in src only
    by the one-time copy (`OLD_GRANTS` beside `copy_old_grants` in store.py)."""
    from assistant.core.permissions import PermissionsHandler

    old = "data/permissions.toml"
    naming = sorted(f"{p.relative_to(REPO).as_posix()}:{n}" for p in (REPO / "src").rglob("*")
                    if p.is_file() and p.suffix in (".py", ".toml", ".md")
                    for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
                    if old in line)  # fmt: skip
    assert len(naming) == 1 and naming[0].startswith("src/assistant/core/permissions/store.py:"), naming
    default = inspect.signature(PermissionsHandler).parameters["grants_file"].default
    assert default == REPO / "config" / "permissions.toml"  # (the conftest points GRANTS_FILE into tmp)


def test_a_local_only_module_file_still_counts(tmp_path) -> None:
    from assistant.infra.config import load_config

    folder = tmp_path / "config"
    _write(folder, "default.toml", "[core]\n")
    _write(folder, "usage.local.toml", "x = 1\n")
    config = load_config(folder)
    assert config["modules"] == {"usage": {"x": 1}}  # no modules.toml: nothing enabled, no error


SRC = REPO / "src"
SHARED_CODE = (SRC / "assistant" / "core", SRC / "assistant" / "contracts", SRC / "assistant" / "infra", SRC / "app_kit")


def _groups() -> dict[str, str]:
    """Each module's group (`core` or `add-on`), from its docs/docs.toml."""
    return {p.name: _toml(p / "docs" / "docs.toml").get("group", "") for p in module_folders()}


def _code_strings(path: Path) -> list[tuple[int, str]]:
    """The string literals and imported names in `path`'s code, without its docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.append((node.lineno, node.value))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
    return found


# The add-ons: every module whose docs/docs.toml says group = "add-on" (read, not listed).
ADD_ONS = sorted(m for m, g in _groups().items() if g == "add-on")


def test_no_core_code_names_an_add_on() -> None:
    """Item 15: the core group and the shared code never name an add-on's id or its menu items."""
    assert {"html_viewer", "cv", "job_search", "voice_notes"} <= set(ADD_ONS)  # the list stays true
    classes = [_module_class(m) for m in ADD_ONS]
    tools = sorted({name for cls in classes if cls.menu is not None for name in cls.menu.names()})
    heard = sorted({name for cls in classes for name in cls.manifest.publishes_named}, key=len, reverse=True)
    assert "viewer.open" in tools and "viewer.highlight" in tools
    words = [re.compile(r"(?<![\w.])" + re.escape(w) + r"(?![\w])") for w in (*ADD_ONS, *tools)]
    folders = [MODULES_FOLDER / m for m, g in _groups().items() if g == "core"] + list(SHARED_CODE)
    naming = []
    for path in _python_files(*folders):
        if {"tests", "app"} & set(path.relative_to(SRC).parts):
            continue
        for line, text in _code_strings(path):
            for event in heard:  # an add-on's named event, heard by name (decision 9)
                text = text.replace(event, "")
            naming += [f"{path.relative_to(REPO).as_posix()}:{line}: {w.pattern}" for w in words if w.search(text)]
    assert not naming, f"core code naming an add-on (use a contract it provides instead): {naming}"


def test_no_viewer_tool_in_the_talker_temp_ui_or_infra() -> None:
    """Item 15's done-when, as `git grep -n "viewer\\.open"` over the three folders (code, docs, tests)."""
    folders = (MODULES_FOLDER / "temp_ui", MODULES_FOLDER / "talker", SRC / "assistant" / "infra")
    naming = [f"{p.relative_to(REPO).as_posix()}:{n}" for folder in folders for p in folder.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts
              for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
              if "viewer.open" in line]  # fmt: skip
    assert not naming, naming


def test_html_viewer_fills_the_page_opener_slot() -> None:
    from assistant.contracts import IPageOpener, StartProvider
    from assistant.infra import AGENT_SENDS, AGENT_USES

    assert IPageOpener in _module_class("html_viewer").manifest.provides
    assert _module_toml("html_viewer")["start_on_use"] is True  # opening a page still turns it on (StartProvider)
    for module_id in ("talker", "temp_ui"):
        manifest = _module_class(module_id).manifest
        assert IPageOpener in manifest.uses and StartProvider in manifest.sends, module_id
    assert IPageOpener in AGENT_USES and StartProvider in AGENT_SENDS  # every worker's SHOW tags


# Item 17: cv_agent works from modules/cv/workspace/.


def test_cv_agent_works_from_its_module_workspace() -> None:
    """Item 17's done-when, as `git grep -n "CV_Module" src`, plus where the workspace and its grant are."""
    found = subprocess.run(["git", "grep", "-n", "CV_" + "Module", "--", "src"], cwd=REPO,
                           capture_output=True, text=True).stdout  # fmt: skip
    assert not found, found
    from assistant.modules.cv.module import settings

    checked = settings(_module_toml("cv"))
    workspace = Path(checked["agent"]["config"]["workspace"])
    assert workspace == CV / "workspace" and Path(checked["output_dir"]) == workspace / "out"
    assert Path(checked["work_dir"]).is_relative_to(workspace) and Path(checked["tool"]["data_dir"]) == workspace / "cv_tool"
    ignored = subprocess.run(["git", "check-ignore", "-q", "src/assistant/modules/cv/workspace/x"], cwd=REPO)
    assert ignored.returncode == 0  # its files (your CVs, facts, jobs) never reach git
    pyproject = _toml(REPO / "pyproject.toml")
    assert "workspace" in pyproject["tool"]["pytest"]["ini_options"]["norecursedirs"]  # its old scripts aren't ours
    # the grant: its own module folder (written) holds the workspace, which is asked first
    items = access_items(checked["agent"]["config"], "cv")
    assert items[0].target == str(workspace) and str(CV) in _writes(items)
    with pytest.raises(ValueError, match="own workspace"):  # elsewhere in the repo is still refused
        settings(_module_toml("cv") | {"work_dir": str(CV / "work")})


# Item 18: job_search_agent works from modules/job_search/workspace/.


def test_job_search_agent_works_from_its_module_workspace() -> None:
    """Item 18's done-when: no committed job_search code or config names the old job project
    folder; the workspace (and the job UI's default script) is the module's own, gitignored and
    skipped by pytest; the grant asks for it first, with the module's own folder written."""
    found = subprocess.run(["git", "grep", "-n", "-E", r"Chang[\\/]+Jobs[\\/]+CV", "--", "src/assistant/modules/job_search",
                            ":!src/assistant/modules/job_search/docs"], cwd=REPO, capture_output=True, text=True).stdout  # fmt: skip
    assert not found, found
    from assistant.modules.job_search.module import job_config
    from assistant.modules.job_search.ui import ui_settings
    from assistant.testkit import module_config

    checked = job_config(module_config("job_search"))
    workspace = Path(checked["workspace"])
    assert workspace == JOB_SEARCH / "workspace" and not checked.get("write_dirs")  # no documents shipped
    script = ui_settings({}, checked["workspace"], checked["python"])["script"]
    assert Path(script) == workspace / "Recruiters" / "scripts" / "job_ui.py"
    ignored = subprocess.run(["git", "check-ignore", "-q", "src/assistant/modules/job_search/workspace/x"], cwd=REPO)
    assert ignored.returncode == 0  # its files (your job state, the copied scripts) never reach git
    pyproject = _toml(REPO / "pyproject.toml")
    assert "workspace" in pyproject["tool"]["pytest"]["ini_options"]["norecursedirs"]  # the job project's own tests
    items = access_items(checked, "job_search")
    assert items[0].target == str(workspace) and str(JOB_SEARCH) in _writes(items)


# Item 19: the rule holds for every add-on.


def _workspaces(table: dict, prefix: str = "") -> list[tuple[str, object]]:
    """Every `workspace` key in a TOML table, nested ones too, as (dotted key, value)."""
    found: list[tuple[str, object]] = []
    for key, value in table.items():
        if isinstance(value, dict):
            found += _workspaces(value, f"{prefix}{key}.")
        elif key == "workspace":
            found.append((prefix + key, value))
    return found


def _committed(folder: str) -> list[str]:
    """The files git tracks under `folder` (repo-relative, forward slashes)."""
    return subprocess.run(["git", "ls-files", "--", folder], cwd=REPO, capture_output=True, text=True,
                          check=True).stdout.split()  # fmt: skip


@pytest.mark.parametrize("add_on", ADD_ONS)
def test_nothing_of_an_add_on_is_outside_its_folder(add_on: str) -> None:
    """Delete an add-on's folder and nothing of it is left behind, except your own (gitignored) choices
    in config/. Its app is in its app/ folder, never src/<app>; its needs and packages are in its
    module.toml and its ruff rules in its ruff.toml, none in pyproject.toml; its defaults are in its
    module.toml, never in committed config/ (beyond the on/off list); its tests are in its tests/, none
    in the central tests/; its agent's workspace is in its own folder, never outside the repo."""
    folder = MODULES_FOLDER / add_on
    here = folder.relative_to(REPO).as_posix()
    toml = _module_toml(add_on)
    left: list[str] = []
    # Its app, if any, in app/<its package>, found by folder; no src/<app> or src/<its id>.
    apps = _apps(folder)
    left += [f"src/{name} (belongs in {here}/app/)" for name in (add_on, *apps) if (SRC / name).exists()]
    if apps and (folder / "app" not in loader.app_folders() or (folder / "app" / "__init__.py").exists()):
        left.append(f"{here}/app isn't found by folder as its apps' folder")
    # Its needs and packages in its module.toml, reaching its manifest; nothing of it in pyproject.toml.
    manifest = _module_class(add_on).manifest
    for key in ("needs", "packages"):
        if key not in toml:
            left.append(f"{here}/module.toml has no `{key}`")
        elif tuple(toml[key]) != getattr(manifest, key):
            left.append(f"{here}/module.toml's `{key}` doesn't reach its manifest")
    left += _pyproject_leaks(add_on, by_id=True)
    # No defaults of it in committed config (the on/off list may name it), and no config file of its own committed.
    for name in ("default.toml", "modules.toml"):
        committed = _toml(REPO / "config" / name)
        if add_on in committed:
            left.append(f"config/{name}: [{add_on}]")
        if add_on in committed.get("modules", {}):
            left.append(f"config/{name}: [modules.{add_on}]")
    left += [f"{path} is committed (config/<id>.toml is yours, gitignored)" for path in _committed("config")
             if Path(path).name.split(".")[0] == add_on]  # fmt: skip
    # Its tests in its tests/; none central, by name or by naming only it.
    if not list((folder / "tests").glob("test_*.py")):
        left.append(f"{here}/tests/ has no test_*.py")
    left += [f"{p.relative_to(REPO).as_posix()} (belongs in {here}/tests/)" for p in sorted((REPO / "tests").rglob("*"))
             if add_on in p.name.lower() and "__pycache__" not in p.parts]  # fmt: skip
    left += [f"tests/{name} tests only {add_on} (belongs in {here}/tests/)"
             for name in _module_only_central_tests().get(add_on, [])]  # fmt: skip
    # Its agent's workspace (any `workspace` key in its module.toml) in its own folder, never outside the repo.
    left += [f"{here}/module.toml: {key} = {value!r} is outside {here}" for key, value in _workspaces(toml)
             if not in_module_folder(add_on, value).is_relative_to(folder)]  # fmt: skip
    assert not left, f"add-on {add_on!r} has pieces outside its folder {here}: {left}"
