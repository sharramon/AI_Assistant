"""The voice text cleanup's rules (voice_in/cleanup.py)."""

import pytest

from assistant.modules.voice_in.cleanup import clean_text

TERMS = ["Isaac Sim", "USD", "glTF", "Unity", "Unitree", "Zipformer"]


@pytest.mark.parametrize(
    ("raw", "final", "expected"),
    [
        ("HELLO BIG WORLD", True, "Hello big world."),
        ("HELLO BIG WORLD", False, "Hello big world"),  # the live line gets no end mark
        ("YES", True, "Yes."),
        ("WHAT IS USD IN ISAAC SIM", True, "What is USD in Isaac Sim?"),
        ("CAN YOU OPEN THE FILE", True, "Can you open the file?"),
        ("I THINK I'M DONE AND I'LL GO I'VE SAID I'D", True, "I think I'm done and I'll go I've said I'd."),
        ("IMPORT THE UNITREE G ONE INTO UNITY", True, "Import the Unitree g one into Unity."),
        ("GLTF EXPORT", True, "glTF export."),  # a term at the start keeps its own case
        ("ISAAC   SIM", False, "Isaac Sim"),  # extra spaces are collapsed
        ("THE USDA FILE AND A UNITY'S SCENE", True, "The usda file and a Unity's scene."),  # whole words only
        ("IT IS DONE.", True, "It is done."),  # an end mark already there isn't doubled
        ("WHAT", False, "What"),
        ("", True, ""),
        ("   ", True, ""),
        ("HI THERE I", True, "Hi there I."),
        ("IN IT", True, "In it."),  # "i" inside a word stays
    ],
)
def test_clean_text(raw, final, expected):
    assert clean_text(raw, TERMS, final=final) == expected


def test_without_terms_everything_is_lowercased():
    assert clean_text("ISAAC SIM USD", final=True) == "Isaac sim usd."


def test_cased_text_keeps_its_case_and_punctuation():
    # Whisper writes its own case and punctuation: only the spaces and the terms change, no end mark is added.
    raw = "We imported  it into unity, then isaac sim"
    assert clean_text(raw, TERMS, final=True) == "We imported it into Unity, then Isaac Sim"
    assert clean_text("What is USD?", TERMS, final=True) == "What is USD?"


def test_the_longest_term_wins():
    assert clean_text("USD PRIM", ["USD", "usd prim"], final=False) == "usd prim"
