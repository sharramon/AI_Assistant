"""`modules.remove` (module folders item 16): never refused (the modules that need it stay on);
keep or purge its settings files only."""

from pathlib import Path

from assistant.contracts import InvokeTool, ListModules, Manifest, ModuleProtocol, ModuleState, Status
from assistant.core import App
from assistant.testkit import make_config as _make_config

YOU = "ui"  # you clicking: modules.remove runs at once, no confirm card (tests/test_risky_steps_ask.py)


def make_config(*enabled):
    return _make_config(*enabled, permissions={"you": [YOU]})


class Base(ModuleProtocol):
    manifest = Manifest(id="base", description="Needed by others")

    async def init(self, ctx):
        pass


class NeedsBase(ModuleProtocol):
    manifest = Manifest(id="needs_base", needs=("base",))

    async def init(self, ctx):
        pass


def _config_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "config"
    folder.mkdir()
    for name in ("base.toml", "base.local.toml", "local.toml", "modules.toml", "needs_base.toml", "default.toml"):
        (folder / name).write_text("x = 1\n", encoding="utf-8")
    return folder


async def _remove(app: App, module_id: str, settings: str):
    return await app.router.send(InvokeTool(name="modules.remove", args={"module_id": module_id, "settings": settings},
                                                caller=YOU))


async def _ids(app: App) -> dict[str, ModuleState]:
    return {m.id: m.state for m in (await app.router.send(ListModules())).value}


async def test_remove_works_while_another_module_needs_it(tmp_path):
    folder = _config_dir(tmp_path)
    app = App([Base, NeedsBase], make_config("needs_base"), config_dir=folder)
    await app.start()
    try:
        result = await _remove(app, "base", "keep")
        assert result.is_ok, result.error
        assert result.value["still_on"] == ["needs_base"]
        assert "Still on, and needing it: needs_base." in result.value["message"]
        ids = await _ids(app)
        assert "base" not in ids and ids["needs_base"] is ModuleState.ACTIVE
        assert (folder / "base.toml").is_file() and (folder / "base.local.toml").is_file()  # kept
        unknown = await _remove(app, "nope", "keep")
        assert unknown.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()


async def test_remove_with_keep_deletes_nothing(tmp_path):
    folder = _config_dir(tmp_path)
    before = sorted(p.name for p in folder.iterdir())
    app = App([Base, NeedsBase], make_config("base"), config_dir=folder)
    await app.start()
    try:
        result = await _remove(app, "base", "keep")
        assert result.is_ok, result.error
        assert result.value["deleted"] == [] and len(result.value["kept"]) == 2
        assert result.value["enabled"] is True and "config/modules.toml" in result.value["message"]
        assert "yours to delete" in result.value["message"]
        assert "base" not in await _ids(app)  # turned off and out of the list for this run
        assert sorted(p.name for p in folder.iterdir()) == before
        # needs_base can't start without it now.
        on = await app.router.send(InvokeTool(name="modules.on", args={"module_id": "needs_base"}))
        assert not on.is_ok
    finally:
        await app.stop()


async def test_remove_with_purge_deletes_only_its_two_settings_files(tmp_path):
    folder = _config_dir(tmp_path)
    module_folder = Path(__file__).parent  # the test modules' "folder": never touched
    app = App([Base, NeedsBase], make_config(), config_dir=folder)
    await app.start()
    try:
        result = await _remove(app, "base", "purge")
        assert result.is_ok, result.error
        assert sorted(Path(p).name for p in result.value["deleted"]) == ["base.local.toml", "base.toml"]
        assert result.value["kept"] == [] and result.value["enabled"] is False
        assert sorted(p.name for p in folder.iterdir()) == [
            "default.toml", "local.toml", "modules.toml", "needs_base.toml"
        ]
        assert all((folder / n).read_text(encoding="utf-8") == "x = 1\n" for n in ("local.toml", "modules.toml"))
        assert module_folder.is_dir() and Path(__file__).is_file()
        assert "base" not in await _ids(app)
    finally:
        await app.stop()


async def test_remove_never_takes_a_file_that_isnt_one_modules(tmp_path):
    """A module whose id names a shared config file (`local`) has no settings files to purge."""
    folder = _config_dir(tmp_path)

    class Local(ModuleProtocol):
        manifest = Manifest(id="local")

        async def init(self, ctx):
            pass

    app = App([Local], make_config(), config_dir=folder)
    await app.start()
    try:
        result = await _remove(app, "local", "purge")
        assert result.is_ok and result.value["deleted"] == []
        assert (folder / "local.toml").is_file()
    finally:
        await app.stop()
