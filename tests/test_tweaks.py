"""Tests for the two Tweaks: numbered tags folded into one, and language tags.

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


def cleared(text: str) -> str:
    """The text a language sweep produces."""
    return tweaks.remove_language_tags(text).text


def told(text: str) -> str:
    """Everything the sweep had to say, in one string to search."""
    return tweaks.remove_language_tags(text).summary()


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


# ---------------------------------------------------------------------------
# the language tags
# ---------------------------------------------------------------------------
def test_the_plain_tag_stays_and_the_languages_go():
    text = (
        'description                             "woman3"\n'
        'description-ru                          "kobieta3"\n'
        'description-pl                          "Прохожая3"\n'
    )
    assert cleared(text) == 'description                             "woman3"\n'


def test_every_language_in_the_file_goes_not_just_the_named_ones():
    """The ask is about the tags, so every one of them is meant."""
    text = 'username-cn "a"\nusername-jp "b"\ndescription-de "c"\nkind "interior"\n'
    assert cleared(text) == 'kind "interior"\n'


def test_a_language_tag_is_known_by_the_two_letters_at_the_end_of_the_name():
    """An email is not written in the Ewe language, and eng is three letters."""
    text = (
        'contact-email                           "nobody@example.com"\n'
        'height-range                            0,3\n'
        'category-class                          "BR"\n'
        'description-eng                         "woman3"\n'
        'description-de                          "Frau3"\n'
    )
    assert cleared(text) == (
        'contact-email                           "nobody@example.com"\n'
        'height-range                            0,3\n'
        'category-class                          "BR"\n'
        'description-eng                         "woman3"\n'
    )


def test_the_language_is_the_last_dash_in_the_name():
    """description-de-pl ends in -pl, which is the language part of it."""
    text = 'description-de-pl "woman3"\n'
    assert cleared(text) == ""


def test_a_number_or_a_kuid_after_the_name_is_a_value_like_any_other():
    text = 'trainz-build 1.5\nload0-ru 3\nkuid-de <kuid2:1:2:3>\n'
    assert cleared(text) == 'trainz-build 1.5\n'


def test_a_value_running_over_several_lines_goes_with_its_tag():
    text = (
        'kind "interior"\n'
        'description-de                          "Frau3\n'
        '                                       die Frau\n'
        '"\n'
        'description                             "woman3"\n'
    )
    assert cleared(text) == (
        'kind "interior"\n'
        'description                             "woman3"\n'
    )


def test_the_text_inside_a_value_is_not_read_as_tags():
    """A line of prose that happens to be spelled like a tag stays put."""
    text = (
        'license "\n'
        'description-de was written here in the original\n'
        '"\n'
    )
    assert cleared(text) == text


def test_a_container_under_that_name_goes_whole():
    """Either way of writing the opening brace, the container goes with what is
    inside it, which is what its value is."""
    same_line = 'kind "interior"\ndescription-de {\n  name "x"\n}\n'
    next_line = 'kind "interior"\ndescription-de\n{\n  name "x"\n}\n'
    assert cleared(same_line) == 'kind "interior"\n'
    assert cleared(next_line) == 'kind "interior"\n'


def test_a_container_fully_inside_a_removed_container_is_cut_once():
    """The nested tags go with the block, not as edits of their own."""
    text = (
        'localised-de {\n'
        '  short-de "a"\n'
        '  nested-de {\n'
        '    deep-de "b"\n'
        '  }\n'
        '}\n'
        'kind "interior"\n'
    )
    result = tweaks.remove_language_tags(text)
    assert result.text == 'kind "interior"\n'
    assert len(result.rewrites) == 1
    assert [str(item) for item in result.removals] == [
        'localised-de { short-de "a" nested-de { deep-de "b" } } went; '
        "no localised in the file"
    ]


def test_a_language_tag_inside_a_container_that_stays_is_taken_out():
    text = (
        'kuid-table {\n'
        '  description-de "Frau3"\n'
        '  description "woman3"\n'
        '}\n'
    )
    assert cleared(text) == 'kuid-table {\n  description "woman3"\n}\n'


def test_a_tag_holding_nothing_yet_goes_as_cleanly_as_one_holding_a_value():
    text = 'kind "interior"\ndescription-de\n'
    assert cleared(text) == 'kind "interior"\n'
    assert [str(item) for item in tweaks.remove_language_tags(text).removals] == [
        "description-de went; no description in the file"
    ]


def test_the_line_ending_goes_with_the_tag_so_no_gap_is_left_behind():
    text = 'kind "interior"\n\ndescription-de "x"\n\nauthor "nobody"\n'
    assert cleared(text) == 'kind "interior"\n\n\nauthor "nobody"\n'


def test_the_last_tag_of_a_file_with_no_line_ending_of_its_own_goes_too():
    text = 'kind "interior"\ndescription-de "x"'
    assert cleared(text) == 'kind "interior"\n'


def test_a_container_that_is_never_closed_is_left_alone_and_said():
    text = 'kind "interior"\ndescription-de {\n  name "x"\n'
    result = tweaks.remove_language_tags(text)
    assert result.text == text
    assert result.rewrites == ()
    assert result.notes == ("description-de opens a container that is never closed",)
    assert told(text).endswith(
        "Left alone: description-de opens a container that is never closed."
    )


def test_a_value_that_is_never_closed_is_left_alone_and_said():
    text = 'kind "interior"\ndescription-de "Frau3\nname x\n'
    result = tweaks.remove_language_tags(text)
    assert result.text == text
    assert result.rewrites == ()
    assert result.notes == ("description-de holds a quoted value that is never closed",)


def test_a_language_tag_with_no_plain_tag_of_its_own_is_said_out_loud():
    text = 'description-de "Frau3"\nkind "interior"\n'
    assert told(text) == (
        "Removed 1 language tag:\n"
        "\n"
        '  description-de "Frau3" went; no description in the file'
    )


def test_the_summary_says_which_tag_was_left_behind():
    text = (
        'description "woman3"\n'
        'description-de "Frau3"\n'
        'username-cn "a"\n'
    )
    assert tweaks.remove_language_tags(text).summary() == (
        "Removed 2 language tags:\n"
        "\n"
        '  description-de "Frau3" went; description stays\n'
        '  username-cn "a" went; no username in the file'
    )


def test_the_summary_of_a_file_with_no_language_tags_says_so():
    result = tweaks.remove_language_tags('kind "interior"\ncontact-email "a@b"\n')
    assert result.status == "No language tags"
    assert result.rewrites == ()
    assert result.summary().startswith("Nothing was removed")


def test_the_rewrites_point_at_the_text_they_take_out():
    """The places are document positions, which is what the editor needs."""
    text = 'kind "interior"\n  description-de "Frau3"\nauthor "nobody"\n'
    result = tweaks.remove_language_tags(text)
    assert [
        text[rewrite.start : rewrite.end] for rewrite in result.rewrites
    ] == ['  description-de "Frau3"\n']
    assert all(
        one.end <= two.start for one, two in zip(result.rewrites, result.rewrites[1:])
    )


def test_a_text_file_written_with_crlf_comes_back_with_crlf():
    text = 'description "a"\r\ndescription-de "b"\r\nkind "interior"\r\n'
    assert tweaks.remove_language_tags(text).text == (
        'description "a"\r\nkind "interior"\r\n'
    )


def test_the_sweep_leaves_nothing_for_a_second_sweep_to_do():
    text = read_text_file(SAMPLES / "obsolete_config.txt")
    once = tweaks.remove_language_tags(text)
    assert tweaks.remove_language_tags(once.text).removals == ()


def test_the_language_tags_of_a_real_asset():
    """Twenty translations out, the English and the license left exactly as they
    were, and the file still reads."""
    text = read_text_file(SAMPLES / "obsolete_config.txt")
    result = tweaks.remove_language_tags(text)

    assert len(result.removals) == 20
    assert result.notes == ()
    assert result.status == "Removed 20 language tags"

    for language in ("de", "pl", "cn", "fr", "nl", "es", "ru", "it", "hu", "cz"):
        assert f"description-{language}" not in result.text
    for language in ("cn", "nl", "hu", "cz", "jp", "it", "es", "pl", "de", "fr"):
        assert f"username-{language}" not in result.text

    lines_before = text.split("\r\n")
    lines_after = result.text.split("\r\n")
    assert len(lines_after) == len(lines_before) - 20
    # the license runs over lines and is nobody's translation
    assert [line for line in lines_after if "license" in line] == [
        line for line in lines_before if "license" in line
    ]

    # what is left is the same file with the translations missing: same tags in
    # the same order, and nothing else changed its value
    before, after = parse_text(text), parse_text(result.text)
    gone = {item.tag for item in result.removals}
    assert [tag.name for tag in after.tags] == [
        tag.name for tag in before.tags if tag.name not in gone
    ]
    assert after.get("contact-email").value == before.get("contact-email").value
    assert after.get("description").value == before.get("description").value
    assert after.get("license").value == before.get("license").value
    assert after.get("kuid-table").tags == before.get("kuid-table").tags
