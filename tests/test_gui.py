"""Tests for the PyQt6 GUI.

These run offscreen (no window appears) and replace the message boxes so no
dialog can block the test run.  Everything is skipped when PyQt6 is missing.

The window edits a file it was given without touching it on disk, so the
samples of ``test_files`` are copied into a scratch folder first.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QPoint, QUrl  # noqa: E402
from PyQt6.QtGui import QDragLeaveEvent  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QFileDialog,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QWidget,
)

from chumpeditor import __version__  # noqa: E402
from chumpeditor.chump import ChumpError, load_chump, parse_text, read_text_file  # noqa: E402
from chumpeditor.document import (  # noqa: E402
    ALL_SUFFIXES,
    CHUMP_GROUP,
    TEXT_GROUP,
    as_file_text,
    filter_string,
    save_chump,
)
from chumpeditor.gui import APP_TITLE, ChumpWindow, RichTextEditor  # noqa: E402
from chumpeditor.gui.drops import accept_file_drop  # noqa: E402
from chumpeditor.gui.editor import code_font  # noqa: E402
from chumpeditor.gui.resources import (  # noqa: E402
    APP_NAME,
    CREDIT,
    DESCRIPTION,
    DISPLAY_NAME,
    DROP_HINT,
    HOME_URL,
    ICON_FILE,
    SUMMARY,
    resource_path,
    window_icon,
)
from chumpeditor.gui.window import UNTITLED  # noqa: E402

SAMPLES = Path(__file__).parent / "test_files"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def dialogs(monkeypatch):
    """Collect the messages the window would have shown instead of showing them.

    Automatic, because a message box is modal: one that nobody replaced would
    sit on screen and the test run would wait for it for ever.  The answer to a
    question is to throw the work away, which is the answer that lets a test
    carry on and check what happened after it; a test that wants the work kept
    says so itself.
    """
    shown: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("error", title, text))),
    )
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("info", title, text))),
    )
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("warn", title, text))),
    )
    monkeypatch.setattr(
        QMessageBox, "about",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("about", title, text))),
    )
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(
            lambda parent, title, text, *a, **k: (
                shown.append(("question", title, text)),
                QMessageBox.StandardButton.Discard,
            )[1]
        ),
    )
    return shown


@pytest.fixture
def picks(monkeypatch):
    """The dialogs that ask for a name, with the answers handed to them.

    ``choose`` is the list of names the dialogs are answered with, in order; an
    empty answer stands for a dialog the user cancelled.
    """
    picker = _Picks()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(picker.answer("open")))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(picker.answer("save")))
    return picker


class _Picks:
    """What the file dialogs were asked, and what they were answered with."""

    def __init__(self) -> None:
        #: names the dialogs are answered with, in the order they are asked
        self.choose: list[str] = []
        #: which dialog, its title, what it started with, and its filters
        self.asked: list[tuple[str, str, str, str]] = []

    def answer(self, which: str):
        def respond(parent, title, start, filters="", *a, **k):
            self.asked.append((which, title, start, filters))
            return (self.choose.pop(0) if self.choose else ""), ""

        return respond


@pytest.fixture
def window(qapp):
    return ChumpWindow()


@pytest.fixture
def clipboard(qapp):
    """The system clipboard, with whatever was on it put back afterwards."""
    board = qapp.clipboard()
    was = board.text()
    yield board
    board.clear()
    if was:
        board.setText(was)


def copy(sample: str, folder: Path) -> Path:
    """A copy of a sample, so the repository fixtures are only ever read."""
    target = folder / sample
    target.write_bytes((SAMPLES / sample).read_bytes())
    return target


def flat(text: str) -> str:
    """Line endings as one kind, so text can be compared across the editor."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def text_of(widget: QTextEdit) -> str:
    """The editor's text with the line endings the codec uses."""
    return flat(widget.toPlainText())


# ---------------------------------------------------------------------------
# the window, and what is not in it any more
# ---------------------------------------------------------------------------
def test_the_window_is_titled_with_the_version(window):
    assert APP_TITLE.startswith(f"{DISPLAY_NAME} ")
    assert window.windowTitle() == f"{UNTITLED} - {APP_TITLE}"


def test_the_name_spelled_two_ways_is_still_one_name():
    """What is read out loud is 'Chump Editor'; what is typed - the exe, the
    settings folder, the package - is 'ChumpEditor'.  Those two are the same
    name only as long as they match, so the spaced spelling is checked against
    the unspaced one rather than being trusted to stay in step."""
    assert DISPLAY_NAME.replace(" ", "") == APP_NAME


def test_the_main_area_is_one_rich_text_editor(window):
    assert isinstance(window.editor, RichTextEditor)
    assert window.centralWidget() is window.editor
    assert window.editor.acceptRichText()  # colours and attributes survive


def test_the_batch_queue_is_gone(window):
    """No list, no buttons: the file queue and its three buttons are history."""
    assert window.findChildren(QListWidget) == []
    assert window.findChildren(QPushButton) == []


def test_the_text_is_shown_in_a_fixed_width_font(window):
    assert window.editor.font().fixedPitch()
    assert window.editor.font().pointSize() == code_font().pointSize()


def test_the_icon_is_found_when_running_from_the_sources(window):
    # the taskbar icon is set from this file, so it has to be in the repository
    found = resource_path(ICON_FILE)
    assert found is not None and Path(found).is_file()
    assert Path(found).name == ICON_FILE
    assert window_icon() is not None
    assert resource_path("no-such-icon.ico") is None


def test_the_window_introduces_itself(window):
    assert APP_TITLE.startswith(f"{DISPLAY_NAME} ")
    assert CREDIT.startswith("© ")
    assert SUMMARY


# ---------------------------------------------------------------------------
# opening: the text of the file lands in the editor
# ---------------------------------------------------------------------------
def test_nothing_is_in_the_editor_until_a_file_arrives(window):
    assert window.editor.toPlainText() == ""
    assert window.path is None
    assert window.windowTitle() == f"Untitled - {APP_TITLE}"


def test_opening_a_chump_shows_the_text_form_of_it(window, tmp_path):
    source = copy("config1.chump", tmp_path)
    window.open_path(source)
    assert parse_text(text_of(window.editor)) == load_chump(source)
    assert window.path == source


def test_opening_a_txt_shows_the_file_itself(window, tmp_path):
    source = copy("config3.txt", tmp_path)
    window.open_path(source)
    assert text_of(window.editor) == flat(read_text_file(source))


def test_opening_leaves_the_file_where_it_is(window, tmp_path):
    source = copy("config2.chump", tmp_path)
    before = source.read_bytes()
    window.open_path(source)
    assert source.read_bytes() == before
    assert not (tmp_path / "config2.txt").exists()


def test_the_title_follows_the_file_and_any_change_to_it(window, tmp_path):
    source = copy("config1.chump", tmp_path)
    window.open_path(source)
    assert window.windowTitle() == f"config1.chump - {APP_TITLE}"
    window.editor.insertPlainText("x")
    assert window.windowTitle() == f"config1.chump * - {APP_TITLE}"
    window.editor.undo()
    assert window.windowTitle() == f"config1.chump - {APP_TITLE}"


def test_paths_named_on_the_command_line_open_straight_away(tmp_path):
    source = copy("config1.chump", tmp_path)
    started = ChumpWindow([str(source)])
    assert started.path == source
    assert started.editor.toPlainText() != ""


def test_the_first_of_several_paths_is_the_one_that_opens(window, dialogs, tmp_path):
    first = copy("config1.chump", tmp_path)
    second = copy("config2.chump", tmp_path)
    window.open_paths([str(first), str(second)])
    assert window.path == first
    assert "config2.chump" in window.statusBar().currentMessage()


def test_a_path_that_is_not_there_is_skipped(window, tmp_path):
    source = copy("config1.chump", tmp_path)
    window.open_paths([str(tmp_path / "gone.chump"), str(source)])
    assert window.path == source


def test_nothing_to_open_is_said_without_making_a_fuss(window, dialogs, tmp_path):
    notes = tmp_path / "notes.bin"
    notes.write_text("nope")
    window.open_paths([str(notes)])
    assert window.path is None
    assert "no .chump" in window.statusBar().currentMessage()
    assert dialogs == []  # a status line is enough; no dialog


def test_starting_the_window_with_no_paths_says_nothing(window, dialogs):
    ChumpWindow([])
    assert dialogs == []


def test_a_file_that_cannot_be_read_raises_from_open_path(window, tmp_path):
    broken = tmp_path / "broken.chump"
    broken.write_bytes(b"plain text, not a chump")
    with pytest.raises(ChumpError) as exc:
        window.open_path(broken)
    assert "not a chump file" in str(exc.value)
    assert window.editor.toPlainText() == ""
    assert window.path is None


def test_the_same_file_opened_the_way_the_window_opens_makes_a_dialog(window, dialogs, tmp_path):
    broken = tmp_path / "broken.chump"
    broken.write_bytes(b"plain text, not a chump")
    assert window.open_file(broken) is False
    assert len(dialogs) == 1
    kind, title, message = dialogs[0]
    assert (kind, title) == ("error", "Error")
    assert str(broken) in message and "not a chump file" in message
    assert window.editor.toPlainText() == ""


def test_a_broken_file_named_on_the_command_line_does_not_stop_the_window(window, dialogs, tmp_path):
    broken = tmp_path / "broken.chump"
    broken.write_bytes(b"plain text, not a chump")
    started = ChumpWindow([str(broken)])
    assert started.editor.toPlainText() == ""
    assert started.path is None
    assert dialogs and dialogs[0][0] == "error"


# ---------------------------------------------------------------------------
# drag and drop: a file can be let go anywhere in the window
# ---------------------------------------------------------------------------
class _FakeMime:
    """Enough of QMimeData for the two questions the window asks."""

    def __init__(self, urls=(), text: str = ""):
        self._urls = list(urls)
        self._text = text

    def hasUrls(self):  # noqa: N802 - Qt naming
        return bool(self._urls)

    def urls(self):
        return [QUrl.fromLocalFile(path) for path in self._urls]

    def hasText(self):  # noqa: N802 - Qt naming
        return bool(self._text)

    def text(self):
        return self._text


class _FakeDrop:
    def __init__(self, paths=(), text: str = ""):
        self._mime = _FakeMime(list(paths), text)
        self.accepted = False

    def mimeData(self):  # noqa: N802 - Qt naming
        return self._mime

    def acceptProposedAction(self):  # noqa: N802 - Qt naming
        self.accepted = True


def test_both_the_window_and_the_text_area_take_drops(window):
    assert window.acceptDrops()
    assert window.editor.acceptDrops()


def test_dropping_a_chump_on_the_window_loads_it(window, tmp_path):
    source = copy("config1.chump", tmp_path)
    event = _FakeDrop([str(source)])
    window.dragEnterEvent(event)
    assert event.accepted
    window.dropEvent(event)
    assert window.path == source
    assert window.editor.toPlainText() != ""


def test_dropping_on_the_text_area_loads_it_too(window, tmp_path):
    source = copy("config2.chump", tmp_path)
    window.editor.dropEvent(_FakeDrop([str(source)]))
    assert window.path == source
    # the text goes through the same line ending rule saving uses, because a
    # quoted value in this sample spans lines
    assert parse_text(as_file_text(text_of(window.editor))) == load_chump(source)


def test_the_text_area_takes_care_of_its_own_drag_hints(window, tmp_path):
    event = _FakeDrop([str(copy("config1.chump", tmp_path))])
    window.open_paths([str(copy("config2.chump", tmp_path))])
    opened = window.statusBar().currentMessage()

    window.editor.dragEnterEvent(event)
    assert window.statusBar().currentMessage() == DROP_HINT
    window.editor.dragLeaveEvent(QDragLeaveEvent())
    assert window.statusBar().currentMessage() == opened


def test_dragging_over_the_window_offers_the_hint_too(window, tmp_path):
    window.say("something worth keeping")
    window.dragEnterEvent(_FakeDrop([str(copy("config1.chump", tmp_path))]))
    assert window.statusBar().currentMessage() == DROP_HINT
    window.dragLeaveEvent(_FakeDrop())
    assert window.statusBar().currentMessage() == "something worth keeping"


def test_a_drop_of_nothing_usable_leaves_the_editor_alone(window, tmp_path):
    notes = tmp_path / "notes.bin"
    notes.write_text("nope")
    window.dropEvent(_FakeDrop([str(notes)]))
    assert window.path is None
    assert window.editor.toPlainText() == ""
    assert "no .chump" in window.statusBar().currentMessage()


def test_dropping_a_second_file_replaces_the_one_on_screen(window, tmp_path):
    first = copy("config1.chump", tmp_path)
    second = copy("config2.chump", tmp_path)
    window.dropEvent(_FakeDrop([str(first)]))
    window.dropEvent(_FakeDrop([str(second)]))
    assert window.path == second
    assert window.windowTitle() == f"config2.chump - {APP_TITLE}"


def test_a_file_that_will_not_open_is_a_dialog_not_a_crash(window, dialogs, tmp_path):
    broken = tmp_path / "broken.chump"
    broken.write_bytes(b"nope")
    window.editor.dropEvent(_FakeDrop([str(broken)]))
    assert window.path is None
    assert dialogs and dialogs[0][0] == "error"


def test_a_drag_of_plain_text_is_left_to_the_editor(window):
    """Dragging text in is not a file, so QTextEdit keeps handling it."""
    event = _FakeDrop(text="kuid <kuid:1:2>")
    assert not accept_file_drop(event)
    assert not event.accepted

    taken = _FakeDrop([str(Path("whatever.txt"))])
    assert accept_file_drop(taken)
    assert taken.accepted


def test_dropping_reports_which_files_were_left_out(window, tmp_path):
    first = copy("config1.chump", tmp_path)
    second = copy("config2.chump", tmp_path)
    window.dropEvent(_FakeDrop([str(first), str(second)]))
    assert window.path == first
    assert "config2.chump" in window.statusBar().currentMessage()


# ---------------------------------------------------------------------------
# the editor keeps what it is given
# ---------------------------------------------------------------------------
def test_round_tripping_a_sample_through_the_editor_packs_the_same_bytes(window, tmp_path):
    source = copy("config3.chump", tmp_path)
    window.open_path(source)
    written = save_chump(window.editor.toPlainText(), tmp_path / "back.chump")
    assert written.read_bytes() == source.read_bytes()


# ---------------------------------------------------------------------------
# the line numbers down the side of the text
# ---------------------------------------------------------------------------
@pytest.fixture
def shown(window, qapp):
    """The window, on screen.

    Which lines are in sight, and how far down each of them sits, are questions
    about a laid out document; a window that was never shown has no width to lay
    one out in, and every line in it is at the top.
    """
    window.resize(700, 400)
    window.show()
    qapp.processEvents()
    return window


def lines_of(count: int) -> str:
    """A file of exactly that many lines, each named after its own number."""
    return "\n".join(f"tag {number}" for number in range(1, count + 1))


def test_the_numbers_are_part_of_the_editor(window):
    """A strip of its own beside the text, not text written into the document:
    a number can never be selected, deleted, saved or reordered by accident."""
    assert isinstance(window.editor.gutter, QWidget)
    assert window.editor.gutter.parentWidget() is window.editor


def test_the_lines_are_numbered_from_one(shown):
    shown.editor.setPlainText(lines_of(60))
    numbers = [number for number, _, _ in shown.editor.visible_lines()]
    assert numbers == list(range(1, len(numbers) + 1))
    assert 1 < len(numbers) < 60  # the file is longer than the window is


def test_a_number_is_level_with_the_line_it_numbers(shown):
    """The one thing a ruler is for: the number has to be beside the line it
    names.  The text is asked which line sits at that height, which is the same
    way a click in the text finds out, so the two answers have to agree."""
    shown.editor.setPlainText(lines_of(60))
    for number, top, height in shown.editor.visible_lines():
        line = shown.editor.cursorForPosition(QPoint(2, top + height // 2))
        assert line.blockNumber() + 1 == number


def test_the_numbers_are_still_right_at_the_bottom_of_a_long_file(shown, qapp):
    """The numbering comes from the document rather than from what happened to be
    at the top when the file opened, so a scroll changes which lines are named
    and nothing else."""
    shown.editor.setPlainText(lines_of(600))
    qapp.processEvents()  # the file is scrolled once it has been laid out
    shown.editor.verticalScrollBar().setValue(shown.editor.verticalScrollBar().maximum())
    qapp.processEvents()
    lines = shown.editor.visible_lines()
    assert [number for number, _, _ in lines][-1] == 600
    for number, top, height in lines:
        if top >= 0:
            line = shown.editor.cursorForPosition(QPoint(2, top + height // 2))
            assert line.blockNumber() + 1 == number


def test_the_room_for_the_numbers_is_not_a_seesaw(shown):
    """The strip is as wide as its widest possible number, three digits at the
    least, so a file growing past ninety-nine lines does not slide the text
    sideways and a small file does not leave a gap to be filled."""
    widths = set()
    for count in (1, 9, 99, 999):
        shown.editor.setPlainText(lines_of(count))
        assert shown.editor.viewportMargins().left() == shown.editor.gutter_width()
        widths.add(shown.editor.gutter_width())
    assert len(widths) == 1
    shown.editor.setPlainText(lines_of(1000))
    assert shown.editor.gutter_width() > widths.pop()


def test_the_numbers_stand_clear_of_the_text(shown):
    """The room beside the text is reserved for the strip and the strip stands
    in it, top for top and bottom for bottom."""
    strip = shown.editor.gutter.geometry()
    text = shown.editor.viewport().geometry()
    assert strip.width() == shown.editor.gutter_width() > 0
    assert strip.right() < text.left()
    assert strip.top() == text.top()
    assert strip.height() == text.height()


def test_the_numbers_stop_where_the_text_does_when_a_bar_arrives(shown, qapp):
    """A line too wide for the window brings a sideways bar in underneath the
    text; the text area gets shorter, and the strip has to stop with it instead
    of running on behind the bar."""
    before = shown.editor.viewport().height()
    shown.editor.setPlainText("x" * 6000)
    qapp.processEvents()
    assert shown.editor.viewport().height() < before
    assert shown.editor.gutter.height() == shown.editor.viewport().height()


def test_the_numbers_keep_up_when_the_window_changes_shape(shown, qapp):
    """The strip follows the text area wherever the layout puts it, rather than
    being stood once beside a text area that has since moved."""
    shown.editor.setPlainText(lines_of(400))
    qapp.processEvents()
    before = shown.editor.gutter.geometry()
    shown.resize(420, 260)
    qapp.processEvents()
    strip, text = shown.editor.gutter.geometry(), shown.editor.viewport().geometry()
    assert strip != before
    assert strip.top() == text.top()
    assert strip.height() == text.height()


def test_a_line_wrapped_across_the_window_keeps_one_number(shown, qapp):
    """The reader's line 40 is the document's line 40, whatever the word wrap
    makes of it in between: a wrapped line is numbered once, at its first line."""
    shown.editor.set_line_wrap(True)
    shown.editor.setPlainText("x" * 6000)
    qapp.processEvents()
    assert shown.editor.document().blockCount() == 1
    assert [number for number, _, _ in shown.editor.visible_lines()] == [1]


def test_the_numbers_follow_an_edit_and_one_press_of_undo(shown, qapp):
    def last_line_in_sight() -> int:
        qapp.processEvents()
        bar = shown.editor.verticalScrollBar()
        bar.setValue(bar.maximum())
        qapp.processEvents()
        return [number for number, _, _ in shown.editor.visible_lines()][-1]

    shown.editor.setPlainText(lines_of(60))
    assert last_line_in_sight() == 60
    cursor = shown.editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText("\ntag 61\ntag 62")
    assert last_line_in_sight() == 62
    shown.editor.undo()
    assert last_line_in_sight() == 60


# ---------------------------------------------------------------------------
# the menu bar
# ---------------------------------------------------------------------------
def plain(text: str) -> str:
    """A menu label with the Alt key taken back out of it."""
    return text.replace("&", "")


def menu_of(window, name: str):
    for action in window.menuBar().actions():
        if plain(action.text()) == name:
            return action.menu()
    raise AssertionError(f"there is no {name} menu")


def labels(menu) -> list[str]:
    """A menu's items in order, with a separator shown as a dash."""
    return ["-" if action.isSeparator() else plain(action.text()) for action in menu.actions()]


def item(window, menu_name: str, label: str):
    for action in menu_of(window, menu_name).actions():
        if plain(action.text()) == label:
            return action
    raise AssertionError(f"{menu_name} has no {label!r} item")


def click(window, menu_name: str, label: str) -> None:
    item(window, menu_name, label).trigger()


def keys(window, menu_name: str, label: str) -> str:
    return item(window, menu_name, label).shortcut().toString()


def test_the_menu_bar_offers_file_edit_tweaks_and_help(window):
    assert [plain(action.text()) for action in window.menuBar().actions()] == [
        "File", "Edit", "Tweaks", "Help"
    ]


def test_the_file_menu_offers_open_then_the_two_forms_of_writing_then_exit(window):
    assert labels(menu_of(window, "File")) == [
        "Open file...",
        "-",
        "Save chump", "Save chump as...",
        "-",
        "Export txt", "Export txt as...",
        "-",
        "Exit",
    ]


def test_the_file_menu_carries_the_shortcuts_people_already_know(window):
    assert keys(window, "File", "Open file...") == "Ctrl+O"
    assert keys(window, "File", "Save chump") == "Ctrl+S"
    assert keys(window, "File", "Export txt") == "Ctrl+E"
    # the two that always open a dialog are the two nobody presses blind
    assert not keys(window, "File", "Save chump as...")
    assert not keys(window, "File", "Export txt as...")


def test_the_edit_menu_is_the_usual_set_of_edits(window):
    assert labels(menu_of(window, "Edit")) == [
        "Undo", "Redo", "-", "Cut", "Copy", "Paste", "Select All",
    ]
    assert [keys(window, "Edit", name) for name in
            ("Undo", "Redo", "Cut", "Copy", "Paste", "Select All")] == [
            "Ctrl+Z", "Ctrl+Y", "Ctrl+X", "Ctrl+C", "Ctrl+V", "Ctrl+A",
    ]


def test_the_help_menu_holds_the_about_box(window):
    assert labels(menu_of(window, "Help")) == [f"About {DISPLAY_NAME}..."]


def test_the_edit_menu_works_on_the_text(window, clipboard):
    """The Edit items work the text over, whatever has the focus."""
    window.editor.setPlainText("kuid <kuid:1:2>\nkind \"interior\"")
    click(window, "Edit", "Select All")
    click(window, "Edit", "Cut")
    assert window.editor.toPlainText() == ""
    click(window, "Edit", "Paste")
    assert text_of(window.editor) == "kuid <kuid:1:2>\nkind \"interior\""
    click(window, "Edit", "Undo")
    assert window.editor.toPlainText() == ""
    click(window, "Edit", "Redo")
    assert text_of(window.editor) == "kuid <kuid:1:2>\nkind \"interior\""


def test_an_edit_with_nothing_to_work_on_is_greyed_out(window, clipboard):
    assert not item(window, "Edit", "Undo").isEnabled()
    assert not item(window, "Edit", "Redo").isEnabled()
    assert not item(window, "Edit", "Cut").isEnabled()
    assert not item(window, "Edit", "Copy").isEnabled()

    window.editor.setPlainText("kuid <kuid:1:2>")
    click(window, "Edit", "Select All")
    assert item(window, "Edit", "Cut").isEnabled()
    assert item(window, "Edit", "Copy").isEnabled()

    click(window, "Edit", "Cut")
    assert item(window, "Edit", "Undo").isEnabled()
    assert not item(window, "Edit", "Redo").isEnabled()
    click(window, "Edit", "Undo")
    assert item(window, "Edit", "Redo").isEnabled()


def test_the_about_box_names_the_program_the_address_and_the_version(window, dialogs):
    click(window, "Help", f"About {DISPLAY_NAME}...")
    kind, title, text = dialogs[-1]
    assert (kind, title) == ("about", f"About {DISPLAY_NAME}")
    for part in (APP_TITLE, __version__, SUMMARY, DESCRIPTION, CREDIT, HOME_URL):
        assert part in text
    assert f'href="{HOME_URL}"' in text  # the address is a link, not a caption


# ---------------------------------------------------------------------------
# the Tweaks menu
# ---------------------------------------------------------------------------
def lined(tag: str, value: str) -> str:
    """A tag line with its value on column 40, the way a config file writes."""
    return f"{tag:<40}{value}"


OBSOLETE = "".join(
    line + "\n"
    for line in (
        lined("kind", '"interior"'),
        lined("category-era-0", '"1920s"'),
        lined("category-era-1", '"1930s"'),
        lined("category-era-2", '"1940s"'),
        lined("category-region-0", '"RO"'),
    )
)


def test_the_tweaks_menu_holds_the_four_tidy_ups(window):
    assert labels(menu_of(window, "Tweaks")) == [
        "Convert obsolete lists",
        "Convert asset-filename to mesh-table",
        "Remove language tags",
        "Reorder tags",
    ]


def test_converting_folds_the_tags_into_one_line(window, dialogs):
    window.editor.setPlainText(OBSOLETE)
    click(window, "Tweaks", "Convert obsolete lists")
    assert window.editor.toPlainText() == "".join(
        line + "\n"
        for line in (
            lined("kind", '"interior"'),
            lined("category-era", '"1920s;1930s;1940s"'),
            lined("category-region", '"RO"'),
        )
    )


def test_converting_tells_the_user_what_it_did(window, dialogs):
    """The tags that were folded up are named, in a box and in the status bar."""
    window.editor.setPlainText(OBSOLETE)
    click(window, "Tweaks", "Convert obsolete lists")

    kind, title, text = dialogs[-1]
    assert (kind, title) == ("info", "Convert obsolete lists")
    assert "Converted 2 obsolete tags" in text
    for tag in ("category-era-0", "category-era-2", "category-era"):
        assert tag in text
    # the lone region tag is named as well: it lost its number
    assert "category-region-0 became category-region 'RO'" in text
    assert window._message == "Converted 2 obsolete tags"


def test_one_press_of_undo_takes_the_whole_conversion_back(window, dialogs):
    """Every list that was folded up goes back at once, not one press each."""
    cars = lined("car-0", '"a"') + "\n" + lined("car-1", '"b"') + "\n"
    window.editor.setPlainText(OBSOLETE + cars)
    before = window.editor.toPlainText()
    click(window, "Tweaks", "Convert obsolete lists")
    assert window.editor.toPlainText() != before
    click(window, "Edit", "Undo")
    assert window.editor.toPlainText() == before
    click(window, "Edit", "Redo")
    assert lined("car", '"a;b"') in window.editor.toPlainText()


def test_converting_leaves_the_document_dirty_and_the_title_marked(window, dialogs):
    window.editor.setPlainText(OBSOLETE)
    window.editor.document().setModified(False)
    click(window, "Tweaks", "Convert obsolete lists")
    assert window.editor.document().isModified()
    assert window.windowTitle().startswith("Untitled *")


def test_a_file_with_nothing_to_convert_is_left_alone(window, dialogs):
    window.editor.setPlainText('kind "interior"\nkuid <kuid:1:2>\n')
    window.editor.document().setModified(False)
    click(window, "Tweaks", "Convert obsolete lists")

    assert window.editor.toPlainText() == 'kind "interior"\nkuid <kuid:1:2>\n'
    assert not window.editor.document().isModified()
    assert not item(window, "Edit", "Undo").isEnabled()
    assert dialogs[-1][2].startswith("Nothing was converted")
    assert window._message == "Nothing was converted"


def test_a_conversion_the_rules_turn_down_is_said_out_loud(window, dialogs):
    """Repeating a tag the file already has would break it, and the user hears why."""
    window.editor.setPlainText(
        lined("category-era", '"1900s"') + "\n"
        + lined("category-era-0", '"a"') + "\n"
        + lined("category-era-1", '"b"') + "\n"
    )
    click(window, "Tweaks", "Convert obsolete lists")

    assert "would repeat category-era" in dialogs[-1][2]
    assert window._message == "Nothing was converted"


def test_the_obsolete_sample_converts_in_the_window_and_still_reads(window, dialogs, tmp_path):
    """The config file this was asked for, opened from disk and read back."""
    source = copy("obsolete_config.txt", tmp_path)
    assert window.open_file(source)
    before = window.editor.toPlainText()

    click(window, "Tweaks", "Convert obsolete lists")

    after = window.editor.toPlainText()
    eras = '"1920s;1930s;1940s;1950s;1960s;1970s;1980s;1990s;2000s"'
    assert lined("category-era", eras) in after
    assert lined("category-region", '"SE"') in after
    assert len(after.split("\n")) == len(before.split("\n")) - 8
    assert "Left alone" not in dialogs[-1][2]

    names = [tag.name for tag in parse_text(after).tags]
    assert names.count("category-era") == 1
    assert "category-era-0" not in names
    assert names.count("category-region") == 1


TRANSLATIONS = "".join(
    line + "\n"
    for line in (
        lined("kind", '"interior"'),
        lined("description", '"woman3"'),
        lined("description-de", '"Frau3"'),
        lined("description-ru", '"Прохожая3"'),
        lined("contact-email", '"nobody@example.com"'),
    )
)


def test_removing_language_tags_leaves_the_tag_itself_behind(window, dialogs):
    window.editor.setPlainText(TRANSLATIONS)
    click(window, "Tweaks", "Remove language tags")
    assert window.editor.toPlainText() == "".join(
        line + "\n"
        for line in (
            lined("kind", '"interior"'),
            lined("description", '"woman3"'),
            lined("contact-email", '"nobody@example.com"'),
        )
    )


def test_removing_language_tags_says_what_went_and_what_stayed(window, dialogs):
    window.editor.setPlainText(TRANSLATIONS)
    click(window, "Tweaks", "Remove language tags")

    kind, title, text = dialogs[-1]
    assert (kind, title) == ("info", "Remove language tags")
    assert "Removed 2 language tags" in text
    assert 'description-de "Frau3" went; description stays' in text
    assert window._message == "Removed 2 language tags"


def test_one_press_of_undo_takes_the_whole_sweep_back(window, dialogs):
    """Every language that went, went as one change."""
    window.editor.setPlainText(TRANSLATIONS)
    before = window.editor.toPlainText()
    click(window, "Tweaks", "Remove language tags")
    assert window.editor.toPlainText() != before
    click(window, "Edit", "Undo")
    assert window.editor.toPlainText() == before
    click(window, "Edit", "Redo")
    assert lined("description-de", '"Frau3"') not in window.editor.toPlainText()


def test_a_file_with_no_language_tags_is_left_alone(window, dialogs):
    window.editor.setPlainText('kind "interior"\ncontact-email "a@b"\n')
    window.editor.document().setModified(False)
    click(window, "Tweaks", "Remove language tags")

    assert window.editor.toPlainText() == 'kind "interior"\ncontact-email "a@b"\n'
    assert not window.editor.document().isModified()
    assert not item(window, "Edit", "Undo").isEnabled()
    assert dialogs[-1][2].startswith("Nothing was removed")
    assert window._message == "No language tags"


def test_the_obsolete_sample_loses_its_languages_in_the_window(window, dialogs, tmp_path):
    """Twenty translations out of a real config file, the English still there."""
    source = copy("obsolete_config.txt", tmp_path)
    assert window.open_file(source)
    before = window.editor.toPlainText()

    click(window, "Tweaks", "Remove language tags")

    after = window.editor.toPlainText()
    assert len(after.split("\n")) == len(before.split("\n")) - 20
    assert lined("description", '"casualwoman3"') in after
    assert lined("username", '"casualwoman3"') in after
    assert "description-ru" not in after
    assert "username-jp" not in after
    assert "Left alone" not in dialogs[-1][2]
    assert dialogs[-1][2].startswith("Removed 20 language tags")

    names = [tag.name for tag in parse_text(after).tags]
    assert names.count("description") == 1
    assert names.count("username") == 1
    assert "contact-email" in names


MESHES = "".join(
    line + "\n"
    for line in (
        lined("kind", '"vnd.trainsim.asset"'),
        lined("asset-filename", '"MS_Shelter_4"'),
        lined("username", '"MS_Shelter_4"'),
    )
)

NEW_TABLE = (
    "mesh-table\n"
    "{\n"
    "  default\n"
    "  {\n"
    '    mesh                                "MS_Shelter_4.im"\n'
    "    auto-create                         1\n"
    "  }\n"
    "}\n"
)


def test_converting_an_asset_filename_writes_the_newer_kind_of_container(window, dialogs):
    """The tag is gone and a default mesh took its place, on the same column."""
    window.editor.setPlainText(MESHES)
    click(window, "Tweaks", "Convert asset-filename to mesh-table")

    wanted = (
        lined("kind", '"vnd.trainsim.asset"')
        + "\n"
        + NEW_TABLE
        + lined("username", '"MS_Shelter_4"')
        + "\n"
    )
    assert window.editor.toPlainText() == wanted


def test_converting_an_asset_filename_says_which_mesh_it_named(window, dialogs):
    window.editor.setPlainText(MESHES)
    click(window, "Tweaks", "Convert asset-filename to mesh-table")

    kind, title, text = dialogs[-1]
    assert (kind, title) == ("info", "Convert asset-filename to mesh-table")
    assert "Added 1 mesh-table" in text
    assert "asset-filename 'MS_Shelter_4' became mesh-table 'MS_Shelter_4.im'" in text
    assert window._message == "Added 1 mesh-table"


def test_one_press_of_undo_takes_the_whole_mesh_table_back(window, dialogs):
    """Eight lines that went in together come back together."""
    window.editor.setPlainText(MESHES)
    before = window.editor.toPlainText()
    click(window, "Tweaks", "Convert asset-filename to mesh-table")
    assert window.editor.toPlainText() != before
    click(window, "Edit", "Undo")
    assert window.editor.toPlainText() == before
    click(window, "Edit", "Redo")
    assert "mesh-table" in window.editor.toPlainText()


def test_a_file_that_already_has_a_mesh_table_is_warned_about(window, dialogs):
    """Nothing is added, and the louder box says so: Trainz would have two meshes."""
    window.editor.setPlainText(MESHES + NEW_TABLE)
    window.editor.document().setModified(False)
    click(window, "Tweaks", "Convert asset-filename to mesh-table")

    assert window.editor.toPlainText() == MESHES + NEW_TABLE
    assert not window.editor.document().isModified()
    assert not item(window, "Edit", "Undo").isEnabled()

    kind, title, text = dialogs[-1]
    assert (kind, title) == ("warn", "Convert asset-filename to mesh-table")
    assert text.startswith("Already has a mesh-table")
    assert "default mesh" in text
    assert window._message == "Already has a mesh-table"


def test_a_mesh_table_written_by_the_tweak_itself_is_no_cause_for_worry(window, dialogs):
    """Pressing the item twice is not a second conversion, and it is not a warning."""
    window.editor.setPlainText(MESHES)
    click(window, "Tweaks", "Convert asset-filename to mesh-table")
    once = window.editor.toPlainText()
    click(window, "Tweaks", "Convert asset-filename to mesh-table")

    assert window.editor.toPlainText() == once
    assert dialogs[-1][0] == "info"
    assert dialogs[-1][2].startswith("Nothing was converted")
    assert window._message == "Nothing was converted"


def test_the_obsolete_sample_gains_its_mesh_table_in_the_window(window, dialogs, tmp_path):
    """A real config file, converted and read back as a tree by the codec."""
    source = copy("obsolete_config.txt", tmp_path)
    assert window.open_file(source)
    before = window.editor.toPlainText()

    click(window, "Tweaks", "Convert asset-filename to mesh-table")

    after = window.editor.toPlainText()
    assert len(after.split("\n")) == len(before.split("\n")) + 7
    assert '    mesh                                "casualwoman3.im"' in after
    assert "asset-filename" not in after
    assert dialogs[-1][2].startswith("Added 1 mesh-table")

    tags = parse_text(after).tags
    names = [tag.name for tag in tags]
    assert names.count("mesh-table") == 1
    table = next(tag for tag in tags if tag.name == "mesh-table")
    assert [child.name for child in table.tags] == ["default"]


# ---------------------------------------------------------------------------
# reordering the tags
# ---------------------------------------------------------------------------
UNTIDY = "".join(
    line + "\n"
    for line in (
        lined("kind", '"interior"'),
        lined("kuid", "<kuid:2:100>"),
        "mesh-table",
        "{",
        lined("  mesh", '"a.im"'),
        "}",
        lined("username", '"a name"'),
        "kuid-table",
        "{",
        "}",
    )
)

TIDY = "".join(
    line + "\n"
    for line in (
        lined("kuid", "<kuid:2:100>"),
        lined("username", '"a name"'),
        lined("kind", '"interior"'),
        "",
        "mesh-table",
        "{",
        lined("  mesh", '"a.im"'),
        "}",
        "",
        "kuid-table",
        "{",
        "}",
    )
)

# a container holding a container as well as a value, with both of the two
# containers at the top of the file written the wrong way round
DEEPLY_UNTIDY = "".join(
    line + "\n"
    for line in (
        "table",
        "{",
        "  sub",
        "  {",
        "  }",
        "  value 1",
        "}",
        "obsolete-table",
        "{",
        "}",
        "kuid-table",
        "{",
        "}",
    )
)

DEEPLY_TIDY = "".join(
    line + "\n"
    for line in (
        "table",
        "{",
        "  value 1",
        "",
        "  sub",
        "  {",
        "  }",
        "}",
        "",
        "kuid-table",
        "{",
        "}",
        "",
        "obsolete-table",
        "{",
        "}",
    )
)


def test_reordering_puts_the_kuid_and_the_username_at_the_top(window, dialogs):
    """The containers come after the tags holding one value, whole and as they were."""
    window.editor.setPlainText(UNTIDY)
    click(window, "Tweaks", "Reorder tags")

    assert window.editor.toPlainText() == TIDY


def test_reordering_names_the_tags_that_moved(window, dialogs):
    """Which tags moved and to which line, and where a gap came in."""
    window.editor.setPlainText(UNTIDY)
    click(window, "Tweaks", "Reorder tags")

    kind, title, text = dialogs[-1]
    assert (kind, title) == ("info", "Reorder tags")
    assert "Reordered 4 tags, added 2 blank lines" in text
    for line in (
        "kuid moved from line 2 to line 1",
        "username moved from line 7 to line 2",
        "kind moved from line 1 to line 3",
        "mesh-table moved from line 3 to line 5",
        "a blank line went above the mesh-table on line 5",
        "a blank line went under the mesh-table on line 8",
    ):
        assert line in text
    assert window._message == "Reordered 4 tags, added 2 blank lines"


def test_one_press_of_undo_takes_the_whole_reorder_back(window, dialogs):
    """The tags that moved and the blank line that came in go back together."""
    window.editor.setPlainText(UNTIDY)
    click(window, "Tweaks", "Reorder tags")
    assert window.editor.toPlainText() == TIDY
    click(window, "Edit", "Undo")
    assert window.editor.toPlainText() == UNTIDY
    click(window, "Edit", "Redo")
    assert window.editor.toPlainText() == TIDY


def test_the_order_inside_a_container_goes_back_in_one_press_too(window, dialogs):
    """Several short edits, in a container and at the top, are one change."""
    window.editor.setPlainText(DEEPLY_UNTIDY)
    click(window, "Tweaks", "Reorder tags")

    assert window.editor.toPlainText() == DEEPLY_TIDY
    assert window._message == "Reordered 4 tags, added 3 blank lines"

    click(window, "Edit", "Undo")
    assert window.editor.toPlainText() == DEEPLY_UNTIDY


def test_a_file_already_in_order_is_left_as_it_is(window, dialogs):
    """Pressing the item again is not a change, and it is not a warning either."""
    window.editor.setPlainText(TIDY)
    window.editor.document().setModified(False)
    click(window, "Tweaks", "Reorder tags")

    assert window.editor.toPlainText() == TIDY
    assert not window.editor.document().isModified()
    assert not item(window, "Edit", "Undo").isEnabled()

    kind, title, text = dialogs[-1]
    assert (kind, title) == ("info", "Reorder tags")
    assert text.startswith("Nothing was reordered")
    assert window._message == "Nothing was reordered"


def test_a_file_whose_tags_cannot_be_cut_out_is_warned_about(window, dialogs):
    """A container left open means no safe line to cut on, so nothing moves."""
    broken = 'kuid <kuid:2:100>\nusername "a name"\nmesh-table\n{\n  default\n  {\n'
    window.editor.setPlainText(broken)
    window.editor.document().setModified(False)
    click(window, "Tweaks", "Reorder tags")

    assert window.editor.toPlainText() == broken
    assert not window.editor.document().isModified()
    assert not item(window, "Edit", "Undo").isEnabled()

    kind, title, text = dialogs[-1]
    assert (kind, title) == ("warn", "Reorder tags")
    assert text.startswith("The tags cannot be reordered")
    assert "opens a container that is never closed" in text
    assert window._message == "The tags cannot be reordered"


def test_the_containers_are_set_off_even_when_the_order_is_already_right(
    window, dialogs
):
    """Nothing moves, and the blank lines still go in, as one edit Undo takes back."""
    closed = "".join(
        line + "\n"
        for line in (
            lined("kuid", "<kuid:2:100>"),
            lined("kind", '"interior"'),
            "mesh-table",
            "{",
            lined("  mesh", '"a.im"'),
            "}",
            "kuid-table",
            "{",
            "}",
        )
    )
    set_off = "".join(
        line + "\n"
        for line in (
            lined("kuid", "<kuid:2:100>"),
            lined("kind", '"interior"'),
            "",
            "mesh-table",
            "{",
            lined("  mesh", '"a.im"'),
            "}",
            "",
            "kuid-table",
            "{",
            "}",
        )
    )
    window.editor.setPlainText(closed)
    click(window, "Tweaks", "Reorder tags")

    assert window.editor.toPlainText() == set_off
    assert dialogs[-1][2].startswith("Added 2 blank lines")
    assert window._message == "Added 2 blank lines"

    click(window, "Edit", "Undo")
    assert window.editor.toPlainText() == closed


def test_a_real_config_file_is_reordered_in_the_window(window, dialogs, tmp_path):
    """A real asset, reordered and read back as a tree by the codec."""
    source = copy("config2.txt", tmp_path)
    assert window.open_file(source)
    before = window.editor.toPlainText()

    click(window, "Tweaks", "Reorder tags")

    after = window.editor.toPlainText()
    assert dialogs[-1][2].startswith("Reordered ")
    # every container comes out set off from the tags around it, so the file is longer
    assert "}\n\n" in after
    assert len(after.split("\n")) > len(before.split("\n"))

    tags = parse_text(after).tags
    assert [tag.name for tag in tags[:2]] == ["kuid", "username"]
    assert [tag.name for tag in tags[-2:]] == ["kuid-table", "obsolete-table"]
    # nothing was lost or changed on the way round, only moved
    assert sorted(tag.name for tag in tags) == sorted(
        tag.name for tag in parse_text(before).tags
    )


# ---------------------------------------------------------------------------
# opening and writing from the menus
# ---------------------------------------------------------------------------
def test_opening_from_the_menu_asks_for_a_file_and_opens_it(window, picks, tmp_path):
    source = copy("config3.chump", tmp_path)
    picks.choose.append(str(source))
    click(window, "File", "Open file...")
    assert window.path == source
    assert window.editor.toPlainText() != ""


def test_the_open_dialog_offers_everything_the_editor_reads(window, picks):
    click(window, "File", "Open file...")
    which, title, start, filters = picks.asked[0]
    assert (which, title, start) == ("open", "Open file", "")
    assert filters == filter_string()
    for suffix in ALL_SUFFIXES:
        assert f"*{suffix}" in filters


def test_a_dialog_answered_with_nothing_leaves_the_window_alone(window, picks, tmp_path):
    source = copy("config1.chump", tmp_path)
    window.open_path(source)
    picks.choose.append("")  # the dialog was cancelled
    click(window, "File", "Open file...")
    assert window.path == source


def test_opening_over_unsaved_work_is_asked_about(window, picks, monkeypatch, tmp_path):
    """Cancel is the answer of someone who has changed their mind, and it stops
    everything: no file dialog, no new file, the work still on screen."""
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel),
    )
    keep = copy("config1.chump", tmp_path)
    away = copy("config2.chump", tmp_path)
    window.open_path(keep)
    window.editor.insertPlainText("x")

    picks.choose.append(str(away))
    click(window, "File", "Open file...")
    assert window.path == keep
    assert window.editor.toPlainText().startswith("x")
    assert picks.asked == []  # it never got as far as asking which file


def test_the_question_offers_to_save_the_work_not_only_to_lose_it(window, monkeypatch, tmp_path):
    """Save, Discard and Cancel, with Save the button a pressing finger reaches."""
    asked: list[tuple[str, str, int, int]] = []

    def answer(parent, title, text, buttons=0, default=0, *a, **k):
        asked.append((title, text, int(buttons), int(default)))
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", staticmethod(answer))
    source = copy("config1.chump", tmp_path)
    window.open_path(source)
    window.editor.insertPlainText("x")

    click(window, "File", "Open file...")

    box = QMessageBox.StandardButton
    title, text, buttons, default = asked[0]
    assert (title, text) == (DISPLAY_NAME, "Save changes to config1.chump?")
    assert buttons == int(box.Save | box.Discard | box.Cancel)
    assert default == int(box.Save)


def test_answering_save_writes_the_work_and_carries_on(window, monkeypatch, picks, tmp_path):
    """The work goes to its own file, and then the file that was asked for opens."""
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save),
    )
    keep = copy("config1.chump", tmp_path)
    away = copy("config2.chump", tmp_path)
    window.open_path(keep)
    replace(window, 'kind "interior"\nkuid <kuid:9:9>\n')

    picks.choose.append(str(away))
    click(window, "File", "Open file...")

    assert load_chump(keep) == parse_text('kind "interior"\nkuid <kuid:9:9>\n')
    assert window.path == away


def test_answering_save_but_cancelling_the_name_keeps_the_work_on_screen(
    window, monkeypatch, picks, tmp_path
):
    """Answering save is not the same as saving: the name still has to be given.

    A text file being saved as a chump is asked where the new file goes; that
    question answered with nothing means the work is still unsaved, so the open
    that was asked for does not happen either.
    """
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save),
    )
    keep = copy("config2.txt", tmp_path)
    away = copy("config1.chump", tmp_path)
    window.open_path(keep)
    replace(window, 'kind "interior"\nkuid <kuid:9:9>\n')

    picks.choose.append("")  # the save dialog, cancelled
    picks.choose.append(str(away))
    click(window, "File", "Open file...")

    assert keep.read_bytes() == (SAMPLES / "config2.txt").read_bytes()
    assert window.path == keep
    assert window.editor.toPlainText().startswith('kind "interior"')
    assert window.editor.document().isModified()
    assert [which for which, *_ in picks.asked] == ["save"]


def test_saving_writes_the_file_being_edited_and_takes_the_star_off(window, tmp_path, dialogs):
    source = copy("config1.chump", tmp_path)
    window.open_path(source)
    replace(window, 'kind "interior"\nkuid <kuid:2:2>\n')

    save = item(window, "File", "Save chump")
    assert save.isEnabled()
    save.trigger()
    assert window.path == source
    assert load_chump(source) == parse_text('kind "interior"\nkuid <kuid:2:2>\n')
    assert window.windowTitle() == f"config1.chump - {APP_TITLE}"
    assert window.statusBar().currentMessage() == "Saved config1.chump"
    assert dialogs == []  # a save nobody argued with needs no comment


def test_saving_an_untitled_editor_asks_where_the_file_goes(window, picks, tmp_path):
    replace(window, 'kind "interior"\n')
    picks.choose.append(str(tmp_path / "brand.new.chump"))

    assert window.save() == tmp_path / "brand.new.chump"
    assert load_chump(tmp_path / "brand.new.chump") == parse_text('kind "interior"\n')
    assert window.path == tmp_path / "brand.new.chump"
    assert window.windowTitle() == f"brand.new.chump - {APP_TITLE}"


def test_a_name_without_an_extension_gets_the_one_being_written(window, picks, tmp_path):
    replace(window, "kuid <kuid:2:2>\n")
    picks.choose.append(str(tmp_path / "nothint"))
    assert window.save() == tmp_path / "nothint.chump"


def test_saving_as_asks_even_when_the_file_has_a_name(window, picks, tmp_path):
    source = copy("config1.chump", tmp_path)
    window.open_path(source)
    picks.choose.append(str(tmp_path / "second.chump"))

    assert window.save(ask=True) == tmp_path / "second.chump"
    assert source.read_bytes() == (SAMPLES / "config1.chump").read_bytes()
    assert window.path == tmp_path / "second.chump"


def test_saving_a_text_file_as_a_chump_writes_a_chump(window, picks, tmp_path):
    source = copy("config2.txt", tmp_path)
    window.open_path(source)
    picks.choose.append(str(tmp_path / "packed.chump"))

    assert window.save() == tmp_path / "packed.chump"
    assert load_chump(tmp_path / "packed.chump") == load_chump(SAMPLES / "config2.chump")
    assert source.read_bytes() == (SAMPLES / "config2.txt").read_bytes()


def test_the_save_dialog_starts_with_the_name_the_command_line_would_use(window, picks, tmp_path):
    window.open_path(copy("config2.txt", tmp_path))
    window.save()
    which, title, start, filters = picks.asked[-1]
    assert (which, title) == ("save", "Save chump")
    assert start == str(tmp_path / "config2.chump")


def test_the_save_dialog_offers_only_the_form_being_written(window, picks, tmp_path):
    window.open_path(copy("config1.chump", tmp_path))
    window.save(ask=True)
    assert picks.asked[-1][3] == filter_string(CHUMP_GROUP)
    window.export(ask=True)
    assert picks.asked[-1][3] == filter_string(TEXT_GROUP)


def test_exporting_a_chump_makes_a_text_file_and_becomes_the_file(window, picks, tmp_path):
    source = copy("config2.chump", tmp_path)
    window.open_path(source)
    picks.choose.append(str(tmp_path / "given.txt"))

    written = window.export()
    assert written == tmp_path / "given.txt"
    assert written.read_bytes() == (SAMPLES / "config2.txt").read_bytes()
    assert window.path == written
    assert window.windowTitle() == f"given.txt - {APP_TITLE}"
    assert window.statusBar().currentMessage() == "Exported given.txt"


def test_exporting_a_text_file_keeps_it_where_it_stands(window, tmp_path):
    source = copy("config2.txt", tmp_path)
    window.open_path(source)
    window.editor.insertPlainText("x")
    assert window.export() == source


def test_exporting_keeps_the_spacing_the_editor_has(window, picks, tmp_path):
    replace(window, 'kuid    <kuid:2:2>\nname "two  spaces"\n')
    picks.choose.append(str(tmp_path / "kept.txt"))
    assert window.export().read_text(encoding="utf-8-sig", newline="") == (
        'kuid    <kuid:2:2>\r\nname "two  spaces"\r\n'
    )


def test_a_document_that_does_not_pack_is_not_written(window, tmp_path, dialogs):
    source = copy("config1.chump", tmp_path)
    before = source.read_bytes()
    window.open_path(source)
    replace(window, "kuid-table\n{\n")

    assert window.save() is None
    assert dialogs[-1][0] == "error"
    assert "never closed" in dialogs[-1][2]
    assert source.read_bytes() == before
    assert window.editor.document().isModified()  # the work is still on screen


def test_a_loose_quote_mark_is_said_before_any_file_is_asked_for(window, picks, dialogs):
    replace(window, 'username bob"\n')

    assert window.save() is None
    assert picks.asked == []  # the check comes first, so no save dialog was opened
    assert dialogs[-1][0] == "error"
    assert "line 1: value for tag 'username' has a quote mark" in dialogs[-1][2]


def test_exporting_a_document_with_half_a_kuid_writes_nothing(window, picks, tmp_path, dialogs):
    replace(window, "k <kuid:1:2\n")
    picks.choose.append(str(tmp_path / "half.txt"))

    assert window.export() is None
    assert picks.asked == []
    assert not (tmp_path / "half.txt").exists()
    assert dialogs[-1][2] == "line 1: value for tag 'k': '<' with no '>' after it"


def test_an_unclosed_quote_stops_an_export_but_not_the_work(window, tmp_path, dialogs):
    source = copy("config2.txt", tmp_path)
    before = source.read_bytes()
    window.open_path(source)
    replace(window, 'name "abc\n')

    assert window.export() is None
    assert source.read_bytes() == before
    assert dialogs[-1][0] == "error"
    assert window.editor.document().isModified()


def test_a_quote_mark_with_no_partner_in_a_real_file_is_said(window, tmp_path, dialogs):
    """Losing one closing quote is not caught by reading, only by pairing."""
    source = copy("config2.txt", tmp_path)
    before = source.read_bytes()
    window.open_path(source)
    replace(window, text_of(window.editor).replace('"interior"', '"interior'))

    assert window.save() is None
    assert dialogs[-1][0] == "error"
    assert "line 2: quoted value for tag 'kind' has a quote mark with no partner" in dialogs[-1][2]
    assert source.read_bytes() == before


def test_a_write_that_was_turned_down_leaves_the_star_up(window, picks, tmp_path):
    source = copy("config1.chump", tmp_path)
    window.open_path(source)
    window.editor.insertPlainText("x")
    picks.choose.append("")  # cancelled

    assert window.save(ask=True) is None
    assert window.editor.document().isModified()
    assert window.windowTitle() == f"config1.chump * - {APP_TITLE}"
    assert list(tmp_path.glob("*.chump")) == [source]


def test_closing_asks_before_losing_a_change(window, monkeypatch, tmp_path):
    """Cancel keeps the window, the work and the file on disk exactly as they were."""
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel),
    )
    source = copy("config1.chump", tmp_path)
    window.show()
    window.open_path(source)
    replace(window, 'kind "interior"\n')

    click(window, "File", "Exit")
    assert window.isVisible()
    assert source.read_bytes() == (SAMPLES / "config1.chump").read_bytes()


def test_a_change_is_thrown_away_when_someone_says_so(window, tmp_path):
    source = copy("config1.chump", tmp_path)
    window.show()
    window.open_path(source)
    replace(window, 'kind "interior"\n')

    click(window, "File", "Exit")  # the standing answer here is to throw the work away
    assert not window.isVisible()
    assert source.read_bytes() == (SAMPLES / "config1.chump").read_bytes()


def test_answering_save_while_closing_writes_the_file_and_quits(window, monkeypatch, tmp_path):
    """The work is asked about on the way out, and saving it ends the argument."""
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save),
    )
    source = copy("config1.chump", tmp_path)
    window.show()
    window.open_path(source)
    replace(window, 'kind "interior"\nkuid <kuid:9:9>\n')

    click(window, "File", "Exit")
    assert not window.isVisible()
    assert load_chump(source) == parse_text('kind "interior"\nkuid <kuid:9:9>\n')


def test_closing_a_window_with_nothing_at_risk_asks_nothing(window, dialogs):
    window.show()
    click(window, "File", "Exit")
    assert not window.isVisible()
    assert dialogs == []


def replace(window, text: str) -> None:
    """The text of the editor replaced by hand, as a user would do it all at once."""
    window.editor.selectAll()
    window.editor.insertPlainText(text)
