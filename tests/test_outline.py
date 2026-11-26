"""Tests for ``outline.py``: which containers a text holds and which line each is on.

No Qt here, and no window: the answer is a list of records, so these tests read
the samples from ``test_files`` and hand-written text - sound, mid-edit and
plainly broken - and check the names, the depth and the line numbers that come
back.  The line numbers are the ones that matter most: they have to agree with
the numbers down the left of the editor, which count from 1.

What taking one of those containers out of the text would leave behind is
answered by the same file, and is tested here for the same reason: it is a
question about lines and braces, and no window is needed to get it wrong.
"""

from __future__ import annotations

from pathlib import Path

from chumpeditor.chump import read_text_file
from chumpeditor.outline import Container, containers, the_container_block

SAMPLES = Path(__file__).parent / "test_files"


def sample(name: str) -> str:
    return read_text_file(SAMPLES / name)


def spelled(text: str) -> list[tuple[str, int, int]]:
    """Every container as (name, level, line), which is what these tests compare."""
    return [(one.name, one.level, one.line) for one in containers(text)]


# ---------------------------------------------------------------------------
# the three ways a container is written
# ---------------------------------------------------------------------------
def test_a_name_with_its_brace_on_the_line_below():
    """The way the expander writes a container, and the way most config files do."""
    assert spelled(
        "kuid-table\n"
        "{\n"
        "}\n"
    ) == [("kuid-table", 0, 1)]


def test_a_name_with_its_brace_behind_it():
    """The way a hand-written file writes one: ``kuid-table {``."""
    assert spelled("kuid-table {\n}\n") == [("kuid-table", 0, 1)]


def test_an_empty_container_still_counts_as_one():
    """An empty table is a container; it just holds nothing."""
    assert spelled("obsolete-table\n{\n}\n") == [("obsolete-table", 0, 1)]


def test_a_name_holding_spaces_up_to_the_brace_it_opens():
    """A container's name is the whole line its brace opens, so a container named
    after a file name takes one row of the tree and is named as it is written."""
    assert spelled(
        "screenshots\n"
        "{\n"
        "  2018-12-15 162811.jpg\n"
        "  {\n"
        '    tags                                "Trainz Railroad Simulator 2019"\n'
        "  }\n"
        "}\n"
    ) == [("screenshots", 0, 1), ("2018-12-15 162811.jpg", 1, 3)]
    assert spelled("2018-12-15 162811.jpg {\n}\n") == [("2018-12-15 162811.jpg", 0, 1)]


def test_a_brace_closed_on_the_line_it_opened_is_a_value_not_a_container():
    """``name { ... }`` on one line is what the codec reads as a value, so the
    tree leaves it out: there is nothing to open up under it."""
    assert spelled("obsolete-table {}\nkuid-table { }\n") == []


def test_a_tag_holding_one_value_gets_no_row():
    """The single line tags are what the tree is asked to leave out."""
    text = (
        'kind                                    "interior"\n'
        "kuid                                    <kuid:79373:50023>\n"
        "trainz-build                            1.3\n"
        "camera                                  -1.058,0.522,0.887\n"
        "organisation                            \n"
    )
    assert containers(text) == []


# ---------------------------------------------------------------------------
# nesting
# ---------------------------------------------------------------------------
def test_sub_containers_stand_under_their_own():
    text = (
        "mesh-table\n"          # 1
        "{\n"                   # 2
        "  default\n"           # 3
        "  {\n"                 # 4
        '    mesh                                "ind.im"\n'  # 5
        "\n"                   # 6
        "    effects\n"         # 7
        "    {\n"               # 8
        "    }\n"               # 9
        "  }\n"                 # 10
        "}\n"                   # 11
    )
    assert spelled(text) == [
        ("mesh-table", 0, 1),
        ("default", 1, 3),
        ("effects", 2, 7),
    ]


def test_the_list_is_in_tree_order():
    """A container comes before what is written inside it, so a flat list can be
    turned into rows by walking down the levels."""
    text = (
        "table\n"      # 1
        "{\n"
        "  one\n"      # 3
        "  {\n"
        "  }\n"
        "  two\n"      # 6
        "  {\n"
        "    deep\n"   # 8
        "    {\n"
        "    }\n"
        "  }\n"
        "}\n"
        "after\n"      # 13
        "{\n"
        "}\n"
    )
    assert [one.name for one in containers(text)] == [
        "table", "one", "two", "deep", "after"
    ]


def test_the_path_names_where_a_container_stands():
    text = "mesh-table\n{\n  default\n  {\n    effects\n    {\n    }\n  }\n}\n"
    assert [one.path for one in containers(text)] == [
        ("mesh-table",),
        ("mesh-table", "default"),
        ("mesh-table", "default", "effects"),
    ]


def test_two_containers_of_one_name_are_two_rows():
    """A name written twice at the top level is something a file being edited has
    all the time, and both of them are worth a row."""
    text = "table\n{\n}\ntable\n{\n}\n"
    assert spelled(text) == [("table", 0, 1), ("table", 0, 4)]


def test_the_same_name_down_two_containers_is_not_the_same_row():
    text = (
        "outer\n"     # 1
        "{\n"
        "  inner\n"   # 3
        "  {\n"
        "  }\n"
        "}\n"
        "inner\n"     # 7
        "{\n"
        "}\n"
    )
    assert [one.path for one in containers(text)] == [
        ("outer",), ("outer", "inner"), ("inner",)
    ]


# ---------------------------------------------------------------------------
# values running over several lines
# ---------------------------------------------------------------------------
def test_a_line_inside_a_long_value_is_not_read_as_a_tag():
    """A license string spans lines, and its prose is not tags."""
    text = (
        "license                                 \"Any modification of the model\n"
        "or textures is prohibited. mesh-table\n"
        "kuid-table {\n"
        "\"\n"
        "kuid-table\n"
        "{\n"
        "}\n"
    )
    assert spelled(text) == [("kuid-table", 0, 5)]


def test_a_blank_line_inside_a_value_is_part_of_the_value():
    text = (
        "description                             \"one\n"
        "\n"
        "two\"\n"
        "table\n"
        "{\n"
        "}\n"
    )
    assert spelled(text) == [("table", 0, 4)]


# ---------------------------------------------------------------------------
# text that is broken
# ---------------------------------------------------------------------------
def test_a_container_that_is_never_closed_keeps_its_row():
    """Half-way through an edit the file does not balance; the tree still says
    what is there rather than stopping."""
    text = "mesh-table\n{\n  default\n  {\n"
    assert spelled(text) == [("mesh-table", 0, 1), ("default", 1, 3)]


def test_a_closing_brace_ends_a_level_even_when_its_name_was_unreadable():
    """An extra ``}`` brings the level back down, so what follows it is not filed
    under a container that closed three lines ago."""
    text = (
        "one\n"     # 1
        "{\n"
        "  two\n"   # 3
        "  {\n"
        "}\n"       # 5 closes two, and takes one with it as the codec reads it
        "}\n"       # 6 closes one again - nothing open, but the level comes down
        "three\n"   # 7
        "{\n"
        "}\n"
    )
    assert spelled(text) == [
        ("one", 0, 1), ("two", 1, 3), ("three", 0, 7)
    ]


def test_a_value_that_is_never_closed_does_not_stop_the_walk():
    """A missing closing quote is a fault the Syntax check says about; the tree
    carries on reading below it."""
    text = (
        'kind                                    "interior\n'   # 1, never closed
        "table\n"                                              # 2
        "{\n"
        "}\n"
    )
    assert spelled(text) == [("table", 0, 2)]


def test_a_line_that_is_not_a_tag_at_all_is_passed_over():
    text = (
        "# a note someone left in the file\n"
        "table\n"     # 2
        "{\n"
        "}\n"
    )
    assert spelled(text) == [("table", 0, 2)]


def test_a_stray_brace_with_no_name_before_it_harms_nothing():
    text = "{\ntable\n{\n}\n"
    assert spelled(text) == [("table", 0, 2)]


# ---------------------------------------------------------------------------
# nothing at all
# ---------------------------------------------------------------------------
def test_an_empty_text_holds_no_containers():
    assert containers("") == []
    assert containers("\n\n") == []


def test_the_records_are_equal_when_they_say_the_same_thing():
    assert Container("table", 0, 3, ("table",)) == Container("table", 0, 3, ("table",))
    assert str(Container("mesh-table", 1, 3, ("mesh-table", "default"))) == "mesh-table/default"


# ---------------------------------------------------------------------------
# the samples on disk
# ---------------------------------------------------------------------------
def test_the_second_sample_shows_its_two_tables():
    """The values in between are single line tags and get no row; the two tables
    stand at the top of the file."""
    assert spelled(sample("config2.txt")) == [
        ("obsolete-table", 0, 14),
        ("kuid-table", 0, 28),
    ]


def test_the_third_sample_shows_its_mesh_table_three_deep():
    """mesh-table holds default, and default holds effects - all of them opened."""
    assert spelled(sample("config3.txt")) == [
        ("mesh-table", 0, 8),
        ("default", 1, 10),
        ("effects", 2, 15),
        ("kuid-table", 0, 36),
    ]


def test_the_obsolete_sample_holds_one_table_and_nothing_else():
    """Twenty-odd translations and a license written over two lines are values."""
    assert spelled(sample("obsolete_config.txt")) == [("kuid-table", 0, 51)]


def test_a_container_is_found_on_the_line_the_editor_numbers_it():
    """The number in the tree and the number down the left of the text have to
    agree, or choosing a row puts the caret in the wrong place."""
    text = sample("config3.txt")
    lines = text.replace("\r\n", "\n").split("\n")
    for one in containers(text):
        assert lines[one.line - 1].strip() == one.name


# ---------------------------------------------------------------------------
# taking one container out of the text
# ---------------------------------------------------------------------------
def cut(text: str, line: int) -> str:
    """The text with the container whose name stands at ``line`` taken out of it."""
    answer = the_container_block(text, line)
    if not answer.rewrites:
        return text
    one = answer.rewrites[0]
    return text[: one.start] + one.text + text[one.end :]


def test_a_container_takes_everything_written_inside_it():
    """The block runs to the container's own closing brace, so whatever is nested
    in it goes with it - which is what a right click on ``mesh-table`` asks for."""
    assert cut(
        "kind                                    \"interior\"\n"
        "mesh-table\n"
        "{\n"
        "  default\n"
        "  {\n"
        "    mesh                                \"ind.im\"\n"
        "  }\n"
        "}\n"
        "kuid-table\n"
        "{\n"
        "}\n",
        2,
    ) == (
        "kind                                    \"interior\"\n"
        "kuid-table\n"
        "{\n"
        "}\n"
    )


def test_a_container_takes_its_own_closing_brace_and_leaves_no_blank_line():
    """The line ending goes with the block, so what stood under it comes up to
    where the name stood rather than leaving a gap behind."""
    assert cut("table\n{\n  a\n}\nlast\n", 1) == "last\n"


def test_a_container_written_whole_on_one_line_is_taken_out_with_it():
    """``obsolete-table {}`` is what the codec reads as a value rather than a
    container, so no row stands for it and there is nothing to take out."""
    text = "kind \"a\"\nobsolete-table {}\n"
    assert containers(text) == []
    answer = the_container_block(text, 2)
    assert not answer.rewrites
    assert not answer.warning


def test_the_line_is_counted_as_the_editor_counts_it():
    """``Container.line``, the numbers down the left of the text and this answer
    all count from 1, so a row can hand over the number it carries."""
    text = "kind \"a\"\nmesh-table\n{\n  default\n  {\n  }\n}\nlast\n"
    for one in containers(text):
        answer = the_container_block(text, one.line)
        assert len(answer.rewrites) == 1
        assert answer.status == (
            f"deleted the {one.name!r} container and what is written in it"
        )


def test_only_a_line_holding_a_container_has_a_block():
    """Every line of a sound text gets an answer, and only the lines ``containers``
    writes a row for get a block: no row stands for a value or for a brace."""
    text = "kind \"a\"\nmesh-table\n{\n  default\n  {\n  }\n}\nlast\n"
    rows = {one.line for one in containers(text)}
    lines = text.replace("\r\n", "\n").split("\n")
    for where in range(1, len(lines)):
        answer = the_container_block(text, where)
        assert bool(answer.rewrites) == (where in rows), where


def test_a_tag_holding_a_value_rather_than_a_container_says_so():
    """No row stands for either of them, so this can only be reached by a number
    that has moved since the rows were written out; the text is left alone."""
    for text, line, said in (
        ('kind "a"\nlast\n', 1, "does not hold the name of a container"),
        ("table\n{   \n}\n", 2, "no tag written on that line"),
        ("table\n{\n}\n", 2, "no tag written on that line"),
        ("table\n{\n}\n", 3, "no tag written on that line"),
    ):
        answer = the_container_block(text, line)
        assert not answer.rewrites
        assert not answer.warning
        assert said in answer.status


def test_a_block_at_the_end_of_the_text_takes_the_last_line_ending_with_it():
    """There is no line after it to stand at; taking that ending leaves one fewer
    empty line rather than adding one."""
    assert cut("table\n{\n  a\n}\n", 1) == ""


def test_a_closing_brace_is_no_block_of_its_own():
    """No row is ever written for one, and the line under a container answers
    nothing about what to delete."""
    answer = the_container_block("table\n{\n  a\n}\n", 4)
    assert not answer.rewrites
    assert not answer.warning


def test_a_line_holding_nothing_is_no_block():
    answer = the_container_block("table\n{\n\n}\n", 3)
    assert not answer.rewrites
    assert not answer.warning


def test_a_line_beyond_the_end_of_the_text_is_no_block():
    """A row of a tree written out before the text shrank is not a promise that
    there is anything at that number now."""
    answer = the_container_block("table\n{\n}\n", 9)
    assert not answer.rewrites
    assert not answer.warning


def test_a_container_that_never_closes_is_left_alone():
    """Where it should have ended has no answer, and guessing one would take the
    rest of the file with it; that is worth more than a line in the status bar."""
    text = "kind \"a\"\nmesh-table\n{\n  default\n  {\n"
    for line in (2, 4):
        answer = the_container_block(text, line)
        assert not answer.rewrites
        assert answer.warning
        assert "never closed" in answer.status


def test_the_line_endings_are_left_as_the_file_was_written():
    """A file written with CRLF is not turned into one written with LF by a delete
    that only wanted one container out of it."""
    assert cut("table\r\n{\r\n  a\r\n}\r\nlast\r\n", 1) == "last\r\n"


def test_a_name_written_with_spaces_is_taken_out_whole():
    """The brace says where the name ends, so one of the screenshot containers is
    one name and one block - and the row that names it carries that whole name."""
    text = "screenshots\n{\n  2018-12-15 162811.jpg\n  {\n  }\n}\n"
    assert spelled(text) == [("screenshots", 0, 1), ("2018-12-15 162811.jpg", 1, 3)]
    assert cut(text, 3) == "screenshots\n{\n}\n"
    assert the_container_block(text, 1).rewrites


def test_a_stray_closing_brace_does_not_run_the_block_on():
    """The block stops at the brace that closes what the name opened, however many
    braces are written further down."""
    text = "one\n{   \n  two\n  {\n}\n}\nthree\n{\n}\n"
    assert cut(text, 1) == "three\n{\n}\n"
    assert cut(text, 3) == "one\n{   \n}\nthree\n{\n}\n"


def test_a_value_running_over_lines_holds_braces_of_no_account():
    """A license written over half a dozen lines opens and closes braces that are
    only prose; the block is still the container's own."""
    text = (
        "table\n"
        "{\n"
        '  license\n'
        '  "{\n'
        "    not a tag\n"
        '  }"\n'
        "  inner\n"
        "  {\n"
        "    a\n"
        "  }\n"
        "}\n"
    )
    assert spelled(text) == [("table", 0, 1), ("inner", 1, 7)]
    assert cut(text, 7) == 'table\n{\n  license\n  "{\n    not a tag\n  }"\n}\n'
    assert cut(text, 1) == ""


def test_the_blank_line_above_a_container_goes_with_it():
    """The gap over a container is there to set it off from what stands beside it.
    Once the container is gone the gap sets nothing off, and what is left is a hole:
    two blank lines parting ``mesh`` from ``kuid``, where one container used to stand."""
    text = (
        "table\n"
        "{\n"
        '  mesh                                "ro_4.im"\n'
        "\n"
        "  effects\n"
        "  {\n"
        "  }\n"
        "\n"
        "  kuid\n"
        "  {\n"
        "  }\n"
        "}\n"
    )
    assert cut(text, 5) == (
        "table\n"
        "{\n"
        '  mesh                                "ro_4.im"\n'
        "\n"
        "  kuid\n"
        "  {\n"
        "  }\n"
        "}\n"
    )


def test_the_gap_over_a_container_is_taken_whole_and_no_further():
    """However many blank lines stand over the name, they are one gap and they all
    go; what is written above the gap stays, and so does the gap under the block."""
    assert cut('kind "a"\n\n\nmesh-table\n{\n}\nlast\n', 4) == 'kind "a"\nlast\n'
    assert cut('kind "a"\n\nmesh-table\n{\n}\n\nlast\n', 3) == 'kind "a"\n\nlast\n'


def test_a_container_opening_the_text_keeps_its_place_at_the_top():
    """There is nothing over its gap for the gap to part, and taking a file's first
    lines because they happen to be blank would move the start of the text."""
    assert cut("\nmesh-table\n{\n}\nlast\n", 2) == "\nlast\n"
    assert cut("mesh-table\n{\n}\nlast\n", 1) == "last\n"


def test_the_gap_is_taken_by_the_block_rather_than_left_behind():
    """One rewrite, and it starts above the name rather than at it - which is what
    lets one Undo take the gap back along with the container."""
    text = 'kind "a"\n\nmesh-table\n{\n}\n'
    answer = the_container_block(text, 3)
    assert len(answer.rewrites) == 1
    start = answer.rewrites[0].start
    assert text[start : start + len("\nmesh-table")] == "\nmesh-table"


def test_a_container_of_a_file_on_disk_is_taken_out_at_its_own_line():
    """The line a row carries and the block that goes with it are answered out of
    the same text a real file is."""
    text = sample("config3.txt")
    one = [item for item in containers(text) if item.name == "mesh-table"][0]
    answer = the_container_block(text, one.line)
    assert len(answer.rewrites) == 1
    rewrite = answer.rewrites[0]
    # the block may begin above the name, at a blank line set aside for it; what is
    # fixed here is that it starts at a line of its own and ends past the closing brace
    assert text[rewrite.start :].startswith(("\r\n", "\n")) or text[
        rewrite.start - 1
    ] in "\r\n"
    name = text.index("mesh-table")
    assert rewrite.start <= name < rewrite.end
    assert text[rewrite.start : rewrite.end].rstrip().endswith("}")
    after = cut(text, one.line)
    assert [item.name for item in containers(after)] == ["kuid-table"]
