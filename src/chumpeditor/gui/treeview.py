"""The tree of containers that stands beside the text: one row for each container.

It is a dock stood to the left of the text rather than anything written into it,
following ``gui/find.py``: no title bar and nothing to float it away or close it
from, since whether it stands there at all is the View menu's business.  Which
containers the text holds, and which line each of them starts on, is answered by
``outline.py``; this file only turns that list into rows and says which row was
chosen.

Nothing here asks the window anything: a click sends out the line the container's
name is written on, exactly as the find panel only reports sentences.  The tree
holds no editor and knows nothing about one.

Every container starts opened, because the request was for sub-containers to be
visible rather than hunted for; a row's own mark is there to shut it again for
anyone who wants the file down to its top level.  Text that holds no containers
gives an empty tree rather than a row saying so - a placeholder in a tree that is
empty because the document is empty would read as a fault in the file.
"""

from __future__ import annotations

from PyQt6.QtCore import QLine, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QPainter, QPen
from PyQt6.QtWidgets import (
    QDockWidget,
    QProxyStyle,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from ..outline import containers

__all__ = ["ContainerTree", "PANEL_TITLE"]

#: the panel's own name: it has no title bar to show it in, so the name is there
#: for anything that asks a widget what it is
PANEL_TITLE = "Containers"


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
    lines from carrying on beside rows it no longer joins.

    The other two flags answer the mark that says whether a group stands opened:
    ``State_Children`` says there is a group at all, and ``State_Open`` which way
    the mark points - down into the rows held, or along the row when shut.  The
    mark stands on the meeting point and the lines stop at its edges.  A leaf row
    is handed ``State_Open`` too, measured with PyQt6 6.12, so the mark is asked of
    ``State_Children`` rather than of that.

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
        # the lines are drawn in the colour the rows themselves are written in,
        # darkened a little, so they keep their place when the desktop goes dark
        ink = QColor("#808080")
        if widget is not None:
            ink = widget.palette().color(QPalette.ColorRole.Text).darker(170)
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


def _the_mark(middle_x: int, middle_y: int, half: int, opened: bool) -> list[QLine]:
    """The mark itself: pointing down when opened, along the row when shut.

    Answered as the rows of pixels the mark is filled with rather than as a
    polygon, because at the two to four pixels it is given the shape is only a
    handful of pixels wide: a polygon would be outlined and filled by the style's
    own rules and come out leaning to one side.  The point of the mark lands on
    the line it stands on.
    """
    rows: list[QLine] = []
    for step in range(half * 2 + 1):
        # the mark tapers one pixel every other row, from full width at its base
        # down to a single point standing on the line it marks
        reach = half - (step + 1) // 2
        if opened:
            row_y = middle_y - half + step
            rows.append(QLine(middle_x - reach, row_y, middle_x + reach, row_y))
        else:
            row_x = middle_x - half + step
            rows.append(QLine(row_x, middle_y - reach, row_x, middle_y + reach))
    return rows


def _the_join(square: QRect, state, painter: QPainter, ink: QColor) -> None:
    """One square's piece of the joining lines, drawn where Qt points.

    ``square`` is the whole of one level's room on one row, so the vertical of one
    row's square and the vertical of the row under it meet at their shared edge and
    come out as one unbroken line.
    """
    middle_x = square.left() + square.width() // 2
    middle_y = square.top() + square.height() // 2
    follows = bool(state & QStyle.StateFlag.State_Sibling)
    if not state & QStyle.StateFlag.State_Item:
        # a level above this row on the way down: the line only, and only while a
        # row still follows at this level
        if follows:
            painter.drawLine(middle_x, square.top(), middle_x, square.bottom())
        return
    half = _the_mark_size(square) if state & QStyle.StateFlag.State_Children else None
    if half is None:
        above, under, across = middle_y, middle_y, middle_x
    else:
        above, under, across = middle_y - half - 1, middle_y + half + 1, middle_x + half + 1
    painter.save()
    try:
        painter.setPen(QPen(ink))
        # down from the row above, as far as the mark or the middle of the square
        painter.drawLine(middle_x, square.top(), middle_x, above)
        # and on down only while another row follows at this level; stopping here
        # is the corner that says this is the last one under its own
        if follows:
            painter.drawLine(middle_x, under, middle_x, square.bottom())
        # across to the name, from the mark or from the middle of the square
        painter.drawLine(across, middle_y, square.right(), middle_y)
        if half is not None:
            # the mark fills the gap the lines stopped short of
            for row in _the_mark(middle_x, middle_y, half, bool(state & QStyle.StateFlag.State_Open)):
                painter.drawLine(row)
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
    """The rows: one per container, nested as the file nests them."""

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
        self.setWidget(self.tree)
        self.hide()

    # -- what the tree shows --------------------------------------------------
    def set_text(self, text: str) -> None:
        """Write the rows out again from the text on screen.

        The flat list ``outline.containers`` answers with is already in tree
        order - a container comes before what is written inside it - so the rows
        are made by walking down it and keeping the last row at each level as the
        parent of the next one down.  Everything is opened on the way, and an
        empty text leaves an empty tree.
        """
        self.tree.clear()
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
                self.tree.addTopLevelItem(row)
            parents.append(row)
            # opened as it is made: a container's own sub-containers follow it in
            # the list, and opening before they arrive is what shows them
            row.setExpanded(True)

    def top_level_count(self) -> int:
        """How many containers stand at the top of the file."""
        return self.tree.topLevelItemCount()

    def topLevelItem(self, row: int) -> QTreeWidgetItem | None:  # noqa: N802 - Qt naming
        """A container standing at the top of the file, by its place in the tree.

        The rows belong to ``self.tree``, which is asked directly; this is only
        here so a test about what the panel shows can ask for a row without
        reaching into the widget inside the dock.
        """
        return self.tree.topLevelItem(row)

    # -- the parts that are not decisions -------------------------------------
    def _a_row_was_chosen(self, row: QTreeWidgetItem, _column: int) -> None:
        """Say which container was picked, by the line its name is written on."""
        line = row.data(0, Qt.ItemDataRole.UserRole)
        if line:
            self.picked.emit(int(line))

