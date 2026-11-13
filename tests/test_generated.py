"""generated/ (module folders item 14): the core writes the live module list, the directory and the
dependencies at start and on every module state change; deleted, it comes back on the next change."""

from __future__ import annotations

import json
import shutil

from assistant.contracts import ActivateModule, DeactivateModule, Manifest, Menu, ModuleProtocol, Result
from assistant.core import App
from assistant.testkit import Calculator, make_config, stand_in

menu = Menu()


class Counter(ModuleProtocol):
    manifest = Manifest(id="counter", description="Counts", needs=("helper",), packages=("tomli-w",))
    menu = menu

    async def init(self, ctx):
        self.count = 0

    @menu.item("counter.add", "Add one")
    async def add(self) -> Result:
        self.count += 1
        return Result.ok(self.count)


def read(folder, name):
    return json.loads((folder / name).read_text(encoding="utf-8"))


async def test_the_core_writes_generated_and_rewrites_it_after_a_delete(tmp_path) -> None:
    folder = tmp_path / "generated"
    app = App([Calculator, Counter, stand_in("helper")], make_config("calculator", generated_dir=str(folder)))
    await app.start()
    try:
        modules = read(folder, "modules.json")
        assert "_generated" in modules
        assert {m["id"]: m["state"] for m in modules["modules"]} == {
            "calculator": "active", "counter": "inactive", "helper": "inactive"}
        directory = {m["id"]: m for m in read(folder, "directory.json")["modules"]}
        assert [t["name"] for t in directory["counter"]["tools"]] == ["counter.add"]
        assert directory["counter"]["description"] == "Counts"
        assert any(t["name"] == "modules.list" for t in directory["core"]["tools"])
        dependencies = read(folder, "dependencies.json")["modules"]
        assert dependencies["counter"] == {"needs": ["helper"], "requires": [], "packages": ["tomli-w"]}

        shutil.rmtree(folder)
        assert (await app.router.send(ActivateModule(module_id="counter"))).is_ok
        states = {m["id"]: m["state"] for m in read(folder, "modules.json")["modules"]}
        assert states["counter"] == "active" and states["helper"] == "active"  # its need came up first

        assert (await app.router.send(DeactivateModule(module_id="counter"))).is_ok
        assert {m["id"]: m["state"] for m in read(folder, "modules.json")["modules"]}["counter"] == "inactive"
        assert not list(folder.glob("*.tmp"))  # written atomically, nothing left behind
    finally:
        await app.stop()


async def test_no_generated_dir_writes_nothing_and_a_failed_write_never_raises(tmp_path) -> None:
    app = App([Calculator], make_config("calculator"))
    assert app.generated.folder is None
    await app.start()
    await app.stop()

    blocker = tmp_path / "file"
    blocker.write_text("not a folder", encoding="utf-8")
    app = App([Calculator], make_config("calculator", generated_dir=str(blocker / "generated")))
    await app.start()  # the write fails (a file is in the way): logged, the app still runs
    assert (await app.router.send(DeactivateModule(module_id="calculator"))).is_ok
    await app.stop()
