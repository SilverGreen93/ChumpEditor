"""The colours of a theme, put on the text as it is written.

Qt only ever asks for one line at a time, so anything that carries across a
line break - an open string, an unclosed section - has to be remembered in the
state of each line.  ``chumpeditor.scan`` works that out along with which rule
owns which stretch of text; this only turns the answer into Qt formats and
hands it over.  The rules themselves are a plain JSON file described in
``chumpeditor.theme``, not something written in here.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from ..scan import scan_line
from ..theme import Style, Theme

__all__ = ["ThemeHighlighter"]


def _format(style: Style) -> QTextCharFormat:
    """A style of the theme in the form Qt paints with."""
    format = QTextCharFormat()
    format.setForeground(QColor(style.colour))
    if style.bold:
        format.setFontWeight(QFont.Weight.Bold)
    if style.italic:
        format.setFontItalic(True)
    return format


class ThemeHighlighter(QSyntaxHighlighter):
    """One editor's text, coloured by one theme."""

    def __init__(self, document, theme: Theme) -> None:
        super().__init__(document)
        self.theme = theme
        self.formats: dict[str, QTextCharFormat] = {}
        self._make_formats()

    def set_theme(self, theme: Theme) -> None:
        """Colour with a different theme, and recolour what is already there."""
        self.theme = theme
        self._make_formats()
        self.rehighlight()

    def _make_formats(self) -> None:
        """Built once per theme, since making a format is far from free and a
        line is asked for on every keystroke."""
        self.formats = {name: _format(style) for name, style in self.theme.styles.items()}

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt naming
        plain = self.formats.get("default")
        if plain is not None:  # the whole line first, so nothing keeps an old colour
            self.setFormat(0, len(text), plain)

        spans, state = scan_line(text, self.theme, self.previousBlockState())
        for span in spans:
            format = self.formats.get(span.style, plain)
            if format is not None:
                self.setFormat(span.start, span.length, format)
        self.setCurrentBlockState(state)
