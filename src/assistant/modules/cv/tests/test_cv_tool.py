"""The CV Tool app itself (`src/cv_tool`, the cv module's UI half): its engine (`cvlib`) on a temp data
folder, the 10 pt floor (a warning, never a refused Submit), and the server's guard, JSON-only posts, the
Submit's event and quit. Needs `pymupdf` (the `cv` extra);
the real print needs Chrome. Nothing outside tmp_path is written."""

import http.client
import json
import os
import re
from pathlib import Path

import pytest

pytest.importorskip("pymupdf")

from assistant.modules.cv.order import SectionOrder  # noqa: E402
from assistant.modules.cv.tests.pdf_fixture import write_pdf  # noqa: E402
from assistant.modules.cv.tests.test_tool import RICH  # noqa: E402
from assistant.modules.cv.tests.test_worker import DEFAULTS  # noqa: E402
from assistant.modules.cv.tool import MIN_PT, tool_content  # noqa: E402
from cv_tool import cvlib  # noqa: E402
from cv_tool.server import Tool  # noqa: E402


@pytest.fixture
def app_data(tmp_path):
    rules = tmp_path / "cv-writing"
    (rules / "rules").mkdir(parents=True)
    (rules / "SKILL.md").write_text("---\nname: x\n---\n# CV writing\nNo semicolons.", encoding="utf-8")
    (rules / "rules" / "nine.md").write_text("Body text at least 9 pt.", encoding="utf-8")
    cvlib.configure(str(tmp_path / "cv_tool"), str(tmp_path / "CV"), str(rules), str(tmp_path / "work"),
                    str(tmp_path / "facts.json"))  # fmt: skip
    yield tmp_path
    cvlib.configure()  # back to the defaults (nothing is written there by configure but the jobs folder)


def new_job(tmp_path: Path, **extra) -> dict:
    base = write_pdf(RICH, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "work" / "CV_Test_Ada.pdf")
    content, _ = tool_content(RICH)
    return cvlib.import_request({"company": "Ada Co", "role": "Engineer", "jd_text": "Python, Isaac Sim",
                                 "base_cv": str(base), "content": content, **extra})  # fmt: skip


def test_a_job_from_the_module_waits_for_the_pick_and_reads_the_rules(app_data):
    job = new_job(app_data)
    status = cvlib.job_status(job["id"])
    assert status["tool"] == "" and status["ready"] is False  # no pick: the app waits for the user
    assert status["content"]["experience"][0]["title"] == "Engineer" and "Wrote the first program." in status["text"]
    assert os.path.isfile(cvlib.load_job(job["id"])["base_cv"])  # a copy in the app's job, not the original
    assert [r["file"] for r in cvlib.rules()["rules"]] == ["SKILL.md", "nine.md"]
    assert cvlib.rules()["rules"][0]["rule"] == "No semicolons."
    assert cvlib.job_status(new_job(app_data, tool="Rezi")["id"])["tool"] == "Rezi"


def test_a_scored_round_is_saved_and_submit_waits_for_the_user(app_data):
    job = new_job(app_data, tool="Rezi")
    answer = cvlib.agent_round({"job_id": job["id"], "score": 84, "matched": ["Python"], "missing": ["MuJoCo"],
                                "changes": "First Draft", "export": False})  # fmt: skip
    assert answer["job_id"] == job["id"] and [r["file"] for r in answer["rules"]["rules"]] == ["SKILL.md", "nine.md"]
    rounds = cvlib.load_job(job["id"])["rounds"]
    assert rounds[-1]["score"] == 84
    assert cvlib.job_result(job["id"])["ready"] is False
    with pytest.raises(FileNotFoundError):
        cvlib.agent_round({"job_id": "nope"})
    with pytest.raises(ValueError, match="experience"):
        cvlib.agent_round({"job_id": job["id"], "content": {"name": "x"}})


def test_a_submit_archives_the_older_unsubmitted_jobs_of_its_work_folder(app_data):
    work, other = str(app_data / "work" / "job1"), str(app_data / "work" / "job2")
    old, kept, done, mine = (new_job(app_data, work_dir=w) for w in (work, other, work, work))
    open(os.path.join(cvlib.job_dir(done["id"]), "ready.flag"), "w").close()  # submitted: stays
    assert cvlib.archive_older(cvlib.load_job(mine["id"])) == [old["id"]]
    assert os.path.isfile(os.path.join(cvlib.JOBS, "_archive", old["id"], "job.json"))  # moved, not deleted
    assert {j["id"] for j in cvlib.list_jobs()} == {kept["id"], done["id"], mine["id"]}
    assert cvlib.archive_older({"id": "x"}) == []  # no work folder: nothing moves


def test_every_style_on_the_page_is_10_pt_or_more(app_data):
    content, _ = tool_content(RICH)
    sizes = [float(s) for s in re.findall(r"font-size:\s*([\d.]+)pt", cvlib.render(content))]
    assert sizes and min(sizes) >= cvlib.layout()["min_pt"] == 10.0 == MIN_PT  # one number, app and module


def test_the_layout_settings_are_read_at_every_render(app_data):
    content, _ = tool_content(RICH)
    path = os.path.join(cvlib.ROOT, cvlib.PAGE_SETTINGS)
    assert cvlib.layout() == cvlib.LAYOUT_DEFAULTS  # no file: the defaults
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"line_height": 1.2, "name_pt": 16, "body_pt": "x", "heading_pt": 99}, f)
    page = cvlib.render(content)  # same process, no reload
    assert "line-height: 1.2;" in page and "font-size: 16pt" in page
    assert "font-size: 10pt" in page and "font-size: 10.8pt" in page  # a bad or out-of-range value: its default
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"paper": "A4", "bold_weight": 700, "text_color": "#112233", "link_color": "red",
                   "section_before_pt": 6, "skill_gap_pt": 2, "heading_rule_pt": True}, f)
    page = cvlib.render(content)
    assert "size: 595.28pt 841.89pt" in page and cvlib.text_height() == pytest.approx(841.89 - 72)
    assert page.count("font-weight: 700") == 6 and "font-weight: 600" not in page
    assert "color: #112233" in page and "solid #112233" in page and "color: #1F4E79" in page  # a bad colour: its default
    assert "margin: 6pt 0 2.5pt" in page and ".skill { margin: 0 0 2pt;" in page and "0.9pt solid" in page
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert cvlib.layout() == cvlib.LAYOUT_DEFAULTS
    assert "size: 612pt 792pt" in cvlib.render(content) and cvlib.text_width() == 540


def test_the_10_pt_measure_reads_the_pdfs_own_sizes(app_data):
    order = SectionOrder.from_config(DEFAULTS).usual
    fine = write_pdf(RICH, order, app_data / "fine.pdf")
    small = write_pdf(RICH, order, app_data / "small.pdf", extra=((8.0, "tiny print"),))
    assert cvlib.font_sizes(str(fine)) == []
    assert cvlib.font_sizes(str(small)) == [{"size": 8.0, "text": "tiny print", "page": 1}]


@pytest.mark.skipif(not os.path.isfile(cvlib.CHROME), reason="needs Chrome to print the page")
def test_a_round_prints_the_page_and_submit_names_the_final_pdf(app_data):
    job = new_job(app_data, tool="Rezi")
    content = cvlib.load_job(job["id"])["content"]
    answer = cvlib.agent_round({"job_id": job["id"], "content": content, "score": 91, "matched": ["Python"]})
    assert answer["pdf"].endswith(".pdf") and os.path.isfile(answer["pdf"])
    assert answer["small_text"] == []  # nothing under 10 pt as printed
    result = cvlib.submit(cvlib.load_job(job["id"]))
    assert Path(result["pdf_path"]).name == f"CV_Test_{cvlib._slug('Ada Co')}_final.pdf"
    done = cvlib.job_result(job["id"])
    assert done["ready"] is True and done["small_text"] == [] and done["result"]["final_score"] == 91


# --- the server ------------------------------------------------------------------------------------------


def request(tool: Tool, method: str, path: str, body: bytes | None = None, headers: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", tool.port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        conn.close()


def test_the_server_answers_only_this_machine_json_only_and_quits(app_data):
    tool = Tool("127.0.0.1", 0, app_data / "profile", window="none")
    tool.start()
    try:
        status, body = request(tool, "GET", "/api/ping")
        assert status == 200 and json.loads(body)["app"] == "cv_tool"
        assert request(tool, "GET", "/api/ping", headers={"Host": "evil.example"})[0] == 403
        assert request(tool, "GET", "/api/ping", headers={"Origin": "https://evil.example"})[0] == 403
        assert request(tool, "POST", "/api/quit", b"{}", {"Content-Type": "text/plain"})[0] == 415
        assert not tool.quit.is_set()
        status, body = request(tool, "POST", "/api/job/status", b"{}", {"Content-Type": "application/json"})
        assert status == 500 and "error" in json.loads(body)  # no id: the error goes back as JSON
        assert request(tool, "POST", "/api/quit", b"{}", {"Content-Type": "application/json"})[0] == 200
        assert tool.quit.is_set()
    finally:
        tool._http.shutdown()
        tool._http.server_close()
    with pytest.raises(ValueError):
        Tool("0.0.0.0", 0, app_data / "profile", window="none")  # require_loopback


def scored_job_with_small_text(app_data, monkeypatch) -> dict:
    """A scored job whose current PDF has text under 10 pt (no Chrome needed)."""
    small = write_pdf(RICH, SectionOrder.from_config(DEFAULTS).usual, app_data / "small.pdf", extra=((8.0, "tiny"),))
    pdf = {"file": str(small), "name": small.name, "pages": 1, "mtime": 0, "exported": True, "at": "9999"}
    monkeypatch.setattr(cvlib, "current_pdf", lambda job: pdf)
    job = new_job(app_data, tool="Rezi")
    cvlib.agent_round({"job_id": job["id"], "score": 84, "export": False})
    return job


def test_a_submit_with_small_text_goes_through_with_a_warning(app_data, monkeypatch):
    job = scored_job_with_small_text(app_data, monkeypatch)
    result = cvlib.submit(cvlib.load_job(job["id"]))  # not refused
    assert result["small_text"] == [{"size": 8.0, "text": "tiny", "page": 1}] and result["min_pt"] == 10.0
    assert cvlib.job_result(job["id"])["ready"] is True
    assert cvlib.load_job(job["id"])["submitted"]["small_text"] == 1  # the page's warning
    assert cvlib.submitted_jobs() == [{"job_id": job["id"], "submitted_at": result["submitted_at"]}]


def test_the_server_pushes_each_submit_on_its_event_stream(app_data, monkeypatch):
    job = scored_job_with_small_text(app_data, monkeypatch)
    tool = Tool("127.0.0.1", 0, app_data / "profile", window="none")
    tool.start()
    stream = http.client.HTTPConnection("127.0.0.1", tool.port, timeout=5)
    try:
        stream.request("GET", "/api/events")
        events = stream.getresponse()
        assert events.status == 200 and events.getheader("Content-Type") == "text/event-stream"
        status, body = request(tool, "POST", "/api/submit", json.dumps({"id": job["id"]}).encode(),
                               {"Content-Type": "application/json"})  # fmt: skip
        assert status == 200 and json.loads(body)["small_text"]  # small text: accepted all the same
        line = events.fp.readline()
        assert json.loads(line.removeprefix(b"data: ")) == {"kind": "submitted", "job_id": job["id"],
                                                            "submitted_at": json.loads(body)["submitted_at"]}  # fmt: skip
        status, body = request(tool, "GET", "/api/submitted")
        assert [j["job_id"] for j in json.loads(body)["jobs"]] == [job["id"]]
    finally:
        tool.stop()
        stream.close()


def test_the_send_to_rezi_click_is_an_event_and_the_pick_is_not(app_data):
    job = new_job(app_data, tool="Internal")
    tool = Tool("127.0.0.1", 0, app_data / "profile", window="none")
    tool.start()
    stream = http.client.HTTPConnection("127.0.0.1", tool.port, timeout=5)
    js = {"Content-Type": "application/json"}
    try:
        stream.request("GET", "/api/events")
        events = stream.getresponse()
        page = cvlib.load_job(job["id"]) | {"tool": "Rezi"}  # the pick in tab 2: saved, no event
        assert request(tool, "POST", "/api/job/save", json.dumps(page).encode(), js)[0] == 200
        assert cvlib.load_job(job["id"])["tool"] == "Rezi"
        status, body = request(tool, "POST", "/api/draft/rezi", json.dumps({"id": job["id"]}).encode(), js)
        made = json.loads(body)
        assert status == 200 and made["job_id"] == job["id"] and os.path.isfile(made["file"])
        line = events.fp.readline()  # the first event is the click: the save sent none
        assert json.loads(line.removeprefix(b"data: ")) == {
            "kind": "rezi_request", "job_id": job["id"], "request_id": made["request_id"], "at": made["at"],
            "company": "Ada Co", "role": "Engineer"}
        assert cvlib.load_job(job["id"])["rezi_pending"] == made["request_id"]
    finally:
        tool.stop()
        stream.close()


# --- the truth check and the Internal path with no agent ---------------------------------------------------


def test_the_truth_check_reads_the_cv_pdfs_and_the_confirmed_phrases_not_the_notes(app_data):
    order = SectionOrder.from_config(DEFAULTS).usual
    write_pdf(RICH, order, app_data / "CV" / "CV_Test_Ada.pdf")  # a PDF base CV in the CV folder
    (app_data / "facts.json").write_text(json.dumps({"words": [], "phrases": ["modular"],
                                                     "notes": ["Never claim Kubernetesium."]}), encoding="utf-8")  # fmt: skip
    cvlib.configure(str(app_data / "cv_tool"), str(app_data / "CV"), str(app_data / "cv-writing"),
                    str(app_data / "work"), str(app_data / "facts.json"))  # fmt: skip
    assert cvlib.known("Lovelace") and cvlib.known("Babbage")  # read from the PDF
    assert cvlib.known("modular")  # a confirmed phrase
    assert cvlib.known("engine-program")  # hyphenated: every part is on the CVs
    assert not cvlib.known("kubernetesium")  # the notes never back a term


def test_an_internal_job_shows_its_keywords_from_its_own_round(app_data):
    job = cvlib.load_job(new_job(app_data, tool="Internal")["id"])
    job["rounds"] = [{"tool": "Internal", "score": 70, "matched": ["Python"], "missing_backed": ["Babbage"],
                      "missing_not_backed": ["MuJoCo"]}]  # fmt: skip
    lists = cvlib.keyword_lists(job)
    assert lists["source"].startswith("Internal round 1") and [m["term"] for m in lists["matched"]] == ["Python"]
    assert [m["term"] for m in lists["missing"]] == ["Babbage", "MuJoCo"]


@pytest.mark.skipif(not os.path.isfile(cvlib.CHROME), reason="needs Chrome to print the page")
def test_the_internal_draft_and_round_run_with_no_agent(app_data):
    jd = ("Research Engineer\nREQUIRED QUALIFICATIONS\n- Strong Python programming skills\n"
          "- Experience with Isaac Sim simulation\n- Kubernetes deployment experience\n- Mathematics background")
    job = new_job(app_data, tool="Internal", jd_text=jd)
    proposals = cvlib.draft_internal(cvlib.load_job(job["id"]))
    with pytest.raises(ValueError, match="user's yes"):
        cvlib.apply_internal_draft(cvlib.load_job(job["id"]), add=["Kubernetesium"])
    done = cvlib.apply_internal_draft(cvlib.load_job(job["id"]), add=[a["term"] for a in proposals["add"][:1]])
    assert done["state"] and cvlib.load_job(job["id"])["rounds"][-1]["tool"] == "Internal"
    assert done["state"]["keywords"]["source"].startswith("Internal round")
