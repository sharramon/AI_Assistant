"""voice_in's live line with two passes (`LiveLine`, `render`) and `clean_text(capitalize=...)`."""

from __future__ import annotations

from assistant.modules.voice_in.cleanup import clean_text
from assistant.modules.voice_in.line import LiveLine, Segment, render


def line_of(live: str, *spans) -> LiveLine:
    line = LiveLine()
    line.set_live(live)
    for span in spans:
        line.settle(*span)
    return line


def test_a_span_replaces_its_words_and_the_rough_tail_follows():
    line = line_of("HELLO THERE HOW ARE YOU TODAY", (0, 2, "Hello there."))
    assert render(line.segments(), cleanup=False) == ("Hello there. HOW ARE YOU TODAY", len("Hello there."))
    assert render(line.segments()) == ("Hello there. How are you today", len("Hello there."))


def test_a_fallback_span_keeps_its_words_and_carries_on_the_sentence():
    line = line_of("I THINK THAT WE SHOULD GO", (0, 2, "I think"), (2, 4, "", "failed"))
    assert render(line.segments()) == ("I think that we should go", len("I think that we"))


def test_an_empty_span_inserts_text_and_an_empty_cleaned_span_adds_nothing():
    line = line_of("ONE TWO", (0, 0, "Um, hi."), (0, 0, ""))
    assert render(line.segments()) == ("Um, hi. One two", len("Um, hi."))


def test_a_late_live_word_shows_again_in_the_rough_tail():
    line = line_of("A B", (0, 2, "A b c."))
    line.set_live("A B C D")  # the live engine gave "C" just after the cut
    assert render(line.segments()) == ("A b c. C d", len("A b c."))


def test_the_final_parts_get_one_end_mark_on_the_last():
    text, _ = render([Segment("Hello there."), Segment("HOW ARE YOU")], final=True)
    assert text == "Hello there. How are you?"
    assert render([Segment("Done."), Segment("")], final=True)[0] == "Done."


def test_one_engine_renders_as_clean_text_did():
    for raw in ("HELLO WORLD", "WHAT IS IT", "", "Already cased"):
        assert render(line_of(raw).segments()) == (clean_text(raw), 0)
        assert render([Segment(raw)], final=True)[0] == clean_text(raw, final=True)


def test_clean_text_without_capitalize_keeps_a_small_first_letter():
    assert clean_text("WE GO", capitalize=False) == "we go"
    assert clean_text("I THINK SO", capitalize=False) == "I think so"
