"""The tree of containers that stands beside the text: a row for the file, and one
for every container written in it.

It is a dock stood to the left of the text rather than anything written into it,
following ``gui/find.py``: no title bar and nothing to float it away or close it
from, since whether it stands there at all is the View menu's business.  Which
containers the text holds, and which line each of them starts on, is answered by
``outline.py``; this file only turns that list into rows and says which row was
chosen.

Nothing here asks the window anything: a click sends out the line the container's
name is written on, exactly as the find panel only reports sentences.  The tree
holds no editor and knows nothing about one.

At the top of the tree stands the file: one row carrying its name, or
``Untitled`` while the text has been written nowhere.  That is how every other
application shows a file, and it says whose containers the rows below are.  The
name is handed over rather than looked for, because the panel asks the window
nothing - the window says it whenever it says the title, which is the one answer
both of them are showing.

Every container starts opened, because the request was for sub-containers to be
visible rather than hunted for; a row's own mark is there to shut it again for
anyone who wants the file down to its top level.  Text that holds no containers
gives a tree with nothing under the file's own row rather than a row saying so -
a placeholder in a tree that is empty because the document is empty would read as
a fault in the file.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QDockWidget,
    QProxyStyle,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from ..outline import containers
from .editor import code_font
from .resources import UNTITLED

__all__ = ["ContainerTree", "PANEL_TITLE"]

#: the panel's own name: it has no title bar to show it in, so the name is there
#: for anything that asks a widget what it is
PANEL_TITLE = "Containers"

#: how thick a chevron's strokes are, in logical pixels: antialiasing spreads
#: them over about a device pixel and a half at 100 percent, which is the weight
#: the same mark carries in the rest of Windows
CHEVRON_WIDTH = 1.2

#: how much of the joining lines' colour comes from the letters: three eighths of
#: the colour the rows are written in, walked toward the paper they stand on.
#: The same step in both directions, which is what other applications do and what
#: no palette role answers - see ``_the_line_ink``
LINE_STRENGTH = 0.375


def _the_line_ink(palette: QPalette) -> QColor:
    """The grey the joining lines and the chevron are drawn in.

    A line that joins rows is a step off the background, not a mark on it: in a
    light Windows tree that step is a grey around ``#a0a0a0`` standing on white,
    and in a dark one it is a grey around the same distance the other way,
    standing on a background near ``#2d2d2d``.  No palette role gives both,
    measured with PyQt6 6.12 on a dark desktop: there ``Dark`` is ``#1e1e1e``,
    *darker* than the ``#2d2d2d`` the rows stand on, so the lines vanish, and
    ``Midlight`` does the same trick in reverse on a light desktop.  So the step
    is taken from what the palette does answer - the colour the letters are
    written in, walked toward the paper - which keeps the lines the same weight
    above a dark editor as above a light one, and lets a desktop going dark or
    light change them by itself.
    """
    paper = palette.color(QPalette.ColorRole.Base)
    letters = palette.color(QPalette.ColorRole.Text)
    step = LINE_STRENGTH
    return QColor(
        round(letters.red() * step + paper.red() * (1.0 - step)),
        round(letters.green() * step + paper.green() * (1.0 - step)),
        round(letters.blue() * step + paper.blue() * (1.0 - step)),
    )


#: the grey to draw in when Qt asks for a join without naming the widget that
#: owns it, which leaves no palette to ask: the answer for a light desktop
FALLBACK_INK = QColor("#a0a0a0")


class _JoinLines(QProxyStyle):
    """The lines joining a row to the rows under it.

    Qt asks the style for each of those pieces by itself - one square per level
    a row sits behind, saying where the square is and what stands there - and what
    goes inside the square is the style's business.  Measured with PyQt6 6.12 on
    this machine: every style Windows offers answers with a triangle showing
    whether the row is opened, and not one of them draws the lines, which is why
    asking for ``setRootIsDecorated`` on its own left the rows standing there
    unjoined.

    So the square is filled in here instead, out of what Qt already says about it
    (measured with PyQt6 6.12, which hides the direction Qt also hands over, so
    these four flags are all the answer - and they are enough):

    * ``State_Item`` - this square is the row's own join, the one the name follows,
      rather than a level above it on the way down;
    * ``State_Sibling`` - another row follows at this level, so the line coming
      down has somewhere further to go;
    * ``State_Children`` - the row holds rows under it, so there is something to
      open or shut;
    * ``State_Open`` - that row stands opened.

    Which is exactly what a drawn tree asks for: a line down the middle of the
    square whenever a row follows at that level, a line across from the middle to
    the name in front of the row's own square only, and that vertical stopped at
    the middle rather than run through when the row is the last one under its own -
    the corner that says nothing more follows.  Nothing is drawn at all in a level
    whose row above was already such a last one, which is what keeps the strip of
    lines from carrying on beside rows it no longer joins.  The one row joined to
    nothing is the file's own, the only row standing at no level at all: no row
    stands above it for a line to come from, so its square holds the mark alone.

    The other two flags answer the mark that says whether a group stands opened:
    ``State_Children`` says there is a group at all, and ``State_Open`` which way
    the mark points - down into the rows held, or along the row when shut.  The
    mark stands on the meeting point and the lines stop at its edges.  A leaf row
    is handed ``State_Open`` too, measured with PyQt6 6.12, so the mark is asked of
    ``State_Children`` rather than of that.

    The mark is the chevron the rest of Windows uses for a group, drawn as a path
    with antialiasing; the lines are left hard-edged, because Qt puts a
    whole-number line on a whole device pixel and that one pixel is what a joining
    line is meant to be.  Both are drawn in the grey ``_the_line_ink`` works out of
    the palette: the colour the rows are written in, stepped off the paper they
    stand on, which is far lighter than the letters themselves and keeps its weight
    whether the desktop is light or dark.

    A style is stood on the tree rather than a stylesheet laid over it, because a
    stylesheet would have to be given pictures of the lines to draw - files to
    ship with the program and an ``assets`` folder to find them in - while this
    answers the same question from what Qt already hands it.  The style is stood
    on the tree rather than on the whole application, so the rest of the window
    is left exactly as the desktop style draws it.

    Whether the lines are really drawn, and really stop where they should, is
    checked by painting the panel into a picture and reading it back out of it;
    see ``test_the_rows_are_joined_by_lines`` in tests/test_gui.py.
    """

    def drawPrimitive(self, element, option, painter, widget=None) -> None:  # noqa: N802 - Qt naming
        if element != QStyle.PrimitiveElement.PE_IndicatorBranch:
            super().drawPrimitive(element, option, painter, widget)
            return
        square = option.rect
        if square.width() < 3 or square.height() < 5:
            return
        # the lines and the mark are drawn in one grey, worked out from the
        # palette so it keeps its step off the background when the desktop goes
        # dark; the colour the rows are written in is far too heavy by itself,
        # and darkening black does nothing at all: measured with PyQt6 6.12,
        # Text.darker(170) of #000000 is still #000000
        ink = _the_line_ink(widget.palette()) if widget is not None else FALLBACK_INK
        _the_join(square, option.state, painter, ink)


def _the_mark_size(square: QRect) -> int | None:
    """Half the width of an open/shut mark, or ``None`` if the room is too small.

    The mark sits on the place where the lines meet rather than beside it, which
    is where a hand expects to find it and what leaves the lines free to stop at
    it.  It is sized from the room there is - the room is halved, see
    ``_JoinedRows`` - and given up altogether when the room is too small for it,
    since a blob is worse than nothing.  Whether a row gets a mark at all is a
    different question, answered by ``State_Children`` in ``_the_join``.
    """
    half = min(4, square.width() // 4, (square.height() - 4) // 2)
    return half if half >= 2 else None


def _the_chevron(middle_x: int, middle_y: int, half: int, opened: bool) -> QPolygonF:
    """The mark itself: two strokes, ``v`` when opened, ``>`` when shut.

    The same mark every Windows application uses for a group, and drawn the same
    way - as a path with antialiasing, not as pixels laid out by hand.  A filled
    triangle a few logical pixels wide cannot be made to look right at the
    fractions a scaled display asks for: each row of it lands half way between
    two device pixels, and the edge comes out lumpy.
    """
    if opened:
        return QPolygonF([
            QPointF(middle_x - half, middle_y - half),
            QPointF(middle_x, middle_y + half),
            QPointF(middle_x + half, middle_y - half),
        ])
    return QPolygonF([
        QPointF(middle_x - half, middle_y - half),
        QPointF(middle_x + half, middle_y),
        QPointF(middle_x - half, middle_y + half),
    ])


def _the_join(square: QRect, state, painter: QPainter, ink: QColor) -> None:
    """One square's piece of the joining lines, drawn where Qt points.

    ``square`` is the whole of one level's room on one row, so the vertical of one
    row's square and the vertical of the row under it meet at their shared edge and
    come out as one unbroken line.

    Only the file's own row is left unjoined, and it is recognised by standing at
    the left edge as its own join: it is the one row written at no level at all,
    since everything else is written inside it.  Nothing stands above it for a line
    to come from, and no name follows a line across, so its square holds the mark
    alone.  Where a row stands is taken from the square rather than asked of the
    model, because a model asked of the option inside the style takes the process
    down with it - measured with PyQt6 6.12, which reads as an access violation
    with no message at all.
    """
    middle_x = square.left() + square.width() // 2
    middle_y = square.top() + square.height() // 2
    follows = bool(state & QStyle.StateFlag.State_Sibling)
    painter.save()
    try:
        # the pen is set before anything is drawn, or a level above the row gets
        # the style's own pen instead of the ink it was handed
        painter.setPen(QPen(ink))
        if not state & QStyle.StateFlag.State_Item:
            # a level above this row on the way down: the line only, and only
            # while a row still follows at this level
            if follows:
                painter.drawLine(middle_x, square.top(), middle_x, square.bottom())
            return
        half = _the_mark_size(square) if state & QStyle.StateFlag.State_Children else None
        if square.left():
            # a row written inside a level: joined to the row above and to its own
            # name, which the file's own row, written at no level, is not
            if half is None:
                above, under, across = middle_y, middle_y, middle_x
            else:
                above, under, across = middle_y - half - 1, middle_y + half + 1, middle_x + half + 1
            # down from the row above, as far as the mark or the middle of the square
            painter.drawLine(middle_x, square.top(), middle_x, above)
            # and on down only while another row follows at this level; stopping here
            # is the corner that says this is the last one under its own
            if follows:
                painter.drawLine(middle_x, under, middle_x, square.bottom())
            # across to the name, from the mark or from the middle of the square
            painter.drawLine(across, middle_y, square.right(), middle_y)
        if half is not None:
            # the chevron stands in the gap the lines stopped short of, and is the
            # only part of the drawing that is antialiased: the lines are left
            # hard-edged because Qt puts a whole-number line on a whole device
            # pixel, which is the single pixel of width they are meant to have
            pen = QPen(ink, CHEVRON_WIDTH)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            opened = bool(state & QStyle.StateFlag.State_Open)
            painter.drawPolyline(_the_chevron(middle_x, middle_y, half, opened))
    finally:
        painter.restore()


class _JoinedRows(QTreeWidget):
    """The rows: joined by lines, and standing half as far behind their own.

    Qt answers how much room a level needs by asking its style, and that answer
    is taken and halved before anything else measures it, so the panel keeps its
    proportions whatever the desktop happens to be.  Both halves of the job
    belong in one place because they are asked at the same moment: the room is
    measured when the tree is made, and a style that only says what goes inside
    the room cannot change it afterwards.

    Measured on this machine: 20 pixels under windowsvista and fusion alike, 30
    under windows11.  Halved rather than fixed at a number, so the panel stays
    half as wide in relation to the text whatever the desktop style is.  Halved
    once is still room enough for a mark: 20 is the smallest answer measured, so
    the square never comes out under 10 pixels wide.  A stylesheet cannot do this
    either: measured with PyQt6 6.12, ``branch-indentation`` leaves Qt's own
    answer untouched.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setIndentation(self.indentation() // 2)
        self.setStyle(_JoinLines())


class ContainerTree(QDockWidget):
    """The rows: the file's own at the top, and one per container, nested in it as
    the file nests them."""

    #: the line of the container whose row was chosen, counted the way the
    #: numbers down the left of the editor count; the window moves the caret
    picked = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(PANEL_TITLE, parent)
        # part of the window, not a little window of its own: no title bar to
        # drag it by and nothing to float it away or close it from, since the
        # View menu is what decides whether it stands here
        self.setTitleBarWidget(QWidget())
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)

        self.tree = _JoinedRows(self)
        # the same letters and the same size as the text beside it: a row names a
        # container that is read in the editor, and a second font in the window
        # makes the tree look like a different program's window.  Asked of
        # ``code_font``, the very answer the editor asks, rather than of the
        # editor itself, so the panel still knows nothing about the window
        self.tree.setFont(code_font())
        self.tree.setHeaderHidden(True)
        # one column, because the row says the container's name and there is
        # nothing else worth a column of its own; the indentation does the
        # nesting
        self.tree.setColumnCount(1)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
        # the room Qt leaves for a level is measured when the tree is made, so
        # both the lines and the halved room belong to _JoinedRows; see it for
        # why the desktop styles cannot be left to draw the lines themselves
        self.tree.setRootIsDecorated(True)
        self.tree.itemClicked.connect(self._a_row_was_chosen)
        # the file itself stands at the top of the tree with everything written in
        # it below, the way every other application shows a file: the names then
        # read as the contents of one named thing rather than a list with nothing
        # above them.  Made once, here, rather than out of the text, so the name
        # the window gave it and the place the user left it - opened or shut -
        # survive the rows being written out again on every change; and it is
        # given no line number, because it is the file rather than a container in
        # it, so clicking it asks the editor for nothing
        self.file_row = QTreeWidgetItem([UNTITLED])
        self.file_row.setExpanded(True)
        self.tree.addTopLevelItem(self.file_row)
        self.setWidget(self.tree)
        self.hide()

    # -- how the rows are written --------------------------------------------
    def set_font_size(self, points: float) -> None:
        """Write the rows at ``points``, the size the text beside them is at.

        The panel asks for ``code_font`` when it is made, which is the size the
        text starts out at; when the text is made bigger or smaller the rows are
        asked to match it again, because one face at two sizes is two programs'
        windows standing side by side.  Nothing else has to be told: the joining
        lines and the open/shut marks are placed off the room a row takes, which
        Qt measures out of this font, so they move with it.
        """
        font = code_font()
        font.setPointSizeF(points)
        self.tree.setFont(font)

    # -- what the tree shows --------------------------------------------------
    def set_text(self, text: str) -> None:
        """Write the rows out again from the text on screen.

        The flat list ``outline.containers`` answers with is already in tree
        order - a container comes before what is written inside it - so the rows
        are made by walking down it and keeping the last row at each level as the
        parent of the next one down.  Everything is opened on the way, and text
        that holds no containers leaves the file's row standing on its own.
        """
        # only the rows under the file's are thrown away, since that row is the
        # tree's own and carries a name the window gave rather than one the text
        # can answer; it is opened again because the rows under it are new, and a
        # shut one would leave a tree that looks empty
        self.file_row.takeChildren()
        self.file_row.setExpanded(True)
        # the last row made at each level; a container one level deeper than the
        # row before it belongs under that one
        parents: list[QTreeWidgetItem] = []
        for one in containers(text):
            row = QTreeWidgetItem([one.name])
            row.setData(0, Qt.ItemDataRole.UserRole, one.line)
            del parents[one.level:]
            if parents:
                parents[-1].addChild(row)
            else:
                self.file_row.addChild(row)
            parents.append(row)
            # opened as it is made: a container's own sub-containers follow it in
            # the list, and opening before they arrive is what shows them
            row.setExpanded(True)

    def set_file_name(self, name: str) -> None:
        """Say what the file at the top of the tree is called.

        The window says it, because the window is the only thing here that knows
        which file is on screen; ``Untitled`` is what stands there until it does.
        """
        self.file_row.setText(0, name)

    def file_name(self) -> str:
        """What the row at the top of the tree is called."""
        return self.file_row.text(0)

    def top_level_count(self) -> int:
        """How many containers stand at the top of the file.

        The file's own row is not one of them: this counts what is written inside
        the file, which is what the rows under it are.
        """
        return self.file_row.childCount()

    def topLevelItem(self, row: int) -> QTreeWidgetItem | None:  # noqa: N802 - Qt naming
        """A container standing at the top of the file, by its place in the tree.

        The rows belong to ``self.tree``, which is asked directly; this is only
        here so a test about what the panel shows can ask for a row without
        reaching into the widget inside the dock.  The places run from the file's
        own row, which is where its containers are written.
        """
        return self.file_row.child(row)

    # -- the parts that are not decisions -------------------------------------
    def _a_row_was_chosen(self, row: QTreeWidgetItem, _column: int) -> None:
        """Say which container was picked, by the line its name is written on."""
        line = row.data(0, Qt.ItemDataRole.UserRole)
        if line:
            self.picked.emit(int(line))

