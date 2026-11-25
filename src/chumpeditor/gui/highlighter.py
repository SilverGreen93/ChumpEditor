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

Qt hands over one line at a time, but a theme that colours every container needs
to know what the line below says - the ``{`` that opens a container is often
written on a line of its own - so the next line is passed to the scanner.  That
answer can arrive after the line above was coloured, so a changed line sends its
name above off to be coloured again, once the highlighter has finished with it.
"""

from __future__ import annotations

import re

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from ..scan import scan_line
from ..theme import Style, Theme

__all__ = ["ThemeHighlighter"]

#: a line holding one name and nothing else, which is the shape that a brace on
#: the line below can turn into a container
_NAME = re.compile(r"\s*[^\s{}]+\s*")


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
        #: whether a change is one of our own colours, which nobody has to answer
        self._our_own = False
        self._make_formats()
        #: connected after Qt connected its own, so this one runs once the line
        #: that changed has been coloured; see _recolour_the_line_above
        document.contentsChange.connect(self._recolour_the_line_above)

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

        block = self.currentBlock()
        below = block.next().text() if block.next().isValid() else ""
        spans, state = scan_line(text, self.theme, self.previousBlockState(), below)
        for span in spans:
            format = self.formats.get(span.style, plain)
            if format is not None:
                self.setFormat(span.start, span.length, format)
        self.setCurrentBlockState(state)

    def _recolour_the_line_above(self, position: int, removed: int, added: int) -> None:
        """Colour the line above again, when this one says what it really is.

        A name with no value of its own is only known to be a container by the
        ``{`` written on the line below it, so typing that brace, or removing it,
        means colouring the name again - and Qt only colours the line that
        changed.  This answers the document rather than the highlight pass, and
        does so after the highlighter itself has coloured the line that changed:
        the highlighter connects to the document after the document connects to
        the highlighter, so this slot runs last.
        """
        if self._our_own or not (removed or added):
            return  # our own colours changing, or nothing that changes the shape
        document = self.document()
        if document is None:
            return
        for at in {position, position + added}:
            above = document.findBlock(at).previous()
            if above.isValid() and _NAME.fullmatch(above.text()):
                self._our_own = True
                try:
                    self.rehighlightBlock(above)
                finally:
                    self._our_own = False

