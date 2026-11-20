"""The colours of a theme, put on the text as it is written.

Qt only ever asks for one line at a time, so anything that carries across a
line break - an open string, an unclosed section - has to be remembered in the
state of each line.  ``chumpeditor.scan`` works that out along with which rule
owns which stretch of text; this only turns the answer into Qt formats and
hands it over.  The rules themselves are a plain JSON file described in
``chumpeditor.theme``, not something written in here.

A style can be coloured twice, once for a light background and once for a dark
one, and only one of them can be painted at a time: the editor says which by
way of ``set_dark``, because the editor is the one that knows what colour it
displays its text on.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from ..scan import scan_line
from ..theme import Style, Theme

__all__ = ["ThemeHighlighter"]


def _format(style: Style, dark: bool = False) -> QTextCharFormat:
    """A style of the theme in the form Qt paints with."""
    format = QTextCharFormat()
    format.setForeground(QColor(style.colour_for(dark)))
    if style.bold:
        format.setFontWeight(QFont.Weight.Bold)
    if style.italic:
        format.setFontItalic(True)
    return format


class ThemeHighlighter(QSyntaxHighlighter):
    """One editor's text, coloured by one theme."""

    def __init__(self, document, theme: Theme, dark: bool = False) -> None:
        super().__init__(document)
        self.theme = theme
        #: which half of the theme is being painted: dark background or light
        self.dark = dark
        self.formats: dict[str, QTextCharFormat] = {}
        self._make_formats()

    def set_theme(self, theme: Theme) -> None:
        """Colour with a different theme, and recolour what is already there."""
        self.theme = theme
        self._make_formats()
        self.rehighlight()

    def set_dark(self, dark: bool) -> None:
        """Paint with the dark colours, or with the light ones again."""
        if dark == self.dark:
            return
        self.dark = dark
        self._make_formats()
        self.rehighlight()

    def _make_formats(self) -> None:
        """Built once per theme and background, since making a format is far
        from free and a line is asked for on every keystroke."""
        self.formats = {
            name: _format(style, self.dark) for name, style in self.theme.styles.items()
        }

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
