"""job_search in module layout step 1 (docs/next-steps/module-layout-step1-checklist.md, items 3 and 4):
its agent skips the repo's CLAUDE.md (its project's own CLAUDE.md still loads from its workspace), and
your data folder (`data_folder`, config/job_search.toml) becomes its workspace, copied there at its first
use with the paths file still pointing where it did."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assistant.contracts import PermissionMode
from assistant.infra import AgentProfile, repo_claude_md_files
from assistant.modules.job_search.module import copy_job_data, fix_copied_paths, is_absolute_anywhere, job_config
from assistant.testkit import module_config

FOLDER = Path(__file__).resolve().parents[1]  # job_search's own module folder


def test_its_agent_skips_the_repo_claude_md_only(tmp_path) -> None:
    checked = job_config(module_config("job_search"))
    assert checked["repo_claude_md"] is False
    profile = AgentProfile.from_config("job_search_agent", {**checked, "workspace": str(tmp_path),
                                                            "module_folder": str(FOLDER)})  # fmt: skip
    command = profile.command("p", PermissionMode.MANUAL)
    excludes = json.loads(command[command.index("--settings") + 1])["claudeMdExcludes"]
    assert excludes == repo_claude_md_files()
    assert (Path(checked["workspace"]) / "CLAUDE.md").as_posix() not in excludes  # its project's CLAUDE.md loads


def test_unset_the_agent_stays_in_its_module_workspace() -> None:
    checked = job_config(module_config("job_search"))
    assert Path(checked["workspace"]) == FOLDER / "workspace" and "data_folder" not in checked
    assert not copy_job_data(module_config("job_search"))  # nothing set: nothing copied


def test_a_data_folder_is_its_workspace(tmp_path) -> None:
    checked = job_config(module_config("job_search", {"data_folder": str(tmp_path / "jobs")}))
    assert Path(checked["workspace"]) == (tmp_path / "jobs").resolve() and "data_folder" not in checked
    with pytest.raises(ValueError, match="outside the repo"):
        job_config(module_config("job_search", {"data_folder": str(FOLDER / "data")}))


def test_the_first_use_copies_and_keeps_the_paths_file_true(tmp_path) -> None:
    old, data = tmp_path / "repo" / "job_search" / "workspace", tmp_path / "jobs"
    (old / "Recruiters" / "docs").mkdir(parents=True)
    (old / "Recruiters" / "docs" / "queue.md").write_text("mine", encoding="utf-8")
    paths = {"documents": "C:/Jobs/CV", "cv_output": "../../cv/workspace/out", "jobs": "~/Jobs"}
    (old / "job_paths.json").write_text(json.dumps(paths), encoding="utf-8")
    config = {"workspace": str(old), "data_folder": str(data)}
    assert copy_job_data(config)
    assert (data / "Recruiters" / "docs" / "queue.md").read_text(encoding="utf-8") == "mine"
    copied = json.loads((data / "job_paths.json").read_text(encoding="utf-8"))
    assert copied["cv_output"] == (tmp_path / "repo" / "cv" / "workspace" / "out").as_posix()  # where it pointed
    assert copied["documents"] == "C:/Jobs/CV" and copied["jobs"] == "~/Jobs"  # absolute and ~ kept as they were
    assert json.loads((old / "job_paths.json").read_text(encoding="utf-8")) == paths  # the old one untouched
    assert not copy_job_data(config)  # once
    fix_copied_paths(old, tmp_path / "nowhere")  # no paths file: left alone


def test_windows_drive_paths_count_as_absolute_on_any_system() -> None:
    assert is_absolute_anywhere("C:/Jobs/CV") and is_absolute_anywhere("D:\\cv") and is_absolute_anywhere("~/Jobs")
    assert is_absolute_anywhere("//server/share/cv") and is_absolute_anywhere(str(Path.cwd()))
    assert not is_absolute_anywhere("../../cv/workspace/out") and not is_absolute_anywhere("C:relative")
