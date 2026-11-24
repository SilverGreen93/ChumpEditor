"""Tests for the settings the program keeps between one run and the next.

Nothing here needs a window: the settings are kept by ``settings.py``, which is
free of Qt like ``recent.py``.  The GUI tests in ``test_gui.py`` cover what the
window does with them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from chumpeditor.paths import APP_NAME, config_dir
from chumpeditor.settings import Settings, settings_file


def store(tmp_path: Path) -> Settings:
    """Settings kept in the scratch folder instead of your own."""
    return Settings(where=tmp_path / "settings.json")


# ---------------------------------------------------------------------------
# where the settings are kept
# ---------------------------------------------------------------------------
def test_the_settings_are_kept_in_the_programs_own_folder(tmp_path, monkeypatch):
    """One small JSON file beside the themes and the list of recent files."""
    monkeypatch.setattr("chumpeditor.settings.config_dir", lambda: tmp_path)
    assert settings_file() == tmp_path / "settings.json"


def test_that_folder_is_the_programs_name_under_the_users_own_one(tmp_path, monkeypatch):
    """``%APPDATA%\\ChumpEditor`` on Windows, ``~/.config/ChumpEditor``
    elsewhere, which is where the themes and recent files are as well."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    assert config_dir() == tmp_path / APP_NAME

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    assert config_dir() == tmp_path / APP_NAME


def test_the_folder_is_made_when_a_setting_is_written(tmp_path):
    """Looking at the settings leaves nothing behind; changing one does."""
    kept = Settings(where=tmp_path / "not" / "yet" / "settings.json")
    assert not kept.where.parent.exists()
    kept.set("treeview", True)
    assert kept.where.is_file()
    assert kept.broken == ""


# ---------------------------------------------------------------------------
# what the settings hold
# ---------------------------------------------------------------------------
def test_there_are_no_settings_before_anything_has_been_remembered(tmp_path):
    kept = store(tmp_path)
    assert kept.get("treeview") is None
    assert kept.get("treeview", False) is False
    assert not kept.where.exists()  # looking is not the same as writing
    assert kept.broken == ""


def test_a_setting_is_remembered_and_read_back(tmp_path):
    kept = store(tmp_path)
    kept.set("treeview", True)
    assert kept.get("treeview") is True
    assert Settings(where=kept.where).get("treeview") is True


def test_a_setting_written_twice_is_the_one_that_was_written_last(tmp_path):
    kept = store(tmp_path)
    kept.set("treeview", True)
    kept.set("treeview", False)
    assert kept.get("treeview") is False
    assert Settings(where=kept.where).get("treeview") is False


def test_several_settings_live_in_the_one_file(tmp_path):
    kept = store(tmp_path)
    kept.set("treeview", True)
    kept.set("something_else", 4)
    assert json.loads(kept.where.read_text(encoding="utf-8")) == {
        "something_else": 4, "treeview": True,
    }


def test_a_setting_unchanged_writes_nothing(tmp_path):
    """Remembering what is already remembered is not a change to the file."""
    kept = store(tmp_path)
    kept.set("treeview", True)
    written = kept.where.read_bytes()
    kept.set("treeview", True)
    assert kept.where.read_bytes() == written


def test_a_file_is_written_as_it_goes_and_read_by_the_next_opening(tmp_path):
    first = store(tmp_path)
    first.set("treeview", True)
    again = Settings(where=first.where)
    assert again.get("treeview", False) is True


# ---------------------------------------------------------------------------
# a settings file somebody can edit by hand
# ---------------------------------------------------------------------------
def test_a_key_nobody_here_knows_is_kept_rather_than_dropped(tmp_path):
    """A settings file written by a newer build still says what it said.

    Writing the file takes everything that was read, so a setting this version
    does not know about travels through unchanged instead of being quietly lost.
    """
    where = tmp_path / "settings.json"
    where.write_text(
        json.dumps({"a_later_version": {"wide": True}, "treeview": True}), encoding="utf-8"
    )
    kept = Settings(where=where)
    assert kept.get("treeview") is True
    kept.set("treeview", False)
    assert json.loads(where.read_text(encoding="utf-8")) == {
        "a_later_version": {"wide": True}, "treeview": False,
    }


def test_a_value_of_the_wrong_shape_is_nothing_remembered(tmp_path):
    """``"treeview": "yes please"`` typed into the file is a mistake, not a choice.

    Asked for as it was asked for - ``as_=bool`` - and anything that is not one
    counts as nothing having been remembered, so the caller gets its own answer
    rather than whatever happens to be true about a string.
    """
    where = tmp_path / "settings.json"
    where.write_text(
        json.dumps({"treeview": "yes please", "width": "wide"}), encoding="utf-8"
    )
    kept = Settings(where=where)
    assert kept.get("treeview", False, as_=bool) is False
    assert kept.get("width", 940, as_=int) == 940
    # what the file does hold is still there for anyone who asked differently
    assert kept.get("treeview") == "yes please"


def test_a_number_is_not_a_tick_and_a_tick_is_not_a_number(tmp_path):
    """A panel that stands out or not is answered by ``true`` or ``false``.

    JSON writes ``1`` and ``true`` as different things, and a file somebody edits
    by hand should say which of the two it means; a number asked for as a boolean
    is nothing remembered rather than a lucky accident.
    """
    where = tmp_path / "settings.json"
    where.write_text(json.dumps({"treeview": 1, "width": True}), encoding="utf-8")
    kept = Settings(where=where)
    assert kept.get("treeview", False, as_=bool) is False
    assert kept.get("width", 940, as_=int) == 940


# ---------------------------------------------------------------------------
# when the settings file itself is the problem
# ---------------------------------------------------------------------------
def test_a_file_that_is_not_json_is_said_and_done_without(tmp_path):
    where = tmp_path / "settings.json"
    where.write_text("[this is not json", encoding="utf-8")
    kept = Settings(where=where)
    assert kept.get("treeview", False) is False
    assert "settings" in kept.broken

    kept.set("treeview", True)
    assert kept.get("treeview") is True
    assert kept.broken == ""  # writing it again put it right


def test_a_file_that_is_not_a_set_of_names_is_said_and_done_without(tmp_path):
    where = tmp_path / "settings.json"
    where.write_text('["not", "a", "set"]', encoding="utf-8")
    kept = Settings(where=where)
    assert kept.get("treeview") is None
    assert "shape" in kept.broken


def test_a_file_that_cannot_be_written_is_said_and_the_setting_is_still_kept(tmp_path):
    """A setting that will not go to disk is a lost convenience, nothing worse."""
    where = tmp_path / "settings.json"
    where.mkdir()  # a folder where the file should be: nothing can be written
    kept = Settings(where=where)
    kept.set("treeview", True)
    assert kept.get("treeview") is True
    assert "save" in kept.broken
