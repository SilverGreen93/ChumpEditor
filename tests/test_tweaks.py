"""Tests for the Tweaks conversion: numbered tags folded into one list tag.

Nothing here needs a window.  The rules, the edits and the words about them are
all decided in ``tweaks.py``; ``gui.editor`` only carries the edits out.
"""

from __future__ import annotations

from pathlib import Path

from chumpeditor import tweaks
from chumpeditor.chump import parse_text, read_text_file

SAMPLES = Path(__file__).parent / "test_files"


def folded(text: str) -> str:
    """The text a conversion produces."""
    return tweaks.convert_obsolete_lists(text).text


def said(text: str) -> str:
    """Everything the conversion had to say, in one string to search."""
    return tweaks.convert_obsolete_lists(text).summary()


# ---------------------------------------------------------------------------
# the change itself
# ---------------------------------------------------------------------------
def test_a_run_of_numbered_tags_becomes_one_list():
    text = 'era-0 "1920s"\nera-1 "1930s"\nera-2 "1940s"\n'
    assert folded(text) == 'era   "1920s;1930s;1940s"\n'


def test_the_values_come_in_the_order_the_numbers_say():
    """era 9 before era 10, wherever the lines happen to stand."""
    text = 'era-10 "1990s"\nera-9 "1980s"\nera-1 "1930s"\nera-0 "1920s"\n'
    assert folded(text) == 'era    "1920s;1930s;1980s;1990s"\n'


def test_every_tag_matching_the_pattern_is_done_not_just_the_first():
    text = (
        'category-era-0 "1920s"\ncategory-era-1 "1930s"\n'
        'kind "interior"\n'
        'category-region-0 "RO"\ncategory-region-1 "DE"\n'
    )
    assert folded(text) == (
        'category-era   "1920s;1930s"\n'
        'kind "interior"\n'
        'category-region   "RO;DE"\n'
    )


def test_the_indent_and_the_value_column_are_kept():
    """A tag lined up on column 40 stays lined up on column 40."""
    text = (
        'trainz-build                            1.5\n'
        '  category-era-0                        "1940s"\n'
        '  category-era-1                        "1950s"\n'
    )
    assert folded(text) == (
        'trainz-build                            1.5\n'
        '  category-era                          "1940s;1950s"\n'
    )


def test_the_rest_of_the_text_is_left_exactly_as_it_was():
    """Blank lines, comments of no kind, and tags that only look alike."""
    text = (
        'kind "interior"\n'
        'description-ru "Прохожая3"\n'
        'car15 "a"\ncar16 "b"\n'
        'username-jp "x"\n'
        '\n'
        'kuid-table\n{\n}\n'
    )
    assert folded(text) == text


# ---------------------------------------------------------------------------
# a tag standing on its own
# ---------------------------------------------------------------------------
def test_a_tag_on_its_own_keeps_its_value_and_loses_the_number():
    """A list of one is written as one tag, so there is nothing to join up."""
    text = 'category-region-0 "SE"\nkind "interior"\n'
    assert folded(text) == 'category-region   "SE"\nkind "interior"\n'
    assert said(text) == (
        "Converted 1 obsolete tag:\n"
        "\n"
        "  category-region-0 became category-region 'SE'"
    )


def test_a_name_that_ends_in_a_digit_without_a_dash_is_left_alone():
    """load0 is a tag called load0; only the dash marks the old numbered tags."""
    assert folded('load0 "5"\n') == 'load0 "5"\n'


def test_a_lone_tag_gives_way_to_a_list_of_the_same_name_below_it():
    """The run of two is a list beyond doubt; the odd tag out waits its turn."""
    text = 'era-0 "a"\nkind "x"\nera-1 "b"\nera-2 "c"\n'
    assert folded(text) == 'era-0 "a"\nkind "x"\nera   "b;c"\n'
    assert "era-0 would repeat era, which era-1, era-2 became" in said(text)


# ---------------------------------------------------------------------------
# what is turned down, and the words about it
# ---------------------------------------------------------------------------
def test_only_neighbouring_lines_make_one_list():
    """Anything between two of them means two groups, and no guess is made."""
    text = 'era-0 "a"\nera-1 "b"\nkind "interior"\nera-2 "c"\n'
    assert folded(text) == 'era   "a;b"\nkind "interior"\nera-2 "c"\n'
    assert "era-2 would repeat era, which era-0, era-1 became" in said(text)


def test_a_numbered_tag_at_a_different_indent_is_a_different_list():
    """Two of a name in different places are two tags, and only one is renamed."""
    text = 'era-0 "a"\n  era-1 "b"\n'
    assert folded(text) == 'era   "a"\n  era-1 "b"\n'
    assert "era-1 would repeat era, which era-0 became" in said(text)


def test_a_value_that_is_not_a_quoted_one_breaks_the_run():
    """A kuid, a number and an empty value are not elements of a list."""
    text = 'era-0 <kuid:1:2>\nera-1 "b"\nera-2 3\nera-3 ""\nera-4 "c"\n'
    assert folded(text) == 'era-0 <kuid:1:2>\nera   "b"\nera-2 3\nera-3 ""\nera-4 "c"\n'
    assert "era-4 would repeat era, which era-1 became" in said(text)


def test_a_value_running_over_several_lines_is_not_touched():
    """The lines of a long license string are not tags, however they read."""
    text = (
        'license                                 "Any modification\n'
        'era-0 without permission.\nera-1 "\n'
        'kuid-table\n{\n}\n'
    )
    assert folded(text) == text


def test_a_name_the_file_already_has_stops_the_group():
    """One era tag is what a list is; a second one is a broken file."""
    text = 'era "1900s"\nera-0 "1920s"\nera-1 "1930s"\n'
    assert folded(text) == text
    assert "era-0, era-1 would repeat era" in said(text)


def test_a_name_the_file_already_has_stops_a_lone_tag_too():
    text = 'era "1900s"\nera-0 "1920s"\n'
    assert folded(text) == text
    assert "era-0 would repeat era, which the file already has" in said(text)


def test_the_first_tags_of_a_name_take_it_and_the_rest_are_left_alone():
    """Two groups would both be called era; a file with two is not a file."""
    text = 'era-0 "a"\nera-1 "b"\nkind "interior"\nera-2 "c"\nera-3 "d"\n'
    assert folded(text) == 'era   "a;b"\nkind "interior"\nera-2 "c"\nera-3 "d"\n'
    assert said(text).count("would repeat era") == 1
    assert "era-2, era-3 would repeat era, which era-0, era-1 became" in said(text)


def test_a_value_holding_a_semicolon_is_left_alone():
    """Joining it up would turn one element into two."""
    text = 'era-0 "a;b"\nera-1 "c"\n'
    assert folded(text) == text
    assert "holds a ';' in a value" in said(text)
    # one tag on its own has nothing to join up, so its value cannot be misread
    assert folded('era-0 "a;b"\n') == 'era   "a;b"\n'


# ---------------------------------------------------------------------------
# the edits the editor applies, and the words it shows afterwards
# ---------------------------------------------------------------------------
def test_the_rewrites_add_up_to_the_new_text():
    """Cutting out each stretch from the end backwards is the whole change.

    The editor leans on this: it applies the rewrites to a document instead of
    replacing the document, which is what keeps the change to one undo step.
    """
    text = (
        'kind "interior"\n'
        'era-0 "a"\nera-1 "b"\n'
        'region "RO"\n'
        'car-3 "x"\ncar-4 "y"\ncar-5 "z"\n'
    )
    result = tweaks.convert_obsolete_lists(text)
    assert len(result.rewrites) == 2
    manual = text
    for rewrite in sorted(result.rewrites, key=lambda item: item.start, reverse=True):
        assert "\n" not in rewrite.text
        manual = manual[: rewrite.start] + rewrite.text + manual[rewrite.end :]
    assert manual == result.text


def test_a_lone_tag_is_one_rewrite_too():
    """The editor wants places in the text, whatever the tag became."""
    result = tweaks.convert_obsolete_lists('kind "interior"\nregion-0 "RO"\n')
    assert len(result.rewrites) == 1
    rewrite = result.rewrites[0]
    assert rewrite.text == 'region   "RO"'
    assert result.text[: rewrite.start] + rewrite.text + result.text[rewrite.end :] == (
        'kind "interior"\nregion   "RO"\n'
    )


def test_a_text_file_written_with_crlf_comes_back_with_crlf():
    text = 'era-0 "a"\r\nera-1 "b"\r\n'
    result = tweaks.convert_obsolete_lists(text)
    assert result.text == 'era   "a;b"\r\n'
    assert [rewrite.text for rewrite in result.rewrites] == ['era   "a;b"']


def test_the_summary_lists_every_tag_that_was_converted():
    text = 'era-0 "a"\nera-1 "b"\ncar-2 "x"\ncar-3 "y"\n'
    result = tweaks.convert_obsolete_lists(text)
    assert result.status == "Converted 2 obsolete tags"
    assert result.summary() == (
        "Converted 2 obsolete tags:\n"
        "\n"
        "  era-0, era-1 became era 'a;b'\n"
        "  car-2, car-3 became car 'x;y'"
    )


def test_the_summary_of_a_file_with_nothing_to_convert_says_so():
    result = tweaks.convert_obsolete_lists('kind "interior"\n')
    assert result.status == "Nothing was converted"
    assert result.summary().startswith("Nothing was converted")
    assert result.summary().endswith("the shorter name is not already used.")


# ---------------------------------------------------------------------------
# the file this was asked for
# ---------------------------------------------------------------------------
def test_the_obsolete_config_from_a_real_asset():
    """Nine era tags fold up, a lone region tag loses its number, and the
    long license string is left exactly as it was."""
    text = read_text_file(SAMPLES / "obsolete_config.txt")
    result = tweaks.convert_obsolete_lists(text)

    assert [str(item) for item in result.conversions] == [
        "category-region-0 became category-region 'SE'",
        "category-era-0, category-era-1, category-era-2, category-era-3, "
        "category-era-4, category-era-5, category-era-6, category-era-7, "
        "category-era-8 became category-era "
        "'1920s;1930s;1940s;1950s;1960s;1970s;1980s;1990s;2000s'",
    ]
    assert result.skipped == ()
    assert 'category-region                         "SE"' in result.text
    assert 'category-region-0' not in result.text
    assert 'description-ru                          "Прохожая3"' in result.text

    lines_before = text.split("\r\n")
    lines_after = result.text.split("\r\n")
    assert len(lines_after) == len(lines_before) - 8  # nine lines went, one came
    # the long license, which is not a list, kept its two lines as they were
    assert [line for line in lines_after if "license" in line] == [
        line for line in lines_before if "license" in line
    ]

    # the fold is only a change of spelling: the file still reads, everything
    # that was not one of the numbered tags is still there in the same order,
    # and the nine era values are the one value
    before, after = parse_text(text), parse_text(result.text)
    named = {
        "category-region-0",
        *(f"category-era-{number}" for number in range(9)),
    }
    names_before = [tag.name for tag in before.tags]
    names_after = [tag.name for tag in after.tags]
    assert [name for name in names_before if name not in named] == [
        name for name in names_after if name not in {"category-region", "category-era"}
    ]
    assert [tag.value for tag in after.tags if tag.name == "category-region"] == ["SE"]
    assert [tag.value for tag in after.tags if tag.name == "category-era"] == [
        ";".join(tag.value for tag in before.tags if tag.name.startswith("category-era-"))
    ]
    assert len(names_after) == len(names_before) - 8


def test_the_obsolete_config_is_ready_to_be_written_back():
    """The text the conversion hands back is the text form, spacing and all."""
    text = read_text_file(SAMPLES / "obsolete_config.txt")
    result = tweaks.convert_obsolete_lists(text)
    assert tweaks.convert_obsolete_lists(result.text).conversions == ()
