"""Tests for the PyQt6 GUI.

These run offscreen (no window appears); message boxes are replaced so no
dialog can block the test run.  Everything is skipped when PyQt6 is missing.

The window only ever converts files it is handed, so the samples are copied
into a scratch folder first: the repository fixtures are read, never rewritten.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

from chumpeditor import gui  # noqa: E402
from chumpeditor.chump import (  # noqa: E402
    load_chump,
    load_text,
    pack_chump,
    parse_text,
)
from chumpeditor.gui import (  # noqa: E402
    APP_TITLE,
    CREDIT,
    DROP_HINT,
    ICON_FILE,
    ChumpWindow,
)

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
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("info", title, text))),
    )
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("error", title, text))),
    )
    return shown


@pytest.fixture
def window(qapp):
    return ChumpWindow()


def copy(sample: str, folder: Path) -> Path:
    """A copy of a sample, because converting writes beside the input."""
    target = folder / sample
    target.write_bytes((SAMPLES / sample).read_bytes())
    return target


def rows(window: ChumpWindow) -> list[str]:
    return [window.file_list.item(row).text() for row in range(window.file_list.count())]


def label(window: ChumpWindow, name: str) -> QLabel:
    for child in window.findChildren(QLabel):
        if child.objectName() == name:
            return child
    raise AssertionError(f"no label named {name!r} in the window")


# ---------------------------------------------------------------------------
# window chrome
# ---------------------------------------------------------------------------
def test_the_window_is_titled_with_the_version(window):
    assert window.windowTitle() == APP_TITLE
    assert window.windowTitle().startswith("ChumpEditor ")


def test_the_three_buttons_are_the_ones_the_original_had(window):
    assert window.btn_expand.text() == "Expand chump"
    assert window.btn_remove.text() == "Remove item"
    assert window.btn_clear.text() == "Clear list"


def test_the_window_says_what_can_be_dropped_on_it(window):
    assert label(window, "dropHint").text() == DROP_HINT
    assert label(window, "credit").text() == CREDIT


def test_the_list_takes_drops(window):
    assert window.acceptDrops()


def test_the_icon_is_found_when_running_from_the_sources(window):
    # the taskbar icon is set from this file, so it has to be in the repository
    found = gui._resource_path(ICON_FILE)
    assert found is not None and Path(found).is_file()
    assert Path(found).name == ICON_FILE
    assert gui._window_icon() is not None
    assert gui._resource_path("no-such-icon.ico") is None


def test_nothing_can_be_acted_on_before_a_file_arrives(window):
    assert rows(window) == []
    assert not window.btn_expand.isEnabled()
    assert not window.btn_remove.isEnabled()
    assert not window.btn_clear.isEnabled()


# ---------------------------------------------------------------------------
# the queue
# ---------------------------------------------------------------------------
def test_files_of_both_forms_are_queued(window, tmp_path):
    chump = copy("config1.chump", tmp_path)
    text = copy("config2.txt", tmp_path)
    window.load_paths([str(chump), str(text)])
    assert rows(window) == [str(chump), str(text)]
    assert window.btn_expand.isEnabled()
    assert window.btn_clear.isEnabled()


def test_a_file_of_another_kind_is_left_out(window, tmp_path):
    notes = tmp_path / "notes.bin"
    notes.write_text("not a chump")
    window.load_paths([str(notes)])
    assert rows(window) == []


def test_a_folder_is_left_out(window, tmp_path):
    window.load_paths([str(tmp_path)])
    assert rows(window) == []


def test_a_file_that_is_not_there_is_left_out(window, tmp_path):
    window.load_paths([str(tmp_path / "gone.chump")])
    assert rows(window) == []


def test_a_file_queued_twice_is_queued_once(window, tmp_path):
    chump = copy("config1.chump", tmp_path)
    window.load_paths([str(chump)])
    window.load_paths([str(chump)])
    window.load_paths([str(chump), str(chump)])  # duplicates within one call too
    assert rows(window) == [str(chump)]


def test_one_file_has_one_row_whatever_spelling_it_arrives_with(window, tmp_path):
    chump = copy("config1.chump", tmp_path)
    window.load_paths([str(chump), os.path.join(str(chump.parent), ".", chump.name)])
    assert rows(window) == [str(chump)]


def test_removing_a_file_makes_room_to_queue_it_again(window, tmp_path):
    chump = copy("config1.chump", tmp_path)
    window.load_paths([str(chump)])
    window.file_list.setCurrentRow(0)
    window.remove_selected()
    assert rows(window) == []
    window.load_paths([str(chump)])
    assert rows(window) == [str(chump)]


def test_removing_takes_the_selected_row(window, tmp_path):
    """The VB original removed row 0 no matter which row was selected.

    The list picks one row at a time, so selecting the last one and checking
    that the first two survived is enough to pin the difference down.
    """
    for stem in ("config1", "config2", "config3"):
        copy(f"{stem}.chump", tmp_path)
    window.load_paths([str(tmp_path / f"{stem}.chump") for stem in ("config1", "config2", "config3")])
    window.file_list.setCurrentRow(2)
    window.remove_selected()
    assert rows(window) == [str(tmp_path / "config1.chump"), str(tmp_path / "config2.chump")]


def test_clearing_empties_the_list(window, tmp_path):
    copy("config1.chump", tmp_path)
    window.load_paths([str(tmp_path / "config1.chump")])
    window.clear_list()
    assert rows(window) == []
    assert not window.btn_expand.isEnabled()


def test_the_buttons_follow_the_selection(window, tmp_path):
    copy("config1.chump", tmp_path)
    copy("config2.chump", tmp_path)
    window.load_paths([str(tmp_path / "config1.chump"), str(tmp_path / "config2.chump")])
    assert not window.btn_remove.isEnabled()
    window.file_list.setCurrentRow(1)
    assert window.btn_remove.isEnabled()


def test_paths_handed_to_the_constructor_are_queued(window, tmp_path):
    chump = copy("config1.chump", tmp_path)
    started = ChumpWindow([str(chump)])
    assert rows(started) == [str(chump)]


def test_a_drop_of_nothing_usable_says_so(window, dialogs, tmp_path):
    notes = tmp_path / "notes.bin"
    notes.write_text("nope")
    window.load_paths([str(notes)])
    assert dialogs == [("info", "Ready", "Nothing to do: no .chump or .txt file among them.")]


# ---------------------------------------------------------------------------
# converting
# ---------------------------------------------------------------------------
def test_expand_turns_every_queued_chump_into_a_text_file(window, dialogs, tmp_path):
    source = copy("config1.chump", tmp_path)
    window.load_paths([str(source)])
    window.convert_all()
    written = tmp_path / "config1.txt"
    assert written.is_file()
    assert load_chump(source) == load_text(written)
    assert rows(window) == [f"{source}  ->  config1.txt"]
    assert dialogs == [("info", "Ready", "Wrote 1 file.")]


def test_expand_packs_a_queued_text_file_back_into_a_chump(window, dialogs, tmp_path):
    source = copy("config2.txt", tmp_path)
    window.load_paths([str(source)])
    window.convert_all()
    packed = tmp_path / "config2.chump"
    assert packed.read_bytes() == (SAMPLES / "config2.chump").read_bytes()
    assert dialogs == [("info", "Ready", "Wrote 1 file.")]


def test_both_forms_in_the_list_are_converted_in_one_press(window, dialogs, tmp_path):
    chump = copy("config3.chump", tmp_path)
    text = copy("config2.txt", tmp_path)
    window.load_paths([str(chump), str(text)])
    window.convert_all()
    assert parse_text((tmp_path / "config3.txt").read_text(encoding="utf-8-sig", newline="")) == (
        load_chump(chump)
    )
    assert (tmp_path / "config2.chump").read_bytes() == (SAMPLES / "config2.chump").read_bytes()
    assert dialogs == [("info", "Ready", "Wrote 2 files.")]


def test_the_expand_button_is_what_runs_it(window, dialogs, tmp_path):
    copy("config1.chump", tmp_path)
    window.load_paths([str(tmp_path / "config1.chump")])
    window.btn_expand.click()
    assert (tmp_path / "config1.txt").is_file()


def test_a_file_that_cannot_be_read_is_reported_and_kept(window, dialogs, tmp_path):
    broken = tmp_path / "broken.chump"
    broken.write_bytes(b"plain text, not a chump")
    window.load_paths([str(broken)])
    window.convert_all()
    assert rows(window) == [str(broken)]  # still in the list, unchanged
    assert not (tmp_path / "broken.txt").exists()
    kind, title, text = dialogs.pop()
    assert (kind, title) == ("error", "Error")
    assert str(broken) in text
    assert "not a chump file" in text


def test_one_bad_file_does_not_stop_the_good_ones(window, dialogs, tmp_path):
    good = copy("config1.chump", tmp_path)
    broken = tmp_path / "broken.chump"
    broken.write_bytes(b"nope")
    window.load_paths([str(broken), str(good)])
    window.convert_all()
    assert (tmp_path / "config1.txt").is_file()
    assert [kind for kind, _, _ in dialogs] == ["error"]  # no "wrote N files" either


def test_a_text_file_that_does_not_parse_is_reported(window, dialogs, tmp_path):
    broken = tmp_path / "broken.txt"
    broken.write_text("kuid-table\n{\n")
    window.load_paths([str(broken)])
    window.convert_all()
    assert not (tmp_path / "broken.chump").exists()
    assert "is never closed" in dialogs[-1][2]


# ---------------------------------------------------------------------------
# drag and drop
# ---------------------------------------------------------------------------
class _FakeMime:
    def __init__(self, urls):
        self._urls = urls

    def hasUrls(self):  # noqa: N802 - Qt naming
        return True

    def urls(self):
        return self._urls


class _FakeDrop:
    def __init__(self, paths):
        self._mime = _FakeMime([QUrl.fromLocalFile(p) for p in paths])
        self.accepted = False

    def mimeData(self):  # noqa: N802 - Qt naming
        return self._mime

    def acceptProposedAction(self):  # noqa: N802 - Qt naming
        self.accepted = True


def test_a_drop_of_files_queues_them(window, tmp_path):
    chump = copy("config1.chump", tmp_path)
    text = copy("config2.txt", tmp_path)
    event = _FakeDrop([str(chump), str(text)])
    window.dragEnterEvent(event)
    assert event.accepted
    window.dropEvent(event)
    # QUrl normalises separators, so compare as paths
    assert [Path(row) for row in rows(window)] == [chump, text]


def test_dropping_the_same_file_twice_queues_it_once(window, tmp_path):
    chump = copy("config1.chump", tmp_path)
    window.dropEvent(_FakeDrop([str(chump)]))
    window.dropEvent(_FakeDrop([str(chump)]))
    assert rows(window) == [str(chump)]


def test_dropping_something_unusable_leaves_the_list_alone(window, dialogs, tmp_path):
    window.dropEvent(_FakeDrop([str(tmp_path)]))
    assert rows(window) == []
    assert dialogs[0][2].startswith("Nothing to do")


def test_a_dropped_file_can_be_expanded_straight_away(window, dialogs, tmp_path):
    chump = copy("config2.chump", tmp_path)
    window.dropEvent(_FakeDrop([str(chump)]))
    window.convert_all()
    assert (tmp_path / "config2.txt").read_bytes() == (SAMPLES / "config2.txt").read_bytes()
    assert dialogs == [("info", "Ready", "Wrote 1 file.")]


# ---------------------------------------------------------------------------
# what a round trip through the window leaves behind
# ---------------------------------------------------------------------------
def test_expanding_and_packing_from_the_window_returns_the_original_bytes(window, tmp_path):
    for stem in ("config1", "config2", "config3"):
        copy(f"{stem}.chump", tmp_path)
    window.load_paths([str(tmp_path / f"{stem}.chump") for stem in ("config1", "config2", "config3")])
    window.convert_all()
    original = {stem: (SAMPLES / f"{stem}.chump").read_bytes() for stem in ("config1", "config2", "config3")}
    window.clear_list()
    window.load_paths([str(tmp_path / f"{stem}.txt") for stem in ("config1", "config2", "config3")])
    window.convert_all()
    for stem, data in original.items():
        assert pack_chump(load_text(tmp_path / f"{stem}.txt")) == data
