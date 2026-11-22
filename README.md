# Chump Editor

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/SilverGreen93/ChumpEditor)](https://github.com/SilverGreen93/ChumpEditor/releases/latest) [![Downloads (Latest Release)](https://img.shields.io/github/downloads/SilverGreen93/ChumpEditor/latest/total?label=latest%20release%20downloads)](https://github.com/SilverGreen93/ChumpEditor/releases/latest) ![GitHub all releases](https://img.shields.io/github/downloads/SilverGreen93/ChumpEditor/total?label=total%20downloads)

Editor for `config.chump` or `config.txt` files.

Features:

- Can convert Trainz `.chump` files - the binary form of an asset's `config.txt` - to and from their readable text form.
- Can be used directly as an editor for config.txt/config.chump files
- Contains tweaks to modernize obsolete config files (see below)
- Offers syntax highlighting and line numbers
- Syntax checking for files
- Quick find & replace

![screenshot](assets/screenshot.png)

For CLI, the extension picks the direction: a `.chump` (or `.cdp`) is expanded into
`.txt`, a `.txt` is packed back into `.chump`. The text that comes out is laid
out the way Trainz writes it - UTF-8 with a BOM, CRLF line endings, values
starting on column 40 - with one addition of our own: every container is set off
from the tags beside it with a blank line, at the top of the file and as far down
inside other containers as the file goes, which is the same layout rule
[Reorder tags](#reorder-tags) follows. A file you never touched comes back byte
for byte; the one thing the text form cannot carry is the type of a number, so a
float that reads out whole (`fontcolor   0`) goes back as an int.

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
font, coloured by keyword, with the lines numbered down the left. The colours are
paint rather than content - undo only ever goes back over the text, the numbers
are never part of it, and what is saved is plain text whatever a line looked like.

- Name a `.chump`, `.cdp` or `.txt` on the command line, or drop one anywhere on
  the window (including onto the text), and it opens straight in the editor; a
  binary chump is expanded for display and nothing is written until you save.
- The title carries the file's name and a `*` while it has changes that are
  not on disk.
- Work that is not on disk is asked about before anything replaces it - opening
  a file, dropping one in, or quitting - with **Save**, **Discard** and
  **Cancel**. Nothing is written unless you choose Save, and a Save that is
  then talked out of stops the whole thing.
- One file at a time. Several paths at once open the first and say which ones
  were left out.
- **File**: Open file... (Ctrl+O, filtered to `.chump`, `.cdp` and `.txt`), Recent
  files (the ten opened last, and Clear list), Save chump (Ctrl+S), Save chump
  as..., Export txt (Ctrl+E), Export txt as..., Syntax check (F5), Exit.
- **Edit**: Undo, Redo, Copy, Cut, Paste, Select All, Find & Replace (Ctrl+F),
  Find next (F3).
- **Tweaks**: Convert obsolete lists, Convert asset-filename to mesh-table,
  Remove language tags and Reorder tags - the tidy-ups of the way older versions
  of Trainz wrote a file.  Reorder tags also puts the blank lines right: one sets a
  container off from the tags beside it, and a blank line that only parts two tags
  comes out.  A file the editor expands already has its containers set off that way,
  at every depth, so what is left to fix is mostly the order, along with any blank
  line an out-of-place tag carries into the wrong gap.
- **Help**: About - what the program does, the version, the copyright and a link
  to this repository.

Neither Save nor Export writes a file the format would refuse. The text on screen
is read and checked first: a container whose `{` / `}` pair is missing a half,
quote marks that do not come in twos, a quote mark in a tag name, half a kuid
(`<kuid:1:2` or `kuid:1:2>`), and one name written twice in the same container are
named with their line number - counted the same way as the numbers down the side
of the text - instead of going to disk. The
quote pairing is the part that reading alone cannot catch: a
`kind "interior` that lost its closing quote runs on through the tags after it and
stops at the quote meant to open the next value, so the file still reads - it just
reads as one long value instead of several. Inside a quoted value the marks still
have to pair up; a bracket in a license string is only prose.

A name counts against the container it is written in, and a container holds one
tag per name, so two of one name contradict each other and the reader has no way
to choose. This is refused, with the line of the first copy named as well:

```
username                              "abc"
username                              "bcdf"
```

so is a second container of one name written beside the first, which is how a file
ends up with two `kuid-table`s. The same name one level down is a different tag,
since it belongs to another container, and stays:

```
username                              "abc"

container
{
  username                            "bcdf"
}
```

### Recent files

**File > Recent files** lists the ten files opened last, newest first, and
clicking one opens it again. The list keeps the whole name of each file, since
the file's own name is the part that says what it is; a file that has gone
missing since is still listed but greyed out, because the drive it was on may be
away rather than gone. **Clear list**, always the last item, forgets all of them,
and is greyed out when there is nothing to forget.

An opening counts once however many times the same file is opened, and a file
that would not open is not listed. The list is one small file of the program's
own, kept with the themes:

```
%APPDATA%\ChumpEditor\recent.json    (Windows)
~/.config/ChumpEditor/recent.json         (elsewhere)
```

So it is the same list the next time the program starts, and a list you can read
or delete by hand. Writing it is never part of opening a file: should the list
refuse to be written, the file still opens and the status bar says so.

### Find and replace

**Edit > Find & Replace** (Ctrl+F) brings up a panel along the bottom of the
window, under the text: a Find box, a Replace box, a **Match case** checkbox, and
**Find next (F3)**, **Replace**, **Replace all** and **Close** buttons. It is a
strip of the window rather than a window of its own, so nothing about the text
area - the numbers down the side, the colours, the undo history - is disturbed,
and **Close** or Escape puts it away again. Whatever was selected before opening
it goes into the Find box, and what was last asked for stays there, so the same
search can be run again after a change.

- **Find next** (F3, or Enter in the Find box) selects the next place the text
  stands, past the one the caret is on, and the status bar names the line. Past
  the end of the file it starts again from the top and says so, so pressing the
  key over and over walks right round the file.
- **Replace** (or Enter in the Replace box) writes over the match the selection
  is on and moves to the next one. With nothing selected, or with a selection
  that is not the text being sought, nothing is written and the next match is
  found instead.
- **Replace all** does every place in the file at once, and the status bar says
  how many there were.

One press of Undo takes back one Replace, or a whole Replace all, which is one
change however many places it touched. No place is matched twice, so a
replacement that holds the very text it replaces (`kuid` into `kuid_table`) does
not turn into a search that never ends. An empty Find box asks for nothing: the
status bar says *Nothing to look for* rather than finding a match between every
two characters.

What is sought is plain text, not a pattern, so brackets, dots and backslashes
are looked for as the characters they are.

### Syntax check

**File > Syntax check** (F5) asks for those same rules without writing anything.
A write stops at the first fault it finds, which is the right thing to do to a
file and a poor way to answer a question, so this says all of them, one per line,
in the order their lines come:

```
Line 2: tag 'username' is written twice at the same level, the first one on line 1
Line 3: value for tag 'k': '<' with no '>' after it
Line 4: quoted value for tag 'kind' is never closed
```

What follows an unclosed quoted value is left out of the list, because those
lines are part of the value rather than tags of their own. The status bar says how
many were found, and a file with nothing wrong with it is told as well: *No
problems found*. Nothing on screen is touched and no file is written, so the check
is worth pressing before a save rather than only after one refused it.

### Tweaks

#### Convert obsolete lists

Older assets write a list as a run of numbered tags:

```
category-era-0                        "1920s"
category-era-1                        "1930s"
category-era-2                        "1940s"
```

and the same list now reads as one tag with the elements between semicolons:

```
category-era                          "1920s;1930s;1940s"
```

**Tweaks > Convert obsolete lists** makes that change for every group in the text
on screen, keeps the values in the order the numbers say and the columns where
they stood, and ends with a message naming every tag it changed and every one it
left alone, with the reason. One press of Undo takes the whole change back.

A tag with `-number` on the end is changed when it stands on a line of its own
holding a quoted value. A run of them at one indent becomes one tag with the
values between semicolons; one standing on its own keeps its value and only loses
the number, because a list of one is still written as a single tag:

```
category-region-0                       "SE"
```

becomes

```
category-region                         "SE"
```

Nothing is touched when a value holds a `;` itself, or when the file already has
a tag of the plain name, or when another group of the same tags took that name
first - those are listed as left alone, with the reason. A `load0` or `camera0`
carries no dash, means something else entirely, and is never touched.

#### Convert asset-filename to mesh-table

An older asset says which mesh it loads with a single tag:

```
asset-filename                          "MS_Shelter_4"
```

and the newer kind says the same thing with a container:

```
mesh-table
{
  default
  {
    mesh                                "MS_Shelter_4.im"
    auto-create                         1
  }
}
```

**Tweaks > Convert asset-filename to mesh-table** makes that change for every tag
in the text on screen: the tag goes, the container comes in at the indent the tag
stood at with its values on the same column as the rest of the file, and `.im`
goes on the end of the name - which is what the tag left off, and what a name
that already has it keeps once. The message afterwards names the mesh each new
container loads, and one press of Undo takes the whole of it back.

A file that already has a `mesh-table` is left exactly as it was, and the message
is a warning rather than a note: two containers would leave Trainz choosing
between two meshes. A tag that names no mesh - no value, empty quotes, a value
that is not in quotes, one running over several lines, or the tag itself used as
a container - is left where it is and listed with the reason.

#### Remove language tags

An asset with text for several languages writes the same tag once per language:

```
description                             "casualwoman3"
description-de                          "Freizeit-Frau3"
description-ru                          "Прохожая3"
```

**Tweaks > Remove language tags** takes out every tag whose name ends in a dash
and two letters, the value with it, and leaves the plain `description` standing.
The message afterwards names every tag that went and says which one stayed, and
one press of Undo takes the whole sweep back.

The value goes with the tag however it is written: one on the line, one running
over several lines, or a whole container - its braces and everything inside
them, since that is its value. The two letters can be any two letters, because
the assets write `username-cn` and `username-jp` as often as they write the
proper `-zh` and `-ja`. A tag that is only spelled as if it were one, like
`contact-email` or a three-letter `description-eng`, is left alone, and so is a
tag whose value or container is never closed; that is said out loud rather than
cut into.

#### Reorder tags

A chump file works with its tags in any order, but the ones Trainz writes have a
shape to them, and an asset edited by hand over ten years tends to lose it. **Tweaks
> Reorder tags** puts the top level tags back in that shape:

- `kuid` and then `username`, whatever was written above them;
- every tag that holds one value, in the order they were found;
- every container, in the order they were found;
- `kuid-table` and `obsolete-table` after all the other containers, when the file
  has them.

The same tidy-up reaches inside the containers, by a simpler rule: the tags
holding a value come first and the containers written beside them come after,
each keeping the order they were found in, at every depth of the file. Down there
no name is special, so a `kuid` written inside a sub-container stays where the
file put it.

```
kind                                    "interior"
mesh-table
{
  default
  {
    effects
    {
    }
    mesh                                "interior.im"
    auto-create                         1
  }
}
kuid                                    <kuid:79373:50023>
username                                "CFR interior"
obsolete-table
{
}
kuid-table
{
}
```

becomes

```
kuid                                    <kuid:79373:50023>
username                                "CFR interior"
kind                                    "interior"

mesh-table
{
  default
  {
    mesh                                "interior.im"
    auto-create                         1

    effects
    {
    }
  }
}

kuid-table
{
}

obsolete-table
{
}
```

On top of the order, a blank line separates a container from the line written
beside it, and nothing else: one under its closing `}` wherever another tag
follows it, and one above the line naming it wherever a tag stands there, however
deep inside the file the container sits, since those gaps are what show where one
container ends and the next one begins. None stands beside a brace - above another
`}` would drive a wedge between a tag and the container it is written inside, and
below a `{` would part a container from the brace it opens - and none at the start
or the end of the file, where there is nothing to separate. The rule is read both
ways, so a gap comes in where it is missing and comes out where the file has one
the rule does not ask for: a blank line between two tags that each hold one value,
a second blank line in a gap that one already says once, and a blank line inside a
container's braces. One gap between two containers serves the two of them. A blank
line written inside a value that runs over several lines belongs to that value and
is left where it is. The decoder puts those container gaps in when it expands a
`.chump`, so text coming from a `.chump` whose tags already stand in the order needs
nothing but the order; where its tags do not, a blank line travelling with a tag can
land between two tags, and comes out.

Nothing inside a container is moved out of it, and a container moves as one block,
so a subtag cannot be split from the braces holding it. The blank lines under a tag
travel with it and are then looked at as the file stands afterwards, which is why a
gap that belonged to a container keeps working after that container has moved and a
gap that only parted two tags comes out. The blank lines at the start of the file
and the ones at the end are nobody's gap and are left alone. Only the stretch
between the first tag out of place and the last one is rewritten, in every
container that has tags out of place as well as at the top, plus one short edit for
each blank line that has to come in or go where nothing moved - everything else is
not touched, which is why pressing the item a second time says *Nothing was
reordered*. One press of Undo takes the whole change back, every stretch and every
blank line together.

The message names every tag that moved, in a container as well as at the top, and
the line it moved to, every container that gained a blank line - saying whether it
went above the line naming the container or under the `}` closing it, and which
line it went beside - and every blank line that came out, as the line it stood
under. A tag whose value or container is never closed, and a line that is not a tag
at all, mean there is no safe line to cut the file on: nothing moves at all, and the
message is a warning naming the line.

### Colour themes

What gets coloured is a small JSON file, not something written into the program:

```json
{
  "name": "Trainz config",
  "caseSensitive": true,
  "languageSuffixes": true,
  "styles": {
    "default":     {"colour": "#000000", "dark": "#ffffff"},
    "keywords1":   {"colour": "#0000ff", "dark": "#3fd0e0"},
    "keywords3":   {"colour": "#ff0000", "italic": true, "dark": "#ff5f5f"},
    "delimiters1": "#008000"
  },
  "pairs":    [{"style": "delimiters1", "open": "\"", "close": "\""}],
  "keywords": [
    {"style": "keywords1", "words": ["kind", "kuid"],
     "patterns": ["camera[0-9]+", "car[0-9]+",
                  "wave[0-9]+-(magnitude|scale|speed)"]}
  ],
  "numbers":  null
}
```

Add a word to a list or change a colour and the next line is coloured by it. A
pair with an empty `close` colours the rest of the line it starts on, a pair left
open at the end of a line carries on into the next one, and inside a pair the
pair's own colour wins over any keyword.

A list may give `patterns` instead of, or as well as, `words`: regular
expressions tried against a whole word, never part of one. That is how a family
of tags that Trainz numbers as far as it likes - `category-era-0`,
`category-era-1`, and whatever an asset happens to carry - takes one line rather
than one entry each. Spelled-out words are tried first, so one member of a
family can still be picked out and coloured another way. They are ordinary
Python regular expressions, and inside JSON a backslash has to be doubled, so
`[0-9]+` is easier to read than `\\d+`.

`languageSuffixes` (off unless it says `true`) colours a tag ending in a two
letter language code as the tag it is written after: `description-ru` and
`description-ro` take the colour of `description`. Only the shape of the tail is
checked, because a list of every language code is not something to keep up to
date; a tag with nothing to borrow its colour from stays plain.

A style can also name a `dark` colour, which is what it becomes when the desktop
is dark. Blue that is readable on white is nearly invisible on a dark editor, and
black text on a black background is simply missing, so the shipped theme answers
every style twice - the keyword blue, for instance, is cyan `#3fd0e0` in a dark
editor. The editor decides which half to paint from the colour behind its own
text, so it follows the desktop as it goes dark or light. A style that names no
`dark` colour is painted with the one it has either way.

To use your own copy rather than editing the program's files, put a
`trainz.json` here:

```
%APPDATA%\ChumpEditor\themes\    (Windows)
~/.config/ChumpEditor/themes/         (elsewhere)
```

That one wins over the shipped one, and nothing is created there until you write
it.

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

See [chump-format.md](https://github.com/SilverGreen93/CDPExplorer/blob/master/chump-format.md) for the reference. The short version:

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

## Related software

- [CDP Explorer](https://github.com/SilverGreen93/CDPExplorer) - browse and extract `.cdp` files
- [TZarchiver](https://github.com/SilverGreen93/TZarchiver) - extract and create `.tzarc` archives
- [Kuid Lister](https://github.com/SilverGreen93/KuidLister) - create lists of KUIDs from plain text
- [Kuid2Hash](https://github.com/SilverGreen93/Kuid2Hash) - convert KUIDs to binary and get the hash folder
