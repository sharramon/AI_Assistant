"""Every tab's Talker speaks as one with its worker (you-means-the-pair note)."""

from __future__ import annotations

import pytest

from assistant.modules.talker.prompt import talker_prompt


@pytest.mark.parametrize("partner", ["main_assistant", "job_search_agent", "some_future_helper"])
def test_every_pair_is_one(partner: str) -> None:
    text = talker_prompt(partner, "main_assistant", "finds jobs", door=True)
    assert "can't do work yourself" not in text
    assert "Answer simple things yourself" not in text
    assert "Everything the user says is aimed at the two of you" in text
    assert "Never say \"I can't, but" in text
    assert "names one side explicitly" in text
    assert "{" not in text.replace("{folder", "")  # every placeholder filled
    # the pair rule sits before the tags, right after the head
    assert text.index("aimed at the two of you") < text.index("<<WORK:")
