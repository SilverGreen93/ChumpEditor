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

from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtGui import QDragLeaveEvent  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QFileDialog,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
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
    question is yes, which is the answer that lets a test carry on and check
    what happened after it.
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
        QMessageBox, "about",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("about", title, text))),
    )
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(
            lambda parent, title, text, *a, **k: (
                shown.append(("question", title, text)),
                QMessageBox.StandardButton.Yes,
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


def test_the_tweaks_menu_holds_the_conversions(window):
    assert labels(menu_of(window, "Tweaks")) == ["Convert obsolete lists"]


def test_converting_folds_the_tags_into_one_line(window, dialogs):
    window.editor.setPlainText(OBSOLETE)
    click(window, "Tweaks", "Convert obsolete lists")
    assert window.editor.toPlainText() == "".join(
        line + "\n"
        for line in (
            lined("kind", '"interior"'),
            lined("category-era", '"1920s;1930s;1940s"'),
            lined("category-region-0", '"RO"'),
        )
    )


def test_converting_tells_the_user_what_it_did(window, dialogs):
    """The tags that were folded up are named, in a box and in the status bar."""
    window.editor.setPlainText(OBSOLETE)
    click(window, "Tweaks", "Convert obsolete lists")

    kind, title, text = dialogs[-1]
    assert (kind, title) == ("info", "Convert obsolete lists")
    assert "Converted 1 obsolete list" in text
    for tag in ("category-era-0", "category-era-2", "category-era"):
        assert tag in text
    assert "category-region-0" not in text  # one tag on its own is not a list
    assert window._message == "Converted 1 obsolete list"


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
    assert lined("category-region-0", '"SE"') in after
    assert len(after.split("\n")) == len(before.split("\n")) - 8
    assert "Left alone" not in dialogs[-1][2]

    names = [tag.name for tag in parse_text(after).tags]
    assert names.count("category-era") == 1
    assert "category-era-0" not in names
    assert "category-region-0" in names


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
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a: QMessageBox.StandardButton.No),
    )
    keep = copy("config1.chump", tmp_path)
    away = copy("config2.chump", tmp_path)
    window.open_path(keep)
    window.editor.insertPlainText("x")

    picks.choose.append(str(away))
    click(window, "File", "Open file...")
    assert window.path == keep
    assert window.editor.toPlainText().startswith("x")


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
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a: QMessageBox.StandardButton.No),
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

    click(window, "File", "Exit")  # the standing answer in these tests is yes
    assert not window.isVisible()
    assert source.read_bytes() == (SAMPLES / "config1.chump").read_bytes()


def test_closing_a_window_with_nothing_at_risk_asks_nothing(window, dialogs):
    window.show()
    click(window, "File", "Exit")
    assert not window.isVisible()
    assert dialogs == []


def replace(window, text: str) -> None:
    """The text of the editor replaced by hand, as a user would do it all at once."""
    window.editor.selectAll()
    window.editor.insertPlainText(text)
