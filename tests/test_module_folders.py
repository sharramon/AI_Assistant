"""The module-folders migration's tripwires (docs/next-steps/module-folders-checklist.md): one
test per finished item, so a done item can't slip back.

Item 1: every module can edit itself by default. A module's own agent asks for a write on its
own module folder only, and the Hub lets it work beside the Main Assistant's whole-repo grant,
while two agents on one module folder are still refused, with the folder named."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from assistant.contracts import AccessKind, StartTask, Status
from assistant.infra import MODULES_FOLDER, access_items, module_folder, module_folder_of, request_access
from assistant.modules.agent_hub.tasks import folders_clash
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
