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


class Container:
    def __init__(self) -> None:
        self._providers: dict[type[Contract], list[tuple[str, Contract]]] = {}

    def provide(self, contract: type[Contract], impl: Contract, owner: str) -> None:
        if not is_shared_contract(contract):
            raise TypeError(f"{contract!r} is not a contract from assistant.contracts")
        if not isinstance(impl, contract):
            raise TypeError(f"{type(impl).__name__} does not implement {contract.__name__}")
        existing = self._providers.setdefault(contract, [])
        if existing and not contract.multiple:
            raise ValueError(f"{contract.__name__} allows one provider and {existing[0][0]!r} already provides it")
        existing.append((owner, impl))

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
