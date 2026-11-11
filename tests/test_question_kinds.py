"""Chunk 9 (second half) and chunk 10: module names in config, typed question kinds."""

from __future__ import annotations

import tomllib
from pathlib import Path

from assistant.contracts import (
    MAX_SNIPS,
    PASTED_FILE,
    RISKY_PREFIX,
    QuestionKind,
    ReportKind,
    TaskInfo,
    TaskState,
    TaskUpdated,
)
from assistant.core.permissions import handler

CONFIG = Path(__file__).resolve().parents[1] / "config" / "default.toml"


def test_question_kind_of_a_report() -> None:
    assert QuestionKind.of(ReportKind.PERMISSION, "Bash rm x") is QuestionKind.PERMISSION
    assert QuestionKind.of(ReportKind.NEED, f"{RISKY_PREFIX} delete the logs") is QuestionKind.RISKY
    assert QuestionKind.of(ReportKind.NEED, "Which city?") is QuestionKind.NEED
    assert QuestionKind.of(ReportKind.PROGRESS, "Risky: no") is QuestionKind.NONE
    assert QuestionKind.of(None, "") is QuestionKind.NONE


def test_question_kind_defaults_keep_old_senders_working() -> None:
    update = TaskUpdated(task_id="t", state=TaskState.ACTIVE)
    info = TaskInfo(id="t", agent_id="a", text="x", state=TaskState.ACTIVE)
    assert update.question_kind is QuestionKind.NONE and info.question_kind is QuestionKind.NONE
    assert info.question_line == ""


def test_question_line_names_a_permission_request() -> None:
    waiting = dict(id="t", agent_id="a", text="x", state=TaskState.IDLE)
    assert TaskInfo(**waiting, question="Bash rm y", question_kind="permission").question_line == "Permission: Bash rm y"
    assert TaskInfo(**waiting, question="Which city?", question_kind="need").question_line == "Which city?"


def test_shared_limits_live_in_the_contracts() -> None:
    assert MAX_SNIPS == 3 and PASTED_FILE == "(pasted)"


def test_permissions_names_come_from_config_not_code() -> None:
    assert handler.REVIEWER == "" and handler.YOU == ()  # shared code names no module
    perms = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["core"]["permissions"]
    assert perms["reviewer"] == "main_assistant" and perms["you"] == ["temp_ui"]
