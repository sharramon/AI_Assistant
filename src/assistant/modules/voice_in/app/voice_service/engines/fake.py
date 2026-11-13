"""FakeEngine: reveals a set text word by word, for tests. No model, no audio processing."""

from __future__ import annotations

import threading

from . import EngineError, SttEngine, SttStream


class FakeEngine(SttEngine):
    """One more word every `chunks_per_word` chunks; `finish` rounds up to the next word.

    `fail_on_load` makes `load` raise; `fail_on_accept` makes the next stream's first `accept`
    raise (once, so the following session works); `load_gate` holds `load` until it's set.
    """

    name = "fake"

    def __init__(
        self,
        text: str = "hello from the fake engine",
        *,
        chunks_per_word: int = 2,
        fail_on_load: bool = False,
        fail_on_accept: bool = False,
        load_gate: threading.Event | None = None,
    ) -> None:
        self.words = text.split()
        self.chunks_per_word = chunks_per_word
        self.fail_on_load = fail_on_load
        self.fail_on_accept = fail_on_accept
        self.load_gate = load_gate

    def load(self) -> None:
        if self.load_gate is not None:
            self.load_gate.wait(10)
        if self.fail_on_load:
            raise EngineError("fake engine: load failed")

    def new_stream(self) -> SttStream:
        fail, self.fail_on_accept = self.fail_on_accept, False
        return _FakeStream(self.words, self.chunks_per_word, fail)


class _FakeStream(SttStream):
    def __init__(self, words: list[str], chunks_per_word: int, fail: bool) -> None:
        self._words = words
        self._per_word = chunks_per_word
        self._fail = fail
        self._chunks = 0

    def accept(self, pcm: bytes) -> None:
        if self._fail:
            raise RuntimeError("fake engine: accept failed")
        self._chunks += 1

    def partial(self) -> str:
        return " ".join(self._words[: self._chunks // self._per_word])

    def finish(self) -> str:
        return " ".join(self._words[: -(-self._chunks // self._per_word)])
