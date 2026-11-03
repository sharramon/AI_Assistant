"""The shared reader for the tags in agent replies."""

from assistant.infra.agent_tags import ShowTag, Tag, find_tags, last_line, parse_show


def test_find_tags_with_and_without_arguments():
    text = "On it! <<WORK: write\ntwo poems>> then <<LOOK>> and <<SHOW:  C:\\d\\x.html >>"
    tags = find_tags(text, ("WORK", "LOOK", "SHOW"))
    assert [(t.name, t.argument) for t in tags] == [
        ("WORK", "write\ntwo poems"), ("LOOK", ""), ("SHOW", "C:\\d\\x.html")
    ]
    assert text[tags[1].start:tags[1].end] == "<<LOOK>>"
    assert find_tags(text, ("SHOW",)) == [Tag("SHOW", "C:\\d\\x.html", tags[2].start, tags[2].end)]


def test_find_tags_ignores_malformed_and_unknown():
    assert find_tags("<<SHOW: never closed", ("SHOW",)) == []
    assert find_tags("<<SHOW C:\\x.html>>", ("SHOW",)) == []  # no colon
    assert find_tags("<<show: x>> <<OTHER: y>>", ("SHOW",)) == []  # case-sensitive; not asked for
    assert find_tags("<<SHOWX: y>>", ("SHOW",)) == []
    assert find_tags("<<SHOW: x>>", ()) == []
    assert find_tags("No tags here.", ("SHOW",)) == []


def test_parse_show_path_only():
    assert parse_show(r"C:\a b\page.html") == ShowTag(r"C:\a b\page.html", None, None)
    assert parse_show(" “C:\\p.html” ").path == "C:\\p.html"  # every quote mark around a path goes


def test_parse_show_quote_and_heading():
    assert parse_show('C:/p.html | "the core hosts" | Parts') == ("C:/p.html", "the core hosts", "Parts")
    assert parse_show('C:/p.html | "the core hosts"') == ("C:/p.html", "the core hosts", None)
    assert parse_show("'C:/p.html' | “quoted” |") == ("C:/p.html", "quoted", None)
    assert parse_show("C:/p.html | | Parts") == ("C:/p.html", None, "Parts")
    assert parse_show("C:/p.html | a | b | c") == ("C:/p.html", "a", "b | c")


def test_parse_show_keeps_quote_marks_that_belong_to_the_page():
    # Only one matching pair goes; the page's own quote marks and apostrophes stay.
    assert parse_show("p.html | \"the users' files\"").quote == "the users' files"
    assert parse_show("p.html | 'it's \"core\"'").quote == "it's \"core\""
    assert parse_show('p.html | "say "hi""').quote == 'say "hi"'
    assert parse_show("p.html | the users'").quote == "the users'"
    # An unclosed double quote mark is dropped.
    assert parse_show('p.html | "the core hosts').quote == "the core hosts"
    assert parse_show("p.html | the core hosts”").quote == "the core hosts"


def test_last_line_need_and_handoff():
    assert last_line("Working on it.\n\nNEED: Which folder?\n", "NEED:") == "Which folder?"
    assert last_line("Done part 1.\n`HANDOFF: docs/next-steps/x.md`", "HANDOFF:") == "docs/next-steps/x.md"
    assert last_line("*NEED: pick one*", "NEED:") == "pick one"
    assert last_line("need: lower case works", "NEED:") == "lower case works"
    assert last_line("NEED: earlier\nAll done.", "NEED:") is None  # only the last line counts
    assert last_line("", "NEED:") is None
