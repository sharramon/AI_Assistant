"""The cv module's side of the CV Tool (tool.py): the content in the app's shape, the rules folder the
job start loads, the request's pick, and the cv.open_tool / cv.tool_* / cv.check_fonts items against
a fake CV Tool on a free port (the real app is tested in test_cv_tool.py). All in tmp_path."""

import asyncio
import json
import queue
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

from assistant.contracts import AgentNotice, DeliverMessage, InvokeTool, ResponseReady, Result, Status
from assistant.modules.cv.content import CvContent
from assistant.modules.cv.data import CvRequest
from assistant.modules.cv.job_start import JobStart, JobStartError
from assistant.modules.cv.order import SectionOrder
from assistant.modules.cv.reply import reply_text
from assistant.modules.cv.submit_watch import SubmitWatch
from assistant.modules.cv.tests.pdf_fixture import write_pdf
from assistant.modules.cv.tests.test_worker import CV, DEFAULTS, app_with, cv_module
from assistant.modules.cv.tool import CvTool, tool_content, tool_settings

RICH = CvContent(sections={
    "contact": ("Ada Lovelace", "(949) 555-0100 | ada@example.com | linkedin.com/in/ada | London, UK"),
    "summary": ("Engineer who wrote the first program.",),
    "skills": ("Languages: C#, Python", "Simulation: Isaac Sim"),
    "experience": ("Engineer, Engines | Jan 2020 – Present", "• Wrote the first program.",
                   "Analyst | 2018 – 2019", "Babbage Ltd", "• Read the notes."),
    "education": ("Master of Science in Mathematics, 2017", "University of London"),
    "awards": ("• Best paper",),
    "projects": ("Loom | 2016",),
})  # fmt: skip


def test_the_content_comes_in_the_apps_shape():
    content, left_out = tool_content(RICH)
    assert content["name"] == "Ada Lovelace"
    assert content["contact"][:2] == ["(949) 555-0100", "ada@example.com"]
    assert content["contact"][2] == {"text": "linkedin.com/in/ada", "href": "https://www.linkedin.com/in/ada", "visible": True}
    assert content["summary"] == "Engineer who wrote the first program."
    assert content["skills"] == [["Languages", "C#, Python"], ["Simulation", "Isaac Sim"]]
    assert content["experience"] == [
        {"title": "Engineer", "company": "Engines", "dates": "Jan 2020 – Present", "bullets": ["Wrote the first program."]},
        {"title": "Analyst", "company": "Babbage Ltd", "dates": "2018 – 2019", "bullets": ["Read the notes."]}]
    assert content["education"] == [{"degree": "Master of Science in Mathematics, 2017", "detail": ["University of London"]}]
    assert content["awards"] == ["Best paper"] and content["publications"] == []
    assert content["education_first"] is False  # only the user moves Education up
    assert left_out == ["projects"]


def test_the_tool_settings_are_checked():
    checked = tool_settings({}, "C:/CV", "C:/rules", "C:/home")
    assert checked == {"host": "127.0.0.1", "port": 8771, "data_dir": str(Path("C:/home/cv_tool")),
                       "facts": str(Path("C:/home/data/confirmed_facts.json")), "cv_dir": "C:/CV", "rules_dir": "C:/rules",
                       "cv_prefix": "CV_Test_"}
    for bad, reason in (({"host": "0.0.0.0"}, "this machine"), ({"port": 0}, "port"), ("x", "table")):
        with pytest.raises(ValueError, match=reason):
            tool_settings(bad, "", "", "")


def test_the_request_names_the_pick_or_leaves_it_to_the_user():
    base = {"company": "A", "role": "B", "jd_text": "C", "base_cv": "CV_Test_A.pdf"}
    assert CvRequest(**base).tool is None and CvRequest(**base, tool="Rezi").tool == "Rezi"
    with pytest.raises(ValidationError):
        CvRequest(**base, tool="Word")


# --- the rules folder ------------------------------------------------------------------------------------


def rules_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "cv-writing"
    (folder / "rules").mkdir(parents=True)
    (folder / "SKILL.md").write_text("# CV writing\nNo semicolons.", encoding="utf-8")
    (folder / "rules" / "b-nine-pt.md").write_text("Body text at least 9 pt.", encoding="utf-8")
    (folder / "rules" / "a-order.md").write_text("Education after Experience.", encoding="utf-8")
    return folder


def test_every_job_loads_the_rules_folder_then_the_facts(tmp_path):
    folder, facts = rules_folder(tmp_path), tmp_path / "confirmed_facts.json"
    facts.write_text(json.dumps({"words": ["isaac"]}), encoding="utf-8")
    start = JobStart(tmp_path / "work", tmp_path / "CV", [facts], lambda: date(2026, 11, 9), rules_dir=folder)
    assert [s.path.name for s in start.load_skills()] == ["SKILL.md", "a-order.md", "b-nine-pt.md", "confirmed_facts.json"]
    (folder / "rules" / "c-new.md").write_text("A new rule.", encoding="utf-8")  # no reload needed
    assert "c-new.md" in [s.path.name for s in start.load_skills()]
    base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_A.pdf")
    _, block = start.prepare(CvRequest(company="A", role="B", jd_text="C", base_cv=str(base)))
    assert "Body text at least 9 pt." in block and "cv.open_tool" in block and '"isaac"' in block
    (folder / "SKILL.md").unlink()
    with pytest.raises(JobStartError, match="SKILL.md"):
        start.load_skills()


# --- the items, against a fake CV Tool -------------------------------------------------------------------


class FakeTool:
    """The CV Tool's API as the module uses it; records each call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.result: dict = {"ready": False, "submitted": None}
        self.small: list = []
        self.status: dict = {"tool": "", "content": {}}
        self.submitted: list = []  # /api/submitted
        self.events: queue.Queue = queue.Queue()  # /api/events; None ends the stream
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _answer(self, body: dict) -> None:
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                fake.calls.append((self.command, u.path, body or q))
                answer = {"/api/ping": {"app": "cv_tool"},
                          "/api/job/import": {"job_id": "j1", "tool": body.get("tool", "")},
                          "/api/window": {"opened": True, "raised": False},
                          "/api/job/status": {"id": q.get("id"), **fake.status},
                          "/api/round": {"job_id": body.get("job_id"), "pdf": "x.pdf", "small_text": fake.small},
                          "/api/job/result": fake.result,
                          "/api/draft/internal": {"add": [{"term": "Python"}], "ask": []},
                          "/api/draft/internal/apply": {"applied": {"added": body.get("add")}},
                          "/api/loop/internal": {"score": 72, "keywords": {"missing": []}},
                          "/api/submitted": {"jobs": fake.submitted},
                          }.get(u.path, {"error": "not found"})  # fmt: skip
                data = json.dumps(answer).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path != "/api/events":
                    return self._answer({})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                while (item := fake.events.get()) is not None:
                    self.wfile.write(f"data: {json.dumps(item)}\n\n".encode())
                    self.wfile.flush()

            def do_POST(self) -> None:
                self._answer(json.loads(self.rfile.read(int(self.headers["Content-Length"] or 0)) or b"{}"))

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.events.put(None)
        self.http.shutdown()
        self.http.server_close()


async def call(app, name: str, **args):
    return await app.router.send(InvokeTool(name=name, args=args, caller="cv_agent"))


async def test_the_items_open_a_job_and_drive_the_cv_tool(tmp_path):
    fake = FakeTool()
    app = app_with(tmp_path)
    await app.start()
    try:
        module = cv_module(app)
        module.tool = CvTool(None, module.settings["tool"] | {"port": fake.port}, module.settings["work_dir"])
        base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_A.pdf")
        job, _ = module._job_start.prepare(CvRequest(company="A", role="B", jd_text="Python", base_cv=str(base),
                                                     tool="Rezi"))  # fmt: skip

        opened = await call(app, "cv.open_tool", job_dir=job.work_dir)
        assert opened.status is Status.OK, opened.error
        assert opened.value["job_id"] == "j1" and opened.value["tool"] == "Rezi" and opened.value["unplaced"] == []
        api = [c for c in fake.calls if c[1] != "/api/ping"]  # every call pings first (ensure_running)
        _, path, body = api[0]
        assert path == "/api/job/import" and body["jd_text"] == "Python" and body["base_cv"] == job.base_cv_copy
        assert body["content"]["experience"][0]["bullets"] == ["Wrote the first program."]
        assert api[1][1] == "/api/window" and api[1][2] == {"job": "j1"}

        outside = await call(app, "cv.open_tool", job_dir=str(tmp_path))
        assert outside.status is Status.INVALID_ARGUMENTS and "work folder" in outside.error

        status = await call(app, "cv.tool_status", job_id="j1")
        assert status.status is Status.OK and status.value["id"] == "j1"

        fake.small = [{"text": "tiny", "size": 8.5}]
        sent = await call(app, "cv.tool_round", job_id="j1", score=88, matched=["Python"], missing=["MuJoCo"])
        assert sent.status is Status.OK and "never shrink the font" in sent.value["next"]
        assert fake.calls[-1][2] == {"job_id": "j1", "score": 88, "matched": ["Python"], "missing": ["MuJoCo"]}
        fonts = await call(app, "cv.check_fonts", job_id="j1")
        assert fonts.value["small_text"] == fake.small and fake.calls[-1][2] == {"job_id": "j1"}

        assert (await call(app, "cv.tool_result", job_id="j1")).value["ready"] is False
        fake.result = {"ready": True, "result": {"pdf_path": "CV_Test_A_final.pdf"}, "small_text": fake.small}
        submitted = await call(app, "cv.tool_result", job_id="j1")  # small text: a warning, never refused
        assert submitted.status is Status.OK and submitted.value["small_text"] == fake.small
        assert "under 10 pt" in submitted.value["next"] and "always goes through" in submitted.value["next"]
        assert submitted.value["result"]["pdf_path"] == "CV_Test_A_final.pdf"

        proposals = await call(app, "cv.tool_draft", job_id="j1")
        assert proposals.value["add"] == [{"term": "Python"}] and fake.calls[-1][1] == "/api/draft/internal"
        applied = await call(app, "cv.tool_draft", job_id="j1", apply=True, add=["Python"])
        assert applied.value["applied"]["added"] == ["Python"] and fake.calls[-1][2]["reorder"] is True
        scored = await call(app, "cv.tool_internal_round", job_id="j1")
        assert scored.value["state"]["score"] == 72 and fake.calls[-1][2] == {"id": "j1"}

        assert set(module.export_state()) == {"guard", "tool"}
    finally:
        await app.stop()
        fake.close()


async def test_the_submit_reaches_the_asking_agent_once_by_its_id(tmp_path):
    """The return address lives in the job's job_start.json, so no task id or worker memory is needed."""
    fake = FakeTool()
    app = app_with(tmp_path)
    await app.start()
    try:
        module = cv_module(app)
        module.tool = CvTool(None, module.settings["tool"] | {"port": fake.port}, module.settings["work_dir"])
        base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_A.pdf")
        job, _ = module._job_start.prepare(CvRequest(company="A", role="B", jd_text="Python", base_cv=str(base),
                                                     reply_to="job_search_agent"))  # fmt: skip
        fake.result = {"ready": True, "work_dir": job.work_dir, "small_text": [],
                       "result": {"pdf_path": "A_final.pdf", "submitted_at": "t1", "company": "A", "role": "B"}}
        first = await call(app, "cv.tool_result", job_id="j1")
        assert first.value["told"] == "job_search_agent (published cv.job_submitted)"  # cv messages no one
        record = json.loads((Path(job.work_dir) / "job_start.json").read_text(encoding="utf-8"))
        assert record["request"]["reply_to"] == "job_search_agent" and record["replied"]["submitted_at"] == "t1"
        assert "told" not in (await call(app, "cv.tool_result", job_id="j1")).value  # the same Submit: told once
        fake.result["result"]["submitted_at"] = "t2"  # the user submitted again
        assert (await call(app, "cv.tool_result", job_id="j1")).value["told"].startswith("job_search_agent")
        fake.result["work_dir"] = str(tmp_path)  # not a job folder: nobody is told
        assert "told" not in (await call(app, "cv.tool_result", job_id="j1")).value
    finally:
        await app.stop()
        fake.close()


def watched_tool(module, fake, seen_path: Path) -> CvTool:
    """The module on the fake CV Tool, with its Submit watch on it (as `init` wires the real one)."""
    module.tool = CvTool(None, module.settings["tool"] | {"port": fake.port}, module.settings["work_dir"])
    module._watch = SubmitWatch(module.tool, module._deliver_submit, module._ctx.log, remind=module._remind,
                                seen_path=seen_path, on_rezi=module._tell_worker_rezi)  # fmt: skip
    module.tool.on_running = module._watch.follow
    return module.tool


async def replied_at(job_dir: str, submitted_at: str) -> dict:
    """job_start.json's `replied`, once it names `submitted_at` (the watch runs on its own)."""
    async with asyncio.timeout(5):
        while True:
            record = json.loads((Path(job_dir) / "job_start.json").read_text(encoding="utf-8"))
            if (record.get("replied") or {}).get("submitted_at") == submitted_at:
                return record["replied"]
            await asyncio.sleep(0.05)


def job_record(job_dir: str) -> dict:
    return json.loads((Path(job_dir) / "job_start.json").read_text(encoding="utf-8"))


async def test_the_submit_watch_delivers_live_submits_and_only_reminds_missed_ones(tmp_path):
    """Live Submits reach reply_to with no cv.tool_result call. One pressed while cv was down is only
    reminded (one plain notice), never delivered; on the very first start, old Submits are just marked seen.
    Each live delivery gives cv_agent one AgentNotice line for its next turn; cv.tool_result gives none."""
    fake = FakeTool()
    app = app_with(tmp_path)
    notices: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, notices.put)
    agent_notes: asyncio.Queue[AgentNotice] = asyncio.Queue()

    async def hub_stand_in(notice: AgentNotice) -> Result:  # AgentNotice is a command the Hub handles
        agent_notes.put_nowait(notice)
        return Result.ok()

    app.router.register(AgentNotice, hub_stand_in)
    await app.start()
    seen = tmp_path / "cv_tool" / "submits_seen.json"
    try:
        module = cv_module(app)
        watched_tool(module, fake, seen)
        base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_A.pdf")
        job, _ = module._job_start.prepare(CvRequest(company="A", role="B", jd_text="Python", base_cv=str(base),
                                                     reply_to="job_search_agent"))  # fmt: skip
        fake.result = {"ready": True, "work_dir": job.work_dir, "small_text": [{"text": "tiny", "size": 8.0}],
                       "result": {"pdf_path": "A_final.pdf", "submitted_at": "t0", "company": "A", "role": "B"}}
        fake.submitted = [{"job_id": "j1", "submitted_at": "t0"}]  # an old Submit, from before the seen file
        await module.start()  # the first start: t0 is marked seen, nothing reminded or sent
        async with asyncio.timeout(5):
            while not seen.exists():
                await asyncio.sleep(0.05)
        assert json.loads(seen.read_text(encoding="utf-8"))["seen"] == ["j1@t0"]

        fake.result["result"]["submitted_at"] = "t1"  # a live Submit, with small text: delivered by itself
        fake.events.put({"kind": "submitted", "job_id": "j1", "submitted_at": "t1"})
        assert (await replied_at(job.work_dir, "t1"))["to"] == "job_search_agent"
        async with asyncio.timeout(5):
            note = await agent_notes.get()  # cv_agent hears it went out, without a wake
        assert note.agent_id == module._agent_id and note.source == "cv"
        assert "Submit" in note.text and "B at A" in note.text and f"(job {Path(job.work_dir).name})" in note.text
        assert "at t1" in note.text
        assert "passed it on for job_search_agent (cv.job_submitted)" in note.text
        assert "1 text piece print under 10" in note.text
        told = await call(app, "cv.tool_result", job_id="j1")
        assert told.is_ok and "told" not in told.value  # cv_agent's look tells nobody twice

        await module._watch.stop()  # cv goes down; the user presses Submit meanwhile
        fake.result["result"]["submitted_at"] = "t2"
        fake.submitted.append({"job_id": "j1", "submitted_at": "t2"})
        module._watch.follow()  # cv is back: one reminder, nothing delivered
        async with asyncio.timeout(5):
            notice = await notices.get()
        assert "While the cv module was off" in notice.text and "B at A" in notice.text and "t2" in notice.text
        assert "cv.tool_result" in notice.text and notice.agent_id is None
        await asyncio.sleep(0.2)
        assert job_record(job.work_dir)["replied"]["submitted_at"] == "t1"  # t2 was not sent
        assert notices.empty()  # one notice only: t0 and t1 were seen

        await module._watch.stop()  # a second restart: t2 isn't reminded again
        module._watch.follow()
        await asyncio.sleep(0.3)
        assert notices.empty()
        sent = await call(app, "cv.tool_result", job_id="j1")  # the user says send it
        assert sent.value["told"].startswith("job_search_agent")
        await asyncio.sleep(0.1)
        assert agent_notes.empty()  # cv.tool_result's own delivery: its caller sees "told", no notice
    finally:
        await app.stop()
        fake.close()


async def test_the_send_to_rezi_click_tells_cv_agent_once_and_submit_stays_the_same(tmp_path, monkeypatch):
    """A live rezi_request event becomes one DeliverMessage to cv_agent (its yes for the Rezi write, start
    the First Draft); the same request again tells nobody; a Submit still goes to reply_to as before."""
    fake = FakeTool()
    app = app_with(tmp_path)
    await app.start()
    try:
        module = cv_module(app)
        watched_tool(module, fake, tmp_path / "cv_tool" / "submits_seen.json")
        sent: asyncio.Queue[DeliverMessage] = asyncio.Queue()
        real_send = module._ctx.send

        async def send(command, timeout=None):
            if isinstance(command, DeliverMessage) and command.agent_id == module._agent_id:
                await sent.put(command)  # cv_agent's message, kept here (no session is started)
                return Result.ok("message")
            return await real_send(command, timeout)

        monkeypatch.setattr(module._ctx, "send", send)
        base = write_pdf(CV, SectionOrder.from_config(DEFAULTS).usual, tmp_path / "CV" / "CV_Test_A.pdf")
        job, _ = module._job_start.prepare(CvRequest(company="A", role="B", jd_text="Python", base_cv=str(base),
                                                     reply_to="job_search_agent"))  # fmt: skip
        await module.start()
        click = {"kind": "rezi_request", "job_id": "j1", "request_id": "j1_20261110-120000",
                 "at": "2026-11-10T12:00:00", "company": "A", "role": "B"}
        fake.events.put(click)
        async with asyncio.timeout(5):
            message = await sent.get()
        assert message.sender == "cv" and "Send JD and CV to Rezi" in message.text and "B at A" in message.text
        assert "CV Tool job j1" in message.text and "j1_20261110-120000" in message.text
        assert "yes for the Rezi write" in message.text and "start the First Draft" in message.text
        fake.events.put(click)  # the same request again: nobody told twice
        fake.events.put({"kind": "rezi_request", "job_id": "j1"})  # no request id: ignored
        fake.result = {"ready": True, "work_dir": job.work_dir, "small_text": [],
                       "result": {"pdf_path": "A_final.pdf", "submitted_at": "t1", "company": "A", "role": "B"}}
        fake.events.put({"kind": "submitted", "job_id": "j1", "submitted_at": "t1"})  # Submit: as before
        assert (await replied_at(job.work_dir, "t1"))["to"] == "job_search_agent"
        assert sent.empty()
    finally:
        await app.stop()
        fake.close()


def test_the_message_carries_the_small_text_as_a_warning():
    text = reply_text({"role": "B", "company": "A", "small_text": [{"size": 8.0}], "min_pt": 9.0})
    assert "1 text piece print under 9.0 pt" in text and "warning only" in text
    assert "under 10 pt" in reply_text({"role": "B", "company": "A", "small_text": [{"size": 8.0}]})  # MIN_PT
    assert "Note:" not in reply_text({"role": "B", "company": "A"})


async def test_the_round_cap_is_checked_in_code(tmp_path):
    fake = FakeTool()
    app = app_with(tmp_path)
    await app.start()
    try:
        module = cv_module(app)
        module.tool = CvTool(None, module.settings["tool"] | {"port": fake.port}, module.settings["work_dir"],
                             max_rounds=2)  # fmt: skip
        fake.status = {"tool": "Rezi", "loop": {"rounds": [{"n": 1}, {"n": 2}]}}
        refused = await call(app, "cv.tool_round", job_id="j1", score=91)
        assert refused.status is Status.INVALID_ARGUMENTS and "max_rounds" in refused.error
        assert (await call(app, "cv.tool_round", job_id="j1", content={"experience": [1]})).is_ok  # a print, no score
        assert (await call(app, "cv.check_fonts", job_id="j1")).is_ok
        fake.status["tool"] = "Internal"  # an Internal job scores every content round
        assert (await call(app, "cv.tool_round", job_id="j1", content={"experience": [1]})).status is Status.INVALID_ARGUMENTS
        assert (await call(app, "cv.tool_internal_round", job_id="j1")).status is Status.INVALID_ARGUMENTS
        fake.status["loop"]["rounds"] = [{"n": 1}]
        assert (await call(app, "cv.tool_round", job_id="j1", score=91)).is_ok
    finally:
        await app.stop()
        fake.close()


async def test_a_tool_that_doesnt_answer_is_not_available(tmp_path):
    app = app_with(tmp_path)
    await app.start()
    try:
        module = cv_module(app)
        tool = CvTool(None, module.settings["tool"], module.settings["work_dir"])
        tool._companion.app._start_timeout = 0.5
        tool._companion.app.module = "cv_tool_missing_package"  # nothing to launch: it exits at once
        module.tool = tool
        answer = await call(app, "cv.tool_status", job_id="j1")
        assert answer.status is Status.NOT_AVAILABLE and "CV Tool" in answer.error
    finally:
        await app.stop()
