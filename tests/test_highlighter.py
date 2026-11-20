"""Tests for the colours that end up on the screen.

``tests/test_theme.py`` and ``tests/test_scan.py`` settle what a theme means;
these check that the meaning reaches a document, line by line and including the
lines that only make sense together.  Offscreen, like the rest of the GUI
tests, since nothing here needs to be looked at.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtGui import QPalette, QTextCursor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from chumpeditor.gui.editor import RichTextEditor  # noqa: E402
from chumpeditor.theme import bundled_theme_path, load_theme, parse_theme  # noqa: E402

#: the colours of the theme that ships, spelled out so a test can say which
#: part of a line it expected rather than which number it saw
PLAIN = "#000000"
WORDS = "#0000ff"
OTHER = "#800000"
STRING = "#008000"
SECTION = "#ff0080"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qapp) -> RichTextEditor:
    return RichTextEditor()


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
    named = {PLAIN: "plain", WORDS: "words", OTHER: "other", STRING: "string", SECTION: "section"}
    return [
        [(text, named.get(colour, colour)) for text, colour in line]
        for line in painted(widget)
    ]


# ---------------------------------------------------------------------------
# the theme that ships with the program
# ---------------------------------------------------------------------------


def test_the_words_of_the_theme_are_coloured_and_the_rest_is_left_plain(editor):
    editor.setPlainText("kind")
    assert shown(editor) == [[("kind", "words")]]


def test_a_value_in_quotes_is_one_colour_right_across_it(editor):
    editor.setPlainText('kind "cart"')
    assert shown(editor) == [
        [("kind", "words"), (" ", "plain"), ('"cart"', "string")]
    ]


def test_a_word_inside_quotes_is_part_of_the_value(editor):
    """The theme has a rule for both, and the quotes are the one that counts."""
    editor.setPlainText('name "kind"')
    assert shown(editor) == [
        [("name", "words"), (" ", "plain"), ('"kind"', "string")]
    ]


def test_the_two_lists_of_words_are_two_colours(editor):
    editor.setPlainText("kuid-table kuid")
    assert shown(editor) == [
        [("kuid-table", "other"), (" ", "plain"), ("kuid", "words")]
    ]


def test_a_section_in_angle_brackets_is_one_colour(editor):
    editor.setPlainText("<kuid:123:456> kuid")
    assert shown(editor) == [
        [("<kuid:123:456>", "section"), (" ", "plain"), ("kuid", "words")]
    ]


def test_a_value_that_runs_over_several_lines_stays_one_value(editor):
    editor.setPlainText('license "one\ntwo\nthree" end')
    assert shown(editor) == [
        [("license", "words"), (" ", "plain"), ('"one', "string")],
        [("two", "string")],
        [('three"', "string"), (" end", "plain")],
    ]


def test_nothing_is_coloured_that_the_theme_says_nothing_about(editor):
    editor.setPlainText("nonsense 2.7 { = }")
    assert shown(editor) == [[("nonsense 2.7 { = }", "plain")]]


def test_the_colours_are_the_ones_the_shipped_theme_writes(editor):
    theme = load_theme(bundled_theme_path())
    assert theme.styles["keywords1"].colour == WORDS
    assert theme.styles["delimiters1"].colour == STRING


# ---------------------------------------------------------------------------
# typing, and changing the theme
# ---------------------------------------------------------------------------


def test_a_word_typed_in_is_coloured_as_soon_as_it_is_there(editor):
    editor.insertPlainText("kind")
    assert shown(editor) == [[("kind", "words")]]

    editor.insertPlainText(" cart")
    assert shown(editor) == [[("kind", "words"), (" cart", "plain")]]


def test_typing_on_a_line_recolours_only_that_line(editor):
    editor.setPlainText('license "one')
    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.insertPlainText("two")
    assert shown(editor) == [
        [("license", "words"), (" ", "plain"), ('"onetwo', "string")]
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
