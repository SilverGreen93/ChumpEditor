"""The text area the window is built around.

One rich text document, not a queue of files.  Rich text because the colouring
of step 4 - and any hand-made bold, italic or colour - lives in the document
itself, which a plain text edit could not hold.  Everything about the file the
text came from is the window's business, not this widget's.
"""

from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QTextEdit

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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(True)  # colours and attributes stay in the document
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(code_font())
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

    def set_line_wrap(self, wrap: bool) -> None:
        """Wrapped for reading, straight for keeping the columns honest."""
        self.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if wrap else QTextEdit.LineWrapMode.NoWrap
        )
