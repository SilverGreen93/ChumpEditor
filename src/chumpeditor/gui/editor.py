"""The text area the window is built around.

One rich text document, not a queue of files.  Rich text because a hand-made
bold, italic or colour, and anything pasted in carrying them, has to survive -
a plain text edit could not hold any of that.  The keyword colours themselves
are paint laid over the text from a theme file by ``gui.highlighter``, so
nothing about them is written in here either; everything about the file the
text came from is the window's business, not this widget's.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QTextEdit

from ..theme import Theme, default_theme
from .drops import accept_file_drop, dropped_paths
from .highlighter import ThemeHighlighter

__all__ = ["RichTextEditor", "code_font"]

#: tried in order; the first one the system has is used as-is
PREFERRED_MONO = (
    "Cascadia Mono",
    "Consolas",
    "SF Mono",
    "Menlo",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Courier New",
)

FONT_POINT_SIZE = 11


def code_font() -> QFont:
    """A fixed-width font, so the column-40 values of a config line up."""
    have = {family.lower() for family in QFontDatabase.families()}
    family = next((name for name in PREFERRED_MONO if name.lower() in have), None)
    font = QFont(family) if family else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    font.setPointSize(FONT_POINT_SIZE)
    return font


class RichTextEditor(QTextEdit):
    """The document: editable, colourable, and it knows how it is displayed."""

    #: local paths dropped straight onto the text, which the window opens
    files_dropped = pyqtSignal(list)
    #: a file drag is over the text (True) or has left it (False)
    files_dragging = pyqtSignal(bool)

    def __init__(self, parent=None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(True)  # colours and attributes stay in the document
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(code_font())
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setAcceptDrops(True)  # a file lands here as often as on the frame
        self.highlighter = ThemeHighlighter(self.document(), theme or default_theme())

    def set_theme(self, theme: Theme) -> None:
        """Change the colours, and put the new ones over the text."""
        self.highlighter.set_theme(theme)

    def set_line_wrap(self, wrap: bool) -> None:
        """Wrapped for reading, straight for keeping the columns honest."""
        self.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if wrap else QTextEdit.LineWrapMode.NoWrap
        )

    # -- drag and drop ------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if accept_file_drop(event):
            self.files_dragging.emit(True)
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if not accept_file_drop(event):
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.files_dragging.emit(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Files go to the window; anything else is QTextEdit's own business.

        Without this a dropped file would be inserted into the text as a line
        of path names, since that is what a text edit does with urls.
        """
        self.files_dragging.emit(False)
        if not accept_file_drop(event):
            super().dropEvent(event)
            return
        self.files_dropped.emit(dropped_paths(event.mimeData()))
