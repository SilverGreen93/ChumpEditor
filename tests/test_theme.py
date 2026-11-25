"""Tests for the theme file: what it may say, and what it means when it cannot.

Nothing here needs a window; the colours are decided here and only painted in
``gui.highlighter``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chumpeditor import theme as module
from chumpeditor.theme import (
    CONTAINERS,
    DEFAULT_THEME,
    TAGS,
    Keywords,
    Pair,
    Style,
    Theme,
    ThemeError,
    bundled_theme_path,
    default_theme,
    load_theme,
    parse_theme,
    save_theme,
    theme_paths,
)

SIMPLE = """
{
  "name": "simple",
  "styles": {
    "default": {"colour": "#101010"},
    "words": "#0000ff",
    "text": {"colour": "#008000", "italic": true}
  },
  "pairs": [{"style": "text", "open": "\\"", "close": "\\""}],
  "keywords": [{"style": "words", "words": ["kind", "kuid"]}]
}
"""


def written(tmp_path: Path, text: str, name: str = "t.json") -> Path:
    """A theme file with these contents, in a folder of its own."""
    target = tmp_path / name
    target.write_text(text, encoding="utf-8")
    return target


#: what a dark theme paints behind the text, and the two functions that say
#: whether a colour can actually be seen on it - the same contrast ratio WCAG
#: uses, so the number can be looked up rather than trusted
DARK_BACKGROUND = "#2d2d2d"


def luminance(colour: str) -> float:
    """How much light a colour gives off: 0 for black, 1 for white."""

    def part(offset: int) -> float:
        value = int(colour[offset:offset + 2], 16) / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * part(1) + 0.7152 * part(3) + 0.0722 * part(5)


def contrast(one: str, other: str) -> float:
    """How far apart two colours are to an eye: 1 for the same, 21 for black on
    white."""
    light, dark = sorted((luminance(one), luminance(other)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


# ---------------------------------------------------------------------------
# the theme that comes with the program
# ---------------------------------------------------------------------------


def test_the_theme_that_comes_with_the_program_reads():
    theme = load_theme(bundled_theme_path())
    assert theme.name == "Trainz Config"
    assert {style for style in theme.styles} == {
        "default",
        "tags",
        "containers",
        "obsolete",
        "delim_str",
        "delim_kuid",
    }


def test_the_theme_that_comes_with_the_program_colours_words_and_strings():
    theme = default_theme()
    assert theme.style("tags").colour == "#0000ff"
    assert theme.roles == {"tags": "tags", "containers": "containers"}
    assert [pair.open for pair in theme.pairs] == ['"', "<"]
    assert theme.style("obsolete").italic


def test_the_theme_that_comes_with_the_program_colours_names_by_what_they_are():
    """Nothing is matched by an exact word except the tags nobody uses any more:
    a name is coloured by being a tag or a container, however it is spelled."""
    theme = default_theme()
    assert theme.keyword_style("kind", TAGS) == "tags"
    assert theme.keyword_style("a-tag-nobody-has-ever-mentioned", TAGS) == "tags"
    assert theme.keyword_style("kuid-table", CONTAINERS) == "containers"
    assert theme.keyword_style("a-container-nobody-has-ever-mentioned", CONTAINERS) == "containers"


def test_the_theme_that_comes_with_the_program_marks_the_tags_that_are_obsolete():
    """The one list that still says what a word is, because only a word can say
    that a tag is no longer used - and it wins over the colour of every tag."""
    theme = default_theme()
    assert theme.keyword_style("origin", TAGS) == "obsolete"
    assert theme.keyword_style("thumbnail", TAGS) == "obsolete"
    assert theme.keyword_style("night", CONTAINERS) == "obsolete"


def test_the_shipped_theme_writes_a_family_of_tags_as_one_pattern():
    """A Trainz asset numbers these as far as it likes - era 7, icon 31 - and
    the theme has to follow without anyone adding a line."""
    theme = default_theme()
    assert theme.keyword_style("category-era-42") == "obsolete"
    assert theme.keyword_style("category-region-11") == "obsolete"
    assert theme.keyword_style("icon9") == "obsolete"
    assert theme.keyword_style("icon42", TAGS) == "obsolete"


def test_the_shipped_theme_never_lists_a_tag_by_its_number():
    """The families are one pattern each; the only numbered words left are the
    cars coloured differently from the rest of their family on purpose."""
    theme = default_theme()
    listed = sorted(word for word in theme.words if any(digit in word for digit in "0123456789"))
    assert listed == ["car15", "car16", "car17", "car18", "car19", "car20"]
    assert theme.keyword_style("car17") == "obsolete"
    assert theme.keyword_style("car25", TAGS) == "tags"


def test_the_shipped_theme_colours_a_tag_written_for_a_language():
    theme = default_theme()
    assert theme.language_suffixes
    assert theme.keyword_style("icon-texture-ru", TAGS) == "obsolete"
    assert theme.keyword_style("description-ru", TAGS) == "tags"


def test_the_bundled_theme_is_where_the_package_keeps_it():
    assert bundled_theme_path().is_file()
    assert bundled_theme_path().name == DEFAULT_THEME


# ---------------------------------------------------------------------------
# reading and writing
# ---------------------------------------------------------------------------


def test_a_theme_written_by_hand_reads_back_as_one_object(tmp_path):
    theme = load_theme(written(tmp_path, SIMPLE))
    assert theme.name == "simple"
    assert theme.styles["words"] == Style(name="words", colour="#0000ff")
    assert theme.styles["text"].italic
    assert theme.pairs == (Pair(style="text", open='"', close='"'),)
    assert theme.keywords == (Keywords(style="words", words=("kind", "kuid")),)
    assert theme.words == {"kind": "words", "kuid": "words"}


def test_a_theme_written_out_is_read_back_the_same(tmp_path):
    theme = load_theme(written(tmp_path, SIMPLE))
    target = tmp_path / "again" / "t.json"
    assert save_theme(theme, target).is_file()
    assert load_theme(target) == theme


def test_a_colour_may_be_written_short_or_long_or_without_the_hash(tmp_path):
    theme = parse_theme(
        {"styles": {"default": "f80", "words": "#FF8800"}, "keywords": []}
    )
    assert theme.styles["default"].colour == theme.styles["words"].colour == "#ff8800"


def test_a_theme_may_be_the_contents_rather_than_a_file():
    assert parse_theme(json.loads(SIMPLE)).styles["default"].colour == "#101010"


def test_a_missing_theme_file_says_which_file(tmp_path):
    with pytest.raises(ThemeError) as caught:
        load_theme(tmp_path / "nope.json")
    assert "nope.json" in str(caught.value)


def test_untidy_json_says_where_it_stops_making_sense(tmp_path):
    with pytest.raises(ThemeError) as caught:
        load_theme(written(tmp_path, '{"styles": {},,,}'))
    assert "line 1" in str(caught.value)


# ---------------------------------------------------------------------------
# where a theme is looked for
# ---------------------------------------------------------------------------


def test_a_theme_is_looked_for_in_your_folder_before_the_programs(tmp_path, monkeypatch):
    """A theme of your own wins, which is how the colours get changed."""
    mine = tmp_path / "themes" / DEFAULT_THEME
    mine.parent.mkdir(parents=True)
    mine.write_text(SIMPLE, encoding="utf-8")
    monkeypatch.setattr(module, "config_dir", lambda: tmp_path)
    assert load_theme().name == "simple"


def test_a_theme_of_your_own_need_not_be_the_one_in_the_program(tmp_path, monkeypatch):
    mine = tmp_path / "themes" / "simple.json"
    mine.parent.mkdir(parents=True)
    mine.write_text(SIMPLE, encoding="utf-8")
    monkeypatch.setattr(module, "config_dir", lambda: tmp_path)
    assert load_theme("simple").name == "simple"


def test_looking_a_theme_up_names_both_places(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "config_dir", lambda: tmp_path)
    yours, theirs = theme_paths()
    assert yours == tmp_path / "themes" / DEFAULT_THEME
    assert theirs == bundled_theme_path()
    assert theirs.is_file()


def test_a_path_is_a_path_and_not_a_name_to_look_up(tmp_path):
    """A theme given as a file is read from that file, wherever it is."""
    assert load_theme(written(tmp_path, SIMPLE)).name == "simple"


# ---------------------------------------------------------------------------
# what will not do
# ---------------------------------------------------------------------------


def test_plain_text_needs_a_colour_too(tmp_path):
    with pytest.raises(ThemeError, match="default"):
        load_theme(written(tmp_path, '{"styles": {"words": "#fff"}, "keywords": []}'))


def test_a_style_that_is_not_a_colour_is_said_so(tmp_path):
    with pytest.raises(ThemeError, match="banana"):
        load_theme(written(tmp_path, '{"styles": {"default": "banana"}}'))


def test_a_rule_naming_a_colour_that_is_not_there_is_said_so(tmp_path):
    for what in ("pairs", "keywords"):
        with pytest.raises(ThemeError) as caught:
            load_theme(
                written(
                    tmp_path,
                    json.dumps(
                        {
                            "styles": {"default": "#000"},
                            what: [{"style": "nope", "words": ["x"], "open": "(", "close": ")"}],
                        }
                    ),
                )
            )
        assert "nope" in str(caught.value)


def test_numbers_naming_a_colour_that_is_not_there_is_said_so(tmp_path):
    with pytest.raises(ThemeError, match="numbers"):
        load_theme(
            written(tmp_path, '{"styles": {"default": "#000"}, "numbers": "digits"}')
        )


def test_a_pair_needs_something_to_open_it(tmp_path):
    with pytest.raises(ThemeError, match="nothing to open"):
        load_theme(
            written(
                tmp_path,
                '{"styles": {"default": "#000"}, "pairs": [{"style": "default"}]}',
            )
        )


def test_a_theme_that_is_a_list_is_not_a_theme(tmp_path):
    with pytest.raises(ThemeError, match="one object"):
        load_theme(written(tmp_path, "[]"))


def test_a_style_that_is_a_number_is_said_so(tmp_path):
    with pytest.raises(ThemeError, match="default"):
        load_theme(written(tmp_path, '{"styles": {"default": 3}}'))


def test_the_words_of_a_theme_have_to_be_a_list(tmp_path):
    with pytest.raises(ThemeError, match="list"):
        load_theme(
            written(
                tmp_path,
                '{"styles": {"default": "#000"}, "keywords": [{"style": "default",'
                ' "words": "kind"}]}',
            )
        )


# ---------------------------------------------------------------------------
# what the words mean when case is not counted
# ---------------------------------------------------------------------------


def test_a_theme_that_ignores_case_matches_a_word_written_any_way():
    theme = parse_theme(
        {
            "name": "any case",
            "caseSensitive": False,
            "styles": {"default": "#000", "words": "#00f"},
            "keywords": [{"style": "words", "words": ["Kind"]}],
        }
    )
    assert theme.words["kind"] == "words"


def test_a_theme_that_counts_case_only_matches_the_way_it_was_written():
    theme = parse_theme(
        {
            "styles": {"default": "#000", "words": "#00f"},
            "keywords": [{"style": "words", "words": ["Kind"]}],
        }
    )
    assert "kind" not in theme.words
    assert theme.words["Kind"] == "words"


def test_a_word_in_two_lists_takes_the_first_list():
    """The same word coloured two ways is a mistake, but a predictable one."""
    theme = parse_theme(
        {
            "styles": {"default": "#000", "first": "#00f", "second": "#f00"},
            "keywords": [
                {"style": "first", "words": ["kind"]},
                {"style": "second", "words": ["kind"]},
            ],
        }
    )
    assert theme.words["kind"] == "first"


def test_a_colour_the_theme_left_out_falls_back_to_plain_text():
    """The painter asks for a style by name, and a theme missing one says plain."""
    theme = parse_theme({"styles": {"default": "#123456"}})
    assert theme.style("anything").colour == "#123456"


# ---------------------------------------------------------------------------
# a family of words written as one pattern
# ---------------------------------------------------------------------------

FAMILY = """
{
  "name": "families",
  "languageSuffixes": true,
  "styles": {"default": "#000000", "words": "#0000ff", "other": "#800000"},
  "keywords": [
    {"style": "words", "words": ["description"],
     "patterns": ["category-era-[0-9]+", "car[0-9]+"]},
    {"style": "other", "words": ["car17"], "patterns": "icon[0-9]+"}
  ]
}
"""


def test_a_keyword_list_may_give_patterns_as_well_as_words():
    theme = parse_theme(json.loads(FAMILY))
    assert theme.keywords[0].patterns == ("category-era-[0-9]+", "car[0-9]+")
    assert theme.keywords[1].patterns == ("icon[0-9]+",)  # one pattern, written as a string


def test_a_pattern_colours_a_word_the_theme_never_named():
    theme = parse_theme(json.loads(FAMILY))
    assert theme.keyword_style("category-era-42") == "words"
    assert theme.keyword_style("car7") == "words"
    assert theme.keyword_style("icon12345") == "other"


def test_a_pattern_reaches_a_whole_word_and_no_part_of_one():
    """The word is matched against the pattern rather than searched for in it,
    so a pattern cannot colour a piece of something else."""
    theme = parse_theme(json.loads(FAMILY))
    assert theme.keyword_style("mycar1") is None
    assert theme.keyword_style("car") is None
    assert theme.keyword_style("category-era-x") is None


def test_a_word_written_out_keeps_its_colour_against_a_pattern():
    """Which is how one member of a family is picked out and coloured another
    way, the way the shipped theme colours car15 to car20 differently."""
    theme = parse_theme(json.loads(FAMILY))
    assert theme.keyword_style("car17") == "other"
    assert theme.keyword_style("car18") == "words"


def test_a_theme_written_out_keeps_its_patterns(tmp_path):
    theme = parse_theme(json.loads(FAMILY))
    again = load_theme(save_theme(theme, tmp_path / "again.json"))
    assert again.keywords[0].patterns == theme.keywords[0].patterns
    assert again.keyword_style("car7") == "words"


def test_a_theme_with_nothing_to_repeat_writes_nothing_out():
    written = parse_theme(json.loads(SIMPLE)).to_json()
    assert "patterns" not in written["keywords"][0]
    assert "languageSuffixes" not in written


def test_a_pattern_that_cannot_be_read_says_which_file(tmp_path):
    path = written(tmp_path, FAMILY.replace("[0-9]+", "([0-9]+"))
    with pytest.raises(ThemeError) as caught:
        load_theme(path)
    assert str(path) in str(caught.value)
    assert "category-era-([0-9]+" in str(caught.value)


def test_the_patterns_are_read_the_way_the_theme_counts_case():
    counted = parse_theme(json.loads(FAMILY))
    assert counted.keyword_style("CATEGORY-ERA-9") is None
    loose = FAMILY.replace('"name": "families",', '"name": "families", "caseSensitive": false,')
    theme = parse_theme(json.loads(loose))
    assert theme.keyword_style("CATEGORY-ERA-9") == "words"
    assert theme.keyword_style("DESCRIPTION-ru") == "words"


# ---------------------------------------------------------------------------
# a whole sort of name coloured as one
# ---------------------------------------------------------------------------

ROLES = """
{
  "name": "sorts",
  "styles": {
    "default": "#000000", "tags": "#0000ff", "containers": "#800000", "odd": "#ff0000"
  },
  "keywords": [
    {"style": "odd", "words": ["origin"], "patterns": ["icon[0-9]+"]},
    {"style": "tags", "all": "tags"},
    {"style": "containers", "all": "containers"}
  ]
}
"""


def test_a_keyword_list_may_stand_for_every_name_of_a_sort():
    theme = parse_theme(json.loads(ROLES))
    assert theme.keywords[1].all == TAGS
    assert theme.roles == {"tags": "tags", "containers": "containers"}


def test_a_sort_of_name_colours_a_name_the_theme_never_mentioned():
    theme = parse_theme(json.loads(ROLES))
    assert theme.keyword_style("anything-at-all", TAGS) == "tags"
    assert theme.keyword_style("kuid-table", CONTAINERS) == "containers"


def test_a_sort_of_name_says_nothing_about_the_other_sort():
    """A name is only coloured by the sort it is, and asking about a word on its
    own says nothing about either."""
    theme = parse_theme(json.loads(ROLES))
    assert theme.keyword_style("anything-at-all") is None
    assert theme.keyword_style("kuid-table", TAGS) == "tags"
    assert theme.keyword_style("anything-at-all", CONTAINERS) == "containers"


def test_a_word_the_theme_named_outranks_the_sort_of_name_it_belongs_to():
    """Saying one word says more than saying every name of a kind, whichever
    order the theme lists them in."""
    theme = parse_theme(json.loads(ROLES))
    assert theme.keyword_style("origin", TAGS) == "odd"
    assert theme.keyword_style("icon12", CONTAINERS) == "odd"


def test_a_list_may_name_words_in_one_place_and_a_sort_of_name_in_another():
    """The words are tried first whoever lists them, so the list that covers a
    whole sort only colours the names nobody spelled out."""
    theme = parse_theme(
        {
            "styles": {"default": "#000", "odd": "#ff0000", "tags": "#0000ff"},
            "keywords": [
                {"style": "odd", "words": ["origin"]},
                {"style": "tags", "all": "tags"},
            ],
        }
    )
    assert theme.keyword_style("origin", TAGS) == "odd"
    assert theme.keyword_style("anything-at-all", TAGS) == "tags"


def test_a_list_gives_a_sort_of_name_its_own_colour_whatever_words_it_names():
    """One list, one colour: the words only matter against a list that says more
    about them, or one that covers the same sort of name later on."""
    theme = parse_theme(
        {
            "styles": {"default": "#000", "odd": "#ff0000", "tags": "#0000ff"},
            "keywords": [{"style": "odd", "words": ["origin"], "all": "tags"}],
        }
    )
    assert theme.keyword_style("origin", TAGS) == "odd"
    assert theme.keyword_style("anything-at-all", TAGS) == "odd"


def test_the_first_list_to_cover_a_sort_of_name_decides_its_colour():
    theme = parse_theme(
        {
            "styles": {"default": "#000", "first": "#0000ff", "second": "#ff0000"},
            "keywords": [
                {"style": "first", "all": "tags"},
                {"style": "second", "all": "tags"},
            ],
        }
    )
    assert theme.keyword_style("anything-at-all", TAGS) == "first"


def test_a_local_tag_is_coloured_before_the_sort_of_name_it_belongs_to():
    loose = ROLES.replace('"name": "sorts",', '"name": "sorts", "languageSuffixes": true,')
    theme = parse_theme(json.loads(loose))
    assert theme.keyword_style("origin-ru", TAGS) == "odd"
    assert theme.keyword_style("anything-at-all-ru", TAGS) == "tags"


def test_a_theme_written_out_keeps_the_sort_of_name_it_covers(tmp_path):
    theme = parse_theme(json.loads(ROLES))
    target = save_theme(theme, tmp_path / "again.json")
    assert json.loads(target.read_text(encoding="utf-8"))["keywords"][1] == {
        "style": "tags",
        "all": "tags",
    }
    again = load_theme(target)
    assert again.roles == theme.roles
    assert again.keyword_style("anything-at-all", TAGS) == "tags"


def test_a_sort_of_name_that_is_not_one_of_the_two_says_so(tmp_path):
    path = written(tmp_path, ROLES.replace('"all": "tags"', '"all": "values"'))
    with pytest.raises(ThemeError) as caught:
        load_theme(path)
    assert "values" in str(caught.value)


# ---------------------------------------------------------------------------
# the two letter tail that says which language a tag is written for
# ---------------------------------------------------------------------------


def test_a_language_suffix_borrows_the_colour_of_the_tag_it_follows():
    theme = parse_theme(json.loads(FAMILY))
    assert theme.keyword_style("description-ru") == "words"
    assert theme.keyword_style("description-de") == "words"
    assert theme.keyword_style("category-era-3-ro") == "words"


def test_a_suffix_is_two_letters_and_neither_one_nor_three():
    theme = parse_theme(json.loads(FAMILY))
    assert theme.keyword_style("description-r") is None
    assert theme.keyword_style("description-rus") is None
    assert theme.keyword_style("description-russian") is None


def test_a_suffix_cannot_invent_a_colour_for_a_tag_nobody_listed():
    theme = parse_theme(json.loads(FAMILY))
    assert theme.keyword_style("nonsense-ru") is None


def test_a_theme_that_says_nothing_about_languages_leaves_a_local_tag_plain():
    theme = parse_theme(json.loads(FAMILY.replace('"languageSuffixes": true,', "")))
    assert theme.language_suffixes is False
    assert theme.keyword_style("description-ru") is None
    assert theme.keyword_style("description") == "words"


# ---------------------------------------------------------------------------
# the second colour, for text on a dark background
# ---------------------------------------------------------------------------


def test_a_style_may_name_a_second_colour_for_a_dark_background():
    theme = parse_theme(
        {
            "styles": {
                "default": {"colour": "#000000", "dark": "#ffffff"},
                "words": {"colour": "#0000ff", "dark": "#3fd0e0"},
            },
            "keywords": [{"style": "words", "words": ["kind"]}],
        }
    )
    assert theme.styles["words"].dark == "#3fd0e0"
    assert theme.styles["words"].colour_for(False) == "#0000ff"
    assert theme.styles["words"].colour_for(True) == "#3fd0e0"
    assert theme.styles["default"].colour_for(True) == "#ffffff"


def test_a_style_that_names_no_dark_colour_is_painted_the_same_either_way():
    style = Style(name="words", colour="#0000ff")
    assert style.dark is None
    assert style.colour_for(True) == style.colour_for(False) == "#0000ff"


def test_a_dark_colour_is_a_colour_like_any_other(tmp_path):
    with pytest.raises(ThemeError, match="banana"):
        load_theme(
            written(
                tmp_path,
                '{"styles": {"default": {"colour": "#000", "dark": "banana"}}}',
            )
        )


def test_a_theme_written_out_keeps_the_dark_colours(tmp_path):
    theme = parse_theme(
        {"styles": {"default": {"colour": "#000000", "dark": "#ffffff"}}}
    )
    target = save_theme(theme, tmp_path / "t.json")
    assert json.loads(target.read_text(encoding="utf-8"))["styles"]["default"]["dark"] == "#ffffff"
    assert load_theme(target) == theme


def test_a_theme_that_never_mentions_dark_mode_stays_that_way(tmp_path):
    """Nothing is invented on the way out; a style with one colour is written
    with one colour."""
    theme = load_theme(written(tmp_path, SIMPLE))
    target = save_theme(theme, tmp_path / "again" / "t.json")
    assert "dark" not in json.loads(target.read_text(encoding="utf-8"))["styles"]["words"]


def test_the_shipped_theme_can_be_read_on_a_dark_background():
    """The program cannot know what the desktop looks like, so every style of
    the theme it ships has to say what it becomes on a dark one."""
    theme = default_theme()
    missing = [name for name, style in theme.styles.items() if not style.dark]
    assert not missing, f"no dark colour: {missing}"


def test_the_dark_colours_of_the_shipped_theme_stand_out_on_a_dark_background():
    """The point of the second colour is that it can be seen, so the one that
    ships is checked against the background it is meant for.

    The ratio is the one WCAG calls acceptable for body text (4.5), and the
    background is what a dark theme paints behind a text edit.
    """
    for name, style in default_theme().styles.items():
        ratio = contrast(style.dark, DARK_BACKGROUND)
        assert ratio >= 4.5, f"{name}: {style.dark} on {DARK_BACKGROUND} is only {ratio:.1f}"
