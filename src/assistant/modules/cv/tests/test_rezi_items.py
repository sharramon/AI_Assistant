"""Chunk 5: the `rezi.*` items, the resume guard and Rezi's resume JSON as sections. Every item
call goes to the fake Rezi (`fake_rezi.py`) through `httpx2.ASGITransport`; nothing reaches the
network or the real Rezi."""

from __future__ import annotations

import socket
from pathlib import Path

import httpx2
import pytest

from assistant.contracts import InvokeTool, ReloadModule, Status
from assistant.core import App
from assistant.modules.cv import CvModule
from assistant.modules.cv.compare import FieldCompare
from assistant.modules.cv.content import CvContent
from assistant.modules.cv.guard import GuardRefused, ResumeGuard
from assistant.modules.cv.mcp import ToolInfo
from assistant.modules.cv.rezi import TOOLS, answer_id, check_tools, resume_ids
from assistant.modules.cv.rezi_json import read_rezi
from assistant.modules.cv.tests.fake_rezi import FAKE_URL, browser_for, fake_rezi

# --- the guard --------------------------------------------------------------------------------------------


def test_the_guard_allows_new_resumes_and_only_its_own_updates():
    guard = ResumeGuard()
    guard.check_write(None, {"name": "Acme – Engineer"})  # a new resume
    with pytest.raises(GuardRefused, match="protected"):
        guard.check_write("r1", {"name": "x"})
    for hidden in ({"id": "r1"}, {"resumeId": "r1"}, {"resume_id": "r1"}, {"_id": "r1"}):
        with pytest.raises(GuardRefused, match="resume_id"):
            guard.check_write(None, hidden)
    guard.created("r9", "Acme – Engineer")
    guard.check_write("r9", {"name": "Acme – Engineer 2"})
    assert guard.owns("r9") and not guard.owns("r1")
    back = ResumeGuard.from_value(guard.as_value())
    assert back.as_value() == {"created": [{"id": "r9", "name": "Acme – Engineer"}]}
    assert ResumeGuard.from_value(None).as_value() == {"created": []}
    assert ResumeGuard.from_value({"created": ["junk", {"name": "no id"}]}).as_value() == {"created": []}
    with pytest.raises(ValueError):
        guard.created("")


# --- reading Rezi's answers ------------------------------------------------------------------------------


def test_ids_from_the_list_and_from_a_write_answer():
    listing = {"resumes": [{"id": "r1", "name": "A", "sections": [{"id": "s1"}]}, {"resumeId": 7}], "total": 2}
    assert resume_ids(listing) == {"r1", "7"}  # not the section's id inside a resume
    assert resume_ids([{"_id": "x"}]) == {"x"} and resume_ids(None) == set()
    assert answer_id({"id": "r3"}) == "r3" and answer_id({"resume": {"resume_id": "r4"}}) == "r4"
    assert answer_id({"saved": True}) is None and answer_id("r3") is None and answer_id({"id": True}) is None


def test_the_live_tool_list_is_checked_against_what_the_items_send():
    def tool(name, props=(), required=()):
        return ToolInfo(name, "", {"type": "object", "properties": {p: {} for p in props}, "required": list(required)})

    same = [tool(n, a, a) for n, a in TOOLS.items()]
    assert check_tools(same) == {"ok": True, "missing": [], "new": [], "arguments": {}}
    changed = [t for t in same if t.name != "search_jobs"] + [tool("export_pdf", ["resume_id"])]
    changed[1] = tool("read_resume", ["id"], ["id"])
    report = check_tools(changed)
    assert not report["ok"] and report["missing"] == ["search_jobs"] and report["new"] == ["export_pdf"]
    assert report["arguments"]["read_resume"] == {"we_send": ["resume_id"], "it_takes": ["id"], "it_requires": ["id"]}
    assert "write_resume" not in check_tools([tool("write_resume", ["resume", "resume_id"], ["resume"])])["arguments"]
    assert "write_resume" in check_tools([tool("write_resume", ["resume_id", "name"], ["name"])])["arguments"]


# --- Rezi's resume JSON as sections ---------------------------------------------------------------------

REZI_RESUME = {
    "id": "r3", "name": "Acme – Engineer", "updatedAt": "2026-11-06",
    "contact": {"firstName": "Jane", "lastName": "Doe", "email": "c@example.com", "phone": "555-0100"},
    "summary": "Engineer who builds robots.\nTen years of widgets.",
    "experience": [
        {"title": "Senior Engineer", "company": "Initech", "location": "Springfield, IL",
         "startDate": "2018-04", "current": True, "highlights": ["Cut widget cost 30%", "Led 4 testers"]},
    ],
    "education": [{"degree": "M.S. Widget Engineering", "school": "Example State University", "date": "06/2012"}],
    "skills": [{"name": "Languages", "keywords": ["Python", "C++"]}],
    "theme": {"color": "blue"},
}  # fmt: skip


def test_rezi_json_becomes_the_cvs_sections():
    content, skipped = read_rezi(REZI_RESUME)
    assert content.sections == {
        "contact": ("Jane Doe", "c@example.com", "555-0100"),
        "summary": ("Engineer who builds robots.", "Ten years of widgets."),
        "experience": ("Senior Engineer, Initech, Springfield, IL | Apr 2018 – Present",
                       "• Cut widget cost 30%", "• Led 4 testers"),
        "education": ("M.S. Widget Engineering, Example State University | Jun 2012",),
        "skills": ("Languages", "• Python", "• C++"),
    }  # fmt: skip
    assert skipped == ["theme"]
    assert CvContent.from_rezi({"resume": REZI_RESUME}).sections == content.sections  # unwrapped


def test_rezi_json_as_a_list_of_blocks_and_nothing_known():
    blocks = {"sections": [{"type": "Work Experience", "items": [{"position": "Engineer", "employer": "Acme",
                                                                  "start": "2019-03", "end": "2020-12"}]},
                           {"title": "Summary", "content": "Builds things"}, {"type": "hobbies", "items": ["chess"]}]}
    content, skipped = read_rezi(blocks)
    assert content.sections == {"experience": ("Engineer, Acme | Mar 2019 – Dec 2020",), "summary": ("Builds things",)}
    assert skipped == ["[2]"]
    with pytest.raises(ValueError, match="no resume sections"):
        read_rezi({"id": "r1", "hobbies": ["chess"]})


def test_the_cv_and_rezis_reading_of_it_compare_clean():
    mine = CvContent(sections={
        "contact": ("Jane Doe", "c@example.com | 555-0100"),
        "experience": ("Senior Engineer, Initech, Springfield, IL | Apr 2018 – Present", "• Cut widget cost 30%",
                       "• Led 4 testers"),
        "education": ("Example State University, M.S. Widget Engineering | Jun 2012",),
    })  # fmt: skip
    rezi = CvContent.from_rezi({k: REZI_RESUME[k] for k in ("contact", "experience", "education")})
    assert FieldCompare().diff(mine, rezi).match_ok
    lost_place = CvContent(sections={**mine.sections, "experience": ("Senior Engineer, Initech | Apr 2018 – Present",
                                                                    "• Cut widget cost 30%", "• Led 4 testers")})
    assert [i.kind for i in FieldCompare().diff(lost_place, rezi).issues] == ["extra"]  # Rezi shows a place the CV hasn't


# --- the items, against the fake Rezi ---------------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def start(tmp_path: Path, monkeypatch, transport, opened: list[str] | None = None) -> App:
    monkeypatch.setattr(CvModule, "http_transport", transport)
    if opened is not None:
        monkeypatch.setattr(CvModule, "open_browser", staticmethod(browser_for(transport, opened)))
    section = {"output_dir": str(tmp_path / "out"), "token_file": str(tmp_path / "rezi_token.json"),
               "rezi_url": FAKE_URL, "callback_port": free_port()}  # fmt: skip
    app = App([CvModule], {"modules": {"enabled": ["cv"], "cv": section | {"agent": {"enabled": False}}}, "core": {}})
    await app.start()
    return app


async def use(app: App, name: str, **args):
    return await app.router.send(InvokeTool(name=name, args=args, caller="cv_agent"))


def never_called(request: httpx2.Request) -> httpx2.Response:
    raise AssertionError(f"no request expected, got {request.method} {request.url}")


async def test_signed_out_items_send_nothing_and_say_sign_in(tmp_path, monkeypatch):
    app = await start(tmp_path, monkeypatch, httpx2.MockTransport(never_called))
    try:
        status = await use(app, "rezi.status")
        assert status.is_ok and status.value["signed_in"] is False and status.value["created"] == []
        for name, args in (("rezi.list_resumes", {}), ("rezi.read_resume", {"resume_id": "r1"}),
                           ("rezi.get_resume_format", {}), ("rezi.write_resume", {"resume": {"name": "x"}}),
                           ("rezi.search_jobs", {"role": "Engineer"}), ("rezi.get_job_details", {"job_id": "j1"})):  # fmt: skip
            result = await use(app, name, **args)
            assert result.status is Status.NOT_AVAILABLE and "rezi.sign_in" in result.error, name
        assert (await use(app, "rezi.sign_in", timeout=5)).status is Status.INVALID_ARGUMENTS
        assert (await use(app, "rezi.write_resume", resume={})).status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()
    assert not (tmp_path / "rezi_token.json").exists()


async def test_sign_in_read_and_write_only_what_it_made(tmp_path, monkeypatch):
    opened: list[str] = []
    async with fake_rezi() as (auth, transport):
        app = await start(tmp_path, monkeypatch, transport, opened)
        try:
            signed = await use(app, "rezi.sign_in", timeout=30)
            assert signed.is_ok, signed.error
            assert signed.value["signed_in"] and len(opened) == 1
            assert signed.value["check"] == {"ok": True, "missing": [], "new": ["broken"], "arguments": {}}

            listed = await use(app, "rezi.list_resumes")
            assert [r["id"] for r in listed.value["data"]["resumes"]] == ["r1", "r2"]
            read = await use(app, "rezi.read_resume", resume_id="r1")
            assert read.value["sections"] == {"summary": ["Engineer"]} and read.value["created_here"] is False
            assert (await use(app, "rezi.get_resume_format")).value["data"]["sections"][0] == "contact"

            # every resume already there is protected; nothing is sent
            refused = await use(app, "rezi.write_resume", resume={"name": "x"}, resume_id="r1")
            assert refused.status is Status.INVALID_ARGUMENTS and "protected" in refused.error
            hidden = await use(app, "rezi.write_resume", resume={"name": "x", "id": "r1"})
            assert hidden.status is Status.INVALID_ARGUMENTS
            assert auth.store.writes == [] and auth.store.resumes["r1"]["name"] == "CV_Test_Umbrella"

            made = await use(app, "rezi.write_resume", resume={"name": "Acme – Engineer",
                                                               "sections": {"summary": ["Robots"]}})  # fmt: skip
            assert made.is_ok, made.error
            assert made.value["created"] and made.value["resume_id"] == "r3"
            assert made.value["read_back"]["data"]["name"] == "Acme – Engineer"
            updated = await use(app, "rezi.write_resume", resume={"sections": {"skills": ["Python"]}}, resume_id="r3",
                                verify=False)  # fmt: skip
            assert updated.is_ok and not updated.value["created"] and "read_back" not in updated.value
            assert auth.store.resumes["r3"]["sections"] == {"summary": ["Robots"], "skills": ["Python"]}
            assert (await use(app, "rezi.read_resume", resume_id="r3")).value["created_here"] is True
            status = (await use(app, "rezi.status")).value
            assert status["created"] == [{"id": "r3", "name": "Acme – Engineer"}] and status["days_left"] == 30.0

            jobs = await use(app, "rezi.search_jobs", role="Engineer", location="Springfield")
            assert jobs.value["data"]["jobs"][0]["location"] == "Springfield"
            job = await use(app, "rezi.get_job_details", job_id="j1")
            assert job.value["data"]["job_id"] == "j1"
            missing = await use(app, "rezi.read_resume", resume_id="nope")
            assert missing.status is Status.FAILED and not missing.retryable and "not found" in missing.error

            # a reload keeps the ids it made
            assert (await app.router.send(ReloadModule(module_id="cv", now=True))).is_ok
            assert (await use(app, "rezi.status")).value["created"] == [{"id": "r3", "name": "Acme – Engineer"}]
        finally:
            await app.stop()


async def test_a_slow_sign_in_goes_on_after_the_item_answers(tmp_path, monkeypatch):
    # The module door gives an item 30 s and cancels it after; a real sign-in waits for you in the
    # browser for longer (first real run, 2026-11-07). The item answers "waiting"; the sign-in goes on.
    import asyncio

    opened: list[str] = []
    async with fake_rezi() as (_auth, transport):
        follow = browser_for(transport, opened)
        go = asyncio.Event()

        async def slow_browser(url: str) -> None:
            opened.append("asked")
            await go.wait()  # you're still on Rezi's page
            await follow(url)

        monkeypatch.setattr(CvModule, "sign_in_wait", 0.2)
        monkeypatch.setattr(CvModule, "open_browser", staticmethod(slow_browser))
        app = await start(tmp_path, monkeypatch, transport)
        try:
            first = await use(app, "rezi.sign_in", timeout=30)
            assert first.is_ok and first.value["signing_in"] and first.value["sign_in"]["state"] == "waiting"
            again = await use(app, "rezi.sign_in", timeout=30)  # the same sign-in: no second browser
            assert again.value["signing_in"] and opened == ["asked"]
            assert (await use(app, "rezi.status")).value["sign_in"]["state"] == "waiting"
            go.set()
            for _ in range(100):
                status = (await use(app, "rezi.status")).value
                if status["sign_in"]["state"] != "waiting":
                    break
                await asyncio.sleep(0.05)
            assert status["signed_in"] and status["sign_in"]["state"] == "done", status
            assert status["sign_in"]["check"]["ok"] is True
        finally:
            await app.stop()


async def test_a_write_answer_without_the_id_finds_it_in_the_list(tmp_path, monkeypatch):
    async with fake_rezi() as (auth, transport):
        auth.store.answer_with_id = False
        app = await start(tmp_path, monkeypatch, transport, [])
        try:
            assert (await use(app, "rezi.sign_in", timeout=30)).is_ok
            made = await use(app, "rezi.write_resume", resume={"name": "Acme – Engineer"})
            assert made.is_ok and made.value["resume_id"] == "r3" and "warning" not in made.value
            assert (await use(app, "rezi.write_resume", resume={"name": "Acme 2"}, resume_id="r3")).is_ok
        finally:
            await app.stop()


async def test_no_answer_from_rezi_is_retryable(tmp_path, monkeypatch):
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    from assistant.modules.cv.mcp import TokenStore

    TokenStore(tmp_path / "rezi_token.json").save({"access_token": "abc", "token_type": "Bearer"})
    app = await start(tmp_path, monkeypatch, httpx2.MockTransport(down))
    try:
        result = await use(app, "rezi.list_resumes")
        assert result.status is Status.FAILED and result.retryable
    finally:
        await app.stop()


async def test_cv_compare_takes_rezis_resume_json(tmp_path, monkeypatch):
    app = await start(tmp_path, monkeypatch, httpx2.MockTransport(never_called))
    try:
        edited = {"experience": ["Senior Engineer, Initech, Springfield, IL | Apr 2018 – Present",
                                 "• Cut widget cost 30%", "• Led 4 testers"]}
        same = await use(app, "cv.compare", edited=edited, parsed_resume={"experience": REZI_RESUME["experience"]})
        assert same.is_ok and same.value["match_ok"], same.value
        lost = await use(app, "cv.compare", edited=edited, parsed_resume={"experience": [{"title": "Senior Engineer"}]})
        assert lost.is_ok and not lost.value["match_ok"]
        both = await use(app, "cv.compare", edited=edited, parsed_text="x", parsed_resume={"summary": "x"})
        assert both.status is Status.INVALID_ARGUMENTS
        nothing = await use(app, "cv.compare", edited=edited, parsed_resume={"hobbies": ["chess"]})
        assert nothing.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()
