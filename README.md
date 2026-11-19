# ChumpEditor

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/SilverGreen93/ChumpEditor)](https://github.com/SilverGreen93/ChumpEditor/releases/latest) [![Downloads (Latest Release)](https://img.shields.io/github/downloads/SilverGreen93/ChumpEditor/latest/total?label=latest%20release%20downloads)](https://github.com/SilverGreen93/ChumpEditor/releases/latest) ![GitHub all releases](https://img.shields.io/github/downloads/SilverGreen93/ChumpEditor/total?label=total%20downloads)

Converts Trainz `.chump` files - the binary form of an asset's `config.txt` -
to and from their readable text form.

![screenshot](assets/screenshot.png)

The extension picks the direction: a `.chump` (or `.cdp`) is expanded into
`.txt`, a `.txt` is packed back into `.chump`. The text that comes out is laid
out the way Trainz writes it - UTF-8 with a BOM, CRLF line endings, values
starting on column 40 - so a file you never touched comes back byte for byte.

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

Prebuilt Windows builds come as a portable zip and a per-user MSI; see
[Releases](https://github.com/SilverGreen93/ChumpEditor/releases/latest).

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

The window is deliberately the one the original expander had: a file queue,
and three buttons.

- Drop `.chump` and `.txt` files onto the window (there is no file picker, and
  that is how it was). A converted row is rewritten as `input  ->  output`.
- **Expand chump** converts everything in the queue - `.txt` rows are packed
  back, not skipped.
- **Remove item** takes the selected row out of the queue, **Clear list** empties it.
- A file that cannot be read is reported and stays in the list.

## Project layout

```
src/chumpeditor/chump.py     the codec: parse/pack binary, parse/pack text, convert_file
src/chumpeditor/cli.py       command line
src/chumpeditor/gui.py       PyQt6 window
chumpeditor_cli_entry.py     entry points used by PyInstaller
chumpeditor_gui_entry.py
tests/                       188 tests
tests/test_files/            sample .chump/.txt pairs
build.py                     PyInstaller exes, dmg, deb, pkg.tar.zst
installer/                   WiX v5 per-user MSI (Windows)
hooks/                       PyInstaller hooks
assets/                      icon and README screenshot
```

The GUI and the command line both call `convert_file()` in `chump.py`, so the
extension rule exists once.

## Tests

```
pip install -e ".[test]"
python -m pytest
```

The samples in `tests/test_files` are ground truth: each `.chump` is expanded
and the text compared to the sample `.txt`, then packed back and compared to
the original bytes. Those files are kept byte-exact by `.gitattributes`, so
don't let an editor rewrite them.

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

## Notes on the format

[chump-format.md](https://github.com/SilverGreen93/CDPExplorer/blob/master/chump-format.md)
is the reference. The short version:

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

## Issues

[github.com/SilverGreen93/ChumpEditor/issues](https://github.com/SilverGreen93/ChumpEditor/issues)

## License

GPL-3.0. See [LICENSE](LICENSE).

## Related software

- [CDP Explorer](https://github.com/SilverGreen93/CDPExplorer) - browse and extract `.cdp` files
- [TZarchiver](https://github.com/SilverGreen93/TZarchiver) - extract and create `.tzarc` archives
- [Kuid Lister](https://github.com/SilverGreen93/KuidLister) - create lists of KUIDs from plain text
- [Kuid2Hash](https://github.com/SilverGreen93/Kuid2Hash) - convert KUIDs to binary and get the hash folder
