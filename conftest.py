"""Test-wide setup for every test, in tests/ and in each module's own tests/ folder: no test may
write the repo's saved permission grants or wait on a real card.

Every App builds the core's permissions handler. Here its grants file is in tmp, a card counts as
Deny after 2 s instead of 10 minutes, and no review task is started unless a test's config names
a reviewer. Tests that need a module on pre-grant its list (`support.pre_grant`) or answer the card.
"""

import pytest

from assistant.core.permissions import handler


@pytest.fixture(autouse=True)
def _permissions_for_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(handler, "GRANTS_FILE", tmp_path / "permissions.toml")
    monkeypatch.setattr(handler, "ANSWER_TIMEOUT", 2.0)
    monkeypatch.setattr(handler, "REVIEW_TIMEOUT", 2.0)
    monkeypatch.setattr(handler, "REVIEWER", "")
