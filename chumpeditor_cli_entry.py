"""PyInstaller entry point for the CLI exe (ChumpEditorCli.exe).

Built with --console so stdout/stderr are attached to the terminal by
default.  With no arguments it prints usage and exits; use ChumpEditor.exe
(GUI subsystem) for the GUI.
"""

import sys
from pathlib import Path

if __name__ == "__main__":
    # when run from the source tree without installing, make src/ importable
    _src = Path(__file__).resolve().parent / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

    from chumpeditor.cli import main

    if not sys.argv[1:]:
        print('Usage: ChumpEditorCli.exe "config.chump"      (writes config.txt)')
        print('       ChumpEditorCli.exe "config.txt"        (writes config.chump)')
        print('       ChumpEditorCli.exe "config.chump" -o "other.txt"')
        print('       ChumpEditorCli.exe "config.chump" --stdout')
        print("       Use ChumpEditor.exe for the GUI.")
        sys.exit(1)

    sys.exit(main())
