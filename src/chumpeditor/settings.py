"""What the program remembers about itself between one run and the next.

The list of files opened lately is kept in ``recent.py``; this is for the rest -
the panels a person left standing out or put away, and anything else of that
kind.  Like ``recent.py`` it is free of Qt, so a setting can be read, written and
tested without a window, and it lives as one small JSON file in the folder the
program keeps its own files in, next to the themes and the list of recent files:
``%APPDATA%\\ChumpEditor\\settings.json`` on Windows,
``~/.config/ChumpEditor/settings.json`` elsewhere.

One file rather than one per setting, because it is all one person's preferences
and one place is one thing to look at, edit or delete.  Reading and writing never
raise: no file yet is an empty set of settings, and a file that cannot be read or
written leaves the reason in ``broken`` for the window to put in the status bar,
the same way a broken list of recent files is handled.

The file is written as it is read, plus whatever is asked for: keys this version
does not know about are kept rather than dropped, so a settings file written by a
newer build still says what it said when this one opens it again.
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import config_dir

__all__ = ["SETTINGS_NAME", "Settings", "settings_file"]

#: the settings' own file, named after what is in it
SETTINGS_NAME = "settings.json"


def _answers_for(value, as_: type) -> bool:
    """Does ``value`` count as an instance of ``as_``?"""
    if as_ is bool:
        return isinstance(value, bool)
    if as_ in (int, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, as_)


def settings_file() -> Path:
    """Where the settings are kept: ``settings.json`` in the settings folder."""
    return config_dir() / SETTINGS_NAME


class Settings:
    """The handful of things worth remembering, read once and written on changes.

    A setting is a name and a value; ``get`` answers with what was asked for
    rather than raising when there is none, so the caller says what it would do
    anyway:

    >>> settings = Settings()
    >>> settings.get("treeview", False)
    False

    By default the file is read from and written to :func:`settings_file`; pass
    ``where`` to keep it somewhere else, which is how the tests avoid writing in
    your settings folder.
    """

    def __init__(self, where: Path | None = None) -> None:
        self.where = where or settings_file()
        #: why the file could not be read or written, empty when it could
        self.broken = ""
        self._values = self._read()

    def get(self, name: str, default=None, *, as_: type | None = None):
        """The value of ``name``, or ``default`` if nothing remembers it.

        Pass ``as_`` for the kind of value that was asked for - ``bool``, say -
        and a value of any other kind counts as nothing remembering it.  A
        settings file is a text file somebody can edit by hand, so
        ``"treeview": "yes please"`` is a mistake rather than a decision, and the
        caller would otherwise have to take a string for a boolean simply because
        a non-empty string is true.

        The kinds are asked for plainly: a number answers for a float, and
        ``True`` or ``False`` does not answer for a number, since counting a
        ticked panel as an amount is never what was meant.
        """
        if name not in self._values:
            return default
        value = self._values[name]
        if as_ is None or _answers_for(value, as_):
            return value
        return default

    def set(self, name: str, value) -> None:
        """Remember ``value`` for ``name``, and write the file.

        Writing the whole file each time is enough for a handful of settings, and
        it means a program that stops halfway through has written everything it
        knew rather than part of one change.
        """
        if self._values.get(name) == value:
            return
        self._values[name] = value
        self._save()

    def _read(self) -> dict:
        self.broken = ""
        if not self.where.is_file():
            return {}
        try:
            written = json.loads(self.where.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.broken = f"ChumpEditor could not read its settings: {exc}"
            return {}
        if not isinstance(written, dict):
            self.broken = "the settings file is not in the shape ChumpEditor expects"
            return {}
        return dict(written)

    def _save(self) -> None:
        self.broken = ""  # what the last read said is not this write's business
        try:
            self.where.parent.mkdir(parents=True, exist_ok=True)
            self.where.write_text(
                json.dumps(self._values, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            self.broken = f"ChumpEditor could not save its settings: {exc}"

