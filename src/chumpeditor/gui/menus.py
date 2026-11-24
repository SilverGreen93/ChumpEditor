"""The menu bar: what can be done to the file on screen, and to its text.

The actions are made here and the window does the work behind them, so the
names, the shortcuts and the enabled state live in one place while the file
rules themselves stay in ``document.py`` and the tidy-ups of the text in
``tweaks.py``, where the command line can follow them too.

Actions are named out loud rather than given Qt's standard roles because the
two save commands are not the same thing: *Save chump* packs the text back
into a binary file, *Export txt* writes the indented text form.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtGui import QClipboard, QGuiApplication, QKeySequence
from PyQt6.QtWidgets import QMainWindow

from .resources import DISPLAY_NAME

__all__ = ["build_menus"]


def build_menus(window: QMainWindow) -> None:
    """Put File, Edit, View, Tweaks and Help on the window, wired to its methods."""
    bar = window.menuBar()
    _file(bar.addMenu("&File"), window)
    _edit(bar.addMenu("&Edit"), window)
    _view(bar.addMenu("&View"), window)
    _tweaks(bar.addMenu("&Tweaks"), window)
    _help(bar.addMenu("&Help"), window)


def _file(menu, window: QMainWindow) -> None:
    """Open a file, write the text out in either form, say what is wrong with
    it, and finish."""
    _add(menu, "&Open file...", QKeySequence.StandardKey.Open, window.prompt_open)

    # the files opened lately, so a person does not have to hunt for them again
    _recent(menu.addMenu("Recent &files"), window)

    menu.addSeparator()
    _add(menu, "&Save chump", QKeySequence.StandardKey.Save, lambda: window.save())
    _add(menu, "Save chump &as...", None, lambda: window.save(ask=True))

    menu.addSeparator()
    _add(menu, "E&xport txt", QKeySequence("Ctrl+E"), lambda: window.export())
    _add(menu, "Export txt as...", None, lambda: window.export(ask=True))

    menu.addSeparator()
    # the rules a write is guarded by, asked for on their own and all at once
    _add(menu, "Sy&ntax check", QKeySequence("F5"), window.syntax_check)

    menu.addSeparator()
    _add(menu, "E&xit", QKeySequence.StandardKey.Quit, window.close)


def _recent(menu, window: QMainWindow) -> None:
    """The files opened lately, newest first, and one item to forget them.

    The names change as files are opened, so the menu is written out as they are
    opened and again as the menu opens: see ``window.fill_recent_menu``.  The
    window keeps hold of this menu because it is the window that rewrites it.
    """
    window.recent_menu = menu
    menu.aboutToShow.connect(window.fill_recent_menu)
    window.fill_recent_menu()


def _edit(menu, window: QMainWindow) -> None:
    """The usual work on the text, which the text area does for us, and the
    search that looks through it from a panel at the bottom of the window."""
    editor = window.editor
    panel = window.find_panel
    document = editor.document()

    undo = _add(menu, "&Undo", QKeySequence.StandardKey.Undo, editor.undo)
    redo = _add(menu, "&Redo", QKeySequence.StandardKey.Redo, editor.redo)
    menu.addSeparator()
    cut = _add(menu, "Cu&t", QKeySequence.StandardKey.Cut, editor.cut)
    copy = _add(menu, "&Copy", QKeySequence.StandardKey.Copy, editor.copy)
    paste = _add(menu, "&Paste", QKeySequence.StandardKey.Paste, editor.paste)
    _add(menu, "Select &All", QKeySequence.StandardKey.SelectAll, editor.selectAll)

    menu.addSeparator()
    # the ampersand that is part of the name has to be written twice, so the one
    # that marks the Alt key can sit on the R of Replace
    _add(menu, "Find && &Replace", QKeySequence("Ctrl+F"), panel.open)
    find_next = _add(menu, "Find &next", QKeySequence("F3"), panel.find_next)

    # an action that has nothing to work on is greyed out rather than beeping,
    # and repeating a search is one of them while the panel is put away
    for action in (undo, redo, cut, copy, find_next):
        action.setEnabled(False)
    document.undoAvailable.connect(undo.setEnabled)
    document.redoAvailable.connect(redo.setEnabled)
    editor.copyAvailable.connect(_keep_both(cut, copy))
    panel.showing.connect(find_next.setEnabled)

    paste.setEnabled(editor.canPaste())
    _clipboard().dataChanged.connect(lambda: paste.setEnabled(editor.canPaste()))


def _view(menu, window: QMainWindow) -> None:
    """How the file is shown: the tree of its containers beside the text, and
    whether the lines are bent to the width of the text area.

    Both items are ticked rather than pressed, because the state each one changes
    goes on being - a panel that stands there until asked not to, lines that stay
    wrapped until asked not to - and a person looking at the menu should be able
    to tell which way each stands now.

    F2 is the key for the tree and F4 the key for the wrap: F3 searches and F5
    checks the syntax, and anything wanted on file after file is something nobody
    wants to reach through a menu each time.
    """
    treeview = _add(menu, "&Treeview", QKeySequence("F2"), window.toggle_treeview)
    treeview.setCheckable(True)

    wrapped = _add(menu, "Wrap &lines", QKeySequence("F4"), window.toggle_line_wrap)
    wrapped.setCheckable(True)


def _tweaks(menu, window: QMainWindow) -> None:
    """One-off tidy-ups of the text itself: fixes for the way files used to be written.

    Nothing here is automatic: every one of them is something a person asks for
    and then reads the result of, because a change that quietly rewrites an
    asset's tags is not a change to discover later.
    """
    _add(menu, "&Convert obsolete lists", None, window.convert_obsolete_lists)
    _add(
        menu,
        "Convert asset-&filename to mesh-table",
        None,
        window.convert_asset_filename_to_mesh_table,
    )
    _add(menu, "&Remove language tags", None, window.remove_language_tags)
    _add(menu, "&Reorder tags", None, window.reorder_tags)


def _help(menu, window: QMainWindow) -> None:
    """Who wrote this, and where it comes from."""
    _add(menu, f"&About {DISPLAY_NAME}...", None, window.about)


def _add(menu, text: str, shortcut, slot: Callable[[], None]):
    """One action in a menu, with a shortcut that may be none."""
    action = menu.addAction(text)
    if shortcut is not None:
        action.setShortcut(QKeySequence(shortcut))
    action.triggered.connect(slot)
    return action


def _keep_both(*actions):
    """One handler that enables, or disables, several actions at once."""

    def changed(available: bool) -> None:
        for action in actions:
            action.setEnabled(available)

    return changed


def _clipboard() -> QClipboard:
    """The system clipboard, which Qt makes once for the application."""
    return QGuiApplication.clipboard()
