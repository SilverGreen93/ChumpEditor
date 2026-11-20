"""The menu bar: what can be done to the file on screen, and to its text.

The actions are made here and the window does the work behind them, so the
names, the shortcuts and the enabled state live in one place while the file
rules themselves stay in ``document.py``, where the command line follows them
too.

Actions are named out loud rather than given Qt's standard roles because the
two save commands are not the same thing: *Save chump* packs the text back
into a binary file, *Export txt* writes the indented text form.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtGui import QGuiApplication, QKeySequence
from PyQt6.QtWidgets import QMainWindow

from .resources import APP_NAME

__all__ = ["build_menus"]


def build_menus(window: QMainWindow) -> None:
    """Put File, Edit and Help on the window, wired to its methods."""
    bar = window.menuBar()
    _file(bar.addMenu("&File"), window)
    _edit(bar.addMenu("&Edit"), window.editor)
    _help(bar.addMenu("&Help"), window)


def _file(menu, window: QMainWindow) -> None:
    """Open a file, write the text out in either form, and finish."""
    _add(menu, "&Open file...", QKeySequence.StandardKey.Open, window.prompt_open)

    menu.addSeparator()
    _add(menu, "&Save chump", QKeySequence.StandardKey.Save, lambda: window.save())
    _add(menu, "Save chump &as...", None, lambda: window.save(ask=True))

    menu.addSeparator()
    _add(menu, "E&xport txt", QKeySequence("Ctrl+E"), lambda: window.export())
    _add(menu, "Export txt as...", None, lambda: window.export(ask=True))

    menu.addSeparator()
    _add(menu, "E&xit", QKeySequence.StandardKey.Quit, window.close)


def _edit(menu, editor):
    """The usual work on the text, which the text area does for us."""
    document = editor.document()

    undo = _add(menu, "&Undo", QKeySequence.StandardKey.Undo, editor.undo)
    redo = _add(menu, "&Redo", QKeySequence.StandardKey.Redo, editor.redo)
    menu.addSeparator()
    cut = _add(menu, "Cu&t", QKeySequence.StandardKey.Cut, editor.cut)
    copy = _add(menu, "&Copy", QKeySequence.StandardKey.Copy, editor.copy)
    paste = _add(menu, "&Paste", QKeySequence.StandardKey.Paste, editor.paste)
    _add(menu, "Select &All", QKeySequence.StandardKey.SelectAll, editor.selectAll)

    # an action that has nothing to work on is greyed out rather than beeping
    for action in (undo, redo, cut, copy):
        action.setEnabled(False)
    document.undoAvailable.connect(undo.setEnabled)
    document.redoAvailable.connect(redo.setEnabled)
    editor.copyAvailable.connect(_keep_both(cut, copy))

    paste.setEnabled(editor.canPaste())
    _clipboard().dataChanged.connect(lambda: paste.setEnabled(editor.canPaste()))


def _help(menu, window: QMainWindow) -> None:
    """Who wrote this, and where it comes from."""
    _add(menu, f"&About {APP_NAME}...", None, window.about)


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
