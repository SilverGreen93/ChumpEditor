"""The window: one file at a time, shown in one rich text area.

There is no queue here and nothing is converted beside it any more.  A file
arrives - named on the command line, dropped on the window, picked in the Open
dialog - its text form goes into the editor, and the window's title says which
file that is and whether it has been changed since it was written.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QMainWindow, QMessageBox

from ..chump import ChumpError
from ..document import is_readable, read_document
from .editor import RichTextEditor
from .resources import APP_TITLE, SUMMARY, window_icon

__all__ = ["ChumpWindow", "WINDOW_SIZE"]

#: the starting size: wide enough for a value on column 40 plus its text
WINDOW_SIZE = (940, 660)

#: what the title shows before any file is in the editor
UNTITLED = "Untitled"


class ChumpWindow(QMainWindow):
    """The editor, the title, and the messages the window can give."""

    def __init__(self, paths: list[str] | None = None) -> None:
        super().__init__()
        self.path: Path | None = None

        self.editor = RichTextEditor(self)
        self.setCentralWidget(self.editor)

        self.setWindowTitle(APP_TITLE)
        icon = window_icon()
        if icon:
            self.setWindowIcon(icon)
        self.resize(*WINDOW_SIZE)

        # the star in the title follows the document's own idea of being changed
        self.editor.document().modificationChanged.connect(lambda _changed: self._refresh_title())

        self.statusBar().showMessage(SUMMARY)

        if paths:
            self.open_paths(paths)
        self._refresh_title()

    # -- opening ------------------------------------------------------------
    def open_path(self, path: str | Path) -> Path:
        """Show one file in the editor; it stays where it is until saved.

        Raises what the codec raises - a file that is not a chump, or a chump
        that is damaged - so the caller decides how loudly to complain.
        """
        text = read_document(path)
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.path = Path(path)
        self._refresh_title()
        self.say(f"Opened {self.path.name}")
        return self.path

    def open_file(self, path: str | Path) -> bool:
        """The same, with the failure made visible instead of raised.

        Every way a file reaches the editor - command line, drop, Open dialog -
        ends up here, because a file that will not open deserves a dialog
        either way.
        """
        try:
            self.open_path(path)
        except (OSError, ChumpError) as exc:
            self.error(f"{path}\n{exc}")
            return False
        return True

    def open_paths(self, paths: list[str]) -> Path | None:
        """Open the first usable path; one document at a time is the rule here.

        Whatever else was dropped or named is reported rather than quietly
        dropped, because "where is the file I just dropped?" is a bad question
        to have to ask.
        """
        usable = [path for path in paths if is_readable(path)]
        if not usable:
            if paths:
                self.say("Nothing to open: no .chump, .cdp or .txt among them")
            return None

        if not self.open_file(usable[0]):
            return None
        opened = self.path
        extra = len(usable) - 1
        if extra:
            skipped = ", ".join(Path(path).name for path in usable[1:])
            self.say(f"Opened {opened.name}; one file at a time, so not {skipped}")
        return opened

    # -- messages -----------------------------------------------------------
    def say(self, text: str) -> None:
        """A line in the status bar: what just happened, or what to do next."""
        self.statusBar().showMessage(text)

    def error(self, message: str) -> None:
        """Something went wrong and the editor is not going to show it itself."""
        QMessageBox.critical(self, "Error", message)

    def _refresh_title(self) -> None:
        """The file's name, a star while it is unsaved, and the version."""
        name = self.path.name if self.path else UNTITLED
        star = " *" if self.editor.document().isModified() else ""
        self.setWindowTitle(f"{name}{star} - {APP_TITLE}")
