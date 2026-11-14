"""The job agent bundled with its module: an ITaskAgent beside the others, Chrome, its job.search callback."""

import sys
from pathlib import Path

import pytest

from app_kit.window import window_profile
from assistant.contracts import (
    AccessItem,
    AccessKind,
    AnswerPermissionRequest,
    DeliverMessage,
    InvokeTool,
    ITaskAgent,
    ListAgents,
    ListModules,
    Manifest,
    Menu,
    ModuleProtocol,
    ModuleState,
    PermissionMode,
    PermissionRequested,
    Result,
    Status,
)
from assistant.core import App
from assistant.infra.agent_profile import path_rule
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.job_search import JobSearchModule
from assistant.modules.job_search.module import JOB_PROMPT, UI_SHORTCUT
from assistant.modules.job_search.ui import ui_settings
from assistant.modules.talker.prompt import talker_prompt
from assistant.testkit import FAKE, FAKE_JOB_UI, FakeAgent, free_port, module_config, pre_grant, wait_until

FOLDER = Path(__file__).resolve().parents[1]  # job_search's own module folder


async def start_app(tmp_path, ui: dict | None = None, cv: type | None = None, cv_wait: float | None = None) -> App:
    """The Hub and job_search; `cv`: a module class standing in for cv, off at start."""
    section = {"program": FAKE, "workspace": str(tmp_path / "CV"), "chrome": True}
    if ui is not None:
        section["ui"] = ui
    if cv_wait is not None:
        section["cv_wait"] = cv_wait
    config = {
        "modules": {
            "enabled": ["agent_hub", "job_search"],
            "agent_hub": {"door": False},
            "job_search": section,
        },
        "core": {"permissions": {"you": ["temp_ui"]}},
    }
    app = App([AgentHubModule, JobSearchModule, *([cv] if cv else [])], config)
    pre_grant(app, "job_search", "job_search_agent", module_config("job_search", section))
    await app.start()
    return app


def fake_cv(fails: str = "", card: bool = False) -> tuple[type, list]:
    """A cv stand-in whose menu has only `cv.task`, recording (caller, args). `fails`: its start
    raises that; `card`: its start asks for cv_agent's access list (a card unless granted)."""
    calls: list[tuple[str, dict]] = []
    cv_menu = Menu()

    class FakeCv(ModuleProtocol):
        manifest = Manifest(id="cv", permissions=("agent.access",))
        menu = cv_menu

        async def init(self, ctx) -> None:
            self._ctx = ctx

        async def start(self) -> None:
            if fails:
                raise RuntimeError(fails)
            if card:
                await self._ctx.permissions.request_set([AccessItem(kind=AccessKind.CHROME)], subject="cv_agent")

        @cv_menu.item("cv.task", "The fake hand-off", {k: {"type": "string"} for k in
                      ("company", "role", "base_cv", "jd_text", "for_agent")})  # fmt: skip
        async def task(self, caller: str = "", **args) -> Result:
            calls.append((caller, args))
            return Result.ok({"agent_id": "cv_agent", "task_id": "t9"})

    return FakeCv, calls


def told(app: App, monkeypatch) -> list[DeliverMessage]:
    """The messages job_search sends its agent, caught before the Hub (no claude runs)."""
    job = app._lifecycle._active["job_search"][0]
    caught: list[DeliverMessage] = []
    real = job._ctx.send

    async def send(command, *args, **kwargs):
        if isinstance(command, DeliverMessage):
            caught.append(command)
            return Result.ok("caught")
        return await real(command, *args, **kwargs)

    monkeypatch.setattr(job._ctx, "send", send)
    return caught


async def cv_state(app: App) -> ModuleState:
    return next(i.state for i in (await app.router.send(ListModules())).value if i.id == "cv")


JOB = {"company": "Acme", "role": "Engineer", "base_cv": "C:/x/CV_Test_Base.pdf", "jd_text": "Build things."}


def test_its_defaults_are_in_its_module_toml_under_the_apps_section():
    # The config the module sees: module.toml, with [modules.job_search] (config/local.toml) over it.
    defaults = module_config("job_search")
    assert defaults["needs"] == [] and defaults["packages"] == [] and defaults["cv_wait"] == 600.0
    for key in ("workspace", "read_dirs", "python", "tools", "permission_mode", "transcript"):
        assert defaults[key], key
    assert defaults["chrome"] is True and defaults["permission_timeout"] == 600.0
    assert JobSearchModule.manifest.needs == ()
    app = App([JobSearchModule],
              {"modules": {"enabled": [], "job_search": {"workspace": "C:/elsewhere", "ui": {"port": 9}}}, "core": {}})  # fmt: skip
    seen = app._config_of("job_search")
    assert seen["workspace"] == "C:/elsewhere" and seen["ui"] == {"port": 9}  # yours wins
    assert {k: v for k, v in seen.items() if k not in ("workspace", "ui")} == {
        k: v for k, v in defaults.items() if k != "workspace"}  # the rest unchanged


async def test_turning_it_on_leaves_cv_off(tmp_path):
    cv, calls = fake_cv()
    app = await start_app(tmp_path, cv=cv)
    try:
        assert "job_search" in app._lifecycle._active and "cv" not in app._lifecycle._active
        assert await cv_state(app) is ModuleState.INACTIVE and not calls
    finally:
        await app.stop()


async def test_tailor_cv_turns_cv_on_sends_cv_task_for_its_agent_and_tells_it(tmp_path, monkeypatch):
    cv, calls = fake_cv()
    app = await start_app(tmp_path, cv=cv)
    messages = told(app, monkeypatch)
    try:
        started = await app.router.send(InvokeTool(name="job.tailor_cv", args=JOB, caller="job_search_agent"))
        assert started.is_ok and "turning cv on" in started.value
        await wait_until(lambda: messages)
        assert await cv_state(app) is ModuleState.ACTIVE
        assert calls == [("job_search", {**JOB, "for_agent": "job_search_agent"})]
        message = messages[0]
        assert (message.agent_id, message.sender) == ("job_search_agent", "job_search")
        assert message.text.startswith("cv has the CV job for Engineer at Acme") and "task t9" in message.text
        again = await app.router.send(InvokeTool(name="job.tailor_cv", args=JOB, caller="job_search_agent"))
        assert again.is_ok  # cv already on: straight to cv.task
        await wait_until(lambda: len(calls) == 2 and len(messages) == 2)
    finally:
        await app.stop()


async def test_tailor_cv_is_only_for_the_job_agent(tmp_path):
    cv, calls = fake_cv()
    app = await start_app(tmp_path, cv=cv)
    try:
        for caller in ("main_assistant", "cv_agent", ""):
            refused = await app.router.send(InvokeTool(name="job.tailor_cv", args=JOB, caller=caller))
            assert refused.status is Status.NOT_AVAILABLE and "job_search_agent" in refused.error, caller
        assert await cv_state(app) is ModuleState.INACTIVE and not calls
    finally:
        await app.stop()


async def test_tailor_cv_asks_about_the_untailored_pdf_when_cv_cant_come_on(tmp_path, monkeypatch):
    cv, calls = fake_cv(fails="no soffice")
    app = await start_app(tmp_path, cv=cv)
    messages = told(app, monkeypatch)
    try:
        assert (await app.router.send(InvokeTool(name="job.tailor_cv", args=JOB, caller="job_search_agent"))).is_ok
        await wait_until(lambda: messages)
        text = messages[0].text
        assert text.startswith("cv couldn't take the CV job") and "no soffice" in text
        assert "untailored (C:/x/CV_Test_Base.pdf)" in text and "NEED" in text and not calls
    finally:
        await app.stop()


async def test_tailor_cv_waits_on_cvs_card_then_sends_on_allow_and_gives_up_on_deny(tmp_path, monkeypatch):
    cv, calls = fake_cv(card=True)
    app = await start_app(tmp_path, cv=cv)
    cards: list[PermissionRequested] = []

    async def record(event):
        cards.append(event)

    app.bus.subscribe(PermissionRequested, record)
    messages = told(app, monkeypatch)
    try:
        # Deny: no cv.task, the untailored question.
        assert (await app.router.send(InvokeTool(name="job.tailor_cv", args=JOB, caller="job_search_agent"))).is_ok
        await wait_until(lambda: cards)
        assert (cards[0].module_id, cards[0].subject) == ("cv", "cv_agent") and not messages  # it waits
        await app.router.send(AnswerPermissionRequest(request_id=cards[0].request_id, allow=False))
        await wait_until(lambda: messages)
        assert "wasn't allowed" in messages[0].text and "untailored" in messages[0].text and not calls

        # Asked again (a denied list opens a new card), Allow: cv comes on and gets the job.
        assert (await app.router.send(InvokeTool(name="job.tailor_cv", args=JOB, caller="job_search_agent"))).is_ok
        await wait_until(lambda: len(cards) == 2)
        await app.router.send(AnswerPermissionRequest(request_id=cards[1].request_id, allow=True))
        await wait_until(lambda: len(messages) == 2)
        assert messages[1].text.startswith("cv has the CV job") and calls[0][0] == "job_search"
        assert await cv_state(app) is ModuleState.ACTIVE
    finally:
        await app.stop()


async def test_tailor_cv_stops_waiting_after_cv_wait(tmp_path, monkeypatch):
    cv, calls = fake_cv(card=True)
    app = await start_app(tmp_path, cv=cv, cv_wait=0.2)
    messages = told(app, monkeypatch)
    try:
        assert (await app.router.send(InvokeTool(name="job.tailor_cv", args=JOB, caller="job_search_agent"))).is_ok
        await wait_until(lambda: messages)
        assert "no answer on cv_agent's access card in 0.2 seconds" in messages[0].text and not calls
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
    main = FakeAgent("main_assistant", ())  # the Hub handles AgentNotice and hands it to the agent's `note`
    app.container.provide(ITaskAgent, main, "test")
    try:
        started = await app.router.send(InvokeTool(name="job.search", args={"days": 7}, caller="main_assistant"))
        assert started.is_ok and "main_assistant" in started.value
        await wait_until(lambda: main.notes)
        assert main.notes[0].startswith("[job_search] ") and "7 days" in main.notes[0]  # the sender's module id
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
