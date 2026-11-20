"""Tests for which part of a line a theme colours.

The theme here is a small made-up one, because what matters is the order the
rules are tried in and what happens at a line break, not the words of Trainz.
"""

from __future__ import annotations

import json

import pytest

from chumpeditor.scan import STATE_NONE, scan_line
from chumpeditor.theme import Theme, parse_theme

TEXT = """
{
  "name": "scan test",
  "styles": {
    "default": {"colour": "#000000"},
    "words": {"colour": "#0000ff"},
    "other": {"colour": "#800000"},
    "text": {"colour": "#008000"},
    "part": {"colour": "#ff0080"},
    "digits": {"colour": "#808080"}
  },
  "pairs": [
    {"style": "text", "open": "\\"", "close": "\\""},
    {"style": "part", "open": "<", "close": ">"}
  ],
  "keywords": [
    {"style": "words", "words": ["kind", "trainz-build", "length", "license", "name"]},
    {"style": "other", "words": ["kuid-table"]}
  ],
  "numbers": "digits"
}
"""


@pytest.fixture
def theme() -> Theme:
    return parse_theme(json.loads(TEXT))


def colours(text: str, theme: Theme, state: int = STATE_NONE):
    """Which style covers which stretch of this line, and what it leaves open."""
    spans, state = scan_line(text, theme, state)
    return [(text[span.start : span.start + span.length], span.style) for span in spans], state


def test_a_word_that_is_a_keyword_gets_its_style(theme):
    assert colours("kind", theme)[0] == [("kind", "words")]


def test_a_word_that_is_not_a_keyword_gets_nothing(theme):
    assert colours("nonsense", theme)[0] == []


def test_a_word_with_a_dash_in_it_is_one_word(theme):
    assert colours("  trainz-build 2.7", theme)[0] == [
        ("trainz-build", "words"),
        ("2.7", "digits"),
    ]


def test_each_list_of_words_has_its_own_style(theme):
    assert colours("kuid-table", theme)[0] == [("kuid-table", "other")]


def test_a_pair_colours_the_whole_of_itself(theme):
    assert colours('kind "cart"', theme)[0] == [("kind", "words"), ('"cart"', "text")]


def test_a_word_inside_a_pair_takes_the_colour_of_the_pair(theme):
    """A keyword in a value is part of the value, which is why pairs come first."""
    assert colours('name "kind"', theme)[0] == [("name", "words"), ('"kind"', "text")]


def test_what_follows_a_pair_is_coloured_again(theme):
    assert colours('kind "cart" kind', theme)[0] == [
        ("kind", "words"),
        ('"cart"', "text"),
        ("kind", "words"),
    ]


def test_a_pair_inside_a_pair_is_only_text(theme):
    assert colours('name "<kind>"', theme)[0] == [("name", "words"), ('"<kind>"', "text")]


def test_a_number_inside_a_pair_is_part_of_the_pair(theme):
    assert colours('length "12.5"', theme)[0] == [
        ("length", "words"),
        ('"12.5"', "text"),
    ]


def test_a_closing_string_on_its_own_is_not_the_start_of_anything(theme):
    assert colours("cart >", theme)[0] == []


def test_a_number_is_a_number_only_when_the_theme_says_so():
    plain = parse_theme({"styles": {"default": "#000000"}})
    assert colours("2.7", plain)[0] == []


def test_a_pair_left_open_at_the_end_of_a_line_carries_on(theme):
    """A Trainz license string runs over several lines, and stays one string."""
    found, state = colours('license "one', theme)
    assert found == [("license", "words"), ('"one', "text")]
    assert state == 0

    found, state = colours("two", theme, state)
    assert found == [("two", "text")]
    assert state == 0

    found, state = colours('three" kind', theme, state)
    assert found == [('three"', "text"), ("kind", "words")]
    assert state == STATE_NONE


def test_a_line_inside_a_pair_left_open_still_closes_it(theme):
    _, state = colours("<kind", theme)
    assert state == 1

    found, state = colours("cart>", theme, state)
    assert found == [("cart>", "part")]
    assert state == STATE_NONE


def test_a_pair_with_no_closing_string_covers_the_rest_of_the_line_only():
    """How a comment to the end of a line would be written: no closing string."""
    theme = parse_theme(
        {
            "styles": {"default": "#000000", "words": "#0000ff", "note": "#008000"},
            "pairs": [{"style": "note", "open": "#", "close": ""}],
            "keywords": [{"style": "words", "words": ["kind"]}],
        }
    )
    found, state = colours("kind # not a kind", theme)
    assert found == [("kind", "words"), ("# not a kind", "note")]
    assert state == STATE_NONE
    assert colours("kind", theme, state)[0] == [("kind", "words")]
