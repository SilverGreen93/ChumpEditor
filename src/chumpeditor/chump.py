"""Reader and writer for the Trainz CHUMP container format.

A ``.chump`` (or ``.cdp``) file holds a Trainz configuration file in a compact
binary form.  This module turns one into the indented text form the original
Chump expander produced, and reads that text form back into the same bytes.

The binary layout (all values little-endian) is::

    header  "ACS$" | version u32 | reserved u32 | content length u32
    tag     tag length u32 | name length u8 | name | NUL | type u8 | value

A tag length counts everything after itself: the name length byte, the name,
its NUL, the type byte and the value, which for a container is the whole run
of its sub-tags.  The content length in the header likewise counts only what
follows it.  Tag names and string values are plain bytes in the file; CDP
Explorer, the tool the format description comes from, reads them as UTF-8, and
so does this code.

Values are kept as Python types that map straight onto the text form, so
``pack_chump(parse_text(render_text(parse_chump(data))))`` reproduces the
input byte for byte:

    type 00  container  ->  list of tags
    type 01  int32      ->  int, or a list when the value holds several
    type 02  float32    ->  float, or a list when the value holds several
    type 03  string     ->  str
    type 04  binary     ->  bytes
    type 05  null       ->  None
    type 0d  kuid       ->  Kuid, "<kuid:uid:cid>" / "<kuid2:uid:cid:version>"

An int or float tag whose value is longer than one element holds a run of
them, one after another until the tag length is used up, and the text form
writes that run comma separated (``camera   -1.058,0.522,0.887``).

The text form carries no type marker, so a float that reads out whole reads
back as an int (a ``fontcolor   0`` stored as type 02 goes back as type 01);
such a file comes back with that one byte changed and the same tags.

Unknown types are kept as ``RawValue``: their bytes are preserved so a file
that uses types this code does not know about still round-trips.
"""

from __future__ import annotations

import io
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator, Sequence

MAGIC = b"ACS$"
#: the version word every chump file carries, 01 00 00 00 on disk
DEFAULT_VERSION = 1
FORMAT_VERSION = DEFAULT_VERSION  # kept as the VB.NET code named it
NAME_ENCODING = "utf-8"  # tag names are bytes in the file, UTF-8 in CDP Explorer
TEXT_ENCODING = "utf-8"  # string values, same, with a NUL on the end
# both decode and encode with surrogateescape so bytes that are not valid UTF-8
# still survive a read/write cycle instead of turning into replacement marks
DEFAULT_EXTENSION = ".chump"


class ChumpError(ValueError):
    """Raised for anything that is not a readable chump file or text file."""


class TagType:
    """The value type codes used in the tag header."""

    CONTAINER = 0x00
    INT32 = 0x01
    FLOAT32 = 0x02
    STRING = 0x03
    BINARY = 0x04
    NULL = 0x05
    INT64 = 0x06
    KUID = 0x0D


#: the column the value is written from, as in the original expander output
VALUE_COLUMN = 40

_NAME_MAX = 0xFF - 1  # the name length byte counts the terminating NUL


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
@dataclass(eq=False)
class Tag:
    """One tag of the tree: a container (no value_type) or a value tag.

    A value tag holds a single value, or a run of them of one type when its
    value is a list; that is how an int or float tag stores a vector.
    """

    name: str
    tags: list["Tag"] = field(default_factory=list)
    value: object = None
    value_type: int | None = None

    def __post_init__(self) -> None:
        # Tag("light", value=1) is a value tag, not an empty container: give it
        # the type its value implies, the way value_tag() does.
        if self.value is not None and self.value_type is None:
            self.value_type = _type_of(self.value)
        elif self.value_type == TagType.KUID:
            # a kuid is written without quotes, so it has to travel as a Kuid
            self.value = _as_kuids(self.value)

    @classmethod
    def container(cls, name: str, tags: Sequence["Tag"] = ()) -> "Tag":
        return cls(name, list(tags))

    @classmethod
    def value_tag(cls, name: str, value: object, value_type: int | None = None) -> "Tag":
        """A value tag; the type is inferred from the Python value when omitted."""
        if value_type is None:
            value_type = _type_of(value)
        return cls(name, (), value, value_type)

    @property
    def is_container(self) -> bool:
        return self.value_type is None

    @property
    def is_array(self) -> bool:
        """A tag holding a run of values instead of a single one."""
        return isinstance(self.value, (list, tuple))

    def get(self, name: str) -> "Tag | None":
        """The first child tag with this name, or None."""
        for tag in self.tags:
            if tag.name == name:
                return tag
        return None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tag):
            return NotImplemented
        return (
            self.name == other.name
            and self.value_type == other.value_type
            and _values_equal(self.value, other.value)
            # tags may be handed over as a tuple or read back as a list
            and tuple(self.tags) == tuple(other.tags)
        )


@dataclass
class RawValue:
    """A value whose type this code does not implement; its bytes are kept."""

    type_id: int
    data: bytes


def _type_of(value: object) -> int:
    """The value type a Python value maps to."""
    if value is None:
        return TagType.NULL
    if isinstance(value, bool):
        return TagType.INT32
    if isinstance(value, int):
        return TagType.INT32 if -(2**31) <= value < 2**31 else TagType.INT64
    if isinstance(value, float):
        return TagType.FLOAT32
    if isinstance(value, Kuid):  # before str, since a Kuid is a str subclass
        return TagType.KUID
    if isinstance(value, str):
        return TagType.STRING
    if isinstance(value, (bytes, bytearray)):
        return TagType.BINARY
    if isinstance(value, RawValue):  # a type code the reader did not know
        return value.type_id
    if isinstance(value, (list, tuple)):
        if not value:
            raise ChumpError("cannot guess the element type of an empty list")
        # a run of values is stored inline, under the element's own type code
        return _type_of(value[0])
    raise ChumpError(f"unsupported value type: {type(value).__name__}")


def _as_kuids(value: object) -> object:
    """Turn the text of a kuid into a Kuid, wherever the tag holds it.

    The text form writes a kuid bare and a string quoted, so a tag typed KUID
    keeps a Kuid even when the caller handed over a plain str.
    """
    if isinstance(value, (list, tuple)):
        return [item if isinstance(item, Kuid) else Kuid(item) for item in value]
    if isinstance(value, str) and not isinstance(value, Kuid):
        return Kuid(value)
    return value


def _values_equal(left: object, right: object) -> bool:
    if isinstance(left, Kuid) and isinstance(right, Kuid):
        return left == right
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _values_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, float) and isinstance(right, float):
        # the format stores single precision, so two floats are the same value
        # when their float32 bytes are; 1.2999999523162842 and 1.3 both come
        # from the same four bytes, and the text form only ever writes "1.3"
        try:
            return struct.pack("<f", left) == struct.pack("<f", right)
        except (OverflowError, ValueError):  # too big for a float32
            return left == right
    return left == right


# --------------------------------------------------------------------------
# kuid
# --------------------------------------------------------------------------
class Kuid(str):
    """A kuid value, written in the same spelling as the text form.

    Subclasses str so it renders itself, and carries the numbers behind it for
    callers that want to compare ids instead of text.
    """

    __slots__ = ()

    @property
    def kind(self) -> str:
        return "kuid2" if self.startswith("<kuid2:") else "kuid"

    @property
    def uid(self) -> int:
        """The id of the asset this kuid points at."""
        return parse_kuid(str(self))[0]

    @property
    def cid(self) -> int:
        """The id of the asset within its owner."""
        return parse_kuid(str(self))[1]

    @property
    def version(self) -> int:
        """The asset revision, 0 when the text form leaves it out."""
        return parse_kuid(str(self))[2]


#: a kuid's first word holds a 25 bit signed uid, the top 7 bits a version
_UID_BITS = 25
_UID_MAX = (1 << (_UID_BITS - 1)) - 1
_UID_MIN = -(1 << (_UID_BITS - 1))


def kuid_to_hex(text: str) -> bytes:
    """The 8 bytes of a ``<kuid:uid:cid>`` / ``<kuid2:uid:cid:version>``."""
    uid, cid, version = parse_kuid(text)
    if not _UID_MIN <= uid <= _UID_MAX:
        raise ChumpError(f"kuid uid out of range: {uid}")
    if not -(2**31) <= cid < 2**31:  # the content id is a signed 32 bit value
        raise ChumpError(f"kuid content id out of range: {cid}")
    if not 0 <= version < 128:
        raise ChumpError(f"invalid kuid version: {version}")

    # a negative uid has the sign bit of its 25 bits set, which leaves no room
    # for a version: its top bits are just sign extension
    word = (version << _UID_BITS) | (uid & ((1 << _UID_BITS) - 1)) if version else uid
    word &= 0xFFFFFFFF  # a version of 64 or more sets the sign bit of the word
    if word >= 2**31:
        word -= 2**32
    return struct.pack("<ii", word, cid)


def hex_to_kuid(data: bytes) -> Kuid:
    """The ``<kuid:uid:cid>`` literal for 8 kuid bytes.

    The first word is UUUVNNNN: 25 bits of signed uid, then 7 bits of version.
    A negative uid has its sign bit set, so those 7 bits read back as 127; the
    version is only real for a positive uid, and a kuid with no version is
    written the short way, like Trainz displays it.
    """
    if len(data) != 8:
        raise ChumpError(f"a kuid is 8 bytes, got {len(data)}")
    word, cid = struct.unpack("<Ii", data)
    version = word >> _UID_BITS
    uid = word & ((1 << _UID_BITS) - 1)
    uid = uid - (1 << _UID_BITS) if uid > _UID_MAX else uid
    if (version > 0 and uid > 0) or (version == 0 and uid < 0):
        return Kuid(f"<kuid2:{uid}:{cid}:{version}>")
    return Kuid(f"<kuid:{uid}:{cid}>")


def parse_kuid(text: str) -> tuple[int, int, int]:
    """The uid, content id and version of a ``<kuid...>`` literal.

    Read the way the Trainz tools read it: the brackets and the ``kuid`` word
    are optional, a lone number is an uid on its own, and a kuid with no
    version written down has version 0.
    """
    body = text.strip()
    if body.startswith("<") and body.endswith(">"):
        body = body[1:-1]
    for prefix in ("kuid2", "kuid"):
        if body.startswith(prefix):
            body = body[len(prefix):]
            break
    if body.startswith(":"):
        body = body[1:]
    if not body:
        return -1, -1, 0

    parts = [part.strip() for part in body.split(":")]
    if len(parts) == 1:
        parts = [parts[0], "-1"]
    if len(parts) not in (2, 3) or not all(parts):
        raise ChumpError(f"invalid kuid: {text}")
    try:
        uid, cid = int(parts[0]), int(parts[1])
        version = int(parts[2]) if len(parts) == 3 else 0
    except ValueError as exc:
        raise ChumpError(f"invalid kuid: {text}") from exc
    return uid, cid, version


# --------------------------------------------------------------------------
# reading the binary form
# --------------------------------------------------------------------------
def parse_chump(data: bytes) -> Tag:
    """The root container of a CHUMP file."""
    if len(data) < 16:
        raise ChumpError(f"file too short to be a chump file ({len(data)} bytes)")
    if data[:4] != MAGIC:
        raise ChumpError(f"not a chump file (starts with {data[:4]!r})")
    body = data[12:]
    (size,) = struct.unpack_from("<I", body, 0)
    if size != len(body) - 4:
        # the original expander stopped reading at the declared length; a file
        # that does not end there is truncated or padded, and saying so beats
        # returning half a tree
        raise ChumpError(
            f"content length {size} does not match the {len(body) - 4} bytes that follow the header"
        )
    return parse_tag_tree(body[4:])


def load_chump(path: str | Path) -> Tag:
    """Read a .chump file from disk and return its tags."""
    return parse_chump(Path(path).read_bytes())


def parse_tag_tree(data: bytes) -> Tag:
    """A container holding the tags packed into ``data`` (no tag length)."""
    root = Tag("<root>", list(iter_tags(data)))
    return root


def iter_tags(data: bytes) -> Iterator[Tag]:
    """The tags packed one after another into ``data``."""
    offset = 0
    while offset < len(data):
        if len(data) - offset < 5:
            raise ChumpError(f"tag header truncated at {offset}")
        (size,) = struct.unpack_from("<I", data, offset)
        if size < 4:
            # name length byte, name, NUL and type byte cannot fit in less
            raise ChumpError(f"tag length {size} at {offset} is too small for a tag")
        if offset + 4 + size > len(data):
            raise ChumpError(f"tag length {size} at {offset} runs past the end")
        yield _parse_tag(data[offset + 4:offset + 4 + size])
        offset += 4 + size


def _parse_tag(body: bytes) -> Tag:
    """One tag, from the bytes that follow its length."""
    (name_len,) = struct.unpack_from("<B", body, 0)
    # the name length byte counts the name and its NUL; the type byte follows
    if name_len < 2 or name_len + 2 > len(body):
        raise ChumpError(f"tag name length {name_len} does not fit in {len(body)} bytes")
    if body[name_len] != 0:
        raise ChumpError("tag name is not NUL terminated")
    name = body[1:name_len].decode(NAME_ENCODING, "surrogateescape")
    value_type = body[name_len + 1]
    value_bytes = body[name_len + 2:]

    if value_type == TagType.CONTAINER:
        return Tag(name, list(iter_tags(value_bytes)))

    return Tag(name, (), _parse_value(value_type, value_bytes), value_type)


def _parse_value(value_type: int, data: bytes) -> object:
    if value_type == TagType.NULL:
        return None
    if value_type == TagType.INT32:
        if len(data) % 4 or not data:
            raise ChumpError("int32 tag truncated")
        values = [value for (value,) in struct.iter_unpack("<i", data)]
        return values[0] if len(values) == 1 else values
    if value_type == TagType.INT64:
        if len(data) % 8 or not data:
            raise ChumpError("int64 tag truncated")
        values = [value for (value,) in struct.iter_unpack("<q", data)]
        return values[0] if len(values) == 1 else values
    if value_type == TagType.FLOAT32:
        if len(data) % 4 or not data:
            raise ChumpError("float32 tag truncated")
        values = [value for (value,) in struct.iter_unpack("<f", data)]
        return values[0] if len(values) == 1 else values
    if value_type == TagType.STRING:
        # the value is NUL terminated; only that terminator is dropped, a NUL in
        # the middle is part of the string and goes back in when packing
        if data.endswith(b"\x00"):
            data = data[:-1]
        return data.decode(TEXT_ENCODING, "surrogateescape")
    if value_type == TagType.BINARY:
        return data
    if value_type == TagType.KUID:
        if len(data) % 8 or not data:
            raise ChumpError("kuid tag truncated")
        values = [hex_to_kuid(chunk) for (chunk,) in struct.iter_unpack("<8s", data)]
        return values[0] if len(values) == 1 else values
    return RawValue(value_type, data)


# --------------------------------------------------------------------------
# writing the binary form
# --------------------------------------------------------------------------
def write_chump(root: Tag, stream: BinaryIO, *, version: int = FORMAT_VERSION) -> None:
    """Write the container's tags as a CHUMP file."""
    content = b"".join(_pack_tag(tag) for tag in root.tags)
    stream.write(MAGIC)
    stream.write(struct.pack("<I", version))
    stream.write(struct.pack("<I", 0))
    stream.write(struct.pack("<I", len(content)))
    stream.write(content)


def dump_chump(root: Tag, path: str | Path, *, version: int = FORMAT_VERSION) -> Path:
    """Write a CHUMP file to disk. Returns the path written."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        write_chump(root, stream, version=version)
    return target


def pack_chump(root: Tag, *, version: int = FORMAT_VERSION) -> bytes:
    """The whole CHUMP file for a container, in memory."""
    handle = io.BytesIO()
    write_chump(root, handle, version=version)
    return handle.getvalue()


def pack_tag_tree(tags: Sequence[Tag]) -> bytes:
    """The bytes of a container's contents: the tags packed one after another."""
    return b"".join(_pack_tag(tag) for tag in tags)


def _pack_tag(tag: Tag) -> bytes:
    if tag.is_container:
        body = pack_tag_tree(tag.tags)
        value_type = TagType.CONTAINER
    else:
        # not None: is_container is exactly "value_type is None"
        value_type = tag.value_type
        body = _pack_value(value_type, tag.value)

    try:
        name = tag.name.encode(NAME_ENCODING, "surrogateescape")
    except UnicodeEncodeError as exc:  # only a surrogate pair outside the escape range
        raise ChumpError(f"tag name {tag.name!r} cannot be encoded: {exc}") from exc
    if not name:
        raise ChumpError("a tag needs a name")
    if b"\x00" in name:
        raise ChumpError(f"tag name {tag.name!r} contains a NUL")
    if len(name) > _NAME_MAX:
        raise ChumpError(f"tag name too long: {tag.name!r}")
    # the length counts the name length byte, the name, its NUL, the type and
    # the value, but not the length itself
    size = len(name) + 3 + len(body)
    if size > 0xFFFFFFFF:
        raise ChumpError(f"tag {tag.name!r} is too big to store ({size} bytes)")
    return struct.pack("<I", size) + bytes([len(name) + 1]) + name + b"\x00" + bytes([value_type]) + body


def _pack_value(value_type: int, value: object) -> bytes:
    """The value bytes; anything struct refuses becomes a ChumpError."""
    try:
        return _encode_value(value_type, value)
    except ChumpError:
        raise  # already says what is wrong with the value
    except (struct.error, OverflowError, TypeError, ValueError) as exc:
        raise ChumpError(f"cannot store {value!r} as type {value_type:#02x}: {exc}") from exc


def _encode_value(value_type: int, value: object) -> bytes:
    if value_type == TagType.NULL:
        return b""
    if value_type in (TagType.INT32, TagType.INT64):
        fmt = "<i" if value_type == TagType.INT32 else "<q"
        values = value if isinstance(value, (list, tuple)) else [value]
        return b"".join(struct.pack(fmt, _as_int(item)) for item in values)
    if value_type == TagType.FLOAT32:
        values = value if isinstance(value, (list, tuple)) else [value]
        return b"".join(struct.pack("<f", float(item)) for item in values)
    if value_type == TagType.STRING:
        _one_value(value_type, value)
        return str(value).encode(TEXT_ENCODING, "surrogateescape") + b"\x00"
    if value_type == TagType.BINARY:
        _one_value(value_type, value)
        return bytes(value)
    if value_type == TagType.KUID:
        # the spec spells a kuid as 8 bytes and repeats that run until the tag
        # length is used up, same as the other number types
        values = value if isinstance(value, (list, tuple)) else [value]
        return b"".join(kuid_to_hex(str(item)) for item in values)
    if isinstance(value, RawValue):
        return value.data
    raise ChumpError(f"cannot write value type {value_type:#02x}")


def _one_value(value_type: int, value: object) -> None:
    """A string or binary tag holds one value, never a run of them."""
    if isinstance(value, (list, tuple)):
        raise ChumpError(
            f"tag value type {value_type:#02x} holds one value, not {len(value)}"
        )


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ChumpError(f"not an integer: {value!r}") from exc


# --------------------------------------------------------------------------
# rendering the text form
# --------------------------------------------------------------------------
def render_text(root: Tag, *, eol: str = "\r\n") -> str:
    """The indented text form of a container, the way the expander wrote one.

    Every container comes out set off from the tags beside it with a blank line,
    at the top of the file and as far down inside other containers as the file
    goes: a gap under its ``}`` where a tag stands there, and a gap above the line
    naming it where a tag stands there.  The expander left that line between the
    entries at the top of the file only; carrying it down every level is the same
    rule the editor's Reorder tags tweak asks for, which ``tweaks`` spells out in
    ``_the_blank_lines_to_open``.
    """
    lines = [""]
    _render_tags(root.tags, 0, lines)
    return eol.join(lines) + eol


def dump_text(root: Tag, path: str | Path, *, eol: str = "\r\n") -> Path:
    """Write a chump's text form to disk. Returns the path written.

    The original expander wrote UTF-8 with a BOM, so the samples and any file
    it produced start with one.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open(
        "w", encoding="utf-8-sig", errors="surrogateescape", newline=""
    ) as stream:
        stream.write(render_text(root, eol=eol))
    return target


def _render_tags(tags: Sequence[Tag], level: int, lines: list[str]) -> None:
    """One container's tags, written at this indent, each container set off.

    A blank line beside a container is what tells it apart from the tags written
    level with it: without one above, its name sits straight under the value over
    it, and without one below, its ``}`` sits straight above the tag under it.  One
    blank line does both jobs at once, so a container standing after another
    container asks for nothing of its own - the gap under the brace above it is
    already the gap above its name.  Nothing goes in below the opening brace or
    above the closing brace of the container these tags belong to, and nothing at
    the start or the end of them, where there is no tag on the other side to
    separate.
    """
    for before, tag in enumerate(tags):
        if not tag.is_container:
            lines.append(_render_name(tag.name, level) + _render_value(tag.value, tag.value_type))
            continue
        if before and not tags[before - 1].is_container:
            lines.append("")
        # a container's name stands alone, the brace opens the next line
        lines.append(_render_name(tag.name, level, padded=False))
        lines.append(" " * (2 * level) + "{")
        _render_tags(tag.tags, level + 1, lines)
        lines.append(" " * (2 * level) + "}")
        if before + 1 < len(tags):
            lines.append("")


def _render_name(name: str, level: int, *, padded: bool = True) -> str:
    indent = 2 * level
    if not padded:
        # a container's own name line is left alone, its '{' follows below
        return " " * indent + name
    # values start on VALUE_COLUMN, two spaces at the closest
    pad = max(VALUE_COLUMN - indent - len(name), 2)
    return " " * indent + name + " " * pad


def _render_value(value: object, value_type: int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        # a run of values of one type, comma separated, like a vector
        return ",".join(_render_one(item, value_type) for item in value)
    return _render_one(value, value_type)


def _render_one(value: object, value_type: int | None) -> str:
    if isinstance(value, Kuid):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode(TEXT_ENCODING, "surrogateescape")
    if isinstance(value, RawValue):
        return value.data.decode(TEXT_ENCODING, "surrogateescape")
    return str(value)


def _format_float(value: float) -> str:
    """Round to the digits a float32 holds, then drop trailing zeros (G style)."""
    if value != value:  # NaN
        return "NaN"
    if value in (float("inf"), float("-inf")):
        return "Infinity" if value > 0 else "-Infinity"
    text = f"{value:.{7 if abs(value) < 1e7 else 15}g}"
    if "e" in text:
        mantissa, _, exponent = text.partition("e")
        return f"{mantissa}e{int(exponent):+d}"
    return text


# --------------------------------------------------------------------------
# reading the text form
# --------------------------------------------------------------------------
def read_text_file(path: str | Path) -> str:
    """The text of a chump text file, without the BOM the format starts with.

    Line endings are kept as they are on disk so a value that spans lines
    survives a round trip unchanged, and surrogateescape means a value holding
    bytes that are not valid UTF-8 comes back as the same bytes.
    """
    with Path(path).open(
        "r", encoding="utf-8-sig", errors="surrogateescape", newline=""
    ) as stream:
        return stream.read()


def parse_text(text: str) -> Tag:
    """A container holding the tags written in the indented text form.

    The text form is the one the expander emits: one tag per line, its value
    after a gap of spaces, containers as a ``{`` / ``}`` pair at the parent's
    indent.  A value that starts with a quote can span lines, which is how the
    multi line license strings of a config.txt survive a round trip.
    """
    lines, eol = _split_lines(text)
    tags, index = _parse_lines(lines, 0, eol)
    if index != len(lines):
        raise ChumpError(f"line {index + 1}: '}}' with no container open")
    return Tag("<root>", tags)


def _split_lines(text: str) -> tuple[list[str], str]:
    """The lines of a text file and the line ending it uses.

    Splitting by hand rather than with splitlines keeps the line ending, which
    a quoted value spanning lines needs to come back unchanged.
    """
    eol = "\r\n" if "\r\n" in text else ("\r" if "\r" in text else "\n")
    return text.split(eol), eol


def load_text(path: str | Path) -> Tag:
    """Read a config.txt style file and return its tags."""
    return parse_text(read_text_file(path))


def _parse_lines(lines: list[str], index: int, eol: str) -> tuple[list[Tag], int]:
    """The tags in one container body, up to the ``}`` that closes it.

    The braces say where a container ends; the indentation is only for people,
    so a file indented with four spaces reads the same as one with two.
    """
    tags: list[Tag] = []
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue
        if stripped == "}":
            # leave the brace for the caller, which knows which container it
            # closes; at the top level nothing can close, and parse_text says so
            return tags, index
        if stripped == "{":
            raise ChumpError(f"line {index + 1}: '{{' without a tag name before it")

        name, rest = _split_name(stripped)
        opened_at = index
        index += 1
        if rest == "{":
            # a container, its opening brace on the name's own line, the way
            # most config.txt files write "kuid-table {"
            children, index = _parse_lines(lines, index, eol)
            if index >= len(lines):
                raise ChumpError(
                    f"line {opened_at + 1}: container '{name}' is never closed"
                )
            index += 1
            tags.append(Tag.container(name, children))
        elif rest:
            value, value_type, index = _parse_value_text(rest, lines, index, eol, name, opened_at)
            tags.append(Tag.value_tag(name, value, value_type))
        elif index < len(lines) and lines[index].strip() == "{":
            index += 1
            children, index = _parse_lines(lines, index, eol)
            if index >= len(lines):
                raise ChumpError(
                    f"line {opened_at + 1}: container '{name}' is never closed"
                )
            index += 1  # past the '}' the inner call stopped at
            tags.append(Tag.container(name, children))
        else:
            tags.append(Tag.value_tag(name, None, TagType.NULL))
    return tags, index


def _split_name(stripped: str) -> tuple[str, str]:
    """A tag name and the text after the spaces that separate it from a value."""
    parts = stripped.split(None, 1)
    name = parts[0]
    if name.endswith(":"):  # tolerate the config.txt spelling "name: value"
        name = name[:-1]
    rest = parts[1].strip() if len(parts) > 1 else ""
    return name, rest


def check_text(text: str) -> Tag:
    """Parse text in the indented form, first blaming a line for what breaks it.

    ``parse_text`` understands the layout of a chump text file and stops at a
    container whose ``{`` / ``}`` pair is missing one half.  What it cannot see
    is a quote or a ``<`` / ``>`` pair broken by hand, or one name written twice
    in the same container, because all of that looks like ordinary text.  So each
    line is looked at first:

    * a quoted value whose quote marks do not come in twos is refused.  The
      reader takes the value from the first quote to the last one, so a loose
      mark either moves the end of a value into the middle of the line - ``k
      "a" b"`` reads back as ``a" b`` - or swallows as much of what follows as
      it takes to find an even number: a ``kind "interior`` missing its closing
      quote runs on through the next tags and ends at the quote that was meant
      to open the tag after it;
    * a quote mark loose in a value that does not start with a quote is refused
      as well: that value reads as plain text now, and the next render writes
      it with a quote in front, which is a different value;
    * a quote mark in a tag name is refused, because a name is never quoted and
      has no partner for it either;
    * an angle bracket with no partner in a value that is not wrapped in quotes
      is refused, because it leaves a kuid half written - ``<kuid:1:2`` and
      ``kuid:1:2>`` both read back as text without the brackets that make a
      kuid a kuid;
    * a name has to be written once in one container, so a second ``username``
      written beside the first, or a second ``kuid-table``, is refused.  A
      container holds one tag per name, so two of one name say contradictory
      things and the reader has no way to choose between them.  A name written
      again further down is a different tag, since it belongs to another
      container, and names are compared exactly, which is how the binary form
      stores them.

    Quotes that do come in twos are taken at face value, however odd they look:
    a value holding ``say ""hi""`` is a string and stays one, and a bracket in
    a license string is prose.  A value whose run never reaches a closing quote
    at all is left to the parser, which says so with the line the value started
    on.  The walk follows the same lines as ``_parse_lines`` and reads each line
    before the parser turns it into tags, which is what lets it name the line at
    fault, and it keeps one set of names per open container, which is what lets
    it name the line the first copy of a repeated name was written on.
    """
    lines = text.splitlines()
    index, size = 0, len(lines)
    # the containers standing open, each with the names written in it and the
    # line each name was written on
    written: list[dict[str, int]] = [{}]
    while index < size:
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if line == "}":
            # which container this closes is the parser's business; here the
            # brace only closes the set of names collected for it.  A brace with
            # nothing open under it is a file whose layout is broken, and the
            # parser blames that by line, so nothing further is read here.
            if len(written) == 1:
                break
            written.pop()
            continue
        if line == "{":
            # a brace with no tag name before it, which the parser refuses too
            break
        name, rest = _split_name(line)
        if '"' in name:
            raise ChumpError(f"line {index}: tag name '{name}' has a quote mark in it")
        _check_repeated(name, index, written[-1])
        if not rest:
            if index < size and lines[index].strip() == "{":
                index += 1  # the brace this name opens, its body comes after
                written.append({})
            continue
        if rest == "{":
            written.append({})  # the brace written on the name's own line
            continue
        if rest.startswith('"'):
            if len(rest) > 1 and rest.endswith('"'):  # a one line string
                _check_pairs(name, index, rest.count('"'))
                continue
            # a value running over the lines that follow, to the line that ends
            # with a quote: its marks have to pair up over the whole run
            opened_on, marks, closed = index, rest.count('"'), False
            while index < size:
                marks += lines[index].count('"')
                if lines[index].endswith('"'):
                    closed = True
                    index += 1  # past the line that closed the value
                    break
                index += 1
            if closed:  # otherwise the parser has the better message
                _check_pairs(name, opened_on, marks)
            continue
        if '"' in rest:
            raise ChumpError(
                f"line {index}: value for tag '{name}' has a quote mark and does "
                "not start with one"
            )
        _check_brackets(name, index, rest)
    return parse_text(text)


def _check_repeated(name: str, index: int, names: dict[str, int]) -> None:
    """Complain about a name written twice in the container being read.

    ``names`` is the one set for that container: it holds every name written at
    that level and the line each one first appeared on.  A container holds one
    tag per name, so a second copy contradicts the first, and the line the
    first one stands on is what makes the complaint findable in the text.
    """
    first = names.get(name)
    if first is None:
        names[name] = index
        return
    raise ChumpError(
        f"line {index}: tag '{name}' is written twice at the same level, "
        f"the first one on line {first}"
    )


def _check_pairs(name: str, index: int, marks: int) -> None:
    """Complain about a quoted value whose quote marks do not come in twos."""
    if marks % 2:
        raise ChumpError(
            f"line {index}: quoted value for tag '{name}' has a quote mark with "
            "no partner"
        )


def _check_brackets(name: str, index: int, value: str) -> None:
    """Complain about a ``<`` or ``>`` in a value that is not wrapped in quotes."""
    depth = 0
    for char in value:
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
            if depth < 0:
                raise ChumpError(
                    f"line {index}: value for tag '{name}': '>' with no '<' before it"
                )
    if depth:
        raise ChumpError(f"line {index}: value for tag '{name}': '<' with no '>' after it")


def _parse_value_text(
    rest: str, lines: list[str], index: int, eol: str, name: str, opened_at: int
) -> tuple[object, int, int]:
    """A value from the text on its line, plus any continuation lines."""
    if rest.startswith('"'):
        if len(rest) > 1 and rest.endswith('"'):  # a one line string
            return rest[1:-1], TagType.STRING, index

        chunks = [rest[1:]]
        while index < len(lines):
            line = lines[index]
            if line.endswith('"'):
                chunks.append(line[:-1])
                index += 1
                break
            chunks.append(line)
            index += 1
        else:
            raise ChumpError(
                f"line {opened_at + 1}: quoted value for tag '{name}' is never closed"
            )
        return eol.join(chunks), TagType.STRING, index

    if rest.startswith("<"):
        return Kuid(rest), TagType.KUID, index

    parts = [part.strip() for part in rest.split(",")]
    if len(parts) > 1:
        # a run of numbers written comma separated, like a vector: stored as
        # one tag holding several values of the same type, no array header
        values, value_type = [], None
        for part in parts:
            if not part:
                raise ChumpError(f"the value {rest!r} has an empty element")
            value, part_type, index = _parse_one_text(part, lines, index, eol, name, opened_at)
            if value_type is None:
                value_type = part_type
            elif part_type != value_type:
                raise ChumpError(
                    f"the value {rest!r} mixes a type 0x{value_type:02x} "
                    f"with a type 0x{part_type:02x}"
                )
            values.append(value)
        return values, value_type, index

    return _parse_one_text(rest, lines, index, eol, name, opened_at)


def _parse_one_text(
    token: str, lines: list[str], index: int, eol: str, name: str, opened_at: int
) -> tuple[object, int, int]:
    if token.startswith('"'):
        value, value_type, index = _parse_value_text(token, lines, index, eol, name, opened_at)
        return value, value_type, index
    if token.startswith("<"):
        return Kuid(token), TagType.KUID, index
    if not token:
        return None, TagType.NULL, index

    try:
        return int(token), TagType.INT32, index
    except ValueError:
        pass
    try:
        return float(token), TagType.FLOAT32, index
    except ValueError:
        pass
    return token, TagType.STRING, index


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------
CHUMP_SUFFIXES = (".chump", ".cdp")
TEXT_SUFFIXES = (".txt",)


def convert_file(src: str | Path, dst: str | Path | None = None) -> Path:
    """Convert a file by extension: .chump/.cdp to .txt, .txt to .chump.

    The destination defaults to the source with the other extension, written
    next to it, which is what the original expander did.
    """
    source = Path(src)
    suffix = source.suffix.lower()
    if suffix in CHUMP_SUFFIXES:
        target = Path(dst) if dst else source.with_suffix(".txt")
        with source.open("rb") as stream:
            root = parse_chump(stream.read())
        dump_text(root, target)
    elif suffix in TEXT_SUFFIXES:
        target = Path(dst) if dst else source.with_suffix(DEFAULT_EXTENSION)
        dump_chump(parse_text(read_text_file(source)), target)
    else:
        raise ChumpError(
            f"{source.name}: not a chump file ('{'/'.join(CHUMP_SUFFIXES)}') "
            f"and not a text file ('{'/'.join(TEXT_SUFFIXES)}')"
        )
    return target
