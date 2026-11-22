"""Tests for the Tweaks: numbered tags folded into one, language tags out, and
an asset-filename tag turned into a mesh-table container.

Nothing here needs a window.  The rules, the edits and the words about them are
all decided in ``tweaks.py``; ``gui.editor`` only carries the edits out.
"""

from __future__ import annotations

from pathlib import Path

from chumpeditor import tweaks
from chumpeditor.chump import check_text, load_chump, parse_text, read_text_file, render_text

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


def meshed(text: str) -> str:
    """The text a mesh-table conversion produces."""
    return tweaks.convert_asset_filename_to_mesh_table(text).text


def mesh_said(text: str) -> str:
    """Everything the mesh-table conversion had to say, in one string to search."""
    return tweaks.convert_asset_filename_to_mesh_table(text).summary()


def ordered(text: str) -> str:
    """The text a reorder produces."""
    return tweaks.reorder_tags(text).text


def order_said(text: str) -> str:
    """Everything the reorder had to say, in one string to search."""
    return tweaks.reorder_tags(text).summary()


def held(root) -> dict:
    """The top level tags of a parsed file, gathered by name.

    A reorder moves tags about without changing any of them, so this is what
    the file is checked against before and after: every tag of every name, with
    everything under it, in the order the file has them.
    """
    tags: dict = {}
    for tag in root.tags:
        tags.setdefault(tag.name, []).append(the_shape_of(tag))
    return tags


def the_shape_of(tag):
    """A tag and everything under it, as plain values that can be compared."""
    return (tag.name, tag.value, tuple(the_shape_of(child) for child in tag.tags))


def out_of_order(tag) -> list[str]:
    """The values written below a sub-container, in this tag and below it.

    A container holds its tags in order when nothing holding a value is written
    after a container written inside it, which is asked of every container of the
    file rather than only of the top of it.
    """
    left: list[str] = []
    deeper = False
    for child in tag.tags:
        if child.is_container:
            deeper = True
        elif deeper:
            left.append(child.name)
        left.extend(out_of_order(child))
    return left


def the_gaps_left(text: str) -> list[int]:
    """The lines of this text where a container stands without a gap beside it.

    A container is set off on both sides: a blank line above the line naming it,
    unless a ``{`` or the start of the container it is written in stands there,
    and a blank line under the ``}`` closing it, unless another ``}`` or the end
    of the file stands there.  The lines are read exactly as they stand, with
    nothing moved, which is how the same rule is asked of text that never goes
    through a reorder at all.
    """
    lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
    left: list[int] = []
    for at, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "}":
            under = lines[at + 1].strip() if at + 1 < len(lines) else ""
            if under and not under.startswith("}"):
                left.append(at + 1)
        if stripped.endswith("{"):
            named = at if stripped != "{" else at - 1
            above = lines[named - 1].strip() if named >= 1 else ""
            if above and not above.endswith("{"):
                left.append(named + 1)
    return left


def the_blanks_in_the_way(text: str) -> list[int]:
    """The blank lines of this text standing where no blank line is asked for.

    A blank line parts a container from the line written beside it and nothing
    else, so one is in the way between two tags that each hold one value, under a
    ``{``, above a ``}``, and twice over where one gap says the same thing once.
    The blank lines above the first tag of the text and the ones making up its
    ending are nobody's gap, and a blank line inside a value written over several
    lines belongs to that value rather than to a gap.  The lines are read exactly
    as they stand, which is how the rule is asked of text that never goes through
    a reorder at all.
    """
    lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
    named: set[int] = set()
    opened: set[int] = set()
    closed: set[int] = set()
    value: set[int] = set()
    running = False  # inside a quoted value that ran over the line
    for at, line in enumerate(lines):
        stripped = line.strip()
        if running:
            value.add(at)
            if '"' in stripped:
                running = False
            continue
        if not stripped:
            continue
        if stripped == "{":
            opened.add(at)
            named.add(at - 1)
        elif stripped == "}":
            closed.add(at)
        elif stripped[0].isalpha() and stripped.endswith("{"):
            named.add(at)
        if stripped.count('"') % 2:
            running = True

    keep = len(lines)
    while keep and not lines[keep - 1].strip():
        keep -= 1
    at = 0
    while at < keep and not lines[at].strip():
        at += 1  # the blank lines above the first tag are nobody's gap

    in_the_way: list[int] = []
    while at < keep:
        if lines[at].strip():
            at += 1
            continue
        run = [at]
        while run[-1] + 1 < keep and not lines[run[-1] + 1].strip():
            run.append(run[-1] + 1)
        over, under = run[0] - 1, run[-1] + 1
        parts_a_container = over in closed and under not in opened | closed
        parts_a_container_too = under in named and over not in opened | closed
        if value.intersection(run) or value.intersection((over, under)):
            pass  # written inside a value, so part of that value
        elif not parts_a_container and not parts_a_container_too:
            in_the_way.append(run[0] + 1)
        elif len(run) > 1:
            in_the_way.extend(number + 1 for number in run[1:])
        at = run[-1] + 1
    return in_the_way


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


# ---------------------------------------------------------------------------
# the mesh-table container
# ---------------------------------------------------------------------------
TABLE = (
    "mesh-table\n"
    "{\n"
    "  default\n"
    "  {\n"
    # the value starts on column 40, as it does everywhere else in a config file
    f'    {"mesh":<36}"MS_Shelter_4.im"\n'
    f'    {"auto-create":<36}1\n'
    "  }\n"
    "}\n"
)


def test_an_asset_filename_tag_becomes_a_container_holding_its_mesh():
    assert meshed('asset-filename "MS_Shelter_4"\n') == TABLE


def test_the_mesh_name_keeps_an_extension_it_already_had():
    result = tweaks.convert_asset_filename_to_mesh_table('asset-filename "MS_Shelter_4.im"\n')
    assert result.mesh_tables[0].mesh == "MS_Shelter_4.im"
    assert 'mesh                                "MS_Shelter_4.im"' in result.text
    assert ".im.im" not in result.text


def test_the_container_stands_where_the_tag_stood_and_at_the_same_indent():
    text = 'buildable\n{\n  asset-filename                        "MS_Shelter_4"\n}\n'
    result = tweaks.convert_asset_filename_to_mesh_table(text)
    assert result.text == (
        "buildable\n"
        "{\n"
        "  mesh-table\n"
        "  {\n"
        "    default\n"
        "    {\n"
        f'      {"mesh":<34}"MS_Shelter_4.im"\n'
        f'      {"auto-create":<34}1\n'
        "    }\n"
        "  }\n"
        "}\n"
    )


def test_the_values_stand_on_the_same_column_as_the_rest_of_the_file():
    """The new lines are laid out the way every other value in the file is."""
    lines = meshed('asset-filename "MS_Shelter_4"\n').split("\n")
    assert lines[4][40] == '"'
    assert lines[5][40] == "1"


def test_every_asset_filename_in_the_file_is_converted():
    text = (
        'asset-filename "MS_Shelter_4"\n'
        "kind\n"
        "{\n"
        '  asset-filename "MS_Shelter_5"\n'
        "}\n"
    )
    result = tweaks.convert_asset_filename_to_mesh_table(text)
    assert len(result.mesh_tables) == 2
    assert result.text.count("mesh-table") == 2
    assert "asset-filename" not in result.text


def test_the_rest_of_the_file_is_left_exactly_as_it_was():
    text = (
        "kind\n"
        '{\n'
        '  name "shelter"\n'
        "}\n"
        'asset-filename "MS_Shelter_4"\n'
        "kuid-table\n"
        "{\n"
        "  kuid                <kuid:123:456>\n"
        "}\n"
    )
    result = tweaks.convert_asset_filename_to_mesh_table(text)
    assert result.text.startswith(text[: text.index("asset-filename")])
    assert result.text.endswith(text[text.index("kuid-table"):])


def test_a_file_that_has_a_mesh_table_is_not_touched_at_all():
    text = 'asset-filename "MS_Shelter_4"\n\nmesh-table\n{\n  default\n  {\n    mesh "a.im"\n  }\n}\n'
    result = tweaks.convert_asset_filename_to_mesh_table(text)

    assert result.text == text
    assert result.rewrites == ()
    assert result.status == "Already has a mesh-table"
    assert result.warning
    assert result.summary() == (
        "Already has a mesh-table: a mesh-table with a default mesh is in the file"
    )


def test_a_mesh_table_holding_nothing_still_stops_the_change():
    """Two containers would leave Trainz picking, default mesh or no default."""
    text = 'asset-filename "MS_Shelter_4"\n\nmesh-table\n{\n}\n'
    result = tweaks.convert_asset_filename_to_mesh_table(text)

    assert result.text == text
    assert result.blocked == "a mesh-table is in the file"
    assert result.summary() == "Already has a mesh-table: a mesh-table is in the file"


def test_a_mesh_table_found_anywhere_in_the_file_stops_the_change():
    text = (
        "textures\n"
        "{\n"
        "  mesh-table\n"
        "  {\n"
        "    default\n"
        "    {\n"
        "    }\n"
        "  }\n"
        "}\n"
        'asset-filename "MS_Shelter_4"\n'
    )
    assert tweaks.convert_asset_filename_to_mesh_table(text).blocked == (
        "a mesh-table with a default mesh is in the file"
    )


def test_the_words_mesh_table_inside_a_value_are_not_a_container():
    text = (
        "license\n"
        '"Nobody may use this file with a mesh-table of their own,\n'
        'not even one holding a default mesh"\n'
        'asset-filename "MS_Shelter_4"\n'
    )
    result = tweaks.convert_asset_filename_to_mesh_table(text)

    assert result.blocked == ""
    assert len(result.mesh_tables) == 1


def test_an_asset_filename_that_names_no_mesh_is_left_alone():
    text = (
        "asset-filename\n"
        'asset-filename ""\n'
        "asset-filename MS_Shelter_4\n"
        'asset-filename "MS_Shelter_4\n'
        "more lines\"\n"
        "asset-filename\n"
        "{\n"
        "}\n"
    )
    result = tweaks.convert_asset_filename_to_mesh_table(text)

    assert result.text == text
    assert result.mesh_tables == ()
    assert result.notes == (
        "the asset-filename on line 1 has no value",
        "the asset-filename on line 2 has empty quotes where the mesh name should be",
        "the asset-filename on line 3 holds 'MS_Shelter_4' rather than a name in quotes",
        "the asset-filename on line 4 has a value running over several lines",
        "the asset-filename on line 6 is a container rather than a name",
    )
    assert result.status == "Nothing was converted"
    assert not result.warning
    assert "Left alone: the asset-filename on line 1 has no value." in result.summary()


def test_the_summary_names_the_mesh_that_went_into_the_container():
    assert tweaks.convert_asset_filename_to_mesh_table('asset-filename "MS_Shelter_4"\n').summary() == (
        "Added 1 mesh-table:\n"
        "\n"
        "  asset-filename 'MS_Shelter_4' became mesh-table 'MS_Shelter_4.im'"
    )


def test_the_summary_of_a_file_with_no_asset_filename_says_so():
    result = tweaks.convert_asset_filename_to_mesh_table('kind "interior"\nusername "a"\n')
    assert result.status == "Nothing was converted"
    assert result.rewrites == ()
    assert result.summary().startswith("Nothing was converted")


def test_the_rewrite_covers_the_tag_and_not_the_break_after_it():
    text = 'kind "interior"\nasset-filename "MS_Shelter_4"\nauthor "nobody"\n'
    result = tweaks.convert_asset_filename_to_mesh_table(text)

    assert [text[one.start : one.end] for one in result.rewrites] == ['asset-filename "MS_Shelter_4"']
    assert result.text == (
        'kind "interior"\n' + result.rewrites[0].text + '\nauthor "nobody"\n'
    )


def test_a_conversion_records_the_container_it_wrote():
    result = tweaks.convert_asset_filename_to_mesh_table('asset-filename "MS_Shelter_4"\n')
    table = result.mesh_tables[0]
    assert (table.name, table.source, table.mesh) == ("default", "MS_Shelter_4", "MS_Shelter_4.im")
    assert table.text + "\n" == TABLE
    assert (table.start, table.end) == (0, len('asset-filename "MS_Shelter_4"'))


def test_a_text_file_written_with_crlf_comes_back_with_crlf():
    result = tweaks.convert_asset_filename_to_mesh_table('asset-filename "MS_Shelter_4"\r\n')
    assert result.text == TABLE.replace("\n", "\r\n")


def test_the_conversion_leaves_nothing_for_a_second_conversion_to_do():
    """And the container it wrote itself is no reason to warn anybody."""
    text = read_text_file(SAMPLES / "obsolete_config.txt")
    once = tweaks.convert_asset_filename_to_mesh_table(text)
    twice = tweaks.convert_asset_filename_to_mesh_table(once.text)

    assert twice.text == once.text
    assert twice.status == "Nothing was converted"
    assert twice.blocked == ""
    assert not twice.warning


def test_the_asset_filename_of_a_real_asset():
    """A config file that named its mesh with a tag, and now names it the new way."""
    text = read_text_file(SAMPLES / "obsolete_config.txt")
    result = tweaks.convert_asset_filename_to_mesh_table(text)

    assert result.status == "Added 1 mesh-table"
    assert result.notes == ()
    assert not result.warning
    assert result.mesh_tables[0].mesh == "casualwoman3.im"

    lines_before = text.split("\r\n")
    lines_after = result.text.split("\r\n")
    assert len(lines_after) == len(lines_before) + 7
    assert '    mesh                                "casualwoman3.im"' in result.text
    assert '    auto-create                         1' in result.text
    assert "asset-filename" not in result.text

    before, after = parse_text(text), parse_text(result.text)
    assert [tag.name for tag in after.tags] == [
        "mesh-table" if tag.name == "asset-filename" else tag.name for tag in before.tags
    ]
    table = after.get("mesh-table")
    assert [child.name for child in table.tags] == ["default"]
    default = table.get("default")
    assert [leaf.name for leaf in default.tags] == ["mesh", "auto-create"]
    assert default.get("mesh").value == "casualwoman3.im"
    assert default.get("auto-create").value == 1
    assert after.get("username").value == before.get("username").value
    assert after.get("kuid-table").tags == before.get("kuid-table").tags


# ---------------------------------------------------------------------------
# putting the tags in order
# ---------------------------------------------------------------------------
def test_the_kuid_and_the_username_come_first():
    text = 'kind "interior"\nkuid <kuid:2:100>\nauthor "nobody"\nusername "a name"\n'
    assert ordered(text) == (
        'kuid <kuid:2:100>\n'
        'username "a name"\n'
        'kind "interior"\n'
        'author "nobody"\n'
    )


def test_the_kuid_comes_first_even_when_the_username_was_written_first():
    text = 'username "a name"\nkuid <kuid:2:100>\nkind "interior"\n'
    assert ordered(text) == (
        'kuid <kuid:2:100>\nusername "a name"\nkind "interior"\n'
    )


def test_a_kuid_the_file_never_had_is_not_invented():
    text = 'kind "interior"\nauthor "nobody"\nusername "a name"\n'
    assert ordered(text) == (
        'username "a name"\nkind "interior"\nauthor "nobody"\n'
    )


def test_the_tags_holding_one_value_stay_in_the_order_they_were_found():
    text = 'kuid <kuid:2:100>\nauthor "nobody"\nkind "interior"\nusername "n"\n'
    assert ordered(text) == (
        'kuid <kuid:2:100>\nusername "n"\nauthor "nobody"\nkind "interior"\n'
    )


def test_the_containers_come_after_every_tag_that_holds_one_value():
    text = (
        'kuid <kuid:2:100>\n'
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "a.im"\n'
        "  }\n"
        "}\n"
        'kind "interior"\n'
    )
    assert ordered(text) == (
        'kuid <kuid:2:100>\n'
        'kind "interior"\n'
        "\n"
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "a.im"\n'
        "  }\n"
        "}\n"
    )


def test_the_containers_stay_in_the_order_they_were_found():
    text = (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        "other-table\n{\n  b 2\n}\n"
        'kind "interior"\n'
        "one-table\n{\n  a 1\n}\n"
    )
    assert ordered(text) == (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        'kind "interior"\n'
        "\n"
        "other-table\n{\n  b 2\n}\n"
        "\n"
        "one-table\n{\n  a 1\n}\n"
    )


def test_a_container_travels_whole_and_its_subtags_are_left_as_they_are():
    """The names pinned to the top of a file are not pinned inside a container."""
    text = (
        'kind "vnd.trainsim.asset"\n'
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        "table\n"
        "{\n"
        '  username "inside"\n'
        "  kuid <kuid:2:1>\n"
        "}\n"
    )
    assert ordered(text) == (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        'kind "vnd.trainsim.asset"\n'
        "\n"
        "table\n"
        "{\n"
        '  username "inside"\n'
        "  kuid <kuid:2:1>\n"
        "}\n"
    )


def test_kuid_table_and_obsolete_table_are_the_last_two_containers():
    text = (
        "obsolete-table\n{\n}\n"
        'kuid <kuid:2:100>\n'
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "a.im"\n'
        "  }\n"
        "}\n"
        'kind "interior"\n'
        "kuid-table\n{\n}\n"
    )
    assert ordered(text) == (
        'kuid <kuid:2:100>\n'
        'kind "interior"\n'
        "\n"
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "a.im"\n'
        "  }\n"
        "}\n"
        "\n"
        "kuid-table\n{\n}\n"
        "\n"
        "obsolete-table\n{\n}\n"
    )


def test_the_last_two_containers_stay_last_when_only_one_of_them_is_there():
    text = (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        "obsolete-table\n{\n  a 1\n}\n"
        "mesh-table\n{\n  b 2\n}\n"
    )
    assert ordered(text) == (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        "\n"
        "mesh-table\n{\n  b 2\n}\n"
        "\n"
        "obsolete-table\n{\n  a 1\n}\n"
    )


def test_kuid_table_alone_comes_after_every_other_container():
    text = (
        'kuid <kuid:2:100>\n'
        "kuid-table\n{\n  a 1\n}\n"
        "mesh-table\n{\n  b 2\n}\n"
        'kind "interior"\n'
    )
    assert ordered(text) == (
        'kuid <kuid:2:100>\n'
        'kind "interior"\n'
        "\n"
        "mesh-table\n{\n  b 2\n}\n"
        "\n"
        "kuid-table\n{\n  a 1\n}\n"
    )


def test_a_value_running_over_several_lines_travels_with_its_tag():
    text = (
        'kind "interior"\n'
        'license "first line\nstill the same value"\n'
        'kuid <kuid:2:100>\n'
        'username "n"\n'
    )
    assert ordered(text) == (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        'kind "interior"\n'
        'license "first line\nstill the same value"\n'
    )


def test_a_line_inside_a_value_running_over_several_lines_is_not_a_tag():
    """The license string says what may be done with the asset, and is not tags."""
    text = (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        'license "one line\nkind not-a-tag\nthe value ends here"\n'
    )
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.status == "Nothing was reordered"
    assert not result.warning


def test_the_blank_lines_under_a_tag_travel_with_it():
    text = 'kind "interior"\n\nkuid <kuid:2:100>\nusername "n"\n'
    assert ordered(text) == (
        'kuid <kuid:2:100>\nusername "n"\nkind "interior"\n\n'
    )


def test_the_blank_lines_at_the_end_of_the_file_stay_at_the_end():
    text = 'kind "interior"\nkuid <kuid:2:100>\n\n\n'
    assert ordered(text) == 'kuid <kuid:2:100>\nkind "interior"\n\n\n'


def test_the_gaps_above_the_first_tag_stay_above_the_first_tag():
    text = '\n\nkind "interior"\nkuid <kuid:2:100>\n'
    assert ordered(text) == '\n\nkuid <kuid:2:100>\nkind "interior"\n'


def test_a_tag_written_with_indentation_keeps_its_indentation():
    text = '  kind "interior"\n  kuid <kuid:2:100>\n'
    assert ordered(text) == '  kuid <kuid:2:100>\n  kind "interior"\n'


def test_a_text_file_written_with_crlf_comes_back_with_crlf():
    text = 'kind "interior"\r\nkuid <kuid:2:100>\r\n'
    assert ordered(text) == 'kuid <kuid:2:100>\r\nkind "interior"\r\n'


def test_a_file_with_nothing_after_the_last_tag_has_nothing_to_move():
    text = "kuid-table\n{\n  a 1\n}\n"
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.rewrites == ()
    assert result.status == "Nothing was reordered"


def test_an_empty_file_is_left_alone():
    result = tweaks.reorder_tags("")

    assert result.text == ""
    assert result.rewrites == ()
    assert result.status == "Nothing was reordered"
    assert not result.warning


# ---------------------------------------------------------------------------
# the order inside a container
# ---------------------------------------------------------------------------
def test_the_values_of_a_container_come_before_the_containers_inside_it():
    text = (
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        "    effects\n"
        "    {\n"
        "    }\n"
        '    mesh "ind.im"\n'
        "    auto-create 1\n"
        "  }\n"
        "}\n"
    )
    assert ordered(text) == (
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "ind.im"\n'
        "    auto-create 1\n"
        "\n"
        "    effects\n"
        "    {\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def test_the_order_is_put_right_at_every_depth_of_the_file():
    text = (
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        "    effects\n"
        "    {\n"
        "      effect-mesh\n"
        "      {\n"
        '        mesh "e.im"\n'
        "      }\n"
        '      effect "a"\n'
        "    }\n"
        '    mesh "ind.im"\n'
        "  }\n"
        "}\n"
    )
    assert ordered(text) == (
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "ind.im"\n'
        "\n"
        "    effects\n"
        "    {\n"
        '      effect "a"\n'
        "\n"
        "      effect-mesh\n"
        "      {\n"
        '        mesh "e.im"\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def test_a_container_written_on_one_line_is_a_value_down_there_as_well():
    text = (
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        "    kofi { a 1 }\n"
        "    effects\n"
        "    {\n"
        "    }\n"
        '    mesh "ind.im"\n'
        "  }\n"
        "}\n"
    )
    assert ordered(text) == (
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        "    kofi { a 1 }\n"
        '    mesh "ind.im"\n'
        "\n"
        "    effects\n"
        "    {\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def test_the_inside_of_a_container_is_put_right_in_the_stretch_moving_it():
    """A container that moves takes its new inside along in the same edit."""
    text = (
        'kind "vnd.trainsim.asset"\n'
        "table\n"
        "{\n"
        "  sub\n"
        "  {\n"
        "  }\n"
        "  value 1\n"
        "}\n"
        'kuid <kuid:2:100>\n'
    )
    result = tweaks.reorder_tags(text)

    assert [text[one.start : one.end] for one in result.rewrites] == [text[:-1]]
    assert result.text == (
        'kuid <kuid:2:100>\n'
        'kind "vnd.trainsim.asset"\n'
        "\n"
        "table\n"
        "{\n"
        "  value 1\n"
        "\n"
        "  sub\n"
        "  {\n"
        "  }\n"
        "}\n"
    )


def test_a_container_that_stands_still_gets_a_stretch_of_its_own():
    """Two short edits rather than one long one covering the whole file."""
    text = (
        "table\n"
        "{\n"
        "  sub\n"
        "  {\n"
        "    x 1\n"
        "  }\n"
        "  value 1\n"
        "}\n"
        "obsolete-table\n"
        "{\n}\n"
        "kuid-table\n"
        "{\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert [text[one.start : one.end] for one in result.rewrites] == [
        # the two containers that change place at the top of the file
        "obsolete-table\n{\n}\nkuid-table\n{\n}",
        # and the tags inside the container that stands still
        "  sub\n  {\n    x 1\n  }\n  value 1",
        # the blank line between them, where nothing moved at all
        "",
    ]
    assert result.text == (
        "table\n"
        "{\n"
        "  value 1\n"
        "\n"
        "  sub\n"
        "  {\n"
        "    x 1\n"
        "  }\n"
        "}\n"
        "\n"
        "kuid-table\n"
        "{\n}\n"
        "\n"
        "obsolete-table\n"
        "{\n}\n"
    )


def test_the_tags_moved_inside_a_container_are_named_as_well():
    text = (
        "table\n"
        "{\n"
        "  sub\n"
        "  {\n"
        "  }\n"
        "  value 1\n"
        "}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.status == "Reordered 2 tags, added 1 blank line"
    assert result.summary() == (
        "Reordered 2 tags, added 1 blank line:\n"
        "\n"
        "  value moved from line 6 to line 3\n"
        "  sub moved from line 3 to line 5\n"
        "  a blank line went above the sub on line 5"
    )


def test_a_container_already_holding_its_values_first_is_left_as_it_is():
    text = (
        'kuid <kuid:2:100>\n'
        'kind "interior"\n'
        "\n"
        "table\n"
        "{\n"
        "  value 1\n"
        "\n"
        "  sub\n"
        "  {\n"
        "  }\n"
        "}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.rewrites == ()
    assert result.moves == ()
    assert result.gaps == ()
    assert result.status == "Nothing was reordered"


# ---------------------------------------------------------------------------
# a file whose tags cannot be told apart
# ---------------------------------------------------------------------------
def test_a_stray_brace_at_the_top_leaves_everything_alone():
    text = 'kuid <kuid:2:100>\n}\nusername "n"\n'
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.rewrites == ()
    assert result.warning
    assert result.status == "The tags cannot be reordered"
    assert "line 2 holds '}', which is not a tag" in order_said(text)


def test_a_container_that_is_never_closed_leaves_everything_alone():
    text = 'kuid <kuid:2:100>\nusername "n"\nmesh-table\n{\n  default\n  {\n'
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.warning
    assert "the mesh-table on line 3 opens a container that is never closed" in (
        order_said(text)
    )


def test_a_value_that_is_never_closed_leaves_everything_alone():
    text = 'kuid <kuid:2:100>\nusername "n"\ndescription "left open\n'
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.warning
    assert "the description on line 3 holds a quoted value that is never closed" in (
        order_said(text)
    )


# ---------------------------------------------------------------------------
# what is said about it
# ---------------------------------------------------------------------------
def test_the_summary_says_which_tags_moved_and_to_which_line():
    text = 'kind "interior"\nkuid <kuid:2:100>\nusername "n"\n'
    result = tweaks.reorder_tags(text)

    assert result.status == "Reordered 3 tags"
    assert result.summary() == (
        "Reordered 3 tags:\n"
        "\n"
        "  kuid moved from line 2 to line 1\n"
        "  username moved from line 3 to line 2\n"
        "  kind moved from line 1 to line 3"
    )
    assert not result.warning


def test_the_lines_named_are_the_ones_the_tags_are_on_afterwards():
    text = 'kind "interior"\nkuid <kuid:2:100>\nusername "n"\n'
    result = tweaks.reorder_tags(text)
    lines = result.text.split("\n")

    for move in result.moves:
        assert lines[move.to_line - 1].startswith(move.tag)


def test_only_the_tags_that_move_are_rewritten():
    """Above the first one out of place the file is already in order."""
    text = (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        'author "nobody"\n'
        "mesh-table\n{\n  a 1\n}\n"
        'kind "interior"\n'
    )
    result = tweaks.reorder_tags(text)

    assert [text[one.start : one.end] for one in result.rewrites] == [
        'mesh-table\n{\n  a 1\n}\nkind "interior"'
    ]
    assert result.text == (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        'author "nobody"\n'
        'kind "interior"\n'
        "\n"
        "mesh-table\n{\n  a 1\n}\n"
    )


def test_a_file_already_in_the_asked_for_order_is_left_as_it_is():
    text = (
        'kuid <kuid:2:100>\n'
        'username "n"\n'
        'kind "interior"\n'
        "\n"
        "mesh-table\n{\n  a 1\n}\n"
        "\n"
        "kuid-table\n{\n}\n"
        "\n"
        "obsolete-table\n{\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.rewrites == ()
    assert result.moves == ()
    assert result.gaps == ()
    assert not result.warning
    assert result.status == "Nothing was reordered"
    assert result.summary().startswith("Nothing was reordered")


# ---------------------------------------------------------------------------
# a blank line beside every container
# ---------------------------------------------------------------------------
def test_blank_lines_go_above_a_container_and_under_it_even_when_no_tag_moves():
    text = (
        'kuid <kuid:2:100>\n'
        'kind "interior"\n'
        "mesh-table\n{\n  a 1\n}\n"
        "kuid-table\n{\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.moves == ()
    assert result.status == "Added 2 blank lines"
    assert not result.warning
    assert result.text == (
        'kuid <kuid:2:100>\n'
        'kind "interior"\n'
        "\n"
        "mesh-table\n{\n  a 1\n}\n"
        "\n"
        "kuid-table\n{\n}\n"
    )
    assert [(one.tag, one.line, one.above) for one in result.gaps] == [
        ("mesh-table", 4, True),
        ("mesh-table", 7, False),
    ]


def test_the_blank_lines_go_beside_the_containers_at_every_depth():
    """The subtags of a container are separated from each other as well."""
    text = (
        'kind "scenery"\n'
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "ind.im"\n'
        "    effects\n"
        "    {\n"
        "    }\n"
        "    other\n"
        "    {\n"
        "      a 1\n"
        "    }\n"
        "  }\n"
        "}\n"
        "kuid-table\n{\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == (
        'kind "scenery"\n'
        "\n"
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "ind.im"\n'
        "\n"
        "    effects\n"
        "    {\n"
        "    }\n"
        "\n"
        "    other\n"
        "    {\n"
        "      a 1\n"
        "    }\n"
        "  }\n"
        "}\n"
        "\n"
        "kuid-table\n{\n}\n"
    )
    assert [(one.tag, one.above) for one in result.gaps] == [
        ("mesh-table", True),
        ("effects", True),
        ("effects", False),
        ("mesh-table", False),
    ]
    assert result.status == "Added 4 blank lines"


def test_no_blank_line_goes_beside_a_brace_or_at_the_end_of_the_file():
    """A gap under the last subtag of a container would part it from its parent."""
    text = (
        'kind "scenery"\n'
        "\n"
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        '    mesh "ind.im"\n'
        "  }\n"
        "}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.gaps == ()
    assert result.status == "Nothing was reordered"


def test_the_first_subtag_of_a_container_is_not_set_off_from_its_opening_brace():
    """A blank line below a { would separate a container from what it opens."""
    text = (
        'kind "scenery"\n'
        "mesh-table {\n"
        '  mesh "ind.im"\n'
        "  effects {\n"
        "  }\n"
        "}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == (
        'kind "scenery"\n'
        "\n"
        "mesh-table {\n"
        '  mesh "ind.im"\n'
        "\n"
        "  effects {\n"
        "  }\n"
        "}\n"
    )
    assert [(one.tag, one.above) for one in result.gaps] == [
        ("mesh-table", True),
        ("effects", True),
    ]


def test_a_blank_line_that_is_already_there_is_left_as_it_is():
    """The tweak opens out a container that had no gap; it does not count them."""
    text = (
        'kind "interior"\n'
        "\n"
        "mesh-table\n{\n}\n"
        "\n"
        "kuid-table\n{\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.gaps == ()
    assert result.shut == ()


def test_a_second_blank_line_where_one_stands_comes_out():
    """One gap between two containers says the same thing once as the next one."""
    text = (
        'kind "interior"\n'
        "\n"
        "mesh-table\n{\n}\n"
        "\n"
        "\n"
        "kuid-table\n{\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == (
        'kind "interior"\n'
        "\n"
        "mesh-table\n{\n}\n"
        "\n"
        "kuid-table\n{\n}\n"
    )
    assert result.shut == (6,)
    assert result.status == "Removed 1 blank line"
    assert "a blank line came out under line 6" in result.summary()
    assert tweaks.reorder_tags(result.text).rewrites == ()


def test_a_blank_line_between_two_tags_comes_out():
    """A blank line parts a container from what stands beside it and nothing else."""
    text = (
        "kuid <kuid:2:100>\n"
        "\n"
        'kind "interior"\n'
        "\n"
        'author "nobody"\n'
    )
    result = tweaks.reorder_tags(text)

    assert result.text == (
        "kuid <kuid:2:100>\n"
        'kind "interior"\n'
        'author "nobody"\n'
    )
    assert result.shut == (1, 2)
    assert result.moves == ()
    assert tweaks.reorder_tags(result.text).rewrites == ()


def test_a_blank_line_beside_a_brace_comes_out():
    """A blank line written inside a container parts it from its own braces."""
    text = (
        "kuid <kuid:2:100>\n"
        "\n"
        "mesh-table\n"
        "{\n"
        "\n"
        "  a 1\n"
        "  b 2\n"
        "\n"
        "}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == (
        "kuid <kuid:2:100>\n"
        "\n"
        "mesh-table\n"
        "{\n"
        "  a 1\n"
        "  b 2\n"
        "}\n"
    )
    assert result.shut == (4, 6)
    assert tweaks.reorder_tags(result.text).rewrites == ()


def test_a_blank_line_inside_a_value_is_left_alone():
    """A value written over several lines keeps the blank lines written in it."""
    text = (
        "kuid <kuid:2:100>\n"
        'license "- one\n'
        "\n"
        '- two"\n'
        'author "nobody"\n'
    )
    result = tweaks.reorder_tags(text)

    assert result.text == text
    assert result.shut == ()


def test_a_container_that_stays_where_it_is_still_gets_its_blank_lines():
    """The container above the tags that moved is not left out of the change."""
    text = (
        'kuid <kuid:2:100>\n'
        "mesh-table\n{\n  a 1\n}\n"
        "obsolete-table\n{\n  b 2\n}\n"
        "kuid-table\n{\n  c 3\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == (
        'kuid <kuid:2:100>\n'
        "\n"
        "mesh-table\n{\n  a 1\n}\n"
        "\n"
        "kuid-table\n{\n  c 3\n}\n"
        "\n"
        "obsolete-table\n{\n  b 2\n}\n"
    )
    assert [(one.tag, one.line) for one in result.gaps] == [
        ("mesh-table", 3),
        ("mesh-table", 6),
        ("kuid-table", 11),
    ]


def test_a_tag_whose_braces_close_on_the_line_they_opened_is_a_value():
    """One line, one value: the codec reads no container, so no gap goes beside it."""
    text = (
        'kind "x"\n'
        "table-a { x 1 }\n"
        'author "nobody"\n'
        "mesh-table\n{\n  a 1\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.text == (
        'kind "x"\n'
        "table-a { x 1 }\n"
        'author "nobody"\n'
        "\n"
        "mesh-table\n{\n  a 1\n}\n"
    )
    assert result.moves == ()
    assert [(one.tag, one.above) for one in result.gaps] == [("mesh-table", True)]


def test_the_blank_lines_named_are_the_ones_beside_the_containers():
    text = (
        'kind "scenery"\n'
        "mesh-table\n{\n  default\n{\n  mesh \"ind.im\"\n  }\n}\n"
        "kuid-table\n{\n}\n"
        'author "nobody"\n'
    )
    result = tweaks.reorder_tags(text)
    lines = result.text.split("\n")

    assert any(one.above for one in result.gaps)
    assert any(not one.above for one in result.gaps)
    for gap in result.gaps:
        if gap.above:
            assert lines[gap.line - 1].strip() == gap.tag
            assert lines[gap.line - 2] == ""
        else:
            assert lines[gap.line - 1].strip() == "}"
            assert lines[gap.line] == ""


def test_the_summary_says_which_containers_got_a_blank_line():
    text = (
        'kind "interior"\n'
        'kuid <kuid:2:100>\n'
        "mesh-table\n{\n  a 1\n}\n"
        "kuid-table\n{\n}\n"
    )
    result = tweaks.reorder_tags(text)

    assert result.status == "Reordered 2 tags, added 2 blank lines"
    assert result.summary() == (
        "Reordered 2 tags, added 2 blank lines:\n"
        "\n"
        "  kuid moved from line 2 to line 1\n"
        "  kind moved from line 1 to line 2\n"
        "  a blank line went above the mesh-table on line 4\n"
        "  a blank line went under the mesh-table on line 7"
    )


# ---------------------------------------------------------------------------
# the real config files
# ---------------------------------------------------------------------------
def test_the_values_of_a_real_asset_come_before_its_sub_containers_at_every_depth():
    for name in ("config1.txt", "config2.txt", "config3.txt", "obsolete_config.txt"):
        text = read_text_file(SAMPLES / name)
        result = tweaks.reorder_tags(text)

        assert not out_of_order(parse_text(result.text)), name


def test_reordering_loses_no_tag_and_needs_no_second_press():
    for name in ("config1.txt", "config2.txt", "config3.txt", "obsolete_config.txt"):
        text = read_text_file(SAMPLES / name)
        once = tweaks.reorder_tags(text)
        twice = tweaks.reorder_tags(once.text)

        assert not once.warning, name
        assert held(parse_text(once.text)) == held(parse_text(text)), name
        assert twice.text == once.text, name
        assert twice.status == "Nothing was reordered", name


def test_a_real_asset_ends_up_set_off_on_both_sides_of_every_container():
    for name in ("config1.txt", "config2.txt", "config3.txt", "obsolete_config.txt"):
        text = read_text_file(SAMPLES / name)
        left = the_gaps_left(tweaks.reorder_tags(text).text)

        assert not left, f"{name}: line {left}"


def test_a_real_asset_ends_up_with_no_blank_line_that_is_not_a_container_gap():
    for name in ("config1.txt", "config2.txt", "config3.txt", "obsolete_config.txt"):
        text = read_text_file(SAMPLES / name)
        stray = the_blanks_in_the_way(tweaks.reorder_tags(text).text)

        assert not stray, f"{name}: line {stray}"


def test_the_real_config_files_are_already_set_off_wherever_a_container_stands():
    # the text files come out of the decoder, which lays a file out this way
    # before anybody touches it, so the reorder is never asked for a gap
    for name in ("config1.txt", "config2.txt", "config3.txt", "obsolete_config.txt"):
        left = the_gaps_left(read_text_file(SAMPLES / name))

        assert not left, f"{name}: line {left}"


def test_a_decoded_file_sets_its_containers_off_at_every_depth():
    for name in ("config1.chump", "config2.chump", "config3.chump", "semnal.chump"):
        text = render_text(load_chump(SAMPLES / name))
        left = the_gaps_left(text)

        assert not left, f"{name}: line {left}"


def test_a_decoded_file_writes_no_blank_line_that_is_not_a_container_gap():
    for name in ("config1.chump", "config2.chump", "config3.chump", "semnal.chump"):
        text = render_text(load_chump(SAMPLES / name))
        stray = the_blanks_in_the_way(text)

        assert not stray, f"{name}: line {stray}"


def test_a_decoded_file_needs_no_blank_line_and_no_second_press():
    for name in ("config1.chump", "semnal.chump"):
        text = render_text(load_chump(SAMPLES / name))
        once = tweaks.reorder_tags(text)
        twice = tweaks.reorder_tags(once.text)

        assert not once.warning, name
        assert not once.gaps, name
        assert held(parse_text(once.text)) == held(parse_text(text)), name
        assert not the_gaps_left(once.text), name
        assert twice.text == once.text, name
        assert twice.status == "Nothing was reordered", name


def test_no_tweak_writes_text_the_save_would_refuse():
    # adding a mesh-table and folding a run of numbered tags are exactly where a
    # second tag of one name could come from, and both tweaks turn that down;
    # nothing they hand over may fail the check a write is guarded by
    for name in ("config1.txt", "config2.txt", "config3.txt", "obsolete_config.txt"):
        text = read_text_file(SAMPLES / name)
        for tweak in (
            tweaks.convert_obsolete_lists,
            tweaks.remove_language_tags,
            tweaks.convert_asset_filename_to_mesh_table,
            tweaks.reorder_tags,
        ):
            check_text(tweak(text).text)


def test_a_real_asset_ends_up_in_the_asked_for_order():
    text = read_text_file(SAMPLES / "config2.txt")
    result = tweaks.reorder_tags(text)
    before, after = parse_text(text).tags, parse_text(result.text).tags

    assert [tag.name for tag in after[:2]] == ["kuid", "username"]
    assert [tag.name for tag in after[-2:]] == ["kuid-table", "obsolete-table"]

    # every tag holding one value comes before every container, in the order the
    # file had them, with the two that belong at the top moved up
    values = [tag.name for tag in before if not tag.is_container]
    assert [tag.name for tag in after if not tag.is_container] == [
        "kuid",
        "username",
    ] + [name for name in values if name not in ("kuid", "username")]

    first_container = next(at for at, tag in enumerate(after) if tag.is_container)
    assert all(not tag.is_container for tag in after[:first_container])
    assert all(tag.is_container for tag in after[first_container:])
    assert not any(tag.is_container for tag in after[:-2])

    # the containers themselves kept what they hold
    assert held(parse_text(result.text)) == held(parse_text(text))
