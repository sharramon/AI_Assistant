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
from assistant.modules.cv.tests.pdf_fixture import write_pdf
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
    for needed in ("You are cv_agent", "95 or more", "at most 3 rounds", "app.rezi.ai", "WITHOUT resume_id",
                   "The 5 steps", "Job & CV", "cv.open_tool", "cv.tool_status", "cv.tool_round",
                   "cv.check_fonts", "pick Internal or Rezi in the CV Tool's tab 2", "First Draft", "ATS Loop",
                   "the user's review of the First Draft", "Start only when the user tells you to",
                   "never download Rezi's PDF", "copy the same change into the content", "never shrink the font",
                   "CV_Test_<Company>_final.pdf", "keywords_left_out", "Never add a skill", "NEED:",
                   "end your task", 'status "ready"', "[cv] line", 'end as "approved"',
                   "C:/Chang/Jobs/CV", "CV_JOB:", "base_cv_copy",
                   "Work only in work_dir", "never run a script or command on a file in C:/Chang/Jobs/CV",
                   "CV_Test_*.pdf", "the job description (JD) as text", "PDFs only", "confirmed facts"):  # fmt: skip
        assert needed in prompt, needed
    assert "odt_path" not in prompt and "CV_Test_*.odt" not in prompt
    # design A: no NEED for the Submit, no cv.tool_result check (the cv module delivers the Submit itself)
    assert "cv.tool_result" not in prompt and "ready for their Submit." not in prompt
    assert "Don't ask them to tell you when they've submitted" in prompt
    assert "cv.build" not in prompt and "<Company> – check" not in prompt  # the old LibreOffice page and import check
    assert WORKER_PROMPT.count("{") == WORKER_PROMPT.count("}")


# --- the worker in the app -----------------------------------------------------------------------------


SKILL_TEXT = "# Test rules\nNever run a script on a file in the CV folder; copy it first."


def section(tmp_path: Path, **agent) -> dict:
    """cv's config for a test app, all in tmp_path (its one rule file written here)."""
    rules = tmp_path / "rules" / "SKILL.md"
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(SKILL_TEXT, encoding="utf-8")
    return {"output_dir": str(tmp_path / "out"), "cv_dir": str(tmp_path / "CV"),
            "token_file": str(tmp_path / "token.json"), "job_skills": [str(rules)], "rules_dir": "",
            "tool": {"data_dir": str(tmp_path / "cv_tool"), "port": 18771},
            "agent": {"program": FAKE, "workspace": str(tmp_path / "cv_agent"),
                      "read_dirs": [str(tmp_path / "CV")]} | agent}  # fmt: skip


def app_with(tmp_path: Path, grant: bool = True, extra: tuple = (), **agent) -> App:
    """The Hub and cv, all in tmp_path; `extra`: more module classes, enabled too."""
    own = section(tmp_path, **agent)
    enabled = ["agent_hub", "cv", *(m.manifest.id for m in extra)]
    config = {"modules": {"enabled": enabled, "agent_hub": {"door": False}, "cv": own}, "core": {}}
    app = App([AgentHubModule, CvModule, *extra], config)
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
        # its workspace, then its own module folder (every module can edit itself)
        own = str(Path(__file__).resolve().parents[1])
        assert worker.profile.write_folders() == (str((tmp_path / "cv_agent").resolve()), own)
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


async def test_cv_read_gives_the_sections_of_any_pdf_and_refuses_an_odt_or_a_missing_file(tmp_path):
    order = SectionOrder.from_config(DEFAULTS).usual
    base = write_pdf(CV, order, tmp_path / "CV" / "CV_Test_Base.pdf")
    elsewhere = write_pdf(CV, order, tmp_path / "other" / "My Resume.pdf")  # any folder, no prefix
    odt = OdtWriter().write(CV, order, tmp_path / "CV" / "CV_Test_Base.odt")  # a real .odt: still refused
    garbled = tmp_path / "CV" / "CV_Test_Garbled.pdf"
    garbled.write_bytes(b"not a pdf")
    app = app_with(tmp_path, enabled=False)
    await app.start()
    try:
        read = await app.router.send(InvokeTool(name="cv.read", args={"pdf": str(base)}, caller="cv_agent"))
        assert read.is_ok, read.error
        assert read.value["sections"]["experience"] == list(CV.lines("experience"))
        assert list(read.value["names"]) == ["contact", "skills", "experience"]
        assert read.value["complete"] is True and read.value["unplaced"] == [] and read.value["pages"] == 1
        assert "next" not in read.value
        anywhere = await app.router.send(InvokeTool(name="cv.read", args={"pdf": str(elsewhere)}, caller="cv_agent"))
        assert anywhere.is_ok, anywhere.error  # any existing .pdf, as given
        assert anywhere.value["sections"]["experience"] == list(CV.lines("experience"))
        refused = await app.router.send(InvokeTool(name="cv.read", args={"pdf": str(odt)}, caller="cv_agent"))
        assert refused.status is Status.INVALID_ARGUMENTS and ".odt isn't read" in refused.error
        for pdf in (str(tmp_path / "CV" / "missing.pdf"), str(tmp_path / "CV" / "notes.txt"), str(garbled)):
            refused = await app.router.send(InvokeTool(name="cv.read", args={"pdf": pdf}, caller="cv_agent"))
            assert refused.status is Status.INVALID_ARGUMENTS, pdf
        old = await app.router.send(InvokeTool(name="cv.read", args={"odt": str(odt)}, caller="cv_agent"))
        assert old.status is Status.INVALID_ARGUMENTS  # the old argument is gone
    finally:
        await app.stop()


async def test_cv_read_says_stop_and_ask_when_text_cant_be_placed(tmp_path):
    base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_Base.pdf",
                     extra=((14.0, "Hobbies"), (10.0, "chess")))  # a heading it doesn't know  # fmt: skip
    app = app_with(tmp_path, enabled=False)
    await app.start()
    try:
        read = await app.router.send(InvokeTool(name="cv.read", args={"pdf": str(base)}, caller="cv_agent"))
        assert read.is_ok and read.value["complete"] is False and read.value["unplaced"] == ["Hobbies", "chess"]
        assert "NEED:" in read.value["next"]
    finally:
        await app.stop()
