"""The files this program was last asked to open.

People work on one or two configuration files at a time, editing and checking
the same thing over an afternoon.  Rather than make them find it in a folder
again, the file menu lists the last few, newest first.

Free of Qt like :mod:`chumpeditor.document`, so the list can be read, tested
and written without a window.  It lives as one small JSON file in the folder
the program keeps its own settings in, next to the themes:
``%LOCALAPPDATA%\\ChumpEditor\\recent.json`` on Windows,
``~/.config/ChumpEditor/recent.json`` elsewhere.
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import config_dir

__all__ = ["LIMIT", "RecentFiles", "recent_file"]

#: how many names the menu shows.  More than this stops being a shortcut and
#: becomes a list nobody reads.
LIMIT = 10

#: the list's own file, named after what is in it
RECENT_NAME = "recent.json"


def recent_file() -> Path:
    """Where the list is kept: ``recent.json`` in the settings folder."""
    return config_dir() / RECENT_NAME


class RecentFiles:
    """The last files opened, newest first, no more than ``limit`` of them.

    Reading and writing never raise.  No list yet is simply an empty one, and a
    list that cannot be read or written is left in ``broken`` so the window can
    say so in the status bar instead of spoiling the file a person is working on.

    By default the list is read from and written to :func:`recent_file`; pass
    ``where`` to keep it somewhere else, which is how the tests avoid writing
    in your settings folder.
    """

    def __init__(self, limit: int = LIMIT, where: Path | None = None):
        self.limit = limit
        self.where = _steady(where) or recent_file()
        self.broken = ""
        self._paths = self._read()

    def __len__(self) -> int:
        return len(self._paths)

    def __iter__(self):
        return iter(self._paths)

    def paths(self) -> list[Path]:
        """The names, newest first."""
        return list(self._paths)

    def remember(self, path: Path) -> None:
        """Put ``path`` at the top of the list and save it.

        Opening a file twice does not list it twice: the older entry goes so the
        names stay a record of which files, not of how often they were opened.
        Anything past the limit falls off the end.
        """
        wanted = _steady(path)
        if wanted is None:
            return
        keep = [one for one in self._paths if _steady(one) != wanted]
        self._save([wanted, *keep][: self.limit])

    def clear(self) -> None:
        """Forget every name, and write the empty list so it stays forgotten."""
        self._save([])

    def _read(self) -> list[Path]:
        self.broken = ""
        if not self.where.is_file():
            return []
        try:
            listed = json.loads(self.where.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.broken = f"ChumpEditor could not read the list of recent files: {exc}"
            return []
        if not isinstance(listed, list):
            self.broken = "the list of recent files is not in the shape ChumpEditor expects"
            return []
        return [Path(one) for one in listed if isinstance(one, str) and one][: self.limit]

    def _save(self, paths: list[Path]) -> None:
        self._paths = paths
        self.broken = ""  # what the last read said is not this write's business
        try:
            self.where.parent.mkdir(parents=True, exist_ok=True)
            self.where.write_text(
                json.dumps([str(one) for one in paths], indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            self.broken = f"ChumpEditor could not save the list of recent files: {exc}"


def _steady(path: Path | None) -> Path | None:
    """One way of naming ``path``, so the same file opened twice counts once.

    Made absolute because a file opened from a terminal, from a drag, and from
    the menu do not have to be spelled alike.  A name the system cannot place at
    all is dropped rather than guessed at.
    """
    if path is None:
        return None
    try:
        return Path(path).expanduser().resolve()
    except OSError:
        return None
