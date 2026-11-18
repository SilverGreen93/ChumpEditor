"""Command line entry point.

With no arguments the GUI launches; with one or more paths the app runs in CLI
mode and converts every file to the other form beside it, which direction
being decided by the extension: a ``.chump`` (or ``.cdp``) file is expanded
into ``.txt``, a ``.txt`` file is packed back into ``.chump``.  That is what
the original expander's single button did, only in both directions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .chump import (
    CHUMP_SUFFIXES,
    TEXT_SUFFIXES,
    ChumpError,
    convert_file,
    parse_chump,
    read_text_file,
    render_text,
)

__all__ = ["main", "run_cli", "text_of"]


def main(argv: list[str] | None = None) -> int:
    """Entry point: no args -> GUI; paths -> CLI conversion."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="chumpeditor",
        description="Convert Trainz .chump files to and from their text form.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=".chump files to expand and/or .txt files to pack back",
    )
    parser.add_argument(
        "-o",
        "--out",
        help="write the result here instead of beside the input, same name, other extension",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print the text form instead of writing a file",
    )
    args = parser.parse_args(argv)

    if not args.paths:
        try:
            from .gui import run_gui
        except ImportError:
            # distro packages ship the CLI as pure Python and expect the
            # system python to provide PyQt6; it may genuinely be missing
            print(
                "Error: the GUI needs PyQt6, which is not installed.\n"
                "Install it (pip install \"chumpeditor[gui]\", or your distro's\n"
                "python3-pyqt6 / python-pyqt6 package), or work from the\n"
                "terminal: chumpeditor \"config.chump\"",
                file=sys.stderr,
            )
            return 1

        return run_gui(args.paths)

    if args.out and len(args.paths) != 1:
        parser.error("--out takes a single input file")

    return 0 if run_cli(args.paths, out=args.out, to_stdout=args.stdout) else 1


def run_cli(
    paths: list[str],
    *,
    out: str | None = None,
    to_stdout: bool = False,
) -> bool:
    """Convert every path, printing what happened. Returns False if any failed."""
    ok = True
    for raw in paths:
        path = Path(raw)
        try:
            if to_stdout:
                sys.stdout.write(text_of(path))
            else:
                target = convert_file(path, out)
                print(f"{verb(path)} {path} -> {target}")
        except (ChumpError, OSError) as exc:
            print(f"Error: {path}: {exc}", file=sys.stderr)
            ok = False
    return ok


def verb(path: Path) -> str:
    """What this direction is called, for the message."""
    suffix = path.suffix.lower()
    if suffix in CHUMP_SUFFIXES:
        return "expanded"
    if suffix in TEXT_SUFFIXES:
        return "packed"
    return "converted"


def text_of(path: str | Path) -> str:
    """The text form of a file, whether it comes in as chump or as text."""
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in CHUMP_SUFFIXES:
        with source.open("rb") as stream:
            return render_text(parse_chump(stream.read()))
    if suffix in TEXT_SUFFIXES:
        return read_text_file(source)
    raise ChumpError(
        f"not a chump file ('{'/'.join(CHUMP_SUFFIXES)}') "
        f"and not a text file ('{'/'.join(TEXT_SUFFIXES)}')"
    )


if __name__ == "__main__":
    sys.exit(main())
