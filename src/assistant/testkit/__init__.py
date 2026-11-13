"""The public test kit: the fakes and helpers every test may use, central (`tests/`) or a module's
own (`modules/<id>/tests/`). A module's tests import shared helpers from here only, never from
`tests.*`, so a module's folder carries its tests whole.

For tests only: nothing in the app imports it (a tripwire in `tests/test_module_folders.py`). It may
import `assistant.*`; the module builders (`start_hub`, `pre_grant_kinds`) import their modules when
called. The fake scripts (`fake_claude.py`, `fake_job_ui.py`) run as subprocesses, found by path
(`FAKE`, `FAKE_JOB_UI`). `pages` talks to a module's local page, stands in for voice_in, and makes the snip events. Needs no pytest."""

from .agents import (
    FAKE,
    FAKE_JOB_UI,
    TIMEOUT,
    FakeAgent,
    StubContext,
    StubSession,
    agent_module,
    next_matching,
    report,
    start_hub,
    status,
)
from .pages import FakeVoiceIn, clip_event, dropped_event, next_item, post, read_events, request, ui_port
from .support import (
    Calculator,
    Speaker,
    free_port,
    make_config,
    module_config,
    pre_grant,
    pre_grant_kinds,
    sample_card,
    stand_in,
    wait_until,
)

__all__ = [
    "FAKE",
    "FAKE_JOB_UI",
    "TIMEOUT",
    "Calculator",
    "FakeAgent",
    "FakeVoiceIn",
    "Speaker",
    "StubContext",
    "StubSession",
    "agent_module",
    "clip_event",
    "dropped_event",
    "free_port",
    "make_config",
    "module_config",
    "next_item",
    "next_matching",
    "post",
    "pre_grant",
    "pre_grant_kinds",
    "read_events",
    "report",
    "request",
    "sample_card",
    "stand_in",
    "start_hub",
    "status",
    "ui_port",
    "wait_until",
]
