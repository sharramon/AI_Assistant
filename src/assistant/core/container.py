"""Dependency injection: maps shared contracts to the modules providing them."""

from __future__ import annotations

from assistant.contracts import Contract


def is_shared_contract(t: object) -> bool:
    """True for Contract subclasses defined in `assistant.contracts`, never a module's own type."""
    return (
        isinstance(t, type)
        and issubclass(t, Contract)
        and t is not Contract
        and t.__module__.startswith("assistant.contracts")
    )


def allows_another(contract: type[Contract], current: object) -> bool:
    """The single-provider rule, in one place: may one more module provide `contract`, given
    what provides it now (`current`: any sized or truthy collection of providers or their ids)?"""
    return contract.multiple or not current


class Container:
    def __init__(self) -> None:
        self._providers: dict[type[Contract], list[tuple[str, Contract]]] = {}

    def provide(self, contract: type[Contract], impl: Contract, owner: str) -> None:
        if not is_shared_contract(contract):
            raise TypeError(f"{contract!r} is not a contract from assistant.contracts")
        if not isinstance(impl, contract):
            raise TypeError(f"{type(impl).__name__} does not implement {contract.__name__}")
        existing = self._providers.setdefault(contract, [])
        if not allows_another(contract, existing):
            raise ValueError(f"{contract.__name__} allows one provider and {existing[0][0]!r} already provides it")
        existing.append((owner, impl))

    def remove(self, contract: type[Contract], impl: Contract, owner: str) -> None:
        """Take back one provider `owner` gave; nothing if it isn't there."""
        remaining = [e for e in self._providers.get(contract, []) if not (e[0] == owner and e[1] is impl)]
        if remaining:
            self._providers[contract] = remaining
        else:
            self._providers.pop(contract, None)

    def remove_owner(self, owner: str) -> None:
        for contract in list(self._providers):
            remaining = [entry for entry in self._providers[contract] if entry[0] != owner]
            if remaining:
                self._providers[contract] = remaining
            else:
                del self._providers[contract]

    def get_all(self, contract: type[Contract]) -> list:
        return [impl for _, impl in self._providers.get(contract, [])]

    def get_one(self, contract: type[Contract]):
        providers = self._providers.get(contract)
        return providers[0][1] if providers else None
