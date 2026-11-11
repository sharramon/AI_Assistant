"""Chunk 12: the core's one single-provider rule and the permission card actions."""

from __future__ import annotations

from assistant.contracts import IModuleDoor, IToolProvider, PermissionRequested
from assistant.core.container import allows_another
from assistant.core.permissions.handler import CardAction


def test_one_provider_contract_allows_only_the_first() -> None:
    assert allows_another(IModuleDoor, [])
    assert allows_another(IModuleDoor, None)
    assert not allows_another(IModuleDoor, ["agent_hub"])
    assert not allows_another(IModuleDoor, "agent_hub")


def test_multiple_provider_contract_always_allows_another() -> None:
    assert IToolProvider.multiple
    assert allows_another(IToolProvider, ["html_viewer", "echo"])


def test_card_actions_are_the_cards_action_values() -> None:
    assert [a.value for a in CardAction] == ["access", "grant", "revoke", "message"]
    for action in CardAction:
        assert PermissionRequested(request_id="r", module_id="m", action=action.value).action == action
