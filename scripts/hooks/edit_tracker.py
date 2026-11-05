"""PreToolUse hook for file edits: a note when a file is edited again.

Reads the hook JSON from stdin, records the normalized file path in
.claude/state/, and on a repeat edit returns a non-blocking note to the agent
through hookSpecificOutput.additionalContext. The note arrives with the tool
call itself, so it never costs an extra step.

Two behaviors:
- Your own Claude Code sessions (no ASSISTANT_AGENT): Edit and Write, counted per
  session, a note on every repeat edit. Unchanged.
- The app's worker (ASSISTANT_AGENT set, by the main_assistant module): every edit
  tool, counted per task (the id in ASSISTANT_TASK_FILE, so the count survives
  handoffs), one note per file, on its second edit. ASSISTANT_EDIT_NOTE=0 turns it off.

Never blocks and never fails: on any error it prints nothing and exits 0.
Standard library only.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parents[2] / ".claude" / "state"
MAX_AGE_SECONDS = 24 * 60 * 60
# Same list as EDIT_TOOLS in assistant/infra/session_agent.py: tool → where its input names the file.
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
WORKER_ONLY_TOOLS = ("MultiEdit", "NotebookEdit")


def _normalize(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").lower()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def _cleanup() -> None:
    cutoff = time.time() - MAX_AGE_SECONDS
    for old in STATE_DIR.glob("edits-*.txt"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def _message(path: str, count: int) -> str:
    if count == 2:
        lead = f"You already edited {path} in this task."
    else:
        lead = f"This is edit number {count} to {path} in this task."
    return (
        f"{lead} Fold the remaining changes to this file into one Write "
        "unless a second edit is truly needed (batching skill)."
    )


def _worker_message(path: str) -> str:
    return f"You've now edited {path} twice in this task. Make the rest of its changes in one pass (batching skill)."


def _task_id() -> str:
    task_file = os.environ.get("ASSISTANT_TASK_FILE")
    if not task_file:
        return ""
    try:
        return Path(task_file).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def main() -> None:
    worker = bool(os.environ.get("ASSISTANT_AGENT"))
    if worker and os.environ.get("ASSISTANT_EDIT_NOTE") == "0":
        return
    # utf-8-sig: PowerShell pipes add a BOM that json.loads rejects.
    data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    tool = str(data.get("tool_name") or "")
    if not worker and tool in WORKER_ONLY_TOOLS:
        return
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get(EDIT_TOOLS.get(tool, "file_path"))
    session_id = str(data.get("session_id") or "")
    task_id = _task_id() if worker else ""
    if not file_path or not (task_id or session_id):
        return
    name = f"edits-task-{_safe(task_id)}.txt" if task_id else f"edits-{_safe(session_id)}.txt"

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup()

    state = STATE_DIR / name
    key = _normalize(str(file_path))
    seen = state.read_text(encoding="utf-8").splitlines() if state.exists() else []
    count = seen.count(key) + 1
    with state.open("a", encoding="utf-8") as f:
        f.write(key + "\n")

    if worker:
        note = _worker_message(str(file_path)) if count == 2 else None
    else:
        note = _message(str(file_path), count) if count >= 2 else None
    if note:
        out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}
        sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
