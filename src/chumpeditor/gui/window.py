"""The window: one file at a time, shown in one rich text area.

There is no queue here and nothing is converted beside it any more.  A file
arrives - named on the command line, dropped on the window, picked in the Open
dialog - its text form goes into the editor, and the window's title says which
file that is and whether it has been changed since it was written.

Writing the file back is the window's decision, not the editor's: *Save chump*
packs the text into a binary file and *Export txt* writes the text form, and
whichever was last written becomes the file the window is talking about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PyQt6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from ..chump import ChumpError
from ..document import (
    CHUMP_GROUP,
    TEXT_GROUP,
    filter_string,
    is_readable,
    read_document,
    save_chump,
    save_text,
    suggested_path,
)
from .about import ABOUT_TITLE, about_html
from .drops import accept_file_drop, dropped_paths
from .editor import RichTextEditor
from .menus import build_menus
from .resources import APP_TITLE, DISPLAY_NAME, DROP_HINT, window_icon

__all__ = ["CHUMP_WRITE", "ChumpWindow", "TEXT_WRITE", "UNTITLED", "WINDOW_SIZE"]

#: the starting size: wide enough for a value on column 40 plus its text
WINDOW_SIZE = (940, 660)

#: what the title shows before any file is in the editor
UNTITLED = "Untitled"


@dataclass(frozen=True)
class WriteForm:
    """One of the two ways the text on screen can be written out."""

    #: what the menu item is called, and what the save dialog is titled
    verb: str
    #: what the status bar says once it has been done
    done: str
    #: the extension a file of this form has
    suffix: str
    #: the extension the save dialog offers, and nothing else
    group: tuple[str, tuple[str, ...]]
    #: the function that does the writing
    write: Callable[[str, Path], Path]


CHUMP_WRITE = WriteForm("Save chump", "Saved", ".chump", CHUMP_GROUP, save_chump)
TEXT_WRITE = WriteForm("Export txt", "Exported", ".txt", TEXT_GROUP, save_text)


class ChumpWindow(QMainWindow):
    """The editor, the title, and the messages the window can give."""

    def __init__(self, paths: list[str] | None = None) -> None:
        super().__init__()
        self.path: Path | None = None
        #: the folder the last file came from or went to, to start a dialog in
        self._folder: Path | None = None
        self._message = ""

        self.editor = RichTextEditor(self)
        self.setCentralWidget(self.editor)

        self.setWindowTitle(APP_TITLE)
        icon = window_icon()
        if icon:
            self.setWindowIcon(icon)
        self.resize(*WINDOW_SIZE)
        build_menus(self)

        # the star in the title follows the document's own idea of being changed
        self.editor.document().modificationChanged.connect(lambda _changed: self._refresh_title())

        # a file can be let go anywhere in the window, the text included
        self.setAcceptDrops(True)
        self.editor.files_dropped.connect(self.open_paths)
        self.editor.files_dragging.connect(self._drop_hint)

        self.say(DROP_HINT)

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
        self._folder = self.path.parent
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
        to have to ask.  Asking before replacing is what keeps a drop from
        wiping work that was never written out.
        """
        usable = [path for path in paths if is_readable(path)]
        if not usable:
            if paths:
                self.say("Nothing to open: no .chump, .cdp or .txt among them")
            return None
        if not self._ok_to_replace():
            return None

        if not self.open_file(usable[0]):
            return None
        opened = self.path
        extra = len(usable) - 1
        if extra:
            skipped = ", ".join(Path(path).name for path in usable[1:])
            self.say(f"Opened {opened.name}; one file at a time, so not {skipped}")
        return opened

    # -- the menus ------------------------------------------------------------
    def prompt_open(self) -> None:
        """File > Open: ask for a file, then open it if that is allowed.

        Asking first is what makes the menu safe to press with work in the
        editor: opening replaces the text without saving it.
        """
        if not self._ok_to_replace():
            return
        name, _chosen = QFileDialog.getOpenFileName(
            self, "Open file", self._folder_name(), filter_string()
        )
        if name:
            self.open_file(name)

    def save(self, *, ask: bool = False) -> Path | None:
        """File > Save chump: the text back into a binary config file."""
        return self._write(CHUMP_WRITE, ask)

    def export(self, *, ask: bool = False) -> Path | None:
        """File > Export txt: the text as a .txt file, spacing and all."""
        return self._write(TEXT_WRITE, ask)

    def about(self) -> None:
        """Help > About: what this is, and where it comes from."""
        QMessageBox.about(self, ABOUT_TITLE, about_html())

    def _write(self, form: WriteForm, ask: bool) -> Path | None:
        """Write out in one form, and make that the file being edited.

        The file changes identity because that is what the window has been
        asked for: exporting a chump to text leaves the text on screen, and so
        the text file is the one it now belongs to.
        """
        target = self._target(form, ask)
        if target is None:
            return None
        try:
            form.write(self.editor.toPlainText(), target)
        except (OSError, ChumpError) as exc:
            self.error(f"{target}\n{exc}")
            return None
        self.path = target
        self._folder = target.parent
        self.editor.document().setModified(False)
        self._refresh_title()
        self.say(f"{form.done} {target.name}")
        return target

    def _target(self, form: WriteForm, ask: bool) -> Path | None:
        """The file to write: the one being edited, or one just now chosen."""
        if not ask and self.path and self.path.suffix.lower() == form.suffix:
            return self.path

        start = suggested_path(self.path, form.suffix)
        name, _chosen = QFileDialog.getSaveFileName(
            self,
            form.verb,
            str(start) if start else self._folder_name(),
            filter_string(form.group),
        )
        if not name:
            return None
        target = Path(name)
        return target if target.suffix else target.with_suffix(form.suffix)

    def _folder_name(self) -> str:
        """Where a dialog starts: the folder of the last file, or nowhere."""
        return str(self._folder) if self._folder else ""

    def _ok_to_replace(self) -> bool:
        """Whether the editor may be cleared, asking first if anything is at risk."""
        if not self.editor.document().isModified():
            return True
        name = self.path.name if self.path else UNTITLED
        return self._confirm(f"Discard the changes to {name}?")

    def _confirm(self, question: str) -> bool:
        """A yes or no the user answers; anything else counts as no."""
        return (
            QMessageBox.question(self, DISPLAY_NAME, question)
            == QMessageBox.StandardButton.Yes
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Closing throws away unsaved work, so it is worth one more question."""
        if self._ok_to_replace():
            event.accept()
        else:
            event.ignore()

    # -- drag and drop ------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if accept_file_drop(event):
            self._drop_hint(True)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        accept_file_drop(event)  # without this the drop is never offered

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._drop_hint(False)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if accept_file_drop(event):
            self.open_paths(dropped_paths(event.mimeData()))

    def _drop_hint(self, active: bool) -> None:
        """Offer the hint while a file hovers, and give the line back after."""
        self.statusBar().showMessage(DROP_HINT if active else self._message)

    # -- messages -----------------------------------------------------------
    def say(self, text: str) -> None:
        """A line in the status bar: what just happened, or what to do next."""
        self._message = text
        self.statusBar().showMessage(text)

    def error(self, message: str) -> None:
        """Something went wrong and the editor is not going to show it itself."""
        QMessageBox.critical(self, "Error", message)

    def _refresh_title(self) -> None:
        """The file's name, a star while it is unsaved, and the version."""
        name = self.path.name if self.path else UNTITLED
        star = " *" if self.editor.document().isModified() else ""
        self.setWindowTitle(f"{name}{star} - {APP_TITLE}")
