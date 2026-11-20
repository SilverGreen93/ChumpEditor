"""The name of this program, and where it keeps the files a person can change.

Free of Qt so the rest of the package can ask where things are without a
window.  Everything else is a file whose name the user chooses; this is only
for the files this program reads on its own, of which there is one kind so far:
themes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["APP_NAME", "config_dir"]

#: the name as it is typed, and so spelled without a space: it is the folder
#: below, the exe and the package.  The name a person reads is spelled
#: "Chump Editor", with a space, and lives with the other display strings in
#: ``gui/resources.py``; tests/test_gui.py keeps the two spellings in step.
APP_NAME = "ChumpEditor"


def config_dir() -> Path:
    """The directory this program's own settings and themes live in.

    Where each system expects them: ``%LOCALAPPDATA%\\ChumpEditor`` on Windows,
    ``~/.config/ChumpEditor`` elsewhere.  Nothing is created here, since most
    of the time the answer is only used to look something up, and a program
    that leaves an empty directory behind after being run once has done
    something rude.
    """
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        home = Path(base) if base else Path.home() / "AppData" / "Local"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        home = Path(base) if base else Path.home() / ".config"
    return home / APP_NAME
