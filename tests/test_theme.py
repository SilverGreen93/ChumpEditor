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
    DEFAULT_THEME,
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
        "keywords1",
        "keywords2",
        "keywords3",
        "delimiters1",
        "delimiters2",
    }


def test_the_theme_that_comes_with_the_program_colours_words_and_strings():
    theme = default_theme()
    assert theme.style("keywords1").colour == "#0000ff"
    assert theme.words["kind"] == "keywords1"
    assert [pair.open for pair in theme.pairs] == ['"', "<"]
    assert theme.style("keywords3").italic


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
