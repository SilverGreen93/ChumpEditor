"""Tests for the list of files opened lately.

Nothing here needs a window: the list is kept by ``recent.py``, which is free of
Qt like ``document.py``.  The GUI tests in ``test_gui.py`` cover the menu itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from chumpeditor.paths import APP_NAME, config_dir
from chumpeditor.recent import LIMIT, RecentFiles, recent_file


def named(folder: Path, which: str) -> Path:
    """A file that exists, so nobody is blamed for a file that is missing."""
    one = folder / which
    one.write_text("kuid <kuid:123:456>\n", encoding="utf-8")
    return one


def store(tmp_path: Path) -> RecentFiles:
    """A list kept in the scratch folder instead of your settings."""
    return RecentFiles(where=tmp_path / "recent.json")


# ---------------------------------------------------------------------------
# where the list is kept
# ---------------------------------------------------------------------------
def test_the_list_is_kept_in_the_programs_own_folder(tmp_path, monkeypatch):
    """One small JSON file beside the themes, not a setting in some registry."""
    monkeypatch.setattr("chumpeditor.recent.config_dir", lambda: tmp_path)
    assert recent_file() == tmp_path / "recent.json"


def test_that_folder_is_the_programs_name_under_the_users_own_one(tmp_path, monkeypatch):
    """``%LOCALAPPDATA%\\ChumpEditor`` on Windows, ``~/.config/ChumpEditor``
    elsewhere, which is where the themes are looked for as well."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    assert config_dir() == tmp_path / APP_NAME

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    assert config_dir() == tmp_path / APP_NAME


def test_the_folder_is_made_when_the_list_is_written(tmp_path):
    """Nobody hunts for the settings folder, so nothing exists before the first
    file is opened."""
    list_of = RecentFiles(where=tmp_path / "not" / "yet" / "recent.json")
    assert not list_of.where.parent.exists()
    list_of.remember(named(tmp_path, "config.txt"))
    assert list_of.where.is_file()
    assert list_of.broken == ""


# ---------------------------------------------------------------------------
# what the list holds
# ---------------------------------------------------------------------------
def test_there_is_no_list_before_anything_has_been_opened(tmp_path):
    list_of = store(tmp_path)
    assert list_of.paths() == []
    assert len(list_of) == 0
    assert list(list_of) == []
    assert not list_of.where.exists()  # looking is not the same as writing
    assert list_of.broken == ""


def test_a_file_opened_is_the_first_name_on_the_list(tmp_path):
    one = named(tmp_path, "config.txt")
    list_of = store(tmp_path)
    list_of.remember(one)
    assert list_of.paths() == [one]


def test_the_last_file_opened_is_the_first_name_on_the_list(tmp_path):
    first = named(tmp_path, "config1.txt")
    second = named(tmp_path, "config2.txt")
    list_of = store(tmp_path)
    list_of.remember(first)
    list_of.remember(second)
    assert list_of.paths() == [second, first]


def test_a_file_opened_twice_is_named_once(tmp_path):
    """The list says which files, not how often each of them was opened."""
    first = named(tmp_path, "config1.txt")
    second = named(tmp_path, "config2.txt")
    list_of = store(tmp_path)
    list_of.remember(first)
    list_of.remember(second)
    list_of.remember(first)
    assert list_of.paths() == [first, second]


def test_a_relative_name_lands_on_the_file_it_points_at(tmp_path, monkeypatch):
    """A path typed in a terminal and the same path from a dialog are one file."""
    one = named(tmp_path, "config.txt")
    monkeypatch.chdir(tmp_path)
    list_of = store(tmp_path)
    list_of.remember(Path(one.name))
    list_of.remember(Path(".") / one.name)
    assert list_of.paths() == [one]


def test_only_the_ten_most_recent_openings_are_kept(tmp_path):
    opened = [named(tmp_path, f"config{number}.txt") for number in range(LIMIT + 3)]
    list_of = store(tmp_path)
    for one in opened:
        list_of.remember(one)
    assert list_of.paths() == list(reversed(opened[-LIMIT:]))
    assert len(list_of) == LIMIT


def test_a_list_read_back_holds_no_more_than_the_limit(tmp_path):
    """A list written by a longer version is trimmed rather than shown in full."""
    where = tmp_path / "recent.json"
    too_many = [str(named(tmp_path, f"config{number}.txt")) for number in range(LIMIT + 4)]
    where.write_text(json.dumps(too_many), encoding="utf-8")
    assert len(RecentFiles(where=where)) == LIMIT


def test_clearing_the_list_forgets_every_name(tmp_path):
    list_of = store(tmp_path)
    list_of.remember(named(tmp_path, "config.txt"))
    list_of.clear()
    assert list_of.paths() == []
    assert json.loads(list_of.where.read_text(encoding="utf-8")) == []


def test_a_cleared_list_stays_cleared(tmp_path):
    list_of = store(tmp_path)
    list_of.remember(named(tmp_path, "config.txt"))
    list_of.clear()
    assert RecentFiles(where=list_of.where).paths() == []


def test_the_list_is_written_as_it_goes_and_read_back_by_the_next_opening(tmp_path):
    first = named(tmp_path, "config1.txt")
    second = named(tmp_path, "config2.txt")
    list_of = store(tmp_path)
    list_of.remember(first)
    list_of.remember(second)
    assert RecentFiles(where=list_of.where).paths() == [second, first]


# ---------------------------------------------------------------------------
# when the list itself is the problem
# ---------------------------------------------------------------------------
def test_a_list_that_is_not_written_as_a_list_is_said_and_done_without(tmp_path):
    where = tmp_path / "recent.json"
    where.write_text('{"not": "a list"}', encoding="utf-8")
    list_of = RecentFiles(where=where)
    assert list_of.paths() == []
    assert "recent files" in list_of.broken

    one = named(tmp_path, "config.txt")
    list_of.remember(one)
    assert list_of.paths() == [one]
    assert list_of.broken == ""  # writing it again put it right


def test_a_list_that_cannot_be_read_at_all_is_said_and_done_without(tmp_path):
    where = tmp_path / "recent.json"
    where.write_text("[this is not json", encoding="utf-8")
    list_of = RecentFiles(where=where)
    assert list_of.paths() == []
    assert "recent files" in list_of.broken


def test_a_list_holding_something_odd_ignores_that_name_and_keeps_the_rest(tmp_path):
    where = tmp_path / "recent.json"
    one = named(tmp_path, "config.txt")
    where.write_text(json.dumps([str(one), 7, "", None, {}]), encoding="utf-8")
    assert RecentFiles(where=where).paths() == [one]


def test_a_list_that_cannot_be_written_is_said_and_the_names_are_still_kept(tmp_path):
    """A list that will not go to disk is a lost convenience, nothing worse."""
    where = tmp_path / "recent.json"
    where.mkdir()  # a folder where the file should be: nothing can be written
    list_of = RecentFiles(where=where)
    one = named(tmp_path, "config.txt")
    list_of.remember(one)
    assert list_of.paths() == [one]
    assert "save" in list_of.broken
    assert RecentFiles(where=tmp_path / "other.json").paths() == []


def test_a_name_the_system_cannot_place_is_left_out_rather_than_guessed(tmp_path):
    list_of = store(tmp_path)
    list_of.remember(named(tmp_path, "config.txt"))
    list_of.remember(None)
    assert len(list_of) == 1
