"""The job agent bundled with its module: an ITaskAgent beside the others, Chrome, its job.search callback."""

import asyncio
import sys
from pathlib import Path

import pytest

from app_kit.window import window_profile
from assistant.contracts import (
    AgentNotice,
    AnswerPermissionRequest,
    InvokeTool,
    ListAgents,
    PermissionMode,
    PermissionRequested,
    Status,
)
from assistant.core import App
from assistant.infra.agent_profile import path_rule
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.job_search import JobSearchModule
from assistant.modules.job_search.module import JOB_PROMPT, UI_SHORTCUT
from assistant.modules.job_search.ui import ui_settings
from assistant.modules.talker.prompt import talker_prompt
from assistant.testkit import FAKE, FAKE_JOB_UI, free_port, module_config, pre_grant, stand_in, wait_until

FOLDER = Path(__file__).resolve().parents[1]  # job_search's own module folder


async def start_app(tmp_path, ui: dict | None = None) -> App:
    """The Hub and job_search, with a stand-in for cv (job_search needs cv: it's turned on first)."""
    section = {"program": FAKE, "workspace": str(tmp_path / "CV"), "chrome": True}
    if ui is not None:
        section["ui"] = ui
    config = {
        "modules": {
            "enabled": ["agent_hub", "job_search"],
            "agent_hub": {"door": False},
            "job_search": section,
        },
        "core": {},
    }
    app = App([AgentHubModule, stand_in("cv"), JobSearchModule], config)
    pre_grant(app, "job_search", "job_search_agent", module_config("job_search", section))
    await app.start()
    return app


def test_its_defaults_are_in_its_module_toml_under_the_apps_section():
    # The config the module sees: module.toml, with [modules.job_search] (config/local.toml) over it.
    defaults = module_config("job_search")
    assert defaults["needs"] == ["cv"] and defaults["packages"] == []
    for key in ("workspace", "read_dirs", "python", "tools", "permission_mode", "transcript"):
        assert defaults[key], key
    assert defaults["chrome"] is True and defaults["permission_timeout"] == 600.0
    assert JobSearchModule.manifest.needs == ("cv",)
    app = App([stand_in("cv"), JobSearchModule],
              {"modules": {"enabled": [], "job_search": {"workspace": "C:/elsewhere", "ui": {"port": 9}}}, "core": {}})  # fmt: skip
    seen = app._config_of("job_search")
    assert seen["workspace"] == "C:/elsewhere" and seen["ui"] == {"port": 9}  # yours wins
    assert {k: v for k, v in seen.items() if k not in ("workspace", "ui")} == {
        k: v for k, v in defaults.items() if k != "workspace"}  # the rest unchanged


async def test_turning_it_on_turns_on_cv_first(tmp_path):
    app = await start_app(tmp_path)
    try:
        started = list(app._lifecycle._active)  # in start order; cv isn't in modules.enabled
        assert "cv" in started and started.index("cv") < started.index("job_search")
    finally:
        await app.stop()


async def test_the_job_agent_is_a_big_agent_with_chrome_and_the_projects_rules(tmp_path):
    app = await start_app(tmp_path)
    try:
        listed = await app.router.send(ListAgents())
        assert [a.agent_id for a in listed.value] == ["job_search_agent"] and listed.value[0].permission_mode is PermissionMode.MANUAL
        job = app._lifecycle._active["job_search"][0]._agent
        command = job.profile.command("prompt", PermissionMode.MANUAL)
        assert "--chrome" in command
        assert "don't run handoff.ps1" in JOB_PROMPT and "Never submit" in JOB_PROMPT
        # its workspace, then its own module folder (every module can edit itself)
        own = str(FOLDER)
        assert job.profile.write_folders() == (str((tmp_path / "CV").resolve()), own)
    finally:
        await app.stop()


async def test_job_search_answers_at_once_and_notes_its_caller(tmp_path):
    app = await start_app(tmp_path)
    notices: asyncio.Queue[AgentNotice] = asyncio.Queue()
    app.bus.subscribe(AgentNotice, notices.put)
    try:
        started = await app.router.send(InvokeTool(name="job.search", args={"days": 7}, caller="main_assistant"))
        assert started.is_ok and "main_assistant" in started.value
        notice = await asyncio.wait_for(notices.get(), 2)
        assert (notice.agent_id, notice.source) == ("main_assistant", "job.search") and "7 days" in notice.text
        nobody = await app.router.send(InvokeTool(name="job.search", args={}))
        assert nobody.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()


async def test_open_the_ui_means_job_open_ui_for_the_agent_and_its_tabs_talker(tmp_path):
    app = await start_app(tmp_path)
    try:
        prompt = JOB_PROMPT.format(agent_id="job_search_agent", ui_shortcut=UI_SHORTCUT)
        assert UI_SHORTCUT in prompt and "job.open_ui" in UI_SHORTCUT and "no searching for a tool" in UI_SHORTCUT
        listed = await app.router.send(ListAgents())
        about = listed.value[0].description
        assert UI_SHORTCUT in about  # the description the tab's Talker reads
        talker = talker_prompt("job_search_agent", "main_assistant", about, door=True)
        assert '"Open the UI" or "open the job UI" means calling job.open_ui' in talker
    finally:
        await app.stop()


def test_job_config_resolves_its_workspace_and_writes_your_documents(tmp_path):
    from assistant.modules.job_search.module import job_config

    shipped = job_config({})
    assert Path(shipped["workspace"]) == FOLDER / "workspace" and "write_dirs" not in shipped  # its own, no documents
    docs = tmp_path / "docs"
    mine = job_config({"workspace": str(tmp_path / "ws"), "documents": str(docs), "write_dirs": [str(tmp_path / "x")]})
    assert mine["workspace"] == str(tmp_path / "ws") and "documents" not in mine
    assert mine["write_dirs"] == [str(tmp_path / "x"), str(docs)]  # read and write (decision 5)
    assert job_config({"documents": str(docs), "write_dirs": [str(docs)]})["write_dirs"] == [str(docs)]  # once
    with pytest.raises(ValueError, match="documents"):
        job_config({"documents": ["C:/x"]})


def test_the_job_uis_settings_default_to_the_job_projects_script_and_python():
    settings = ui_settings({}, "C:/Jobs/CV", "C:/py/python.exe")
    assert Path(settings["script"]) == Path("C:/Jobs/CV/Recruiters/scripts/job_ui.py")
    assert (settings["python"], settings["port"], settings["page"]) == ("C:/py/python.exe", 8781, "/tracker")
    for wrong in ({"port": 0}, {"page": "tracker"}, "x"):
        with pytest.raises(ValueError):
            ui_settings(wrong, "C:/Jobs/CV", "C:/py/python.exe")


async def test_job_open_ui_starts_the_job_ui_once_and_keeps_one_fresh_window(tmp_path, monkeypatch):
    calls: list[tuple[str, object]] = []  # ("close" | "open", profile), in order
    monkeypatch.setattr("assistant.modules.job_search.ui.close_app_windows",
                        lambda profile, **kw: calls.append(("close", profile)))  # fmt: skip
    monkeypatch.setattr("assistant.modules.job_search.ui.open_app_window",
                        lambda url, profile, **kw: calls.append(("open", profile)) or object())  # fmt: skip
    port = free_port()
    script = FAKE_JOB_UI
    monkeypatch.setattr("assistant.modules.job_search.ui.EDGE", [Path(script)])  # "Edge is installed" anywhere
    app = await start_app(tmp_path, {"script": script, "python": sys.executable, "port": port})
    try:
        first = await app.router.send(InvokeTool(name="job.open_ui", args={}, caller="job_search_agent"))
        assert first.is_ok, first.error
        assert first.value["launched"] is True and first.value["url"] == f"http://127.0.0.1:{port}/tracker"
        again = await app.router.send(InvokeTool(name="job.open_ui", args={}))
        assert again.is_ok and again.value["launched"] is False  # answering: no second server
        profile = window_profile("job_ui")
        # Each open closes the window on the job UI's own profile, then opens a fresh one: one window.
        assert calls == [("close", profile), ("open", profile)] * 2
        ui = app._lifecycle._active["job_search"][0].ui
    finally:
        await app.stop()
    assert not await ui.running()  # it launched it, so its stop ended it


async def test_job_open_ui_never_falls_back_to_a_browser_tab(tmp_path, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("assistant.modules.job_search.ui.EDGE", [tmp_path / "no-edge.exe"])
    monkeypatch.setattr("app_kit.window.webbrowser.open", opened.append)
    script = FAKE_JOB_UI
    app = await start_app(tmp_path, {"script": script, "python": sys.executable, "port": free_port()})
    try:
        refused = await app.router.send(InvokeTool(name="job.open_ui", args={}))
        assert refused.status is Status.NOT_AVAILABLE and "Edge" in refused.error
        assert opened == [] and not await app._lifecycle._active["job_search"][0].ui.running()
    finally:
        await app.stop()


async def test_job_open_ui_says_so_when_the_script_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("assistant.modules.job_search.ui.EDGE", [Path(__file__)])
    app = await start_app(tmp_path, {"script": str(tmp_path / "none.py"), "python": sys.executable})
    try:
        missing = await app.router.send(InvokeTool(name="job.open_ui", args={}))
        assert missing.status is Status.NOT_AVAILABLE and "none.py" in missing.error
    finally:
        await app.stop()


async def test_a_grant_reaches_the_job_agents_next_session_live(tmp_path):
    app = await start_app(tmp_path)
    cards: list[PermissionRequested] = []

    async def record(event):
        cards.append(event)

    app.bus.subscribe(PermissionRequested, record)
    try:
        job = app._lifecycle._active["job_search"][0]._agent
        snips = str(tmp_path / "logs" / "snips")
        assert path_rule("Read", snips) in ",".join(job.profile.command("p", PermissionMode.MANUAL, snips=snips))
        more = tmp_path / "drafts"
        asked = await app.router.send(InvokeTool(name="permissions.request", caller="job_search_agent",
                                                 args={"write": [str(more)], "read": [str(tmp_path / "jobs")]}))  # fmt: skip
        assert asked.is_ok, asked.error
        await wait_until(lambda: cards)
        await app.router.send(AnswerPermissionRequest(request_id=cards[0].request_id, allow=True,
                                                      keep=tuple(i.key for i in cards[0].items)))  # fmt: skip
        resolved = str(more.resolve())
        await wait_until(lambda: resolved in job.agent.info().write_folders)
        command = ",".join(job.profile.command("p", PermissionMode.MANUAL))
        assert path_rule("Edit", resolved) in command and path_rule("Read", str((tmp_path / "jobs").resolve())) in command
        assert app._lifecycle._active["job_search"][0]._agent is job  # no off and on
    finally:
        await app.stop()
