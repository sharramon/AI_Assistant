import pytest

from assistant.contracts import Contract
from assistant.core.container import Container
from tests.support import Calculator, Speaker


class Impl(Speaker):
    pass


def test_rejects_contract_outside_contracts_package():
    class Private(Contract):
        pass

    class PrivateImpl(Private):
        pass

    with pytest.raises(TypeError):
        Container().provide(Private, PrivateImpl(), owner="a")


def test_rejects_impl_that_does_not_implement_contract():
    with pytest.raises(TypeError):
        Container().provide(Speaker, object(), owner="a")


def test_single_provider_contract_rejects_second_provider():
    container = Container()
    container.provide(Speaker, Impl(), owner="a")
    with pytest.raises(ValueError, match="one provider"):
        container.provide(Speaker, Impl(), owner="b")


def test_get_and_remove_owner():
    from assistant.contracts import IToolProvider

    container = Container()
    calc, speaker = Calculator(), Impl()
    container.provide(IToolProvider, calc, owner="calc")
    container.provide(Speaker, speaker, owner="calc")
    assert container.get_all(IToolProvider) == [calc]
    assert container.get_one(Speaker) is speaker
    container.remove_owner("calc")
    assert container.get_all(IToolProvider) == []
    assert container.get_one(Speaker) is None
