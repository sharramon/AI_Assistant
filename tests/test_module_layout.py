"""Module layout step 1 (docs/next-steps/module-layout-step1-checklist.md): the shared parts.

Item 1 (the line made hard) is in `test_boundaries.py`.

Item 2: the repo's CLAUDE.md imports only the short overview, which stays short and names no add-on; the
API index covers the core only (no add-on id, no add-on menu item).

Item 3: a module's own agent skips the repo's CLAUDE.md: `claude_command`'s `settings` become `--settings`,
and `AgentProfile` with `repo_claude_md = false` passes `claudeMdExcludes` and the developer rules instead.
The modules' own settings are checked in their tests (cv's and job_search's `test_layout.py`).

Item 4: a data folder named by a module's config: outside the repo, unset means today's workspace, and its
first use copies the old workspace in, never moving or deleting anything.
"""

from __future__ import annotations

import json
import logging
import re
import tomllib
from pathlib import Path

import pytest

from assistant.contracts import PermissionMode
from assistant.core import loader
from assistant.infra import (
    MODULES_FOLDER,
    REPO_FOLDER,
    AgentProfile,
    ProfileAgent,
    claude_command,
    copy_data_once,
    data_folder,
)
from assistant.infra.agent_profile import DEVELOPER_RULES, developer_rules, repo_claude_md_files

REPO = REPO_FOLDER
SHORT_OVERVIEW = "docs/architecture/short-overview.md"
MAX_SHORT = 6000  # characters (about 1.5k tokens); the full overview is about 19k


def _add_ons() -> list[str]:
    def group(folder: Path) -> str:
        toml = folder / "docs" / "docs.toml"
        return tomllib.loads(toml.read_text(encoding="utf-8")).get("group", "") if toml.is_file() else ""

    return sorted(p.name for p in MODULES_FOLDER.iterdir() if (p / "module.toml").is_file() and group(p) == "add-on")


def _naming(text: str, words: list[str]) -> list[str]:
    return [w for w in words if re.search(r"(?<![\w.])" + re.escape(w) + r"(?![\w])", text)]


# Item 2: CLAUDE.md and the short overview.


def test_claude_md_imports_only_the_short_overview() -> None:
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    imports = re.findall(r"^@(\S+)", text, re.M)
    assert imports == [SHORT_OVERVIEW], imports
    assert "docs/architecture/README.md" in text and "docs/api/README.md" in text  # linked, not loaded
    assert "batching" in text and "docs-html" in text  # its other instructions stay


def test_the_short_overview_is_short_and_names_no_add_on() -> None:
    text = (REPO / SHORT_OVERVIEW).read_text(encoding="utf-8")
    assert len(text) < MAX_SHORT, f"the short overview grew to {len(text)} characters"
    add_ons = _add_ons()
    assert {"cv", "job_search", "html_viewer"} <= set(add_ons)
    assert not _naming(text, add_ons), _naming(text, add_ons)


def test_the_api_index_covers_the_core_only() -> None:
    text = (REPO / "docs" / "api" / "README.md").read_text(encoding="utf-8")
    add_ons = _add_ons()
    classes = [loader.find_module_class(__import__(f"assistant.modules.{m}", fromlist=["_"]), m) for m in add_ons]
    tools = sorted({name for cls in classes if cls.menu is not None for name in cls.menu.names()})
    assert "viewer.open" in tools
    found = _naming(text, [*add_ons, *tools])
    assert not found, f"the API index names add-ons (their API belongs on their own docs page): {found}"


# Item 3: claudeMdExcludes for a module's own agent.


def _option(command: list[str], flag: str) -> str | None:
    return command[command.index(flag) + 1] if flag in command else None


def test_claude_command_passes_settings() -> None:
    settings = {"claudeMdExcludes": ["C:/x/CLAUDE.md"]}
    command = claude_command(settings=settings)
    assert json.loads(_option(command, "--settings")) == settings
    assert "--settings" not in claude_command() and "--settings" not in claude_command(settings={})


def test_a_module_agent_skips_the_repo_claude_md(tmp_path) -> None:
    folder = MODULES_FOLDER / "cv"
    own = AgentProfile.from_config("its_agent", {"workspace": str(tmp_path), "repo_claude_md": False,
                                                 "module_folder": str(folder)})  # fmt: skip
    for mode in PermissionMode:
        command = own.command("Its prompt.", mode)
        excludes = json.loads(_option(command, "--settings"))["claudeMdExcludes"]
        assert excludes == repo_claude_md_files() and (REPO / "CLAUDE.md").as_posix() in excludes
        prompt = _option(command, "--append-system-prompt")
        assert prompt.startswith("Its prompt.") and prompt.endswith(developer_rules(str(folder)))
        assert str(folder / "docs" / "README.md") in prompt and "reusable.md" in prompt
    # The default (the Main Assistant, the helpers): CLAUDE.md loads, no rules added.
    plain = AgentProfile.from_config("main", {"workspace": str(tmp_path)})
    command = plain.command("Its prompt.", PermissionMode.MANUAL)
    assert plain.repo_claude_md and "--settings" not in command
    assert "developer rules" not in _option(command, "--append-system-prompt")
    with pytest.raises(ValueError, match="repo_claude_md"):
        AgentProfile.from_config("x", {"workspace": str(tmp_path), "repo_claude_md": "no"})


def test_the_developer_rules_file() -> None:
    import assistant.infra.agent_profile as agent_profile

    assert DEVELOPER_RULES.is_file() and DEVELOPER_RULES.parent == Path(agent_profile.__file__).parent  # beside its code
    text = developer_rules(None)
    assert "(none)" in text and "{" not in text and len(text) < 2000
    assert (REPO / "CLAUDE.md").is_file() and repo_claude_md_files()[0] == (REPO / "CLAUDE.md").as_posix()


def test_profile_agent_names_its_module_folder(tmp_path) -> None:
    class _Session:
        def __init__(self, command, **kwargs):
            self.on_event = None

    class _Ctx:
        log = logging.getLogger("test")
        module_id = "cv"

    config = {"workspace": str(tmp_path), "repo_claude_md": False}
    agent = ProfileAgent(_Ctx(), "its_agent", config, "prompt", session_factory=_Session)
    assert agent.profile.module_folder == str(MODULES_FOLDER / "cv") and not agent.profile.repo_claude_md
    _Ctx.module_id = "no_such_module"  # a stand-in module: no folder named
    assert ProfileAgent(_Ctx(), "other", config, "prompt", session_factory=_Session).profile.module_folder is None


# Item 4: the data folder.


def test_the_data_folder_key(tmp_path) -> None:
    assert data_folder("m", {}) is None and data_folder("m", {"data_folder": ""}) is None  # unset: today's workspace
    assert data_folder("m", {"data_folder": str(tmp_path / "d")}) == (tmp_path / "d").resolve()
    assert data_folder("m", {"data_folder": "~/x"}) == (Path.home() / "x").resolve()
    for bad, why in ((1, "must be a folder"), ("relative/x", "absolute"), (str(REPO / "data"), "outside the repo"),
                     (str(MODULES_FOLDER / "m" / "workspace"), "outside the repo")):  # fmt: skip
        with pytest.raises(ValueError, match=why):
            data_folder("m", {"data_folder": bad})


def test_the_first_use_copies_never_moves(tmp_path) -> None:
    old = tmp_path / "old"
    (old / "work" / "__pycache__").mkdir(parents=True)
    (old / "work" / "job.txt").write_text("mine", encoding="utf-8")
    (old / "work" / "__pycache__" / "x.pyc").write_bytes(b"0")
    new = tmp_path / "data"
    assert copy_data_once(old, new)
    assert (new / "work" / "job.txt").read_text(encoding="utf-8") == "mine"
    assert not (new / "work" / "__pycache__").exists()
    assert (old / "work" / "job.txt").is_file() and (old / "work" / "__pycache__" / "x.pyc").is_file()  # kept
    # Used: never copied over again, even when the old folder changed.
    (old / "work" / "job.txt").write_text("changed", encoding="utf-8")
    assert not copy_data_once(old, new)
    assert (new / "work" / "job.txt").read_text(encoding="utf-8") == "mine"
    # An empty data folder is filled; a missing old workspace copies nothing.
    empty = tmp_path / "empty"
    empty.mkdir()
    assert copy_data_once(old, empty) and (empty / "work" / "job.txt").is_file()
    assert not copy_data_once(tmp_path / "none", tmp_path / "data2") and not (tmp_path / "data2").exists()
