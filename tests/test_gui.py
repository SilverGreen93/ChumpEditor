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

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
)

from chumpeditor.chump import ChumpError, load_chump, parse_text, read_text_file  # noqa: E402
from chumpeditor.document import save_chump  # noqa: E402
from chumpeditor.gui import APP_TITLE, ChumpWindow, RichTextEditor  # noqa: E402
from chumpeditor.gui.editor import code_font  # noqa: E402
from chumpeditor.gui.resources import (  # noqa: E402
    APP_NAME,
    CREDIT,
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
    sit on screen and the test run would wait for it for ever.
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
    return shown


@pytest.fixture
def window(qapp):
    return ChumpWindow()


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
    assert APP_TITLE.startswith(f"{APP_NAME} ")
    assert window.windowTitle() == f"{UNTITLED} - {APP_TITLE}"


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
    assert APP_TITLE.startswith(f"{APP_NAME} ")
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
# the editor keeps what it is given
# ---------------------------------------------------------------------------
def test_round_tripping_a_sample_through_the_editor_packs_the_same_bytes(window, tmp_path):
    source = copy("config3.chump", tmp_path)
    window.open_path(source)
    written = save_chump(window.editor.toPlainText(), tmp_path / "back.chump")
    assert written.read_bytes() == source.read_bytes()
