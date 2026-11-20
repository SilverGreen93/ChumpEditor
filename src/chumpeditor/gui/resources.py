"""The strings and files the window shows about itself.

Kept apart from the widgets so the About box, the title and the icon all read
from one place, and a test can check them without building a window.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon

from .. import __version__

__all__ = [
    "APP_NAME",
    "APP_TITLE",
    "AUTHOR",
    "CREDIT",
    "DESCRIPTION",
    "DROP_HINT",
    "HOME_URL",
    "ICON_FILE",
    "ISSUES_URL",
    "SUMMARY",
    "resource_path",
    "window_icon",
]

APP_NAME = "ChumpEditor"
HOME_URL = "https://github.com/SilverGreen93/ChumpEditor"
ISSUES_URL = f"{HOME_URL}/issues"

APP_TITLE = f"{APP_NAME} {__version__}"
SUMMARY = "Trainz config editor"
DESCRIPTION = (
    "Opens a Trainz config in either form - the binary .chump/.cdp container "
    "or the indented text form - lets you edit it, and writes it back as "
    "either. The text follows the layout Trainz uses: UTF-8 with a BOM, CRLF "
    "line endings, values from column 40."
)
AUTHOR = "SilverGreen93"
#: the copyright line, in the About box and wherever else the app signs itself
CREDIT = f"© {datetime.date.today().year} {AUTHOR}"

#: what the status bar says while a file is being dragged over the window
DROP_HINT = "Drop a .chump, .cdp or .txt file to open it"

#: the icon, bundled next to the code (source tree) or into the exe
ICON_FILE = "chumpeditor.ico"


def resource_path(name: str) -> str | None:
    """Absolute path to a bundled resource, from source or from PyInstaller.

    From source the assets sit at the top of the repository; a frozen build
    unpacks them into ``sys._MEIPASS``, which is where ``--add-data`` puts them.
    """
    if getattr(sys, "frozen", False):  # running under PyInstaller
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates = [base / name, base / "assets" / name]
    else:
        candidates = [parent / "assets" / name for parent in Path(__file__).resolve().parents]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def window_icon() -> QIcon | None:
    """The app icon, if it can be found.

    Setting it on the application as well as the window is what puts it in the
    Windows taskbar; --icon alone only stamps the exe file on disk.
    """
    path = resource_path(ICON_FILE)
    return QIcon(path) if path else None
