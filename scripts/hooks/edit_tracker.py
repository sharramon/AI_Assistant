"""PreToolUse hook for Edit|Write: warn when a file is edited again in one session.

Reads the hook JSON from stdin, records the normalized file path in
.claude/state/edits-<session_id>.txt, and on a repeat edit returns a
non-blocking note to the agent through hookSpecificOutput.additionalContext.
Never blocks and never fails: on any error it prints nothing and exits 0.
Standard library only.
"""

import json
import re
import sys
import time
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parents[2] / ".claude" / "state"
MAX_AGE_SECONDS = 24 * 60 * 60


def _normalize(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").lower()


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


def main() -> None:
    # utf-8-sig: PowerShell pipes add a BOM that json.loads rejects.
    data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    session_id = str(data.get("session_id") or "")
    file_path = (data.get("tool_input") or {}).get("file_path")
    if not session_id or not file_path:
        return
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup()

    state = STATE_DIR / f"edits-{safe_id}.txt"
    key = _normalize(str(file_path))
    seen = state.read_text(encoding="utf-8").splitlines() if state.exists() else []
    count = seen.count(key) + 1
    with state.open("a", encoding="utf-8") as f:
        f.write(key + "\n")

    if count >= 2:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": _message(str(file_path), count),
            }
        }
        sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
