"""The return address: the finished CV reaches the agent that asked for it, by agent id, from disk.

`cv.task` puts its caller in the request (`CvRequest.reply_to`); the job start saves the request in
the job's `job_start.json`. When the Submit watch (or `cv.tool_result`) first sees the user's Submit,
the module sends that agent `reply_text` through the Hub's `DeliverMessage` (into its open task, a
new task, or held until its turn ends or it starts) and marks the Submit told with how
(`mark_replied`), so a second look tells nobody. A Submit the watch delivered also gives cv_agent
`submit_notice`, one line for its next turn. No task id, no worker memory and no reload is involved,
so a relaunch on either side loses nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from assistant.modules.cv.job_start import read_record, write_record
from assistant.modules.cv.tool import MIN_PT


def pending_reply(folder: Path, submitted_at: str) -> str | None:
    """The agent to tell about the Submit made at `submitted_at`: the job's `reply_to`, unless
    there is none or this Submit was already told."""
    record = read_record(folder)
    to = str((record.get("request") or {}).get("reply_to") or "")
    if not to or (record.get("replied") or {}).get("submitted_at") == submitted_at:
        return None
    return to


def mark_replied(folder: Path, submitted_at: str, to: str, how: str) -> None:
    """Note in `job_start.json` that the Submit made at `submitted_at` was told to `to` (`how`)."""
    record = read_record(folder)
    if record:
        write_record(folder, record | {"replied": {"submitted_at": submitted_at, "to": to, "how": how}})


def small_text_note(result: dict[str, Any]) -> str:
    """"Note: N text pieces print under 10 pt (a warning only…)." or "" when there are none."""
    small = result.get("small_text") or []
    if not small:
        return ""
    return (f"Note: {len(small)} text piece{'' if len(small) == 1 else 's'} print under "
            f"{result.get('min_pt') or MIN_PT} pt (a warning only; the user submitted it as it is).")  # fmt: skip


def reply_text(result: dict[str, Any]) -> str:
    """What the asking agent reads: the job, the final PDF, the score and where `result.json` is."""
    role, company = result.get("role") or "the role", result.get("company") or "the company"
    score, target = result.get("final_score"), result.get("target_score")
    warning = f"{note}\n" if (note := small_text_note(result)) else ""
    return (f"From the cv module: the CV for {role} at {company} is ready. The user submitted it in the CV Tool "
            f"at {result.get('submitted_at') or '(unknown time)'}.\nPDF: {result.get('pdf_path') or '(none)'}\n"
            f"Score: {score} (target {target}). The full result is {result.get('report_path') or 'result.json'}.\n"
            f"{warning}Carry on with the application from here: this Submit is the user's yes. cv_agent's own "
            f"CV_RESULT line has status \"ready\" (everything but this Submit); nothing more comes from it.")


def rezi_click_text(item: dict[str, Any]) -> str:
    """cv_agent's message when the user clicks Send JD and CV to Rezi: the click is their yes, so it
    starts the First Draft with Rezi by itself (the CV Tool's `rezi_request` event)."""
    role, company, job_id = item.get("role"), item.get("company"), item.get("job_id")
    what = f"the CV for {role} at {company} (CV Tool job {job_id})" if role and company else f"CV Tool job {job_id}"
    return (f"The user pressed Send JD and CV to Rezi in the CV Tool on {what} at {item.get('at') or 'an unknown time'}"
            f" (request {item.get('request_id')}). That click is their yes for the Rezi write: start the First Draft "
            f"with Rezi now, without asking again (cv.tool_status job_id {job_id} shows the pending rezi_request; "
            f"pass its request_id in cv.tool_round).")


def submit_notice(result: dict[str, Any], job_id: str, to: str, how: str, delivered: bool) -> str:
    """cv_agent's one plain line about a Submit the module delivered by itself: the job, the time,
    who got it and how, and the small-text note if any."""
    role, company = result.get("role"), result.get("company")
    what = f"the CV for {role} at {company} (job {job_id})" if role and company else f"job {job_id}"
    went = f"the cv module delivered it to {to} ({how})" if delivered else f"delivering it to {to} {how}"
    note = f" {note}" if (note := small_text_note(result)) else ""
    return (f"The user pressed Submit in the CV Tool on {what} at {result.get('submitted_at') or 'an unknown time'}; "
            f"{went}.{note}")
