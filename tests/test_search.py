"""Tests for finding a piece of text and putting something else in its place.

Nothing here needs a window: the places are worked out by ``search.py``, which is
free of Qt like ``document.py``.  The GUI tests in ``test_gui.py`` cover the
panel that asks those questions about the text on screen.
"""

from __future__ import annotations

from chumpeditor.search import (
    Match,
    find_all,
    line_of,
    matches,
    next_match,
    replacements,
)
from chumpeditor.tweaks import Rewrite

TEXT = 'kind "interior"\nname "KUID inside"\nkuid <kuid:1:2>\n'


# ---------------------------------------------------------------------------
# where a piece of text stands
# ---------------------------------------------------------------------------
def test_every_place_is_named_once_and_in_the_order_they_come():
    assert find_all("ababab", "ab") == [Match(0, 2), Match(2, 4), Match(4, 6)]


def test_the_stretch_named_is_the_text_itself():
    text = 'kind "interior"\nkind "interior"'
    places = find_all(text, "kind")
    assert [one.start for one in places] == [0, 16]
    assert all(text[one.start:one.end] == "kind" for one in places)


def test_a_match_begun_is_finished_before_the_next_one_is_asked_for():
    """Three of a letter written over each other hold one match, not two, so the
    places never overlap and one stretch is never replaced twice."""
    assert find_all("aaa", "aa") == [Match(0, 2)]


def test_text_that_is_sought_nowhere_is_not_found():
    assert find_all(TEXT, "mesh-table") == []


def test_a_search_for_nothing_at_all_asks_for_nothing():
    """An empty box means nobody has said what to look for; taken literally it
    would find a match between every two characters of the file."""
    assert find_all(TEXT, "") == []
    assert matches("kuid", "") is False


def test_a_letter_is_not_another_one_unless_it_is_told_to_be():
    text = "KUID kuid kuid"
    assert [one.start for one in find_all(text, "kuid")] == [5, 10]
    assert [one.start for one in find_all(text, "kuid", match_case=False)] == [0, 5, 10]


def test_the_letters_are_matched_whole_once_the_box_is_ticked():
    assert matches("KUID", "kuid") is False
    assert matches("KUID", "kuid", match_case=False) is True
    assert matches("kuid", "kuid") is True


def test_a_stretch_is_only_a_match_when_it_is_all_of_the_text_sought():
    """Asked of a selection: a longer stretch holding the sought text is not the
    sought text, and neither is a shorter one."""
    assert matches("kuid <kuid:1:2>", "kuid") is False
    assert matches("kui", "kuid") is False


def test_text_that_means_itself_is_sought_as_text():
    """The box asks for a string, so brackets, dots and backslashes are looked
    for as the characters they are rather than as instructions about searching."""
    text = "kuid <kuid:1:2> a.b [x] \\d"
    for sought in ("<kuid:1:2>", "a.b", "[x]", "\\d"):
        found = find_all(text, sought)
        assert len(found) == 1
        assert text[found[0].start:found[0].end] == sought
    assert find_all("abc", "a.c") == []


# ---------------------------------------------------------------------------
# the next place, which goes on past the end of the file
# ---------------------------------------------------------------------------
def test_the_next_place_is_the_first_one_at_or_after_wherever_the_caret_stands():
    text = "one two one two one"
    assert next_match(text, "one", 0) == Match(0, 3)
    assert next_match(text, "one", 1) == Match(8, 11)
    assert next_match(text, "two", 10) == Match(12, 15)


def test_asking_past_a_match_does_not_find_that_match_again():
    """The panel asks from just after the selection it is sitting on, which is
    what makes pressing the same key over and over walk down the file."""
    assert next_match("ab ab ab", "ab", 3) == Match(3, 5)


def test_a_search_that_finds_nothing_past_the_caret_starts_at_the_top_again():
    text = "one two one"
    assert next_match(text, "one", 10) == Match(0, 3)
    assert next_match(text, "two", 9) == Match(4, 7)


def test_a_search_with_nowhere_to_find_it_says_so():
    assert next_match(TEXT, "mesh-table", 0) is None
    assert next_match("", "kind", 0) is None
    assert next_match(TEXT, "", 0) is None


def test_a_place_before_the_caret_means_the_file_was_gone_round():
    """Nothing was found past the caret, so the answer came from the top again;
    the panel tells that story from where the answer stands."""
    found = next_match("kind kind", "kind", 6)
    assert found == Match(0, 4)
    assert found.start < 6


# ---------------------------------------------------------------------------
# putting something in their places
# ---------------------------------------------------------------------------
def test_every_place_becomes_a_stretch_to_cut_out_with_its_replacement():
    assert replacements("kuid kuid", "kuid", "id") == [
        Rewrite(0, 4, "id"), Rewrite(5, 9, "id")
    ]


def test_an_empty_replacement_takes_the_text_out_and_leaves_nothing():
    assert replacements("a.b.c", ".", "") == [Rewrite(1, 2, ""), Rewrite(3, 4, "")]


def test_the_replacements_are_put_in_in_the_same_order_as_the_places():
    """They are cut out from the far end backwards, which is what keeps every
    earlier stretch where it was worked out to be."""
    every = replacements("one two one", "one", "1")
    assert [one.start for one in every] == sorted(one.start for one in every)
    assert all("one" == "one two one"[one.start:one.end] for one in every)


def test_a_replacement_holding_the_very_text_it_replaces_counts_each_place_once():
    """``kuid`` into ``kuid_table``: the text that was just written is not sought
    again, so the change is neither doubled nor run round for ever."""
    text = "kuid kuid"
    every = replacements(text, "kuid", "kuid_table")
    assert len(every) == 2
    assert all(text[one.start:one.end] == "kuid" for one in every)


def test_replacing_the_lot_follows_the_case_as_well():
    text = "KUID kuid kuid"
    assert len(replacements(text, "kuid", "id")) == 2
    assert len(replacements(text, "kuid", "id", match_case=False)) == 3


def test_nothing_is_cut_out_when_the_text_is_nowhere_in_the_file():
    assert replacements(TEXT, "mesh-table", "mesh") == []
    assert replacements(TEXT, "", "mesh") == []


# ---------------------------------------------------------------------------
# which line a place is on, for what the status bar says
# ---------------------------------------------------------------------------
def test_a_place_is_counted_from_the_top_of_the_file_in_ones():
    assert line_of(TEXT, 0) == 1
    assert line_of(TEXT, 16) == 2
    assert line_of(TEXT, 35) == 3


def test_the_end_of_a_line_belongs_to_the_line_it_ends():
    """A match standing on the break is still on the line it follows, which is
    what a message about where it was found has to say."""
    assert line_of(TEXT, 15) == 1
    assert line_of("a\nb\n", 4) == 3


def test_a_file_of_one_line_puts_everything_on_line_one():
    assert line_of("kind", 3) == 1
