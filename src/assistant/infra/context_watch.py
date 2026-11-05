"""Notice once when a session's context passes a size: the Talker's warning and the worker's reminder."""

from __future__ import annotations


class ContextWatch:
    """Says when a context first passes `limit` tokens, once per crossing.

    `crossed(key, tokens)` is True the first time `key`'s context is at or past the
    limit; it stays False while it stays over, and re-arms once that context comes
    back under (a reset or a fresh session). A `limit` of 0 or less turns it off.
    """

    def __init__(self, limit: int):
        self.limit = limit
        self._over: set[str] = set()

    def crossed(self, key: str, tokens: int) -> bool:
        if self.limit <= 0:
            return False
        if tokens < self.limit:
            self._over.discard(key)
            return False
        if key in self._over:
            return False
        self._over.add(key)
        return True
