"""The file side of the editor: what opening, saving and exporting mean.

Deliberately free of Qt, so the rules the window follows can be read and
tested on their own:

* opening a ``.chump`` or ``.cdp`` puts its text form in the editor, opening a
  ``.txt`` puts the file in as it stands;
* saving writes the editor's text back as a binary chump, whatever the name
  the file has now;
* exporting writes the editor's text as a text file laid out the way the
  original expander wrote one: UTF-8 with a BOM, CRLF line endings;
* both of them start with ``check_text``, so text the format would misread -
  half a container, a loose quote mark, half a kuid, one name written twice in
  the same container - is reported instead of written;
* ``find_problems`` says all of those faults rather than only the first one,
  which is what the window's Syntax check has to read out.
"""

from __future__ import annotations

from pathlib import Path

from .chump import (
    CHUMP_SUFFIXES,
    TEXT_SUFFIXES,
    ChumpError,
    check_text,
    dump_chump,
    find_problems,
    parse_chump,
    read_text_file,
    render_text,
)

__all__ = [
    "ALL_GROUP",
    "ALL_SUFFIXES",
    "CHUMP_GROUP",
    "CHUMP_SUFFIXES",
    "FILTERS",
    "TEXT_GROUP",
    "TEXT_SUFFIXES",
    "as_file_text",
    "check_text",
    "filter_string",
    "find_problems",
    "is_readable",
    "read_document",
    "save_chump",
    "save_text",
    "suggested_path",
]

#: every extension the editor takes, chump forms first
ALL_SUFFIXES = CHUMP_SUFFIXES + TEXT_SUFFIXES

#: the dialog groups, named so a save dialog can offer one form on its own
ALL_GROUP = ("All supported files", ALL_SUFFIXES)
CHUMP_GROUP = ("Chump files", CHUMP_SUFFIXES)
TEXT_GROUP = ("Text files", TEXT_SUFFIXES)

FILTERS = (ALL_GROUP, CHUMP_GROUP, TEXT_GROUP)


def filter_string(*groups: tuple[str, tuple[str, ...]]) -> str:
    """The groups as one filter string for QFileDialog.

    A group is a label and the extensions it covers; ``getOpenFileName`` wants
    them as ``label (*.a *.b);;label2 (*.c)``.
    """
    groups = groups or FILTERS
    return ";;".join(
        f"{label} ({' '.join('*' + suffix for suffix in suffixes)})"
        for label, suffixes in groups
    )


def is_readable(path: str | Path) -> bool:
    """A file the editor can open: one of the forms, there on disk."""
    file = Path(path)
    return file.is_file() and file.suffix.lower() in ALL_SUFFIXES


def read_document(path: str | Path) -> str:
    """The text the editor shows for a file, whichever form it is in.

    A binary chump is expanded first; a text file is read as it stands, so the
    spacing a file already has survives an open-and-save round trip.
    """
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in CHUMP_SUFFIXES:
        return render_text(parse_chump(source.read_bytes()))
    if suffix in TEXT_SUFFIXES:
        return read_text_file(source)
    raise ChumpError(
        f"{source.name}: not a chump file ('{'/'.join(CHUMP_SUFFIXES)}') "
        f"and not a text file ('{'/'.join(TEXT_SUFFIXES)}')"
    )


def save_chump(text: str, path: str | Path) -> Path:
    """Pack the editor's text into a binary chump file.

    The line endings go through CRLF first because the editor's document does
    not keep them: a quoted value spanning lines holds whichever ending the
    format uses, and the format uses CRLF, so that is what a value gets back.
    Nothing that fails ``check_text`` is written, so a missing brace, a quote
    with no partner, half a kuid or a name written twice in one container is a
    ChumpError naming the line instead of a file Trainz would refuse to read.
    """
    return dump_chump(check_text(as_file_text(text)), path)


def save_text(text: str, path: str | Path) -> Path:
    """Write the editor's text as a chump text file.

    The text goes out the way the codec writes one, so an export is
    comparable byte for byte with what ``chumpeditor config.chump`` leaves
    beside it: a BOM, and CRLF on every line.  It is checked first for the
    same reason the binary form is: an export is a file somebody hands to
    Trainz, so a value whose quote or ``<`` / ``>`` pair is broken has to be
    reported rather than written.
    """
    check_text(as_file_text(text))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", errors="surrogateescape", newline="") as stream:
        stream.write(as_file_text(text))
    return target


def as_file_text(text: str) -> str:
    """Line endings as one kind, CRLF, whatever the editor used.

    Worth knowing about on its own: a quoted value that spans lines holds the
    line ending the format uses, so text that came from a Qt document has to be
    put back the way the format has it before it is parsed.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def suggested_path(path: str | Path | None, suffix: str) -> Path | None:
    """A sensible name to pre-fill a save dialog with.

    The file being edited keeps its name and takes the new extension, which is
    the rule the command line follows too; without a file to go on there is
    nothing to suggest and the dialog starts empty.
    """
    if path is None:
        return None
    current = Path(path)
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    if current.suffix.lower() == suffix:
        return current
    return current.with_suffix(suffix)
