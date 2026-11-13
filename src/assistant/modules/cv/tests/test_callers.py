"""cv-path hardening (docs/next-steps/cv-path-hardening.md) and agent-talk-and-questions: the job agent
gets only cv.task and cv.read_result, and cv.task starts cv_agent itself (no coordinator in between).
The caller is set by the core, as the module door does after checking an agent's token."""

from assistant.contracts import GetTaskStatus, Status
from assistant.modules.cv.handoff import read_request
from assistant.modules.cv.order import SectionOrder
from assistant.modules.cv.tests.pdf_fixture import write_pdf
from assistant.modules.cv.tests.test_handoff import JD, use
from assistant.modules.cv.tests.test_worker import CV, DEFAULTS, app_with

JOB_AGENT = "job_search_agent"


async def test_the_job_agent_is_refused_the_workers_items_and_a_free_pick_skips_cv_agent(tmp_path):
    app = app_with(tmp_path)
    await app.start()
    try:
        for name, args in (("cv.open_tool", {"job_dir": str(tmp_path)}), ("cv.tool_round", {"job_id": "j1"}),
                           ("cv.tool_status", {"job_id": "j1"}), ("cv.check_fonts", {"job_id": "j1"}),
                           ("cv.build", {"company": "Acme"}), ("cv.read", {"pdf": "x.pdf"}),
                           ("rezi.write_resume", {"resume": {"name": "x"}}), ("rezi.list_resumes", {}),
                           ("rezi.sign_in", {})):  # fmt: skip
            refused = await use(app, name, caller=JOB_AGENT, **args)
            assert refused.status is Status.NOT_AVAILABLE and "only for: cv_agent" in refused.error, name
        anyone = await use(app, "hub.start", caller=JOB_AGENT, text="Tailor it")  # named_only: a free pick skips cv_agent
        assert anyone.status is Status.NOT_AVAILABLE
        assert (await use(app, "rezi.status", caller=JOB_AGENT)).is_ok  # open to anyone
        for caller in ("talker", "cv_agent", ""):  # the hand-off is only for [hand_off] callers
            refused = await use(app, "cv.read_result", caller=caller, text="CV_RESULT: {}")
            assert refused.status is Status.NOT_AVAILABLE, caller
        talker = await use(app, "hub.start", caller="talker", text="Hello", agent_id="cv_agent")
        assert talker.is_ok, talker.error  # the Talker speaks for the user in cv_agent's tab
    finally:
        await app.stop()


async def test_cv_task_starts_cv_agent_itself_and_refuses_while_it_works_on_another_job(tmp_path):
    base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_Base.pdf")
    app = app_with(tmp_path)
    await app.start()
    try:
        job = dict(company="Acme", role="Senior Engineer", jd_text=JD, base_cv=str(base), notes="SLOW")
        made = await use(app, "cv.task", caller=JOB_AGENT, **job)  # SLOW: the fake claude stays in its turn
        assert made.is_ok, made.error
        assert read_request(made.value["text"]).company == "Acme" and "Nothing more to call" in made.value["next"]
        tasks = (await app.router.send(GetTaskStatus())).value
        assert [(t.id, t.agent_id) for t in tasks if not t.state.is_final] == [(made.value["task_id"], "cv_agent")]
        other = await use(app, "cv.task", caller=JOB_AGENT, **(job | {"company": "Beta"}))
        assert other.status is Status.NOT_AVAILABLE, other.error
        assert "Acme" in other.error and JOB_AGENT in other.error and "Nothing was queued" in other.error
        assert (await use(app, "cv.task", caller="talker", **job)).status is Status.NOT_AVAILABLE
    finally:
        await app.stop()


async def test_a_hand_off_module_sends_cv_task_for_its_agent_and_nobody_else_may_name_one(tmp_path):
    # job_search's job.tailor_cv: the module is the caller, its agent the asker (reply_to).
    base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_Base.pdf")
    app = app_with(tmp_path)
    await app.start()
    try:
        job = dict(company="Acme", role="Engineer", jd_text=JD, base_cv=str(base), notes="SLOW")
        for caller, extra in ((JOB_AGENT, {"for_agent": "someone"}), ("main_assistant", {"for_agent": JOB_AGENT}),
                              ("job_search", {})):  # fmt: skip
            refused = await use(app, "cv.task", caller=caller, **job, **extra)
            assert refused.status is Status.INVALID_ARGUMENTS and "for_agent" in refused.error, caller
        assert (await use(app, "cv.task", caller="voice_notes", **job, for_agent=JOB_AGENT)).status is Status.NOT_AVAILABLE
        made = await use(app, "cv.task", caller="job_search", **job, for_agent=JOB_AGENT)
        assert made.is_ok, made.error
        assert read_request(made.value["text"]).reply_to == JOB_AGENT  # cv's events go to the job agent
        assert (await use(app, "cv.read_result", caller="job_search", text="CV_RESULT: {}")).status is not Status.NOT_AVAILABLE
    finally:
        await app.stop()
