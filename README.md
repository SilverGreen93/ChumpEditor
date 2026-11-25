# Chump Editor

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/SilverGreen93/ChumpEditor)](https://github.com/SilverGreen93/ChumpEditor/releases/latest) [![Downloads (Latest Release)](https://img.shields.io/github/downloads/SilverGreen93/ChumpEditor/latest/total?label=latest%20release%20downloads)](https://github.com/SilverGreen93/ChumpEditor/releases/latest) ![GitHub all releases](https://img.shields.io/github/downloads/SilverGreen93/ChumpEditor/total?label=total%20downloads)

Editor for `config.chump` or `config.txt` files.
Can also open `.cdp` and `assets.tdx` files, decoding both CHUMP blocks of a `.tdx` into the editor.

Features:

- Can convert Trainz `.chump` files - the binary form of an asset's `config.txt` - to and from their readable text form.
- Can be used directly as an editor for `config.txt`/`config.chump` files
- Can open `.cdp` files or `assets.tdx` files and export them as `.chump` file or as `.txt`.
- Contains tweaks to modernize obsolete config files (see below)
- Offers syntax highlighting and line numbers
- Syntax checking for files
- Quick find & replace
- Displays the config tree outline

![screenshot](assets/screenshot.png)

For CLI, the extension picks the direction: a `.chump` (or `.cdp`) is expanded into
`.txt`, a `.tdx` is expanded into `.txt` (both CHUMP blocks together), a `.txt` is
packed back into `.chump`. The text that comes out is laid
out the way Trainz writes it - UTF-8 with a BOM, CRLF line endings, values
starting on column 40 - with one addition of our own: every container is set off
from the tags beside it with a blank line, at the top of the file and as far down
inside other containers as the file goes.

## Getting Started

From a terminal:

```
pip install -e ".[gui]"
chumpeditor-gui                 # open the GUI
chumpeditor config.chump        # -> config.txt beside it
chumpeditor config.txt          # -> config.chump beside it
```

Or, from a checkout, without installing anything (only needs Python 3.9+ and
PyQt6 for the GUI):

```
python chumpeditor_cli_entry.py config.chump
python chumpeditor_gui_entry.py
```

Prebuilt Windows builds come as a portable zip and a per-user MSI; see [Releases](https://github.com/SilverGreen93/ChumpEditor/releases/latest).

## Command line

```
usage: chumpeditor [-h] [-o OUT] [--stdout] [paths ...]

Convert Trainz .chump files to and from their text form.

positional arguments:
  paths          .chump files to expand and/or .txt files to pack back

options:
  -h, --help     show this help message and exit
  -o, --out OUT  write the result here instead of beside the input, same name,
                 other extension
  --stdout       print the text form instead of writing a file
```

- The output normally lands next to the input, same name, other extension. Any
  file already there is overwritten, since that is the file this tool wrote.
- `-o` names the output instead (one input file only).
- `--stdout` prints the text form and writes nothing.
- Run it with **no arguments** and the GUI opens instead.
- Several files at once are fine - `chumpeditor config1.chump config2.chump`,
  or let your shell expand a wildcard (PowerShell does not do that by itself,
  so there `Get-ChildItem *.chump | ForEach-Object { chumpeditor $_ }`). One
  bad file is reported and the rest still convert; the exit code is `1` if
  anything failed.

```
chumpeditor config.chump                    # expand
chumpeditor config.chump --stdout           # just look at it
chumpeditor config.txt -o rebuilt.chump     # pack to a chosen name
```

The verbs in the output name the direction: `expanded` writes text, `packed`
writes binary.

## GUI

The main area is one rich text editor: the text form of a file in a fixed width
font, coloured by keyword, with the lines numbered down the left. Ctrl and the
mouse wheel over the text makes those letters bigger or smaller, and the size you
left them at is waiting there next time. The colours are paint rather than
content - undo only ever goes back over the text, the numbers are never part of
it, and what is saved is plain text whatever a line looked like.

- Name a `.chump`, `.cdp`, `.tdx` or `.txt` on the command line, or drop one anywhere on
  the window (including onto the text), and it opens straight in the editor; a
  binary chump, cdp or tdx is expanded for display and nothing is written until you save.
- The title carries the file's name and a `*` while it has changes that are
  not on disk.
- Work that is not on disk is asked about before anything replaces it - opening
  a file, dropping one in, or quitting - with **Save**, **Discard** and
  **Cancel**. Nothing is written unless you choose Save, and a Save that is
  then talked out of stops the whole thing. A `.cdp` or an `assets.tdx` has no
  form this program can write back, so that question offers only **Discard** and
  **Cancel**, and the export items are where the work goes.
- One file at a time. Several paths at once open the first and say which ones
  were left out.
- **File**: Open file... (Ctrl+O, filtered to `.chump`, `.cdp`, `.tdx` and `.txt`), Recent
  files (the ten opened last, and Clear list), the two write pairs, Syntax check
  (F5), Exit. The words on the write pairs answer to the file that is open:
  **Save** is the form that file is kept in and **Export** the other one, so a
  `.chump` offers Save chump (Ctrl+S), Save chump as..., Export txt (Ctrl+E) and
  Export txt as..., a `.txt` offers the same pair the other way round, and a
  `.cdp` or `assets.tdx` has no save at all - just Export chump (Ctrl+S), Export
  chump as..., Export txt (Ctrl+E) and Export txt as....
- A write of either sort goes to the opened file's own folder, under the same
  name, with the extension of the form being written; no dialog is in the way
  unless the file has no name yet or you chose the *...as* item. A save writes
  the file that is on screen and is never asked about; an export lands on a
  different name every time, so if that name is already taken it asks whether to
  overwrite it, however often the same item was pressed before. A save makes the
  file it wrote the one you are editing; an export
  leaves the opened file on screen and the exported file is never loaded.
- **Edit**: Undo, Redo, Copy, Cut, Paste, Select All, Find & Replace (Ctrl+F).
- **View**: Treeview (F2) - a tick box that puts a list of the file's containers
  along the left of the text. Wrap lines (F4) - a tick box that makes a line too
  wide for the text area stand over several rows inside it, instead of running on
  past the edge. See [Tree of containers](#tree-of-containers) and
  [Wrap lines](#wrap-lines).
- Ctrl held while the mouse wheel turns over the text sizes the letters, one point
  a notch, and that size is remembered. A wheel without Ctrl only scrolls. See
  [The size of the text](#the-size-of-the-text).
- The window comes back the size it was closed at, filled across the screen or not;
  the first time it opens at 940 by 660. See
  [The size of the window](#the-size-of-the-window).
- **Tweaks**: Convert obsolete lists, Convert asset-filename to mesh-table,
  Remove language tags and Reorder tags - the tidy-ups of the way older versions
  of Trainz wrote a file.  Reorder tags also puts the blank lines right: one sets a
  container off from the tags beside it, and a blank line that only parts two tags
  comes out.  A file the editor expands already has its containers set off that way,
  at every depth, so what is left to fix is mostly the order, along with any blank
  line an out-of-place tag carries into the wrong gap.
- **Help**: About - what the program does, the version, the copyright and a link
  to this repository.

The GUI settings are stored in:

```
%APPDATA%\ChumpEditor\settings.json    (Windows)
~/.config/ChumpEditor/settings.json    (elsewhere)
```

### Tweaks

The list and description of the available tweaks can be found here: [tweaks.md](tweaks.md)

### Colour themes

What gets coloured is a small JSON file, not something written into the program:

```json
{
  "name": "Trainz config",
  "caseSensitive": true,
  "languageSuffixes": true,
  "styles": {
    "default":    {"colour": "#000000", "dark": "#ffffff"},
    "tags":       {"colour": "#0000ff", "dark": "#3fd0e0"},
    "obsolete":   {"colour": "#ff0000", "italic": true, "dark": "#ff5f5f"},
    "delim_str":  "#008000"
  },
  "pairs":    [{"style": "delim_str", "open": "\"", "close": "\""}],
  "keywords": [
    {"style": "obsolete", "words": ["origin", "reskin"],
     "patterns": ["category-(era|region)-[0-9]+", "icon[0-9]+"]},
    {"style": "tags",       "all": "tags"},
    {"style": "containers", "all": "containers"}
  ],
  "numbers":  null
}
```

Add a word to a list or change a colour and the next line is coloured by it. A
pair with an empty `close` colours the rest of the line it starts on, a pair left
open at the end of a line carries on into the next one, and inside a pair the
pair's own colour wins over any keyword.

Most of the colouring of a config file follows what a name *is* rather than which
name it is, so a list may say `all` instead of naming any word: `"all": "tags"`
colours the name of every tag, `"all": "containers"` the name of every container.
A container is the one a `{` follows, on the same line or on the one below, which
is how the file is read anyway; every other name at the start of a line is a tag.
Naming words says more than naming a sort of name, so where a name is covered
both ways the words decide the colour - which is how the shipped theme marks the
tags Trainz no longer uses in red while every other tag is blue. Two lists may
cover the same sort of name, in which case the first one wins.

A list may give `patterns` instead of, or as well as, `words`: regular
expressions tried against a whole word, never part of one. That is how a family
of tags that Trainz numbers as far as it likes - `category-era-0`,
`category-era-1`, and whatever an asset happens to carry - takes one line rather
than one entry each. Spelled-out words are tried first, so one member of a
family can still be picked out and coloured another way. They are ordinary
Python regular expressions, and inside JSON a backslash has to be doubled, so
`[0-9]+` is easier to read than `\\d+`.

`languageSuffixes` (off unless it says `true`) colours a tag ending in a two
letter language code as the tag it is written after: `icon-texture-ru` and
`icon-texture-ro` take the colour of `icon-texture`, which is one of the tags
Trainz no longer uses. Only the shape of the tail is checked, because a list of
every language code is not something to keep up to date, and a tag with nothing
to borrow its colour from falls back on the colour of its sort of name.

A style can also name a `dark` colour, which is what it becomes when the desktop
is dark. Blue that is readable on white is nearly invisible on a dark editor, and
black text on a black background is simply missing, so the shipped theme answers
every style twice - the tag blue, for instance, is cyan `#3fd0e0` in a dark
editor. The editor decides which half to paint from the colour behind its own
text, so it follows the desktop as it goes dark or light. A style that names no
`dark` colour is painted with the one it has either way.

To use your own copy rather than editing the program's files, put a
`trainz.json` here:

```
%APPDATA%\ChumpEditor\themes\    (Windows)
~/.config/ChumpEditor/themes/         (elsewhere)
```

## Project layout

```
src/chumpeditor/chump.py       the codec: parse/pack binary, parse/pack text, convert_file
src/chumpeditor/document.py    opening, saving, exporting: the rules the editor follows
src/chumpeditor/theme.py       the colour themes: the JSON format, reading and writing one
src/chumpeditor/scan.py        which rule of a theme owns which stretch of a line
src/chumpeditor/tweaks.py      the four tidy-ups of the way older files read: Tweaks does this
src/chumpeditor/search.py      where a piece of text stands in another, and what replaces it
src/chumpeditor/paths.py       where this program's own files are kept
src/chumpeditor/recent.py      the ten files opened last: recent.json in that folder
src/chumpeditor/settings.py    what is remembered between runs: settings.json there
src/chumpeditor/cli.py         command line
src/chumpeditor/themes/        the theme that ships (trainz.json)
src/chumpeditor/gui/           PyQt6 window: window.py, editor.py, menus.py, about.py,
                               highlighter.py, drops.py, find.py, resources.py
chumpeditor_cli_entry.py       entry points used by PyInstaller
chumpeditor_gui_entry.py
tests/                         614 tests
tests/test_files/              sample .chump/.txt pairs
build.py                       PyInstaller exes, dmg, deb, pkg.tar.zst
installer/                     WiX v5 per-user MSI (Windows)
hooks/                         PyInstaller hooks
assets/                        icon and README screenshot
```

The GUI and the command line both go through `chump.py`: `document.py` holds
the open/save/export rules the window follows, `convert_file()` the extension
rule the CLI follows, so neither rule is written twice.

## Tests

```
pip install -e ".[test]"
python -m pytest
```

The samples in `tests/test_files` are ground truth: each `.chump` is expanded
and the text compared to the sample `.txt`, then packed back and compared to
the original bytes.  `semnal.chump` is the one sample with no `.txt` pair and
no byte-exact way back: it is a real signal asset, there to show the blank lines
around containers written deep inside other containers.  Those files are kept
byte-exact by `.gitattributes`, so don't let an editor rewrite them.

## Building

PyInstaller cannot cross-compile, so `build.py` builds what its host OS
supports:

| Host | Artifact | Needs |
| --- | --- | --- |
| Windows | `dist/ChumpEditor-<ver>-windows.zip` (both exes) | `pip install -e ".[gui,build]"` |
| Windows | `dist/ChumpEditor-<ver>.msi` (GUI + CLI) | WiX v5, `pwsh installer/build.ps1` |
| macOS | `dist/ChumpEditor-<ver>-macos.dmg` | `hdiutil` |
| Linux | `dist/chumpeditor_<ver>_amd64.deb` | [fpm](https://fpm.readthedocs.io/) |
| Linux | `dist/chumpeditor-<ver>-x86_64.pkg.tar.zst` | fpm |

```
python build.py                    # everything this host can do
python build.py --only exe         # or dmg, deb, zst
pwsh installer/build.ps1           # MSI; expects the exes build.py just made
```

The version is written in three places - `pyproject.toml`, `VERSION` in
`build.py` and `chumpeditor.__version__` - and they have to agree.

The installer installs **for the current user only**, no elevation: files under
`%LOCALAPPDATA%\Programs\ChumpEditor`, a Start Menu shortcut for the GUI, the
folder added to the *user* `PATH` so `chumpeditorcli` works from any terminal,
and an entry in Add/Remove Programs. Rebuilding the same version is fine - it
replaces the old install.

The name is spelled two ways on purpose. **Chump Editor**, with a space, is
what a person reads: the window title, the Start Menu shortcut, the entry in
Add/Remove Programs. **ChumpEditor**, without one, is what a person types:
`ChumpEditor.exe`, `chumpeditorcli`, and every folder.

## Notes on the format

See [chump-format.md](chump-format.md) for the reference. The short version:

- A `.chump` starts with `ACS$`, the format version (1), a reserved zero and
  the content length; the tags start at offset 16.
- Each tag is its total length, its name length, its name, a NUL, a type byte
  and a value.
- Type bytes: `0x00` container, `0x01` int32, `0x02` float32, `0x03` string,
  `0x04` binary, `0x05` null (a tag with no value), `0x06` int64, `0x0D` kuid.
- Every number in the file is little-endian. A kuid is two 32-bit words: the
  first holds 25 bits of signed uid with 7 bits of asset version above them,
  the second is a signed 32-bit content id. Only a positive uid can carry a
  version, which is what separates a `<kuid2:uid:cid:version>` from a
  `<kuid:uid:cid>`.

Two places where the written spec and the files disagree, resolved in favour of
the bytes: the spec never lists `0x05` or `0x0D`, and `kuid-format.md` says a
kuid is type `0x05` while the example bytes in that same document say `0x0D`.
A type byte the reader does not know is kept as `RawValue` and written back
unchanged.

**Lossy through the text detour.** The text form has no notation for a `BINARY`
(`0x04`) value, so its bytes are written out raw and read back as a string with
a different type byte. Nothing in this repo's samples is `BINARY`, which is why
the round-trip tests pass; if a `.chump` of yours has one, keep the original
next to the text rather than deleting it. Everything else - containers, ints,
floats, strings, nulls, kuids - survives.

The assets.tdx format is described in [tdx-format.md](tdx-format.md)

## Related software

- [CDP Explorer](https://github.com/SilverGreen93/CDPExplorer) - browse and extract `.cdp` files
- [TZarchiver](https://github.com/SilverGreen93/TZarchiver) - extract and create `.tzarc` archives
- [Kuid Lister](https://github.com/SilverGreen93/KuidLister) - create lists of KUIDs from plain text
- [Kuid2Hash](https://github.com/SilverGreen93/Kuid2Hash) - convert KUIDs to binary and get the hash folder
