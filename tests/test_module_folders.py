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
shared fakes and helpers are in `assistant.testkit`, which only tests import; no cv test is central."""

from __future__ import annotations

import ast
import asyncio
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
from assistant.infra import MODULES_FOLDER, access_items, module_folder, module_folder_of, request_access
from assistant.infra.profile_agent import named_only
from assistant.modules.agent_hub.tasks import folders_clash
from assistant.modules.cv import CvModule
from assistant.testkit import FAKE, FAKE_JOB_UI, make_config
from tests.test_agent_hub_parts import FakeAgent, Rig

REPO = MODULES_FOLDER.parents[2]
CV = MODULES_FOLDER / "cv"


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
    toml = tomllib.loads((CV / "module.toml").read_text(encoding="utf-8"))
    assert toml["needs"] == []
    assert loader.apply_needs(CvModule).manifest.needs == ()
    # A module.toml's needs reach the manifest; a wrong value or the module's own id is refused.
    class FromToml(Base):
        manifest = Manifest(id="from_toml")

    monkeypatch.setattr(loader, "module_defaults", lambda cls: {"needs": ["base_part"]})
    assert loader.apply_needs(FromToml).manifest.needs == ("base_part",)
    for bad in ("base_part", ["from_toml"], [1]):
        monkeypatch.setattr(loader, "module_defaults", lambda cls, bad=bad: {"needs": bad})
        with pytest.raises(loader.LoadError):
            loader.apply_needs(FromToml)


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
    toml = tomllib.loads((CV / "module.toml").read_text(encoding="utf-8"))
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

# Where companion apps used to live, outside their module. Items 8 and 9 add src/html_viewer, src/voice_service.
OLD_APPS = ["src/cv_tool"]
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


# Item 5: cv's tests in its module, on the public test kit.

TESTKIT = REPO / "src" / "assistant" / "testkit"
SKIPPED = {"__pycache__", "workspace", ".venv"}  # an agent's workspace holds its own files, not the app's


def _python_files(*folders: Path) -> list[Path]:
    return [f for folder in folders for f in folder.rglob("*.py") if not SKIPPED & set(f.relative_to(REPO).parts)]


def test_module_tests_use_only_the_testkit() -> None:
    files = _python_files(MODULES_FOLDER)
    assert any(f.parts[-2] == "tests" for f in files)  # the modules' own tests are in the walk
    for file in files:
        assert not any(n == "tests" or n.startswith("tests.") for n in _imports(file)), file


def test_no_cv_only_test_is_central() -> None:
    assert (CV / "tests" / "test_worker.py").is_file()  # cv's tests are in its folder
    central = [f.name for f in (REPO / "tests").rglob("*") if "cv" in f.name.lower() and "__pycache__" not in f.parts]
    assert central == []


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
