"""Tests for the colours that end up on the screen.

``tests/test_theme.py`` and ``tests/test_scan.py`` settle what a theme means;
these check that the meaning reaches a document, line by line and including the
lines that only make sense together, on a light background and on a dark one.
Offscreen, like the rest of the GUI tests, since nothing here needs to be
looked at.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtGui import QColor, QPalette, QTextCursor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from chumpeditor.gui.editor import RichTextEditor  # noqa: E402
from chumpeditor.theme import bundled_theme_path, load_theme, parse_theme  # noqa: E402

#: the colours of the theme that ships, spelled out so a test can say which
#: part of a line it expected rather than which number it saw
PLAIN = "#000000"
TAGS = "#0000ff"
CONTAINERS = "#800000"
OBSOLETE = "#ff0000"
STRING = "#008000"
KUID = "#ff0080"

#: the same theme on a dark background, which is what each of those colours has
#: to become for the text to be readable at all
DARK_PLAIN = "#ffffff"
DARK_TAGS = "#3fd0e0"
DARK_CONTAINERS = "#ff9e64"
DARK_OBSOLETE = "#ff5f5f"
DARK_STRING = "#7ac74f"
DARK_KUID = "#ff6fb0"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qapp) -> RichTextEditor:
    widget = RichTextEditor()
    on_dark(widget, False)  # the light colours, whatever the desktop happens to be
    return widget


def on_dark(widget: RichTextEditor, dark: bool) -> None:
    """Put the editor on a dark background, or take it off one.

    Those two colours are what a dark theme uses and what a light one uses, and
    setting them on the widget is what a theme does to it: the editor picks which
    half of the theme to paint with from the colour behind its own text.
    """
    base, text = ("#2d2d2d", "#ffffff") if dark else ("#ffffff", "#000000")
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Base, QColor(base))
    palette.setColor(QPalette.ColorRole.Text, QColor(text))
    widget.setPalette(palette)


def painted(widget: RichTextEditor) -> list[list[tuple[str, str]]]:
    """The document, line by line, as stretches of text and their colours.

    The colours of a highlighter are not stored in the document - that is what
    keeps undo about the text - so they are read where Qt puts them: the extra
    formats of each line's layout, which are exactly what is painted.

    Every colour the theme knows about shows up here, so a test can ask for
    exactly what a reader would see.
    """
    document = widget.document()
    document.documentLayout().documentSize()  # a line has no layout until it is laid out
    plain = widget.palette().color(QPalette.ColorRole.Text).name()
    lines = []
    for number in range(document.blockCount()):
        paragraph = document.findBlockByNumber(number)
        text = paragraph.text()
        colours = [plain] * len(text)
        for run in paragraph.layout().formats():
            for at in range(run.start, min(run.start + run.length, len(text))):
                colours[at] = run.format.foreground().color().name()
        line: list[list[str]] = []
        for character, colour in zip(text, colours):
            if line and line[-1][1] == colour:
                line[-1][0] += character
            else:
                line.append([character, colour])
        lines.append([(part, colour) for part, colour in line])
    return lines


def shown(widget: RichTextEditor) -> list[list[tuple[str, str]]]:
    """The same, with the numbers replaced by the parts of the theme they came from."""
    named = {
        PLAIN: "plain",
        TAGS: "tags",
        CONTAINERS: "containers",
        OBSOLETE: "obsolete",
        STRING: "string",
        KUID: "kuid",
    }
    return [
        [(text, named.get(colour, colour)) for text, colour in line]
        for line in painted(widget)
    ]


# ---------------------------------------------------------------------------
# the theme that ships with the program
# ---------------------------------------------------------------------------


def test_the_names_of_the_theme_are_coloured_and_the_rest_is_left_plain(editor):
    editor.setPlainText("kind")
    assert shown(editor) == [[("kind", "tags")]]


def test_a_value_in_quotes_is_one_colour_right_across_it(editor):
    editor.setPlainText('kind "cart"')
    assert shown(editor) == [
        [("kind", "tags"), (" ", "plain"), ('"cart"', "string")]
    ]


def test_a_word_inside_quotes_is_part_of_the_value(editor):
    """The theme has a rule for both, and the quotes are the one that counts."""
    editor.setPlainText('name "origin"')
    assert shown(editor) == [
        [("name", "tags"), (" ", "plain"), ('"origin"', "string")]
    ]


def test_a_container_is_a_colour_of_its_own(editor):
    """The brace on the name's own line is what says this name opens one."""
    editor.setPlainText("mesh-table {")
    assert shown(editor) == [[("mesh-table", "containers"), (" {", "plain")]]


def test_a_container_with_the_brace_on_the_line_below_is_the_same_colour(editor):
    """The other way a config.txt writes it, and the only way to know it is to
    read the line below as well."""
    editor.setPlainText("mesh-table\n{")
    assert shown(editor) == [
        [("mesh-table", "containers")],
        [("{", "plain")],
    ]


def test_a_name_with_a_value_and_no_brace_is_a_tag_however_it_is_spelled(editor):
    editor.setPlainText("a-name-nobody-has-mentioned 2.5")
    assert shown(editor) == [
        [("a-name-nobody-has-mentioned", "tags"), (" 2.5", "plain")]
    ]


def test_a_name_with_a_dot_in_it_is_coloured_all_of_a_piece(editor):
    """Only a space separates a name from its value, so the dot of
    junction.forward is part of the name rather than something to stop at."""
    editor.setPlainText("junction.forward 1")
    assert shown(editor) == [[("junction.forward", "tags"), (" 1", "plain")]]


def test_a_tag_named_with_a_kuid_is_coloured_as_a_tag(editor):
    """A kuid table names each asset it holds with a kuid, and a name is coloured
    for being a name: the kuid rule colours a value, never the name before it."""
    editor.setPlainText("<kuid2:66277:35027:1>\nkuid <kuid2:66277:35027:1>")
    assert shown(editor) == [
        [("<kuid2:66277:35027:1>", "tags")],
        [("kuid", "tags"), (" ", "plain"), ("<kuid2:66277:35027:1>", "kuid")],
    ]


def test_a_tag_nobody_uses_any_more_is_marked_however_it_is_numbered(editor):
    """The one list of the shipped theme that still names words, because only a
    word can say that a tag is out of date - and Trainz numbers these as far as
    it likes, so era 9 and icon 3 take one pattern each rather than a line."""
    editor.setPlainText("origin category-era-9 icon3")
    assert shown(editor) == [
        [
            ("origin", "obsolete"),
            (" ", "plain"),
            ("category-era-9", "obsolete"),
            (" ", "plain"),
            ("icon3", "obsolete"),
        ]
    ]


def test_a_word_the_theme_named_outranks_the_sort_of_name_it_is(editor):
    """car15 to car20 are spelled out among the tags nobody uses; the rest of
    the family is a tag like any other."""
    editor.setPlainText("car17\ncar25")
    assert shown(editor) == [[("car17", "obsolete")], [("car25", "tags")]]


def test_a_tag_written_for_a_language_takes_the_colour_of_its_tag(editor):
    editor.setPlainText("icon-texture-ru")
    assert shown(editor) == [[("icon-texture-ru", "obsolete")]]


def test_a_section_in_angle_brackets_is_one_colour(editor):
    editor.setPlainText("kuid <kuid:123:456>")
    assert shown(editor) == [
        [("kuid", "tags"), (" ", "plain"), ("<kuid:123:456>", "kuid")]
    ]


def test_a_value_that_runs_over_several_lines_stays_one_value(editor):
    editor.setPlainText('license "one\ntwo\nthree" end')
    assert shown(editor) == [
        [("license", "tags"), (" ", "plain"), ('"one', "string")],
        [("two", "string")],
        [('three"', "string"), (" end", "plain")],
    ]


def test_nothing_is_coloured_that_the_theme_says_nothing_about(editor):
    editor.setPlainText("nonsense 2.7 { = }")
    assert shown(editor) == [[("nonsense", "tags"), (" 2.7 { = }", "plain")]]


def test_the_colours_are_the_ones_the_shipped_theme_writes(editor):
    theme = load_theme(bundled_theme_path())
    assert theme.styles["tags"].colour == TAGS
    assert theme.styles["delim_str"].colour == STRING


# ---------------------------------------------------------------------------
# typing, and changing the theme
# ---------------------------------------------------------------------------


def test_a_word_typed_in_is_coloured_as_soon_as_it_is_there(editor):
    editor.insertPlainText("kind")
    assert shown(editor) == [[("kind", "tags")]]

    editor.insertPlainText(" cart")
    assert shown(editor) == [[("kind", "tags"), (" cart", "plain")]]


def test_a_brace_typed_below_a_name_colours_the_name_as_a_container(editor):
    """A name is only known to open a container by the brace below it, so the
    name has to change colour when the brace arrives."""
    editor.setPlainText("mesh-table\n")
    assert shown(editor)[0] == [("mesh-table", "tags")]

    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.insertPlainText("{")
    assert shown(editor)[0] == [("mesh-table", "containers")]


def test_taking_the_brace_away_makes_the_name_a_tag_again(editor):
    editor.setPlainText("mesh-table\n{")
    assert shown(editor)[0] == [("mesh-table", "containers")]

    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
    cursor.deleteChar()
    editor.setTextCursor(cursor)
    assert shown(editor)[0] == [("mesh-table", "tags")]


def test_typing_on_a_line_recolours_only_that_line(editor):
    editor.setPlainText('license "one')
    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.insertPlainText("two")
    assert shown(editor) == [
        [("license", "tags"), (" ", "plain"), ('"onetwo', "string")]
    ]


def test_a_different_theme_recolours_what_is_already_there(editor):
    editor.setPlainText("kind")
    editor.set_theme(
        parse_theme(
            {
                "name": "green",
                "styles": {"default": "#101010", "words": "#00ff00"},
                "keywords": [{"style": "words", "words": ["kind"]}],
            }
        )
    )
    assert painted(editor) == [[("kind", "#00ff00")]]


def test_a_theme_with_only_plain_text_leaves_the_words_alone(editor):
    editor.setPlainText("kind")
    editor.set_theme(parse_theme({"styles": {"default": "#010203"}}))
    assert painted(editor) == [[("kind", "#010203")]]


def test_a_theme_of_your_own_can_be_the_one_the_editor_starts_with(qapp):
    theme = parse_theme(
        {"name": "yours", "styles": {"default": "#000000", "words": "#123456"},
         "keywords": [{"style": "words", "words": ["kind"]}]}
    )
    widget = RichTextEditor(theme=theme)
    widget.setPlainText("kind kind")
    assert painted(widget) == [[("kind", "#123456"), (" ", "#000000"), ("kind", "#123456")]]


def test_colouring_the_text_does_not_change_the_text(editor):
    """The colours are paint, not content: nothing is written, so there is
    nothing to undo and what is saved out is still plain."""
    editor.setPlainText('kind "cart"\n')
    assert editor.toPlainText() == 'kind "cart"\n'
    assert editor.document().availableUndoSteps() == 0


# ---------------------------------------------------------------------------
# a dark background, where the light colours cannot be seen
# ---------------------------------------------------------------------------


def test_the_editor_colours_for_the_background_it_actually_has(editor):
    """The widget is the one that knows what is behind its text, so it is the
    one that says which half of the theme gets painted."""
    assert editor.on_dark_background() is False
    assert editor.highlighter.dark is False

    on_dark(editor, True)
    assert editor.on_dark_background() is True
    assert editor.highlighter.dark is True


def test_the_plain_text_of_a_dark_editor_is_white_rather_than_black(editor):
    """Black on a dark background is the same colour, which is why a theme has
    to be able to say white."""
    on_dark(editor, True)
    editor.setPlainText("}")  # a brace is structure, which no rule colours
    assert painted(editor) == [[("}", DARK_PLAIN)]]


def test_a_dark_background_takes_the_dark_colour_of_every_style(editor):
    on_dark(editor, True)
    editor.setPlainText('kind\nmesh-table {\n}\nkuid <kuid:1:2> "cart" origin')
    assert painted(editor) == [
        [("kind", DARK_TAGS)],
        [("mesh-table", DARK_CONTAINERS), (" {", DARK_PLAIN)],
        [("}", DARK_PLAIN)],
        [
            ("kuid", DARK_TAGS),
            (" ", DARK_PLAIN),
            ("<kuid:1:2>", DARK_KUID),
            (" ", DARK_PLAIN),
            ('"cart"', DARK_STRING),
            (" ", DARK_PLAIN),
            ("origin", DARK_OBSOLETE),
        ],
    ]


def test_a_light_background_takes_the_light_colours_back(editor):
    on_dark(editor, True)
    editor.setPlainText('kind "cart"')
    on_dark(editor, False)
    assert shown(editor) == [
        [("kind", "tags"), (" ", "plain"), ('"cart"', "string")]
    ]


def test_a_theme_that_names_no_dark_colour_is_painted_the_same_way(editor):
    """One colour is allowed; it is only the shipped theme that has to be
    readable on both, since the program cannot know what the desktop is."""
    editor.set_theme(
        parse_theme(
            {
                "styles": {"default": "#000000", "words": "#0000ff"},
                "keywords": [{"style": "words", "words": ["kind"]}],
            }
        )
    )
    on_dark(editor, True)
    editor.setPlainText("kind")
    assert painted(editor) == [[("kind", TAGS)]]
