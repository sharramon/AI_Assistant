"""R7 (D6): the access-list review is a listener's job. The core sends `ReviewAccessList` and
waits for `AddCardNotes`; it never starts or cancels a task. The Hub's side: its
`tests/test_review.py`."""

import ast
import asyncio
from pathlib import Path

from assistant.contracts import AccessItem, AccessKind, AddCardNotes, PermissionRequested, Status
from assistant.core import App
from assistant.testkit import wait_until

HANDLER = Path(__file__).parents[1] / "src" / "assistant" / "core" / "permissions" / "handler.py"


def test_the_handler_names_no_task_command():
    names = {n.id for n in ast.walk(ast.parse(HANDLER.read_text(encoding="utf-8"))) if isinstance(n, ast.Name)}
    assert not names & {"StartTask", "TaskUpdated", "TaskState"}


async def test_no_reviewer_module_shows_the_card_at_once_not_reviewed(tmp_path):
    item = AccessItem(kind=AccessKind.WORKSPACE, target=str(tmp_path / "ws"))
    app = App([], {"modules": {"enabled": []}, "core": {"door": {"enabled": False}, "permissions": {
        "grants_file": str(tmp_path / "p.toml"), "reviewer": "main_assistant", "review_timeout": 60.0}}})  # fmt: skip
    cards: list = []

    async def record(event):
        cards.append(event)

    app.bus.subscribe(PermissionRequested, record)
    await app.start()
    try:
        asked = asyncio.create_task(app.permissions.request_set("jobs", "jobs", [item], wait=True))
        await wait_until(lambda: cards, timeout=3)  # no 60 s wait: nobody handles ReviewAccessList
        assert cards[0].reviewed is False
        late = await app.router.send(AddCardNotes(request_id=cards[0].request_id, notes=("x",)))
        assert late.status is Status.INVALID_ARGUMENTS  # no review waits any more
        asked.cancel()
    finally:
        await app.stop()
