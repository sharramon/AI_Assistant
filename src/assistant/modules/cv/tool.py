"""The CV Tool, the cv module's UI half: its settings, the CV's content in the app's shape, and
`CvTool`, which launches and calls the app (`src/cv_tool`, its own process) the way `html_viewer`
does its viewer: `CompanionHandover` from `app_kit`, a fixed port, `/api/ping` and `/api/quit`.

The app never imports the main app's code, so the module reads the base CV's PDF (`pdf_read`) and
sends the content in the app's shape (`tool_content`). The items use only the app's JSON API, so
they need no window (`--window none`; `cv.open_tool` opens the window with `/api/window`). The job
start (the gate) never opens the app: cv_agent calls `cv.open_tool` when the user tells it to start.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app_kit import CompanionHandover
from app_kit.local_guard import LOOPBACK_HOSTS
from assistant.modules.cv.content import CvContent
from assistant.modules.cv.odt import BULLET
from assistant.modules.cv.pdf_read import read_pdf
from assistant.modules.cv.rezi_json import split_head

APP = "cv_tool"  # the package `python -m cv_tool` runs, and its ping's name
PORT = 8771
MIN_PT = 10  # the user's floor for text size, a warning only: the default of cv_tool's min_pt setting (page_settings.json), 2026-11-10
MIN_PT_ADVICE = (f"Text under {MIN_PT} pt: shorten the wording (keep every fact) or ask the user; never shrink "
                 "the font. A warning only: the user's Submit always goes through")  # fmt: skip
_DEGREE = re.compile(r"(Master|Bachelor|Doctor|Ph\.?D|M\.S|B\.S|Associate)", re.IGNORECASE)
_CALL_SECONDS = 25.0  # the door gives an item 30 s; a PDF export is a few


class ToolError(Exception):
    """The CV Tool answered with an error: its text."""


def tool_settings(section: Any, cv_dir: str, rules_dir: str, workspace: str) -> dict[str, Any]:
    """The checked `[tool]` table: host (this machine only), port, `data_dir` (default
    `<workspace>/cv_tool`), `facts` (default `<workspace>/data/confirmed_facts.json`), plus the CV
    folder and the rules folder the app reads. ValueError if one is wrong."""
    if not isinstance(section, dict):
        raise ValueError(f"cv: [tool] must be a table, not {section!r}")
    host = str(section.get("host", "127.0.0.1"))
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"cv: tool.host must be this machine ({', '.join(sorted(LOOPBACK_HOSTS))}), not {host!r}")
    port = section.get("port", PORT)
    if not (isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535):
        raise ValueError(f"cv: tool.port must be 1 to 65535, not {port!r}")
    base = Path(workspace) if workspace else None
    data_dir = str(section.get("data_dir") or (base / "cv_tool" if base else ""))
    facts = str(section.get("facts") or (base / "data" / "confirmed_facts.json" if base else ""))
    return {"host": host, "port": port, "data_dir": data_dir, "facts": facts, "cv_dir": cv_dir, "rules_dir": rules_dir}


def tool_content(content: CvContent) -> tuple[dict[str, Any], list[str]]:
    """The CV as the CV Tool holds it (`name, contact, summary, skills [[label, text]], experience
    [{title, company, dates, bullets}], education [{degree, detail}], awards, publications,
    education_first`), and the sections it has no place for (left out, e.g. projects).
    Education stays after Experience: only the user moves it up (the section order rule)."""
    out: dict[str, Any] = {"name": "", "contact": [], "summary": "", "skills": [], "experience": [],
                           "education": [], "awards": [], "publications": [], "education_first": False}  # fmt: skip

    def plain(line: str) -> str:
        return line.strip().removeprefix(BULLET.strip()).strip()

    contact = [line.strip() for line in content.lines("contact") if line.strip()]
    if contact:
        out["name"] = contact[0]
    for part in (p.strip() for line in contact[1:] for p in line.split("|")):
        low = part.lower()
        if not part:
            continue
        if "linkedin" in low or low.startswith("http"):
            href = part if low.startswith("http") else "https://www." + part.removeprefix("www.")
            out["contact"].append({"text": part, "href": href, "visible": True})
        else:
            out["contact"].append(part)
    out["summary"] = " ".join(plain(line) for line in content.lines("summary") if plain(line))
    for line in content.lines("skills"):
        if text := plain(line):
            label, colon, rest = text.partition(":")
            out["skills"].append([label.strip(), rest.strip()] if colon else ["", text])
    for line in content.lines("experience"):
        entries = out["experience"]
        if line.strip().startswith(BULLET.strip()):
            if not entries:
                entries.append({"title": "", "company": "", "dates": "", "bullets": []})
            entries[-1]["bullets"].append(plain(line))
        elif entries and not entries[-1]["company"] and not entries[-1]["bullets"] and " | " not in line:
            entries[-1]["company"] = line.strip()  # "Title | dates" with the company on its own line
        elif line.strip():
            title, company, dates = split_head(line)
            entries.append({"title": title, "company": company, "dates": dates, "bullets": []})
    for line in content.lines("education"):
        text, entries = plain(line), out["education"]
        if not text:
            continue
        if _DEGREE.match(text) or not entries:
            entries.append({"degree": text, "detail": []})
        else:
            entries[-1]["detail"].append(text)
    for name in ("awards", "publications"):
        out[name] = [plain(line) for line in content.lines(name) if plain(line)]
    left_out = [n for n in content.names() if n not in ("contact", "summary", "skills", "experience", "education",
                                                         "awards", "publications")]  # fmt: skip
    return out, left_out


class CvTool:
    """The running CV Tool for the module: launched on the first call (`ensure_running`), kept
    across a reload unless its code changed (`export`), quit at the module's stop if it launched it."""

    def __init__(self, handover: Any, checked: dict[str, Any], work_dir: str, log: Any = None,
                 max_rounds: int = 0) -> None:  # fmt: skip
        self._max_rounds = max_rounds  # 0: no cap here
        args =["--port", str(checked["port"]), "--host", checked["host"], "--window", "none"]
        for flag, key in (("--data-dir", "data_dir"), ("--cv-dir", "cv_dir"), ("--rules-dir", "rules_dir"),
                          ("--facts", "facts")):  # fmt: skip
            if checked.get(key):
                args += [flag, str(checked[key])]
        if work_dir:
            args += ["--agent-work", work_dir]
        self._companion = CompanionHandover(handover, APP, checked["host"], checked["port"], args=args,
                                            ping="/api/ping", label="CV Tool", log=log)  # fmt: skip
        self.on_running: Any = None  # called after each call finds the app running (the module's Submit watch)

    async def running(self) -> bool:
        """Whether the CV Tool answers now (no launch)."""
        return await self._companion.app.ping()

    async def events(self) -> Any:
        """The CV Tool's event stream (`submitted` after each Submit), until the app quits.
        OSError if it can't connect."""
        async for item in self._companion.app.events("/api/events"):
            yield item

    async def submitted(self) -> list[dict[str, Any]]:
        """Every job the user submitted, as {job_id, submitted_at}."""
        return list((await self.call("GET", "/api/submitted")).get("jobs") or [])

    def export(self) -> dict[str, Any] | None:
        return self._companion.export()

    async def stop(self) -> None:
        await self._companion.stop()

    async def call(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        """One API call, starting the app first if it isn't running. ToolError if it answers an
        error; OSError or TimeoutError if it can't start."""
        app = self._companion.app
        await app.ensure_running()
        if self.on_running is not None:
            self.on_running()
        answer = await app.call(method, path, body, timeout=_CALL_SECONDS)
        if isinstance(answer, dict) and "error" in answer:
            raise ToolError(str(answer["error"]))
        return answer if isinstance(answer, dict) else {"value": answer}

    async def open(self, job_dir: Path) -> dict[str, Any]:
        """The job the gate set up in `job_dir` (its `job_start.json`) into the CV Tool: the JD, the
        base CV's copy and its content read here; then the window on it. ValueError if the job's
        record is missing or broken."""
        try:
            record = json.loads((job_dir / "job_start.json").read_text(encoding="utf-8"))
            job, request = record["job"], record.get("request", {})
            jd_text = Path(job["jd_file"]).read_text(encoding="utf-8")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"{job_dir} has no readable job_start.json from the job start: {exc}") from exc
        read = await asyncio.to_thread(read_pdf, job["base_cv_copy"])
        content, left_out = tool_content(read.content)
        body = {"company": request.get("company", ""), "role": request.get("role", ""), "jd_text": jd_text,
                "base_cv": job["base_cv_copy"], "content": content, "work_dir": job["work_dir"],
                "source": "cv module"}  # fmt: skip
        for key in ("tool", "jd_url", "notes"):
            if request.get(key):
                body[key] = request[key]
        imported = await self.call("POST", "/api/job/import", body)
        window = await self.call("POST", "/api/window", {"job": imported["job_id"]})
        return {"job_id": imported["job_id"], "tool": imported.get("tool", ""), "window": window,
                "unplaced": list(read.unplaced), "left_out": left_out}  # fmt: skip

    async def status(self, job_id: str) -> dict[str, Any]:
        return await self.call("GET", f"/api/job/status?id={quote(job_id)}")

    async def round(self, job_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        scored = fields.get("score") is not None or bool(fields.get("request_id"))
        if scored or fields.get("content") is not None:  # a content-only round is scored only on an Internal job
            await self._refuse_past_cap(job_id, None if scored else str(fields.get("tool") or ""))
        return await self.call("POST", "/api/round", {**fields, "job_id": job_id})

    async def _refuse_past_cap(self, job_id: str, content_tool: str | None = None) -> None:
        """ValueError if this call adds a score round past `max_rounds`. `content_tool`: the call only
        sends content (with this pick, or the job's), which is a round only on an Internal job."""
        if not self._max_rounds:
            return
        status = await self.status(job_id)
        if content_tool is not None and (content_tool or status.get("tool")) != "Internal":
            return
        done = len((status.get("loop") or {}).get("rounds") or [])
        if done >= self._max_rounds:
            raise ValueError(f"job {job_id} has had {done} ATS Loop rounds, the most (max_rounds = "
                             f"{self._max_rounds}): no more rounds. Tell the user the score; they Submit, or "
                             "score more in the CV Tool themselves")  # fmt: skip

    async def fonts(self, job_id: str) -> dict[str, Any]:
        """The current PDF and its text under 10 pt (a round with nothing in it changes nothing)."""
        answer = await self.round(job_id, {})
        return {"job_id": job_id, "pdf": answer.get("pdf", ""), "small_text": answer.get("small_text", [])}

    async def draft(self, job_id: str, apply: bool = False, reorder: bool = True,
                    add: list[str] | None = None) -> dict[str, Any]:  # fmt: skip
        """The Internal draft's proposals; with `apply`, the reorder and the named backed terms put in,
        then an Internal round (no agent needed)."""
        if not apply:
            return {"job_id": job_id, **await self.call("POST", "/api/draft/internal", {"id": job_id})}
        body = {"id": job_id, "reorder": reorder, "add": list(add or [])}
        return {"job_id": job_id, **await self.call("POST", "/api/draft/internal/apply", body)}

    async def internal_round(self, job_id: str) -> dict[str, Any]:
        """Print the current content, score it with the Internal estimate, save the round: the loop state,
        with the matched and missing keywords."""
        await self._refuse_past_cap(job_id)
        return {"job_id": job_id, "state": await self.call("POST", "/api/loop/internal", {"id": job_id})}

    async def result(self, job_id: str) -> dict[str, Any]:
        return await self.call("GET", f"/api/job/result?id={quote(job_id)}")
