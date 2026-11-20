"""The PyQt6 front end: a window holding one rich text document.

The pieces are split so each can be read on its own:

``document.py`` (one level up)  what opening, saving and exporting a file means
``resources.py``                the app's own strings, and its icon
``editor.py``                   the text area
``window.py``                   the window: title, menus, drag & drop
``highlighter.py``              the keyword colouring laid over the text

``run_gui`` is what the ``chumpeditor-gui`` script and the GUI exe call; paths
named on the command line open straight away.
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from .editor import RichTextEditor
from .resources import APP_NAME, APP_TITLE, window_icon
from .window import ChumpWindow

__all__ = ["APP_NAME", "APP_TITLE", "ChumpWindow", "RichTextEditor", "main", "run_gui"]


def run_gui(paths: list[str] | None = None) -> int:
    """Launch the GUI. Returns the process exit code."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    icon = window_icon()
    if icon:
        app.setWindowIcon(icon)
    window = ChumpWindow(paths)
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``chumpeditor-gui`` script."""
    if argv is None:
        argv = sys.argv[1:]
    return run_gui(argv)


if __name__ == "__main__":
    sys.exit(run_gui())
