# TDX File Format Specification (assets.tdx)

`assets.tdx` is the main Trainz (TANE / TRS19) user-data file, located in the `UserData` folder. It holds two things in one file:

1. The game's **settings**, stored as embedded CHUMP blocks (see [CHUMP File Format Specification](chump-format.md)).
2. The **asset database**: the index of every asset the game knows about.

The file format specification was determined by reverse-engineering and does not reflect any data provided by Auran/N3V.

All data is stored in little-endian (least significant byte first).

> **Note:** Not every `.tdx` file in `UserData` uses this layout. `asset-cache.tdx` is a plain SQLite 3 database (it starts with `SQLite format 3\0`), and `keystore.tdx` has its own unrelated binary layout. This document covers `assets.tdx` only.

## Overall layout

```
+-----------------------------+  0x00
| TDX header (12 bytes)       |
+-----------------------------+  0x0C
| CHUMP block #1 (header 16 B |
|  + contents)                |
+-----------------------------+
| CHUMP block #2 (header 16 B |
|  + contents)                |
+-----------------------------+
| Asset database              |
|  (until end of file)        |
+-----------------------------+  EOF
```

There are no offsets or a section table. Each part starts right where the previous one ends, so you find the database by walking both CHUMP blocks.

## TDX header

| Offset | Size | Description |
|-------:|-----:|-------------|
| 0x00 | 4 | File ID (magic): always `DB A2 EB CE` |
| 0x04 | 4 | Format version (UInt32). Each game release uses a different value (see [Version differences](#version-differences)). TANE = `40 00 00 00` (64). |
| 0x08 | 4 | Total file size in bytes (UInt32), including this header. E.g. `79 0F D6 09` = 165,023,609 bytes. |

The reference parser checks only the magic bytes. It skips fields 0x04 and 0x08.

> **Note:** From TRS22 on, a short string comes **between** the TDX header and the first CHUMP block (see below). A parser that expects `ACS$` at a fixed offset of 0x0C will reject these files.

## CHUMP blocks (settings)

Two CHUMP blocks always follow the header, back to back. Each block uses exactly the standard CHUMP header and tag encoding from [chump-format.md](chump-format.md):

* 4 bytes: `ACS$` (41 43 53 24)
* 4 bytes: Version: `01 00 00 00`
* 4 bytes: Reserved: `00 00 00 00`
* 4 bytes: Contents length (UInt32), in bytes. Contents start right after this field.
* n bytes: a list of top-level tags (usually containers), each encoded as described in the CHUMP spec.

The contents length may be **0**. In that case the block is just the 16-byte header and the next block starts right after it.

Parsing algorithm (as implemented in `StartParse`):

```
p = 0x0C
repeat 2 times:
    expect "ACS$" at p
    len = UInt32 at p + 0x0C
    p   = p + 0x10
    end = p + len
    while p < end: parse tag at p (recursively), advance p
database_offset = p
```

### Tag encoding recap

The CHUMP spec covers this in full. The rules that matter for walking the file:

* `tag length` (4 bytes) counts everything **after** the length field: name-length byte + name + null + type byte + value.
* For a container (type `00`), the children take `tag length − name length − 2` bytes, where name length is the byte value and already includes the null terminator.
* Types seen in `assets.tdx`: `00` container, `01` integer(s), `02` float(s), `03` string, `05` null, `0D` KUID (UUUVNNNN form: user id first, then content id).

### CHUMP block #1: credentials

In older files this block holds a container named `0` with the Trainz serial number:

```
0
{
    cd-key      "XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"
}
```

In current TANE files this block is **empty** (contents length 0). The serial no longer lives here, probably because it moved to `keystore.tdx`.

> **Note:** This block can contain the user's product key. Treat it as sensitive.

### CHUMP block #2: settings

This block holds the game and Content Manager settings as top-level containers. The containers seen, in no fixed order (the order changes between files):

| Container | Contents |
|-----------|----------|
| `render` | Graphics options (`multithreaded_mode`, `texture_streaming`, `start_full_screen`, `full_screen_width`, `full_screen_height`, `full_screen_resolution`, …) |
| `performance` | Performance and detail settings |
| `developer` | Developer options |
| `trainzcontent` | Content / data-folder settings |
| `interface` | UI settings |
| `sound` | Audio settings |
| `general` | General options |
| `internet` | Online / login data |
| `kuid-generator` | Last generated KUID |
| `controlset-<kuid:…>` | One container per keyboard control set. The KUID of the control set is part of the container name. |
| `controls` | Control settings |
| `named-picklists` | Surveyor picklists |
| `search-filters`, `saved-search-filters` | Content Manager filters |
| `dialog-locations`, `dialog-maximised`, `script-dialog-locations` | Window positions |
| `screenshot`, `screenshots` | Screenshot settings and data |
| `tracking` | Usage tracking |
| `trainz-help-popups` | Help pop-ups already shown |
| `testtrack-previous-test` | Last test-track session |
| `sessions-played` | Sessions history |
| `global-module-library-properties` | Global script-library properties |
| `surveyor`, `surveyor-minimap` | Last-used Surveyor data (e.g. `last-scenery-spline`) |

Example in readable form:

```
render
{
    multithreaded_mode          1
    texture_streaming           1
    start_full_screen           0
    full_screen_display         0
    full_screen_width           2560
    full_screen_height          1440
    ...
}
```

## Asset database

The database starts right after the last byte of CHUMP block #2 and runs to the end of the file. It is a **proprietary binary format**, not SQLite or any other standard database container. For now, treat it as a black box. The notes below are observations only, not a specification.

* It starts with a UInt32, e.g. `63 5D 0C 00` (810,339). It is probably a count or ID counter. It does **not** match the number of asset records found.
* Records are variable-length. Each begins with an **8-byte KUID stored content-id first, then user-id**. This is the reverse of the CHUMP `0D` encoding (the `revKuid` helper in `Form1.vb` converts between the two). For example, `06 F5 2C 01 0B 02 00 00` = `<kuid:523:19723526>`.
* Strings use length prefixes, not null terminators. Short fields use a 1-byte length (category class `TX;ENV;AQUA;?EW`, asset name `Big Ripples`). Longer fields use a 4-byte length (the asset's location, e.g. `fld:$(builtin)/base/content/kuid 523 19723526|`).
* Near the end of the database there are a few embedded CHUMP blocks (`ACS$`, standard header). They hold per-asset metadata such as `locally-modified`, `asset-data` and `client-timestamp`. TANE has 6 of them and TRS22 has 10.
* After the asset records, the file ends in long runs of fixed-size entries (pairs of 32-bit values). These look like dependency or index tables.

## Version differences

Four `assets.tdx` files were compared:

| Game | Version @0x04 | Layout after the 12-byte header |
| ---- | ------------: | ------------------------------- |
| TS2010 SP3 | `2C 00 00 00` (44) | Fully **obfuscated** (see below) |
| TS12 | `32 00 00 00` (50) | Fully **obfuscated** (see below) |
| TANE | `40 00 00 00` (64) | Plain: CHUMP #1, CHUMP #2, database |
| TRS22 | `43 00 00 00` (67) | Plain: **edition string**, CHUMP #1, CHUMP #2, database |

The magic bytes (`DB A2 EB CE`) and the total-file-size field at 0x08 mean the same thing in every version.

### TS2010 / TS12: obfuscated body

Every byte after offset 0x0C has close to 8 bits of entropy, and no `ACS$` signature appears anywhere in the file. So the settings and the database are both encoded together.

* **TS12:** in long stretches, each byte equals `offset & 0xFF` (e.g. at file offset 0xB7 the bytes are `B7 B8 B9 …`). That points to an XOR (or add) with a key derived from the byte's position, applied over runs of zero bytes. Undoing only that XOR still doesn't give readable CHUMP data. There is probably another layer, such as compression or a longer key.
* **TS2010:** no such position-based runs appear, so the scheme or key is different.

These versions are not decoded here.

### TRS22: edition string and new data

* **Edition string:** right after the 12-byte header there is a length-prefixed string: 1 byte length, then the characters, with no null terminator. Example: `0B "standard-45"`. The first `ACS$` comes right after it (offset 0x18 in the sample instead of 0x0C).
* **CHUMP #1** is still empty. CHUMP #2 adds new top-level containers, for example `compatibility`, `driver`, `TRS18DriverUserInterface`, `tmds`, `surveyor2-palettes`, `s20-palette-configuration`, `s20-prev-assets`, `picklist`, `ts17-menu-filters`, `ts17-menu-interface`, `BulkEditOperationWindowSize` and `scrapbook-expiry`.
* **New tag type in settings:** the settings now include tags of type `04` (binary). Earlier versions only used `00`, `01`, `02`, `03`, `05` and `0D`.
* **Database records** start the same way as in TANE: a UInt32 (`0F 54 0C 00`), then records whose 8-byte KUID is stored content-id first. Example: `4F 25 01 00 21 17 0A 02` = `<kuid2:661281:75087:1>`.
* **Location strings** can now point inside `.tzarc` archives, e.g. `subf:arc:fld:$(builtin)/^1^11004.tzarc^1|content/kuid2 661281 75087 1`.

### Reading TANE and TRS22 with one parser

1. Check the magic bytes.
2. Read the version at 0x04.
3. If version ≥ 67, skip `1 + len` bytes (the edition string).
4. Walk the two CHUMP blocks as described above.

## Example: start of a TANE `assets.tdx`

```
00000000: DB A2 EB CE 40 00 00 00 79 0F D6 09   TDX header (file size 0x09D60F79)
0000000C: 41 43 53 24 01 00 00 00 00 00 00 00   CHUMP #1 "ACS$", version 1
00000018: 00 00 00 00                           CHUMP #1 length = 0 (empty)
0000001C: 41 43 53 24 01 00 00 00 00 00 00 00   CHUMP #2 "ACS$", version 1
00000028: D4 A5 00 00                           CHUMP #2 length = 0xA5D4
0000002C: 6A 02 00 00 07 r e n d e r 00 00      tag "render", container, 0x26A bytes
...
0000A600: 63 5D 0C 00 ...                       asset database (0x2C + 0xA5D4)
```
