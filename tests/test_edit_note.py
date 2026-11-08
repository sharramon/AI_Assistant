"""The worker's batching note: the edit hook (scripts/hooks/edit_tracker.py) and the env that reaches it."""

import asyncio
import importlib.util
import io
import json
import sys
import types
from pathlib import Path

import pytest

from assistant.infra import ClaudeSession
from assistant.infra.agent_profile import hook_env
from assistant.modules.main_assistant.module import WORKER_PROMPT

HOOK = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "edit_tracker.py"
WORKER_ENV = ("ASSISTANT_AGENT", "ASSISTANT_TASK_FILE", "ASSISTANT_EDIT_NOTE")


@pytest.fixture
def hook(tmp_path, monkeypatch, capsys):
    """Run the hook in-process with its state in tmp_path; returns the note, or None."""
    spec = importlib.util.spec_from_file_location("edit_tracker", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.STATE_DIR = tmp_path / "state"
    for name in WORKER_ENV:
        monkeypatch.delenv(name, raising=False)

    def run(tool, path, session="s1", **env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        data = {"session_id": session, "tool_name": tool, "tool_input": {key: path}}
        monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(json.dumps(data).encode())))
        module.main()
        out = capsys.readouterr().out
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else None

    return run


def test_your_own_sessions_keep_the_old_behavior(hook):
    assert hook("Edit", "C:\\r\\a.md") is None
    assert "You already edited" in hook("Write", "c:/r/a.md")
    assert "edit number 3" in hook("Edit", "C:\\r\\a.md")  # every repeat, as before
    assert hook("MultiEdit", "C:\\r\\a.md") is None  # the new tools are the worker's only
    assert hook("NotebookEdit", "C:\\r\\n.ipynb") is None


def test_the_worker_gets_one_note_per_file_counted_by_task(hook, tmp_path):
    task_file = tmp_path / "task.txt"
    task_file.write_text("t1")
    env = hook_env("main_assistant", task_file, edit_note=True)
    assert hook("Edit", "C:\\r\\a.md", **env) is None
    note = hook("MultiEdit", "c:/r/a.md", **env)
    assert note.startswith("You've now edited c:/r/a.md twice")
    assert hook("Write", "C:\\r\\a.md", **env) is None  # once per file
    assert hook("NotebookEdit", "C:\\r\\n.ipynb", session="s1", **env) is None
    # A handoff: a new session, the same task, so the count goes on.
    assert "twice" in hook("NotebookEdit", "C:\\r\\n.ipynb", session="s2", **env)
    task_file.write_text("t2")  # a new task starts over
    assert hook("Edit", "C:\\r\\a.md", session="s2", **env) is None


def test_the_off_switch_silences_the_worker_note(hook, tmp_path):
    task_file = tmp_path / "task.txt"
    task_file.write_text("t1")
    env = hook_env("main_assistant", task_file, edit_note=False)
    assert hook("Edit", "C:\\r\\a.md", **env) is None
    assert hook("Edit", "C:\\r\\a.md", **env) is None


def test_the_worker_prompt_has_the_batching_line():
    assert "make them in one pass" in WORKER_PROMPT
    assert "never means skipping" in WORKER_PROMPT


async def test_claude_session_passes_its_env_to_the_process():
    events = []
    code = (
        "import json, os, sys; "
        "print(json.dumps({'type': 'env', 'agent': os.environ.get('ASSISTANT_AGENT')}), flush=True); "
        "sys.stdin.read()"
    )
    session = ClaudeSession([sys.executable, "-c", code], env={"ASSISTANT_AGENT": "main_assistant"},
                            on_event=events.append)
    await session.start()
    async with asyncio.timeout(10):
        while not events:
            await asyncio.sleep(0.01)
    await session.close()
    assert events[0] == {"type": "env", "agent": "main_assistant"}
