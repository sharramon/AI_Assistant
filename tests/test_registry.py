import pytest

from assistant.contracts import Contract, Manifest, Module, ToolProvider
from assistant.core.registry import StartupError, resolve_modules
from tests.support import Speaker


def module(id: str, **manifest) -> type[Module]:
    async def init(self, ctx):
        pass

    return type(id, (Module,), {"manifest": Manifest(id=id, **manifest), "init": init})


def ids(modules) -> list[str]:
    return [m.manifest.id for m in modules]


def test_providers_start_before_dependents():
    user = module("user", requires=(Speaker,))
    speaker = module("speaker", provides=(Speaker,))
    assert ids(resolve_modules([user, speaker], ["user", "speaker"])) == ["speaker", "user"]


def test_optional_dependency_also_orders():
    user = module("user", optional=(ToolProvider,))
    tools = module("tools", provides=(ToolProvider,))
    assert ids(resolve_modules([user, tools], ["user", "tools"])) == ["tools", "user"]


def test_missing_required_contract():
    user = module("user", requires=(Speaker,))
    with pytest.raises(StartupError, match="requires Speaker"):
        resolve_modules([user], ["user"])


def test_missing_optional_contract_is_fine():
    user = module("user", optional=(Speaker,))
    assert ids(resolve_modules([user], ["user"])) == ["user"]


def test_too_many_providers_of_single_contract():
    a = module("a", provides=(Speaker,))
    b = module("b", provides=(Speaker,))
    with pytest.raises(StartupError, match="allows one provider"):
        resolve_modules([a, b], ["a", "b"])


def test_multiple_providers_allowed_when_contract_says_so():
    a = module("a", provides=(ToolProvider,))
    b = module("b", provides=(ToolProvider,))
    assert ids(resolve_modules([a, b], ["a", "b"])) == ["a", "b"]


def test_circular_dependency():
    class Listener(Contract):
        __module__ = "assistant.contracts.testing"

    a = module("a", provides=(Speaker,), requires=(Listener,))
    b = module("b", provides=(Listener,), requires=(Speaker,))
    with pytest.raises(StartupError, match="Circular"):
        resolve_modules([a, b], ["a", "b"])


def test_unknown_enabled_id():
    with pytest.raises(StartupError, match="not found: ghost"):
        resolve_modules([module("a")], ["ghost"])


def test_duplicate_module_ids():
    with pytest.raises(StartupError, match="Two modules"):
        resolve_modules([module("a"), module("a")], ["a"])


def test_rejects_contract_outside_contracts_package():
    class Private(Contract):
        pass

    a = module("a", provides=(Private,))
    with pytest.raises(StartupError, match="not a contract"):
        resolve_modules([a], ["a"])


def test_only_enabled_modules_are_selected():
    assert ids(resolve_modules([module("a"), module("b")], ["b"])) == ["b"]
