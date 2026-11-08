"""Chunk 6: the worker cv_agent (a ProfileAgent with Chrome, its prompt and access) and cv.read.
A fake `claude` only: no session talks to Rezi, and nothing outside tmp_path is touched."""

import tomllib
from pathlib import Path

import pytest

from app_kit.config import merge
from assistant.contracts import (
    InvokeTool,
    ListAgents,
    ListModules,
    ModuleState,
    PermissionMode,
    PermissionRequested,
    ReloadModule,
    Status,
)
from assistant.core import App
from assistant.infra.agent_profile import path_rule
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.cv import CvModule
from assistant.modules.cv.content import CvContent
from assistant.modules.cv.module import settings
from assistant.modules.cv.odt import OdtWriter
from assistant.modules.cv.order import SectionOrder
from assistant.modules.cv.worker import AGENT_ID, WORKER_PROMPT, worker_config, worker_prompt
from tests.support import pre_grant, wait_until
from tests.test_agents import FAKE

DEFAULTS = tomllib.loads((Path(__file__).parents[1] / "module.toml").read_text(encoding="utf-8"))
CV = CvContent(sections={"contact": ("Ada Lovelace", "ada@example.com"), "skills": ("Python",),
                         "experience": ("Engineer, Engines | Jan 2020 – Present", "• Wrote the first program.")})  # fmt: skip


# --- the worker's config and prompt --------------------------------------------------------------------


def test_the_default_worker_is_cv_agent_with_chrome_and_reads_the_output_folder():
    agent = settings(DEFAULTS)["agent"]
    assert agent["enabled"] is True and agent["agent_id"] == AGENT_ID == "cv_agent"
    config = agent["config"]
    assert config["chrome"] is True and config["permission_mode"] == "acceptEdits"
    assert "enabled" not in config and "agent_id" not in config
    assert config["read_dirs"] == ["C:/Chang/Jobs/CV", DEFAULTS["output_dir"]]
    # the output folder isn't added twice, and no [agent] table means the menu only
    again = worker_config({"read_dirs": [DEFAULTS["output_dir"] + "/"]}, DEFAULTS["output_dir"])
    assert len(again["config"]["read_dirs"]) == 1
    assert worker_config({"enabled": False}, "")["enabled"] is False
    plain = {k: v for k, v in DEFAULTS.items() if k != "agent"}
    assert settings(plain)["agent"]["enabled"] is False


@pytest.mark.parametrize("bad", [
    {"enabled": "yes"}, {"agent_id": "CV Agent"}, {"agent_id": ""}, {"read_dirs": "C:/Chang/Jobs/CV"},
])  # fmt: skip
def test_a_bad_agent_table_stops_the_config_check(bad):
    with pytest.raises(ValueError, match="agent"):
        settings(merge(DEFAULTS, {"agent": bad}))
    with pytest.raises(ValueError, match="table"):
        worker_config("cv_agent", "")


def test_the_prompt_holds_the_steps_the_truth_gate_and_the_config():
    checked = settings(merge(DEFAULTS, {"target_score": 95, "max_rounds": 3}))
    prompt = worker_prompt("cv_agent", checked, "C:/Chang/Jobs/CV")
    assert "{" not in prompt and "}" not in prompt  # every placeholder filled
    for needed in ("You are cv_agent", "95 or more", "at most 3 rounds", "paper letter", "app.rezi.ai",
                   "WITHOUT resume_id", "Free Resume formatting review\" OFF", "<Company> – check",
                   "cv.read", "cv.compare (parsed_resume)", "cv.report", "keywords_left_out",
                   "Never add a skill", "NEED:", "without the user's yes", "C:/Chang/Jobs/CV",
                   DEFAULTS["output_dir"]):  # fmt: skip
        assert needed in prompt, needed
    assert WORKER_PROMPT.count("{") == WORKER_PROMPT.count("}")


# --- the worker in the app -----------------------------------------------------------------------------


def section(tmp_path: Path, **agent) -> dict:
    return {"output_dir": str(tmp_path / "out"), "cv_dir": str(tmp_path / "CV"),
            "token_file": str(tmp_path / "token.json"),
            "agent": {"program": FAKE, "workspace": str(tmp_path / "cv_agent"),
                      "read_dirs": [str(tmp_path / "CV")]} | agent}  # fmt: skip


def app_with(tmp_path: Path, grant: bool = True, **agent) -> App:
    own = section(tmp_path, **agent)
    config = {"modules": {"enabled": ["agent_hub", "cv"], "agent_hub": {"door": False}, "cv": own}, "core": {}}
    app = App([AgentHubModule, CvModule], config)
    if grant:
        pre_grant(app, "cv", "cv_agent", settings(merge(DEFAULTS, own))["agent"]["config"])
    return app


def cv_module(app: App) -> CvModule:
    return app._lifecycle._active["cv"][0]


async def cv_state(app: App) -> ModuleState:
    return {m.id: m.state for m in (await app.router.send(ListModules())).value}["cv"]


async def test_the_worker_is_a_big_agent_in_manual_with_chrome_and_its_folders(tmp_path):
    app = app_with(tmp_path)
    await app.start()
    try:
        assert await cv_state(app) is ModuleState.ACTIVE
        listed = await app.router.send(ListAgents())
        agents = {a.agent_id: a for a in listed.value}
        assert agents["cv_agent"].permission_mode is PermissionMode.MANUAL
        worker = cv_module(app).worker
        assert not worker.session.running  # the session starts on its first task, never on load
        command = ",".join(worker.profile.command("p", PermissionMode.MANUAL))
        assert "--chrome" in command
        assert path_rule("Read", str((tmp_path / "out").resolve())) in command
        assert path_rule("Read", str((tmp_path / "CV").resolve())) in command
        assert worker.profile.write_folders() == (str((tmp_path / "cv_agent").resolve()),)
        assert (await app.router.send(InvokeTool(name="rezi.status", caller="cv_agent"))).is_ok  # the menu too
    finally:
        await app.stop()


async def test_without_a_grant_cv_waits_on_one_card_and_with_the_worker_off_on_none(tmp_path):
    cards: list[PermissionRequested] = []

    async def record(event):
        cards.append(event)

    app = app_with(tmp_path, grant=False)
    app.bus.subscribe(PermissionRequested, record)
    await app.start()
    try:
        await wait_until(lambda: cards)
        assert await cv_state(app) is not ModuleState.ACTIVE
        assert not (tmp_path / "cv_agent").exists()  # nothing made before your yes
        assert any(i.kind.value == "chrome" for i in cards[0].items)
    finally:
        await app.stop()

    cards.clear()
    off = app_with(tmp_path / "off", grant=False, enabled=False)
    off.bus.subscribe(PermissionRequested, record)
    await off.start()
    try:
        assert await cv_state(off) is ModuleState.ACTIVE and not cards
        assert cv_module(off).worker is None
        listed = await off.router.send(ListAgents())
        assert "cv_agent" not in [a.agent_id for a in listed.value]
    finally:
        await off.stop()


async def test_a_reload_brings_the_worker_back_and_keeps_the_guard(tmp_path):
    app = app_with(tmp_path)
    await app.start()
    try:
        cv_module(app).guard.created("r1", "Acme – Engineer")
        assert (await app.router.send(ReloadModule(module_id="cv", now=True))).is_ok
        fresh = cv_module(app)
        assert fresh.worker is not None and fresh.guard.owns("r1")
        assert "cv_agent" in [a.agent_id for a in (await app.router.send(ListAgents())).value]
    finally:
        await app.stop()


# --- cv.read -------------------------------------------------------------------------------------------


async def test_cv_read_gives_the_sections_of_an_odt_in_the_cv_folder_only(tmp_path):
    order = SectionOrder.from_config(DEFAULTS).usual
    base = OdtWriter().write(CV, order, tmp_path / "CV" / "CV_Test_Base.odt")
    elsewhere = OdtWriter().write(CV, order, tmp_path / "other" / "CV_Test_Base.odt")
    app = app_with(tmp_path, enabled=False)
    await app.start()
    try:
        read = await app.router.send(InvokeTool(name="cv.read", args={"odt": str(base)}, caller="cv_agent"))
        assert read.is_ok, read.error
        assert read.value["sections"]["experience"] == list(CV.lines("experience"))
        assert list(read.value["names"]) == ["contact", "skills", "experience"]
        for odt in (str(elsewhere), str(tmp_path / "CV" / "missing.odt"), str(tmp_path / "CV" / "notes.txt")):
            refused = await app.router.send(InvokeTool(name="cv.read", args={"odt": odt}, caller="cv_agent"))
            assert refused.status is Status.INVALID_ARGUMENTS, odt
    finally:
        await app.stop()
