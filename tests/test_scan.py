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


def colours(text: str, theme: Theme, state: int = STATE_NONE, following: str = ""):
    """Which style covers which stretch of this line, and what it leaves open.

    ``following`` is the line below, which is how a theme that colours every
    container finds out that this line's name has a brace after it.
    """
    spans, state = scan_line(text, theme, state, following)
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


def test_a_pair_left_open_in_a_value_carries_on_and_closes_later(theme):
    """A bracket left open in a value runs on, the way a license string does."""
    _, state = colours("kuid <kind", theme)
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


# ---------------------------------------------------------------------------
# a family of tags written as one pattern, and written for a language
# ---------------------------------------------------------------------------

FAMILY = """
{
  "name": "family scan",
  "languageSuffixes": true,
  "styles": {
    "default": {"colour": "#000000"},
    "words": {"colour": "#0000ff"},
    "other": {"colour": "#800000"},
    "text": {"colour": "#008000"}
  },
  "pairs": [{"style": "text", "open": "\\"", "close": "\\""}],
  "keywords": [
    {"style": "words", "words": ["description"],
     "patterns": ["category-era-[0-9]+", "car[0-9]+"]},
    {"style": "other", "words": ["car17"], "patterns": ["icon[0-9]+"]}
  ]
}
"""


@pytest.fixture
def families() -> Theme:
    return parse_theme(json.loads(FAMILY))


def test_a_pattern_colours_a_tag_the_theme_never_named(families):
    assert colours("category-era-9 {}", families)[0] == [("category-era-9", "words")]
    assert colours("icon12", families)[0] == [("icon12", "other")]


def test_a_pattern_never_colours_the_middle_of_a_word(families):
    """The scanner hands over whole words and the pattern has to match all of
    one, so nothing here has to say where a word stops."""
    assert colours("mycar1 car1x acategory-era-9", families)[0] == []


def test_a_tag_written_out_by_hand_wins_over_the_pattern_covering_it(families):
    assert colours("car17 car18", families)[0] == [("car17", "other"), ("car18", "words")]


def test_a_language_suffix_colours_a_tag_the_theme_never_named(families):
    assert colours("description-ru description", families)[0] == [
        ("description-ru", "words"),
        ("description", "words"),
    ]


def test_a_tag_from_a_family_and_a_language_at_once(families):
    assert colours("category-era-3-ro", families)[0] == [("category-era-3-ro", "words")]


def test_a_family_tag_inside_a_value_is_part_of_the_value(families):
    assert colours('description-ru "category-era-9"', families)[0] == [
        ("description-ru", "words"),
        ('"category-era-9"', "text"),
    ]


# ---------------------------------------------------------------------------
# the name a line starts with, and the whole sort of name it belongs to
# ---------------------------------------------------------------------------

SORTS = """
{
  "name": "sorts scan",
  "styles": {
    "default": {"colour": "#000000"},
    "tags": {"colour": "#0000ff"},
    "containers": {"colour": "#800000"},
    "odd": {"colour": "#ff0000"},
    "text": {"colour": "#008000"},
    "part": {"colour": "#ff0080"}
  },
  "pairs": [
    {"style": "text", "open": "\\"", "close": "\\""},
    {"style": "part", "open": "<", "close": ">"}
  ],
  "keywords": [
    {"style": "odd", "words": ["origin"]},
    {"style": "tags", "all": "tags"},
    {"style": "containers", "all": "containers"}
  ]
}
"""


@pytest.fixture
def sorts() -> Theme:
    return parse_theme(json.loads(SORTS))


def test_a_name_at_the_start_of_a_line_is_a_tag(sorts):
    assert colours("a-name-nobody-mentioned", sorts)[0] == [("a-name-nobody-mentioned", "tags")]


def test_a_name_inside_a_value_is_not_a_name_of_a_sort(sorts):
    """Only the name the line starts with can be one; what follows is a value."""
    assert colours('kind a-name-nobody-mentioned', sorts)[0] == [("kind", "tags")]


def test_a_name_with_a_brace_after_it_is_a_container(sorts):
    assert colours("kuid-table {", sorts)[0] == [("kuid-table", "containers")]
    assert colours("  mesh-table\t{", sorts)[0] == [("mesh-table", "containers")]
    assert colours("mesh-table{", sorts)[0] == [("mesh-table", "containers")]


def test_a_name_with_a_brace_on_the_line_below_is_a_container(sorts):
    assert colours("mesh-table", sorts, following="{")[0] == [("mesh-table", "containers")]
    assert colours("  default", sorts, STATE_NONE, "  {")[0] == [("default", "containers")]


def test_a_name_with_nothing_after_it_is_only_a_tag(sorts):
    """A name on its own is a tag with no value, unless the line below opens
    something; a value on the line below changes nothing."""
    assert colours("mesh-table", sorts, following="")[0] == [("mesh-table", "tags")]
    assert colours("mesh-table", sorts, following="}")[0] == [("mesh-table", "tags")]
    assert colours("kind", sorts, following='"scenery"')[0] == [("kind", "tags")]


def test_the_name_of_a_sort_never_colours_the_value_after_it(sorts):
    assert colours("origin-table origin", sorts)[0] == [
        ("origin-table", "tags"),
        ("origin", "odd"),
    ]


def test_a_word_the_theme_named_outranks_the_sort_of_name_it_is(sorts):
    assert colours("origin-table", sorts, following="{")[0] == [("origin-table", "containers")]
    assert colours("origin", sorts)[0] == [("origin", "odd")]


def test_a_name_written_with_a_dot_in_it_is_one_name(sorts):
    """Only a space separates a name from its value, so every other symbol -
    the dot here - is part of the name, and the name is coloured all of a piece."""
    assert colours("junction.forward", sorts)[0] == [("junction.forward", "tags")]
    assert colours("  junction.forward 1", sorts)[0] == [("junction.forward", "tags")]


def test_a_name_written_with_a_colon_after_it_is_still_one_name(sorts):
    """The older spelling ``name: value``, which ``chump`` reads the same way;
    the colon is not part of the name, so the name keeps the colour it asks for."""
    assert colours("origin: 1", sorts)[0] == [("origin", "odd")]
    assert colours("junction.forward: 1", sorts)[0] == [("junction.forward", "tags")]


def test_a_name_written_in_brackets_is_a_name_and_not_a_pair(sorts):
    """A kuid table names each asset it holds with a bracketed kuid, and a name
    is a name however it is spelled: the pairs colour a value, never a name."""
    assert colours("<kuid2:66277:35027:1>", sorts)[0] == [("<kuid2:66277:35027:1>", "tags")]
    assert colours("<kuid2:66277:35027:1> {", sorts)[0] == [
        ("<kuid2:66277:35027:1>", "containers")
    ]
    assert colours("<kuid2:66277:35027:1>", sorts, following="{")[0] == [
        ("<kuid2:66277:35027:1>", "containers")
    ]


def test_a_pair_still_colours_a_value_written_after_the_name(sorts):
    assert colours("kuid <kuid2:66277:35027:1>", sorts)[0] == [
        ("kuid", "tags"),
        ("<kuid2:66277:35027:1>", "part"),
    ]
    assert colours('<kuid2:66277:35027:1> "The asset"', sorts)[0] == [
        ("<kuid2:66277:35027:1>", "tags"),
        ('"The asset"', "text"),
    ]


def test_a_name_may_be_written_as_a_number(sorts):
    """Whatever stands before the first space is the name, digits or no digits;
    a value is only ever what follows one."""
    assert colours("42", sorts)[0] == [("42", "tags")]
    assert colours("2.7 1", sorts)[0] == [("2.7", "tags")]


def test_a_container_name_may_hold_spaces(sorts):
    """A container's name runs to the brace it opens, which is the only thing
    that says where it ends: a screenshots container is named after a file, and
    a file name says ``2018-12-15 162811.jpg``."""
    assert colours("2018-12-15 162811.jpg {", sorts)[0] == [
        ("2018-12-15 162811.jpg", "containers")
    ]
    assert colours("  2018-12-15 162811.jpg", sorts, STATE_NONE, "{")[0] == [
        ("2018-12-15 162811.jpg", "containers")
    ]


def test_a_tag_name_may_hold_spaces_up_to_its_value(sorts):
    """A name ends where its value begins, and a value is a quoted string, a
    kuid or a number: the spaces in ``Scenery Objects`` are followed by a word
    that could not be a value, so they belong to the name."""
    assert colours('Scenery Objects   "<kuid2:401543:3220:1>,"', sorts)[0] == [
        ("Scenery Objects", "tags"),
        ('"<kuid2:401543:3220:1>,"', "text"),
    ]
    assert colours("Default Picklist 42", sorts)[0][0] == ("Default Picklist", "tags")


def test_a_name_of_nought_but_words_stops_at_the_first_space(sorts):
    """With nothing after the spaces that could be a value, the name is the first
    word and what follows it is read and coloured as it always was."""
    assert colours("2018-12-15 162811.jpg", sorts)[0] == [("2018-12-15", "tags")]
    assert colours('title "one two"', sorts, STATE_NONE, "{")[0] == [
        ("title", "tags"),
        ('"one two"', "text"),
    ]


def test_a_brace_is_not_a_name_of_a_sort(sorts):
    assert colours("{", sorts)[0] == []
    assert colours("}", sorts)[0] == []
