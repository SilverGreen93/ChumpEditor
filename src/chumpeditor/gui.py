"""PyQt6 GUI for ChumpEditor.

A small window holding a queue of files: drop .chump files and .txt files on
it (or start it with paths on the command line) and press Expand chump to turn
every one of them into the other form next to it.  Remove item takes the
selected rows out of the queue, Clear list empties it.

The layout follows the original WinForms Chump expander; the difference is that
here the conversion runs in both directions, because reading the text form back
into a .chump is what makes the round trip useful.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .chump import CHUMP_SUFFIXES, TEXT_SUFFIXES, ChumpError, convert_file

__all__ = ["ChumpWindow", "run_gui"]

_ASSET_DIR = Path(__file__).resolve().parent.parent.parent / "assets"

APP_TITLE = f"ChumpEditor {__version__}"
ICON_FILE = "chumpeditor.ico"
DROP_HINT = "Drag & drop .chump and .txt files here"
CREDIT = "ChumpEditor, after the Chump expander by vvmm (c) 2016"


def _resource_path(name: str) -> str | None:
    """Absolute path to a bundled resource (works from source and PyInstaller)."""
    if getattr(sys, "frozen", False):  # running under PyInstaller
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / name
    else:
        base = _ASSET_DIR / name
    return str(base) if base.is_file() else None


def _window_icon() -> QIcon | None:
    """The app icon, if it can be found next to the code or in the bundle.

    Setting it on the application as well as the window is what puts it in the
    Windows taskbar; --icon alone only stamps the exe file on disk.
    """
    path = _resource_path(ICON_FILE)
    return QIcon(path) if path else None


def _lookup_key(path: str) -> str:
    """One comparable spelling for one path, for duplicate drop detection."""
    return os.path.normcase(os.path.normpath(path))


def _accepted(path: Path) -> bool:
    """A file the queue will take: one of the two forms, existing on disk."""
    return path.is_file() and path.suffix.lower() in CHUMP_SUFFIXES + TEXT_SUFFIXES


class ChumpWindow(QWidget):
    """The file queue and the three buttons acting on it."""

    def __init__(self, paths: list[str] | None = None) -> None:
        super().__init__()
        self._keys: set[str] = set()
        self._build()
        self.setAcceptDrops(True)
        if paths:
            self.load_paths(paths)

    # -- layout -------------------------------------------------------------
    def _build(self) -> None:
        self.setWindowTitle(APP_TITLE)
        icon = _window_icon()
        if icon:
            self.setWindowIcon(icon)
        self.resize(520, 340)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("File queue:"))
        self.file_list = QListWidget(self)
        self.file_list.setAlternatingRowColors(True)
        layout.addWidget(self.file_list, 1)

        hint = QLabel(DROP_HINT, self)
        hint.setObjectName("dropHint")
        hint.setStyleSheet("color: palette(mid)")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.btn_expand = QPushButton("Expand chump", self)
        self.btn_expand.setDefault(True)
        self.btn_remove = QPushButton("Remove item", self)
        self.btn_clear = QPushButton("Clear list", self)
        buttons.addWidget(self.btn_expand)
        buttons.addWidget(self.btn_remove)
        buttons.addWidget(self.btn_clear)
        layout.addLayout(buttons)

        credit = QLabel(CREDIT, self)
        credit.setObjectName("credit")
        credit.setStyleSheet("color: palette(mid)")
        layout.addWidget(credit)

        self.btn_expand.clicked.connect(self.convert_all)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear_list)
        self.file_list.itemSelectionChanged.connect(self._update_buttons)
        self._update_buttons()

    def _update_buttons(self) -> None:
        rows = self.file_list.count()
        self.btn_expand.setEnabled(bool(rows))
        self.btn_remove.setEnabled(bool(self.file_list.selectedItems()))
        self.btn_clear.setEnabled(bool(rows))

    # -- queue --------------------------------------------------------------
    def load_paths(self, paths: list[str]) -> None:
        """Queue every accepted path, ignoring the rest."""
        added = 0
        for path in paths:
            if self._add_file(path):
                added += 1
        if not added:
            self._info("Nothing to do: no .chump or .txt file among them.")

    def _add_file(self, path: str) -> bool:
        key = _lookup_key(path)
        if key in self._keys:
            return False  # the exact same file is already queued
        file = Path(path)
        if not _accepted(file):
            return False
        self._keys.add(key)
        self.file_list.addItem(str(file))
        self._update_buttons()
        return True

    def remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            self._keys.discard(_lookup_key(item.text()))
            self.file_list.takeItem(self.file_list.row(item))
        self._update_buttons()

    def clear_list(self) -> None:
        self.file_list.clear()
        self._keys.clear()
        self._update_buttons()

    # -- actions ------------------------------------------------------------
    def convert_all(self) -> None:
        """Convert every queued file into the other form, next to it."""
        done = 0
        failed = 0
        for row in range(self.file_list.count()):
            path = self.file_list.item(row).text()
            try:
                target = convert_file(path)
            except (OSError, ChumpError) as exc:
                failed += 1
                self._error(exc, path)
            else:
                done += 1
                self.file_list.item(row).setText(f"{path}  ->  {target.name}")
        if done and not failed:
            self._info(f"Wrote {done} file{'s' if done > 1 else ''}.")

    # -- drag and drop ------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.load_paths(paths)

    # -- messages -----------------------------------------------------------
    def _error(self, exc: Exception, path: str) -> None:
        QMessageBox.critical(self, "Error", f"{path}\n{exc}")

    def _info(self, text: str) -> None:
        QMessageBox.information(self, "Ready", text)


def run_gui(paths: list[str] | None = None) -> int:
    """Launch the GUI. Returns the process exit code."""
    app = QApplication(sys.argv[:1])
    icon = _window_icon()
    if icon:
        app.setWindowIcon(icon)
    window = ChumpWindow(paths)
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``chumpeditor-gui`` script."""
    if argv is None:
        argv = sys.argv[1:]
    return run_gui(argv)


if __name__ == "__main__":
    sys.exit(run_gui())
