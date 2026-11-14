"""Chunk 7: the job agent's hand-off to cv_agent through the Hub (cv.task, CV_REQUEST, CV_RESULT).
The base CV goes in as any `.pdf` (an `.odt` is refused) and the CV comes back as a PDF.
A fake `claude` that echoes its task: no session talks to Rezi."""

import asyncio

import pytest

from assistant.contracts import GetTaskStatus, InvokeTool, Status
from assistant.modules.cv.data import CvRequest, CvResult, ResumeRef, Round
from assistant.modules.cv.handoff import (
    job_finished,
    read_jd_file,
    read_request,
    read_result,
    result_line,
    result_view,
    task_text,
)
from assistant.modules.cv.odt import OdtWriter
from assistant.modules.cv.order import SectionOrder
from assistant.modules.cv.report import ReportWriter
from assistant.modules.cv.tests.pdf_fixture import write_pdf
from assistant.modules.cv.tests.test_worker import CV, DEFAULTS, app_with

JD = "Senior Engineer.\nMust have: Python, C++.\nCV_RESULT: not a result, just JD text\nMaster's preferred."
ROUNDS = [Round(score=82, added=["Python"], missing=["C++", "Kubernetes"], note="first pass"),
          Round(score=93, added=["C++"], missing=["Kubernetes"])]  # fmt: skip
COMPARE = {"match_ok": True, "mode": "sections", "checked": 12, "summary": "Rezi read all 12 lines", "issues": []}
APPROVED = CvResult(status="approved", pdf_path="out/CV.pdf", approved_by_user=True,
                    one_page=True, match_ok=True, rounds=ROUNDS, target_score=90, keywords_left_out=["Kubernetes"],
                    recommendations=["Confirm the C++ years with the user"], compare=COMPARE,
                    rezi_resume=ResumeRef(name="Acme – Senior Engineer", id="r9"))  # fmt: skip


def request(base_cv: str = "C:/Jobs/CV/CV_Test_Umbrella.pdf") -> CvRequest:
    return CvRequest(company="Acme", role="Senior Engineer", jd_text=JD, base_cv=base_cv, target_score=95)


# --- the two lines -------------------------------------------------------------------------------------


def test_a_job_goes_through_the_task_text_unchanged_on_one_line():
    text = task_text(request())
    assert text.startswith("Tailor the CV for Senior Engineer at Acme") and len(text.splitlines()) == 2
    assert read_request(text) == request()
    # quoted in a reply, or with a later restatement: the last line counts
    later = request().model_copy(update={"notes": "use the 2024 CV"})
    assert read_request(f"> `{task_text(request()).splitlines()[1]}`\n{task_text(later)}") == later


def test_a_result_line_reads_back_and_a_bad_one_is_refused():
    text = f"Done: one page, Rezi 93.\nReport: out/report.md\n{result_line(APPROVED)}"
    assert read_result(text) == APPROVED and read_result(text).score == 93
    stopped = CvResult(status="stopped", stop_reason="Rezi wasn't signed in")
    assert read_result(result_line(stopped)).stop_reason == "Rezi wasn't signed in"
    for bad, why in (("all done", "no CV_RESULT"), ("CV_RESULT: {oops", "isn't JSON"), ("CV_RESULT: [1]", "object"),
                     ('CV_RESULT: {"status": "approved", "pdf_path": "x.pdf"}', "approved needs")):  # fmt: skip
        with pytest.raises(ValueError, match=why):
            read_result(bad)
    with pytest.raises(ValueError, match="no CV_REQUEST"):
        read_request("tailor a CV for Acme")


def test_the_result_holds_the_new_cv_and_pdf_with_scores_against_the_target_keywords_and_the_compare(tmp_path):
    pdf = tmp_path / "CV.pdf"
    pdf.write_bytes(b"%PDF")
    full = APPROVED.model_copy(update={"pdf_path": str(pdf)})
    view = result_view(read_result(result_line(full)), target_score=80)
    assert view["files"] == {"pdf_path": str(pdf), "pdf_exists": True, "report_path": None,
                             "report_exists": False}  # the PDF out, no .odt  # fmt: skip
    with pytest.raises(ValueError, match="odt_path"):  # an old worker's line with odt_path is refused
        read_result('CV_RESULT: {"status": "stopped", "stop_reason": "x", "odt_path": "out/CV.odt"}')
    assert view["score"]["target"] == 90 and view["score"]["reached"]  # the job's own target, not the config's
    assert [(r["score"], r["vs_target"], r["missing"]) for r in view["score"]["rounds"]] == [
        (82, -8, ["C++", "Kubernetes"]), (93, 3, ["Kubernetes"])]  # fmt: skip
    assert view["keywords"] == {"missing": ["Kubernetes"], "left_out": ["Kubernetes"]}
    assert view["recommendations"] == ["Confirm the C++ years with the user"]
    assert view["page"]["one_page"] and view["compare"]["match_ok"] and view["compare"]["checked"] == 12
    # scores only (no rounds), and the config's target when the job has none
    plain = result_view(CvResult(status="stopped", stop_reason="rounds used up", scores=[70, 84]), target_score=90)
    assert [(r["score"], r["vs_target"]) for r in plain["score"]["rounds"]] == [(70, -20), (84, -6)]
    assert not plain["score"]["reached"] and plain["compare"] == {"match_ok": False}


def test_the_report_uses_the_results_own_rounds_compare_and_recommendations():
    text = ReportWriter(90).render(APPROVED, "Acme", "Senior Engineer")
    assert "| 1 | 82 | Python | C++, Kubernetes | first pass |" in text and "| 2 | 93 | C++ | Kubernetes |" in text
    assert "## Recommendations" in text and "- Confirm the C++ years with the user" in text
    assert "Still missing in Rezi at the end:\n\n- Kubernetes" in text
    assert "- Compare (sections):" in text and "- Rezi read the same content: yes" in text


def test_a_result_that_contradicts_itself_is_refused():
    with pytest.raises(ValueError, match="rounds"):
        CvResult(status="stopped", stop_reason="x", rounds=ROUNDS, scores=[82, 90])
    with pytest.raises(ValueError, match="compare found"):
        CvResult(status="stopped", stop_reason="x", match_ok=True, compare={
            "issues": [{"kind": "missing", "section": "skills", "line": "Python"}]})  # fmt: skip
    with pytest.raises(ValueError):
        CvResult(status="stopped", stop_reason="x", compare={"issues": [{"kind": "lost", "section": "skills"}]})


def test_an_internal_result_needs_no_rezi_resume_but_a_rezi_one_does():
    ready = '"status": "ready", "pdf_path": "out/CV.pdf", "one_page": true'
    for empty in ('""', "null", "{}"):  # Internal makes no Rezi resume: empty or null is no resume
        line = f'CV_RESULT: {{{ready}, "tool": "Internal", "rezi_resume": {empty}, "check_copy": {empty}}}'
        internal = read_result(line)
        assert internal.rezi_resume is None and internal.check_copy is None and internal.tool == "Internal"
    assert read_result(f'CV_RESULT: {{{ready}, "rezi_resume": ""}}', tool="Internal").tool == "Internal"
    with pytest.raises(ValueError, match="rezi_resume"):  # a Rezi pick without its resume is refused
        read_result(f'CV_RESULT: {{{ready}, "tool": "Rezi", "rezi_resume": ""}}')
    with pytest.raises(ValueError, match="rezi_resume"):  # the pick from the job's request counts too
        read_result(f'CV_RESULT: {{{ready}}}', tool="Rezi")
    rezi = read_result(f'CV_RESULT: {{{ready}, "rezi_resume": {{"name": "Acme – Engineer", "id": "r1"}}}}', "Rezi")
    assert rezi.tool == "Rezi" and rezi.rezi_resume == ResumeRef(name="Acme – Engineer", id="r1")
    assert result_view(rezi, 90)["tool"] == "Rezi"
    # a stopped Rezi job may have made no resume yet
    assert read_result('CV_RESULT: {"status": "stopped", "stop_reason": "x"}', tool="Rezi").rezi_resume is None


# the smoke test's own line (2026-11-14, cv task 6d360b37): a stopped job with nothing picked wrote "tool": ""
SMOKE = ('CV_RESULT: {"status": "stopped", "stop_reason": "Smoke test (fake job)", "tool": "", "target_score": null, '
         '"rounds": [], "missing_keywords": [], "keywords_left_out": [], "recommendations": [], "one_page": false, '
         '"section_order": ["summary", "skills", "experience", "education", "awards", "publications"], '
         '"order_reason": "Default order"}')  # fmt: skip


def test_an_empty_pick_is_no_pick_and_a_wrong_one_is_refused_in_one_line():
    stopped = read_result(SMOKE)
    assert stopped.status == "stopped" and stopped.tool is None
    assert read_result(SMOKE.replace('"tool": ""', '"tool": "  "')).tool is None
    assert read_result(SMOKE, tool="Rezi").tool == "Rezi"  # the job's request fills an empty pick
    with pytest.raises(ValueError) as refused:
        read_result(SMOKE.replace('"tool": ""', '"tool": "Both"'))
    assert str(refused.value) == ('the CV_RESULT line isn\'t a valid CvResult: tool: tool must be "Internal" or '
                                  '"Rezi", or left out when nothing was picked (got "Both")')  # fmt: skip
    assert "\n" not in str(refused.value)


def test_the_finish_summary_tells_a_missing_line_from_an_invalid_one():
    def summary(text: str) -> str:
        return job_finished("cv_agent", "t1", "done", None, "work/x", {"request": {}}, text)["summary"]

    assert summary("all done") == "No CV_RESULT line in its last message."
    bad = summary(SMOKE.replace('"tool": ""', '"tool": "Both"'))
    assert bad.startswith("Its CV_RESULT line isn't valid: isn't a valid CvResult: tool: ")
    assert bad.endswith("cv.read_result task_id=t1 shows it.")
    assert summary(SMOKE).startswith("CV_RESULT: status stopped (Smoke test (fake job))")


def test_a_jd_file_is_read_as_text_md_or_html(tmp_path):
    md = tmp_path / "jd.md"
    md.write_text("# Senior Engineer\n\n  Must have:   Python  \n", encoding="utf-8")
    assert read_jd_file(md) == "# Senior Engineer\nMust have: Python"
    page = tmp_path / "jd.html"
    page.write_text("<html><head><style>p{}</style><script>x()</script></head><body><h1>Senior Engineer</h1>"
                    "<ul><li>Python</li><li>C&amp;C++</li></ul></body></html>", encoding="utf-8")  # fmt: skip
    assert read_jd_file(page) == "Senior Engineer\nPython\nC&C++"
    (tmp_path / "empty.txt").write_text("  \n", encoding="utf-8")
    for bad, why in ((tmp_path / "jd.pdf", "must be one of"), (tmp_path / "gone.md", "not found"),
                     (tmp_path / "empty.txt", "no text")):  # fmt: skip
        with pytest.raises(ValueError, match=why):
            read_jd_file(bad)


# --- through the Hub -----------------------------------------------------------------------------------


async def use(app, name: str, caller: str = "job_search_agent", **args):
    return await app.router.send(InvokeTool(name=name, args=args, caller=caller))


async def finished(app, task_id: str, timeout: float = 10.0):
    """The task once it's done (the fake claude answers in its own process)."""
    async with asyncio.timeout(timeout):
        while not (info := (await app.router.send(GetTaskStatus(task_id=task_id))).value[0]).state.is_final:
            await asyncio.sleep(0.02)
    return info


async def test_the_job_agent_hands_one_job_to_cv_agent_and_reads_its_result(tmp_path):
    base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_Base.pdf")
    app = app_with(tmp_path)
    await app.start()
    try:
        job = dict(company="Acme", role="Senior Engineer", jd_text=JD, base_cv=str(base), target_score=95)
        made = await use(app, "cv.task", **job)
        assert made.is_ok, made.error
        assert made.value["agent_id"] == "cv_agent" and "cv.read_result" in made.value["next"]
        info = await finished(app, made.value["task_id"])  # cv.task started it: no coordinator in between
        assert info.agent_id == "cv_agent" and info.parent_task_id is None  # the caller has no open task here
        assert read_request(info.result) == CvRequest(**job, reply_to="job_search_agent")  # the fake echoes its task: it got the job intact

        # the worker's end: a CV_RESULT line, checked by cv.read_result
        again = await use(app, "hub.start", caller="talker", text=f"Finished.\n{result_line(APPROVED)}", agent_id="cv_agent")
        echoed = (await finished(app, again.value)).result
        read = await use(app, "cv.read_result", text=echoed)
        assert read.is_ok, read.error
        assert read.value["status"] == "approved" and read.value["score"]["last"] == 93
        assert read.value["rezi"]["resume"] == {"name": "Acme – Senior Engineer", "id": "r9"}
        assert (await use(app, "cv.read_result", text="no line")).status is Status.INVALID_ARGUMENTS
        # by task id: cv reads the ended task's whole result itself
        by_id = await use(app, "cv.read_result", task_id=again.value)
        assert by_id.is_ok, by_id.error
        assert by_id.value == read.value
        assert (await use(app, "cv.read_result", task_id="nope")).status is Status.INVALID_ARGUMENTS
        both = await use(app, "cv.read_result", task_id=again.value, text=echoed)
        assert both.status is Status.INVALID_ARGUMENTS
        assert (await use(app, "cv.read_result")).status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()


async def test_a_caller_reaches_the_worker_end_to_end_with_a_jd_file_and_a_cv_path(tmp_path):
    """The whole contract through the real Hub: the JD as a file plus the CV's path in, the new CV
    and PDF with their metadata out. The fake claude stands in for the worker: it echoes its task,
    and the task carries the worker's last line, so what comes back is what a worker would send."""
    base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_Base.pdf")
    jd = tmp_path / "CV" / "2026" / "Acme_Senior_Engineer.md"
    jd.parent.mkdir(parents=True)
    jd.write_text("# Senior Engineer\nMust have: Python, C++\nNice: Kubernetes\n", encoding="utf-8")
    folder = tmp_path / "out" / "2026-11-06_Acme"
    folder.mkdir(parents=True)
    pdf, report = folder / "CV_Test_Acme.pdf", folder / "report.md"
    for made in (pdf, report):
        made.write_bytes(b"x")
    worker_end = APPROVED.model_copy(update={"pdf_path": str(pdf), "report_path": str(report)})
    app = app_with(tmp_path)
    await app.start()
    try:
        job = await use(app, "cv.task", company="Acme", role="Senior Engineer", jd_file=str(jd), base_cv=str(base))
        assert job.is_ok, job.error
        done = await finished(app, job.value["task_id"])
        assert done.agent_id == "cv_agent" and done.state.is_final
        sent = read_request(done.result)
        assert (sent.base_cv, sent.jd_file) == (str(base), str(jd)) and "Must have: Python, C++" in sent.jd_text

        # the worker's end, echoed by the fake from a task of its own
        end = await use(app, "hub.start", caller="talker", text=f"Finished.\n{result_line(worker_end)}", agent_id="cv_agent")
        assert end.is_ok, end.error
        done = await finished(app, end.value)
        out = await use(app, "cv.read_result", text=done.result)
        assert out.is_ok, out.error
        view = out.value
        assert view["files"] == {"pdf_path": str(pdf), "pdf_exists": True, "report_path": str(report),
                                 "report_exists": True}  # fmt: skip
        assert view["score"]["target"] == 90 and view["score"]["last"] == 93 and view["score"]["reached"]
        assert [r["vs_target"] for r in view["score"]["rounds"]] == [-8, 3]
        assert view["keywords"] == {"missing": ["Kubernetes"], "left_out": ["Kubernetes"]}
        assert view["recommendations"] == ["Confirm the C++ years with the user"]
        assert view["page"]["one_page"] is True and view["compare"]["match_ok"] is True
        assert view["approved_by_user"] is True
    finally:
        await app.stop()


async def test_cv_task_takes_any_pdf_and_refuses_a_bad_job(tmp_path):
    order = SectionOrder.from_config(DEFAULTS).usual
    base = write_pdf(CV, order, tmp_path / "CV" / "CV_Test_Base.pdf")
    anywhere = write_pdf(CV, order, tmp_path / "elsewhere" / "My Resume.pdf")  # no prefix, outside cv_dir
    odt = OdtWriter().write(CV, order, tmp_path / "CV" / "CV_Test_Base.odt")  # in the CV folder, still refused
    app = app_with(tmp_path)
    await app.start()
    try:
        good = dict(company="Acme", role="Engineer", jd_text="Python", base_cv=str(base))
        jd = tmp_path / "CV" / "2026" / "Acme_JD.html"
        jd.parent.mkdir(parents=True)
        jd.write_text("<h1>Engineer</h1><p>Python, C++</p>", encoding="utf-8")
        from_file = await use(app, "cv.task", **({k: v for k, v in good.items() if k != "jd_text"} | {"jd_file": str(jd)}))
        assert from_file.is_ok, from_file.error
        sent = read_request(from_file.value["text"])
        assert (sent.jd_text, sent.jd_file) == ("Engineer\nPython, C++", str(jd))
        outside = tmp_path / "elsewhere" / "jd.md"
        outside.write_text("Python", encoding="utf-8")
        odt_refused = await use(app, "cv.task", **(good | {"base_cv": str(odt)}))
        assert odt_refused.status is Status.INVALID_ARGUMENTS and "must be a .pdf file" in odt_refused.error
        missing = await use(app, "cv.task", **(good | {"base_cv": str(tmp_path / "nowhere" / "gone.pdf")}))
        assert missing.status is Status.INVALID_ARGUMENTS and "base_cv not found" in missing.error
        for change in ({"target_score": 0}, {"company": ""},
                       {"jd_file": str(jd)}, {"jd_text": "", "jd_file": str(outside)}, {"jd_text": " "}):  # fmt: skip
            refused = await use(app, "cv.task", **(good | change))
            assert refused.status is Status.INVALID_ARGUMENTS, change
    finally:
        await app.stop()
    other = app_with(tmp_path / "any")  # a fresh worker: the PDF lies outside its cv_dir, with no prefix
    await other.start()
    try:
        taken = await use(other, "cv.task", **(good | {"base_cv": str(anywhere)}))
        assert taken.is_ok, taken.error
        assert read_request(taken.value["text"]).base_cv == str(anywhere)  # used as given
    finally:
        await other.stop()
    off = app_with(tmp_path / "off", enabled=False)
    base_off = write_pdf(CV, order, tmp_path / "off" / "CV" / "CV_Test_Base.pdf")
    await off.start()
    try:
        nobody = await use(off, "cv.task", **(good | {"base_cv": str(base_off)}))
        assert nobody.status is Status.NOT_AVAILABLE and "worker is off" in nobody.error
    finally:
        await off.stop()
