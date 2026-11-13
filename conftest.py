"""Test-wide setup for every test, in tests/ and in each module's own tests/ folder: no test may
write the repo's saved permission grants or wait on a real card, and no test touches the repo's
logs or the Talker's restart note.

Every App builds the core's permissions handler. Here its grants file is in tmp, a card counts as
Deny after 2 s instead of 10 minutes, and no review task is started unless a test's config names
a reviewer. Tests that need a module on pre-grant its list (`assistant.testkit.pre_grant`) or answer the card.

The core modules' defaults are in their `module.toml` files, which every App merges under a test's
config. Two of them name files in the repo: the agents' transcripts (under the default `logs` dir)
and the Talker's `restart_note` (deleted at a plain stop). Here an App without a log session and
without a `[logging] dir` writes under tmp, and a module default `restart_note` points into tmp; a
test's own value for either still wins.

Each module's `app/` folder (its companion app's package, like `cv/app/cv_tool`) goes on the import
path here, the way the core does at startup (`loader.add_app_folders`).
"""

import pytest

from assistant.core import app as core_app
from assistant.core import loader
from assistant.core.loader import add_app_folders
from assistant.core.logs import SessionLogs
from assistant.core.permissions import handler

add_app_folders()


@pytest.fixture(autouse=True)
def _permissions_for_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(handler, "GRANTS_FILE", tmp_path / "permissions.toml")
    monkeypatch.setattr(handler, "OLD_GRANTS_FILE", tmp_path / "old-data" / "permissions.toml")  # never the repo's
    monkeypatch.setattr(handler, "ANSWER_TIMEOUT", 2.0)
    monkeypatch.setattr(handler, "REVIEW_TIMEOUT", 2.0)
    monkeypatch.setattr(handler, "REVIEWER", "")


@pytest.fixture(autouse=True)
def _repo_files_untouched(tmp_path, monkeypatch):
    class TmpLogs(SessionLogs):
        def __init__(self, session=None, root="logs"):
            super().__init__(session, tmp_path / "logs" if str(root) == "logs" else root)

    monkeypatch.setattr(core_app, "SessionLogs", TmpLogs)
    real_defaults = loader.module_defaults

    def module_defaults(cls):
        found = real_defaults(cls)
        if "restart_note" in found:
            found = {**found, "restart_note": str(tmp_path / "restart-note.md")}
        return found

    monkeypatch.setattr(loader, "module_defaults", module_defaults)
