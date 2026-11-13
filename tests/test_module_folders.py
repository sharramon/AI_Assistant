"""The module-folders migration's tripwires (docs/next-steps/module-folders-checklist.md): one
test per finished item, so a done item can't slip back.

Item 1: every module can edit itself by default. A module's own agent asks for a write on its
own module folder only, and the Hub lets it work beside the Main Assistant's whole-repo grant,
while two agents on one module folder are still refused, with the folder named.

Item 2: a `needs` list. cv's module.toml declares `needs`, the core puts it on the manifest, and
the lifecycle turns needed modules on first and refuses to turn one off while a module needs it.

Item 3: cv's `[agent]` section is complete. cv_agent's `named_only = true` is in its own section,
not in agent_hub's config; the Hub reads it from the agent (`AgentInfo.named_only`)."""

from __future__ import annotations

import asyncio
import tomllib
from types import SimpleNamespace

import pytest

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
from tests.support import make_config
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
