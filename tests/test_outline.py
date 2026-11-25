"""Tests for ``outline.py``: which containers a text holds and which line each is on.

No Qt here, and no window: the answer is a list of records, so these tests read
the samples from ``test_files`` and hand-written text - sound, mid-edit and
plainly broken - and check the names, the depth and the line numbers that come
back.  The line numbers are the ones that matter most: they have to agree with
the numbers down the left of the editor, which count from 1.
"""

from __future__ import annotations

from pathlib import Path

from chumpeditor.chump import read_text_file
from chumpeditor.outline import Container, containers

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
