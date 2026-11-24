"""The text area the window is built around.

One rich text document, not a queue of files.  Rich text because a hand-made
bold, italic or colour, and anything pasted in carrying them, has to survive -
a plain text edit could not hold any of that.  The keyword colours themselves
are paint laid over the text from a theme file by ``gui.highlighter``, so
nothing about them is written in here either; everything about the file the
text came from is the window's business, not this widget's.  When the window
asks for a change to the text it is made here, in place and in one undo step,
because this is the only place the document can be edited without losing where
the caret was.

A ruler of line numbers runs down the left, which is a strip of its own beside
the text rather than anything written into it: the numbers count the lines of
the *document*, and the whole point is that they stay right when a line is
edited, undone or re-wrapped without end.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import QEvent, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase, QPainter, QPalette, QTextCursor
from PyQt6.QtWidgets import QTextEdit, QWidget

from ..theme import Theme, default_theme
from ..tweaks import Rewrite
from .drops import accept_file_drop, dropped_paths
from .highlighter import ThemeHighlighter

__all__ = ["LineNumberArea", "RichTextEditor", "code_font"]

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

#: blank either side of a number, in pixels, so nothing is jammed against a rule
GUTTER_SIDE = 8
#: the smallest the strip is ever allowed to be, in digits, so a file growing
#: past 99 lines does not shove the text sideways on the two-hundred-and-first
GUTTER_MIN_DIGITS = 3
#: how far the numbers are dimmed from the text, out of 255: they are a ruler
#: rather than the thing being read, and the lightest text is the keyword
GUTTER_ALPHA = 110


def code_font() -> QFont:
    """A fixed-width font, so the column-40 values of a config line up."""
    have = {family.lower() for family in QFontDatabase.families()}
    family = next((name for name in PREFERRED_MONO if name.lower() in have), None)
    font = QFont(family) if family else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    font.setPointSize(FONT_POINT_SIZE)
    return font


class LineNumberArea(QWidget):
    """The strip of line numbers down the left of the text.

    A widget of our own rather than part of the text, so the text keeps every
    one of its scrollbars, its selection and its editing behaviour untouched.
    It only paints: the editor tells it where to sit, when it needs redrawing
    and in what colour, because all of that follows the text beside it.
    """

    def __init__(self, editor: "RichTextEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt's name
        self._editor.paint_gutter(event)


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
        self.highlighter = ThemeHighlighter(
            self.document(), theme or default_theme(), self.on_dark_background()
        )
        self._setup_gutter()

    # ------------------------------------------------------------------ lines

    def _setup_gutter(self) -> None:
        """Put the line numbers in and make room for them beside the text."""
        self.gutter = LineNumberArea(self)
        self._place_gutter()
        # the text area is what the strip has to keep level with, and it settles
        # whenever it likes - the scrollbars only arrive once the window is on
        # screen, a window changing shape moves them about, soft wrap brings the
        # sideways bar in and out - and there is no one signal for all of it, so
        # the strip is stood again on anything the text area says
        self.viewport().installEventFilter(self)
        # the text asks for its own repaints and the strip is not text, so the
        # ask is copied over to it, and the scrollbar's is copied too because a
        # scroll moves the text out from under numbers that have not moved
        self.document().documentLayout().update.connect(self._repaint_gutter)
        self.verticalScrollBar().valueChanged.connect(self._repaint_gutter)
        # one line more or less is one line more or less of room as well
        self.document().contentsChanged.connect(self._lines_changed)
        self._lines_changed()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt's name
        """Keep the strip level with the text area, which settles late.

        The text area is not the size it ends up being until the window is on
        screen: the scrollbars are only made at show time, and the sideways bar
        comes and goes with the length of the longest line.  Nothing announces
        all of that together, so the strip is stood again on anything at all
        happening to the text area, and only moved when it is out of place.
        """
        if watched is self.viewport():
            self._place_gutter()
        return super().eventFilter(watched, event)

    def gutter_width(self) -> int:
        """How wide the strip has to be: the widest the file can make it.

        Three digits at least, because a two-line file getting a third line
        must not shove the text over, and the width of a digit rather than the
        text's own because the numbers are the same face as the text.
        """
        digits = max(GUTTER_MIN_DIGITS, len(str(self.document().blockCount())))
        return 2 * GUTTER_SIDE + digits * self.fontMetrics().horizontalAdvance("9")

    def _place_gutter(self) -> None:
        """Stand the strip in the room reserved for it, between the frame and
        the text.

        Reserving the room is not the same as using it: ``setViewportMargins``
        only pushes the text area aside, and a child widget goes nowhere until
        it is told where.  It is measured off the text area rather than off the
        frame so that it lines up with it exactly, top for top and bottom for
        bottom, whatever the scrollbars have taken.
        """
        box = self.viewport().geometry()
        width = self.gutter_width()
        place = QRect(box.left() - width, box.top(), width, box.height())
        if self.gutter.geometry() != place:
            self.gutter.setGeometry(place)

    def _lines_changed(self) -> None:
        """Re-reserve the room whenever the number of lines could have changed."""
        width = self.gutter_width()
        if width != self.viewportMargins().left():
            self.setViewportMargins(width, 0, 0, 0)
        self._place_gutter()
        self._repaint_gutter()

    def _repaint_gutter(self, *_: object) -> None:
        """Ask for the strip to be redrawn, in full, whenever anything moved.

        Both signals that prompt it report something about the *text* - a
        rectangle of it, or a scroll position - and neither is of any use to the
        strip: the numbers move with every scroll and every edit, and a scroll
        does not move the strip with them, so anything less than a full repaint
        leaves numbers sitting where other numbers used to be.

        Before the strip has been made there is nothing to repaint, which
        happens: the palette is polished while the widget is still being built.
        """
        if getattr(self, "gutter", None) is not None:
            self.gutter.update()

    def visible_lines(self) -> list[tuple[int, int, int]]:
        """The lines of text in sight, each as its number, the height of its top
        edge in the strip, and its own height.

        Those heights are the document's moved up by however far the text has
        been scrolled, so a line scrolled half out of sight is still listed -
        half a number is what is in sight of it.  A soft-wrapped line is listed
        once, at its first visual line, which is the only numbering that stays
        true to what the reader calls line 40.

        The walk starts from a binary search rather than from line one, because
        a config file runs to thousands of lines and a repaint follows every
        scroll.  That search is legal because the tops of the blocks only ever
        go down the document.
        """
        doc = self.document()
        layout = doc.documentLayout()
        scrolled = self.verticalScrollBar().value()
        low, high = 0, doc.blockCount() - 1
        while low < high:
            middle = (low + high) // 2
            if round(layout.blockBoundingRect(doc.findBlockByNumber(middle)).top()) > scrolled:
                high = middle
            else:
                low = middle + 1
        seen: list[tuple[int, int, int]] = []
        block = doc.findBlockByNumber(max(0, low - 1))
        while block.isValid():
            edge = layout.blockBoundingRect(block)
            top = round(edge.top()) - scrolled
            if top >= self.viewport().height():
                break
            if top + round(edge.height()) >= 0:
                seen.append((block.blockNumber() + 1, top, round(edge.height())))
            block = block.next()
        return seen

    def paint_gutter(self, event) -> None:
        """Draw the numbers that are in sight, and only what was asked for."""
        box = self.gutter.rect().intersected(event.rect())
        if box.isNull():
            return
        painter = QPainter(self.gutter)
        painter.setClipRect(box)
        painter.fillRect(box, self.palette().color(QPalette.ColorRole.Base))
        dim = self.palette().color(QPalette.ColorRole.Text)
        dim.setAlpha(GUTTER_ALPHA)
        painter.setFont(self.font())
        painter.setPen(dim)
        for number, top, height in self.visible_lines():
            painter.drawText(QRect(GUTTER_SIDE, top, box.width() - 2 * GUTTER_SIDE, height),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, str(number))
        painter.end()

    def on_dark_background(self) -> bool:
        """Whether this text sits on a dark background.

        The widget's own base colour is the question and the answer, not what
        the desktop claims: a program handed a light palette by hand has to be
        read with the light colours even on a dark desktop, and the base colour
        is exactly what is painted behind the text.
        """
        return self.palette().color(QPalette.ColorRole.Base).lightness() < 128

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Recolour when the palette changes, which is how a desktop going dark
        - or coming back to light - reaches the keyword colours.

        The events start before the highlighter does, since building the widget
        polishes its palette, so there may be nothing to recolour yet.
        """
        super().changeEvent(event)
        highlighter = getattr(self, "highlighter", None)
        if highlighter is not None and event.type() == QEvent.Type.PaletteChange:
            highlighter.set_dark(self.on_dark_background())
            # the numbers are painted from the same palette, so they are asked
            # for as well; Qt repaints the text for a palette of its own, but a
            # widget of ours beside it is left to us
            self._repaint_gutter()

    def set_theme(self, theme: Theme) -> None:
        """Change the colours, and put the new ones over the text."""
        self.highlighter.set_theme(theme)

    def set_line_wrap(self, wrap: bool) -> None:
        """Wrapped for reading, straight for keeping the columns honest.

        A line that is bent to the width of the area is still one line of the
        document: every character keeps the place it was written in, the line is
        numbered once down the side of the text, and what is saved says what the
        file said.  Which of the two shapes is on screen is a View choice, and the
        window remembers it; the text area only ever answers to being asked.
        """
        self.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if wrap else QTextEdit.LineWrapMode.NoWrap
        )

    def is_line_wrapped(self) -> bool:
        """Whether long lines are bent to the width of the area, or run on past it."""
        return self.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth

    def apply_rewrites(self, rewrites: Iterable[Rewrite]) -> None:
        """Cut out stretches of the text and write their replacements in.

        The positions are the ones counted through ``toPlainText()``, and the
        document counts its characters the same way, so a change worked out from
        the text lands where it was worked out to land.  The last stretch is cut
        out first so the earlier ones keep their places, and the lot of them make
        one edit block: one press of Undo puts the whole change back.
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for rewrite in sorted(rewrites, key=lambda item: item.start, reverse=True):
            cursor.setPosition(rewrite.start)
            cursor.setPosition(rewrite.end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(rewrite.text)
        cursor.endEditBlock()

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
