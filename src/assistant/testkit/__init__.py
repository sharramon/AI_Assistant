"""The public test kit: the fakes and helpers every test may use, central (`tests/`) or a module's
own (`modules/<id>/tests/`). A module's tests import shared helpers from here only, never from
`tests.*`, so a module's folder carries its tests whole.

For tests only: nothing in the app imports it (a tripwire in `tests/test_module_folders.py`). It may
import `assistant.*`; the module builders (`start_hub`, `pre_grant_kinds`) import their modules when
called. The fake scripts (`fake_claude.py`, `fake_job_ui.py`) run as subprocesses, found by path
(`FAKE`, `FAKE_JOB_UI`). Needs no pytest."""

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
from .support import Calculator, Speaker, make_config, pre_grant, pre_grant_kinds, wait_until

__all__ = [
    "FAKE",
    "FAKE_JOB_UI",
    "TIMEOUT",
    "Calculator",
    "FakeAgent",
    "Speaker",
    "StubContext",
    "StubSession",
    "agent_module",
    "make_config",
    "next_matching",
    "pre_grant",
    "pre_grant_kinds",
    "report",
    "start_hub",
    "status",
    "wait_until",
]
