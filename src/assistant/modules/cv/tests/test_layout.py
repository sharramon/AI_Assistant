"""cv in module layout step 1 (docs/next-steps/module-layout-step1-checklist.md, items 3 and 4): its
agent skips the repo's CLAUDE.md, and your data folder (`data_folder`, config/cv.toml) becomes its
workspace, with everything kept in it, copied there at its first use."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assistant.contracts import ListModules, ModuleState, PermissionMode
from assistant.core import App
from assistant.infra import AgentProfile
from assistant.modules.cv import CvModule
from assistant.modules.cv.module import settings, with_defaults

CV = Path(__file__).resolve().parents[1]  # cv's own module folder


def test_its_agent_skips_the_repo_claude_md(tmp_path) -> None:
    agent = settings(with_defaults({}))["agent"]
    assert agent["config"]["repo_claude_md"] is False
    profile = AgentProfile.from_config(agent["agent_id"], {**agent["config"], "workspace": str(tmp_path),
                                                           "module_folder": str(CV)})  # fmt: skip
    command = profile.command("p", PermissionMode.MANUAL)
    assert "claudeMdExcludes" in json.loads(command[command.index("--settings") + 1])
    assert str(CV / "docs" / "README.md") in command[command.index("--append-system-prompt") + 1]


def test_unset_the_worker_stays_in_its_module_workspace() -> None:
    checked = settings(with_defaults({}))
    assert checked["data_folder"] == "" and Path(checked["agent"]["config"]["workspace"]) == CV / "workspace"
    assert checked["data_from"] == str(CV / "workspace")


def test_a_data_folder_is_the_workspace_with_everything_in_it(tmp_path) -> None:
    data = tmp_path / "cv_data"
    checked = settings(with_defaults({"data_folder": str(data)}))
    assert checked["data_folder"] == str(data.resolve()) and checked["data_from"] == str(CV / "workspace")
    assert Path(checked["agent"]["config"]["workspace"]) == data.resolve()
    assert Path(checked["output_dir"]) == data.resolve() / "out" and Path(checked["work_dir"]) == data.resolve() / "work"
    assert Path(checked["tool"]["data_dir"]) == data.resolve() / "cv_tool"
    assert Path(checked["rules_dir"]).is_relative_to(data.resolve())
    assert all(Path(s).is_relative_to(data.resolve()) for s in checked["job_skills"])
    with pytest.raises(ValueError, match="outside the repo"):
        settings(with_defaults({"data_folder": str(CV / "data")}))


async def test_turning_it_on_copies_the_old_workspace_once(tmp_path) -> None:
    old, data = tmp_path / "old", tmp_path / "data"
    (old / "out").mkdir(parents=True)
    (old / "out" / "CV_Test_Acme.pdf").write_bytes(b"%PDF")
    section = {"data_folder": str(data), "agent": {"enabled": False, "workspace": str(old)}}
    app = App([CvModule], {"modules": {"enabled": ["cv"], "cv": section}, "core": {}})
    await app.start()
    try:
        states = {m.id: m.state for m in (await app.router.send(ListModules())).value}
        assert states["cv"] is ModuleState.ACTIVE
        assert (data / "out" / "CV_Test_Acme.pdf").read_bytes() == b"%PDF"
        assert (old / "out" / "CV_Test_Acme.pdf").is_file()  # copied, never moved
    finally:
        await app.stop()
