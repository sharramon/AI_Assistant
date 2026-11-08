"""Rezi's real resume format (seen live 2026-11-07): read into the CV's lines, a CV written into it
and back unchanged, and `rezi.write_resume` from sections against the fake Rezi."""

from __future__ import annotations

from assistant.contracts import InvokeTool, Status
from assistant.modules.cv.content import CvContent
from assistant.modules.cv.rezi_json import read_rezi, rezi_data, write_rezi
from assistant.modules.cv.tests.fake_rezi import fake_rezi
from assistant.modules.cv.tests.test_rezi_items import start

# The shape of a live read_resume answer (made-up person).
LIVE = {
    "id": "x1", "name": "CV_Ada", "hiddenSections": ["references"], "coverLetterId": None, "url": "https://app.rezi.ai/x1",
    "data": {
        "contact": {"name": "Ada Lovelace", "email": "ada@example.com", "phone": "(555) 010-0100",
                    "linkedin": "linkedin.com/in/ada", "city": {"label": "London", "value": "London"},
                    "state": {"label": "UK", "value": "UK"}, "website": ""},
        "summary": {"summary": "Engineer of engines."},
        "experience": {
            "b": {"role": "Analyst", "company": "Babbage Ltd", "location": "Babbage Ltd",
                  "duration": "June 2020 - May 2021", "description": "Wrote the first program\n• Found a bug", "index": 1},
            "a": {"role": "Lead", "company": "Engine Co", "location": "London", "duration": "June 2021 - Present",
                  "description": "Led 5 people", "index": 0},
            "h": {"role": "Old", "company": "Gone", "index": 2, "hide": True},
        },
        "military": {"m": {"title": "Sergeant", "branch": "Air Force", "duration": "2018 - 2019", "index": 0}},
        "education": {"e": {"qualification": "M.S. Mathematics", "date": "2019", "gpa": "3.9/4.0",
                            "institution": "University of London", "location": "London", "index": 0}},
        "skills": {"s2": {"skill": "Tools: Git", "index": 1}, "s1": {"skill": "Languages: Python", "index": 0}},
        "awards": {"w": {"name": "Best Paper", "institution": "Royal Society", "date": "2020", "index": 0}},
        "publication": {"p": {"title": "Notes", "conference": "Taylor's Memoirs", "date": "1843", "index": 0}},
        "references": {"r": {"name": "Charles", "index": 0}},
    },
}  # fmt: skip


def test_rezis_live_format_reads_as_the_cvs_lines():
    content, skipped = read_rezi(LIVE)
    assert content.sections == {
        "contact": ("Ada Lovelace", "(555) 010-0100 | ada@example.com | linkedin.com/in/ada | London, UK"),
        "summary": ("Engineer of engines.",),
        "experience": ("Lead, Engine Co, London | June 2021 - Present", "• Led 5 people",
                       "Analyst, Babbage Ltd | June 2020 - May 2021", "• Wrote the first program", "• Found a bug",
                       "Sergeant, Air Force | 2018 - 2019"),
        "education": ("M.S. Mathematics, 2019 GPA : 3.9/4.0", "University of London, London"),
        "skills": ("Languages: Python", "Tools: Git"),
        "awards": ("• Best Paper, Royal Society | 2020",),
        "publications": ("• Notes, Taylor's Memoirs | 1843",),
    }  # fmt: skip
    assert skipped == ["references"]  # no index ints, no hidden entry, nothing doubled
    assert rezi_data(LIVE["data"]) is LIVE["data"] and rezi_data({"summary": "text"}) is None


CV = CvContent(sections={
    "contact": ("Ada Lovelace", "Engine Engineer", "(555) 010-0100 | ada@example.com | linkedin.com/in/ada | London, UK"),
    "summary": ("Engineer of engines.",),
    "education": ("Master of Science (M.Sc.) in Mathematics, Expected December 2026 GPA : 3.9/4.0 (current)",
                  "University of London, London, England", "Bachelor of Arts in Poetry, 2017",
                  "University of Cambridge, Cambridge, England."),
    "skills": ("Languages: Python, C++", "Tools: Git"),
    "experience": ("Lead, Engine Co (Analytical Group), London | June 2021 – Present", "• Led 5 people",
                   "• Cut cost 30%, on time", "SERGEANT, Royal Air Force (RAF) | March 2018 – Dec 2019"),
    "projects": ("Difference Engine, Home | 2020", "• Built it"),
    "awards": ("• Best Paper, 2020", "• Featured 'Best Games'"),
})  # fmt: skip


def test_a_cv_goes_into_rezis_format_and_back_unchanged():
    resume, left_out = write_rezi(CV, "Acme – Engineer", "Engineer", "Acme", "Build engines")
    assert {k: resume[k] for k in ("name", "jobTitle", "jobCompany", "jobDescription")} == {
        "name": "Acme – Engineer", "jobTitle": "Engineer", "jobCompany": "Acme", "jobDescription": "Build engines"}
    data = resume["data"]
    assert data["contact"] == {"name": "Ada Lovelace", "phone": "(555) 010-0100", "email": "ada@example.com",
                               "linkedin": "linkedin.com/in/ada", "city": "London", "state": "UK"}  # fmt: skip
    assert left_out == ["Engine Engineer"]  # Rezi's contact has no headline field
    first = next(e for e in data["experience"].values() if e["index"] == 0)
    assert first == {"role": "Lead", "company": "Engine Co (Analytical Group), London", "duration":
                     "June 2021 – Present", "description": "Led 5 people\nCut cost 30%, on time", "index": 0}  # fmt: skip
    degree = next(e for e in data["education"].values() if e["index"] == 0)
    assert degree == {"qualification": "Master of Science (M.Sc.) in Mathematics", "date": "Expected December 2026",
                      "gpa": "3.9/4.0 (current)", "institution": "University of London", "location": "London, England",
                      "index": 0}  # fmt: skip
    back, skipped = read_rezi(resume)
    assert skipped == []
    want = dict(CV.sections) | {"contact": (CV.lines("contact")[0], CV.lines("contact")[2])}
    assert back.sections == want


def test_an_update_reuses_the_resumes_entries_and_hides_the_rest():
    made, _ = write_rezi(CV, "Acme – Engineer")
    shorter = CvContent(sections={"experience": ("Lead, Engine Co | 2021",)})
    update, _ = write_rezi(shorter, "Acme – Engineer", existing={"data": made["data"]})
    old_keys = sorted(made["data"]["experience"], key=lambda k: made["data"]["experience"][k]["index"])
    assert list(update["data"]["experience"]) == old_keys
    assert update["data"]["experience"][old_keys[1]] == {"index": 1, "hide": True}


async def call(app, item: str, **args):
    return await app.router.send(InvokeTool(name=item, args=args, caller="test"))


async def test_write_resume_from_sections_through_the_fake(tmp_path, monkeypatch):
    async with fake_rezi() as (auth, transport):
        opened: list[str] = []
        app = await start(tmp_path, monkeypatch, transport, opened)
        try:
            assert (await call(app, "rezi.sign_in")).is_ok
            sections = {k: list(v) for k, v in CV.sections.items()}
            for bad in ({}, {"sections": sections, "resume": {"name": "x"}}, {"sections": sections},
                        {"sections": {"hobbies": ["chess"]}, "name": "x"}, {"sections": {"skills": "x"}, "name": "x"}):
                assert (await call(app, "rezi.write_resume", **bad)).status is Status.INVALID_ARGUMENTS, bad
            refused = await call(app, "rezi.write_resume", sections=sections, resume_id="r1")
            assert refused.status is Status.INVALID_ARGUMENTS and "protected" in refused.error
            made = await call(app, "rezi.write_resume", sections=sections, name="Acme – Engineer", job_title="Engineer",
                             job_company="Acme", jd_text="Build engines")  # fmt: skip
            assert made.is_ok, made.error
            new = made.value["resume_id"]
            assert new == "r3" and made.value["left_out"] == ["Engine Engineer"]
            assert made.value["read_back"]["sections"]["experience"] == list(CV.lines("experience"))
            keywords = await call(app, "rezi.generate_keywords", resume_id=new)
            assert keywords.is_ok and keywords.value["data"]["keywords"] == ["build", "engines"]
            assert (await call(app, "rezi.generate_keywords", resume_id="r1")).status is Status.INVALID_ARGUMENTS
            sent = auth.store.writes[-1]
            assert sent["resume_id"] is None and sent["jobCompany"] == "Acme" and "data" in sent
            edited = sections | {"skills": ["Languages: Python, C++", "Tools: Git, Docker"], "experience":
                                 sections["experience"][:3]}  # fmt: skip
            updated = await call(app, "rezi.write_resume", sections=edited, resume_id=new)
            assert updated.is_ok, updated.error
            back = updated.value["read_back"]["sections"]
            assert back["skills"] == edited["skills"] and back["experience"] == edited["experience"]
            assert [r["id"] for r in auth.store.resumes.values()] == ["r1", "r2", "r3"]  # nothing else made
            assert auth.store.resumes["r1"]["sections"] == {"summary": ["Engineer"]}  # the others untouched
        finally:
            await app.stop()
