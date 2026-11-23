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

Every container is shown opened, because the request was for sub-containers to be
visible rather than hunted for; a file of this size has nothing to gain from
starting them closed.  Text that holds no containers gives an empty tree rather
than a row saying so - a placeholder in a tree that is empty because the document
is empty would read as a fault in the file.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDockWidget, QTreeWidget, QTreeWidgetItem, QWidget

from ..outline import containers

__all__ = ["ContainerTree", "PANEL_TITLE"]

#: the panel's own name: it has no title bar to show it in, so the name is there
#: for anything that asks a widget what it is
PANEL_TITLE = "Containers"


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

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        # one column, because the row says the container's name and there is
        # nothing else worth a column of its own; the indentation does the
        # nesting
        self.tree.setColumnCount(1)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
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

