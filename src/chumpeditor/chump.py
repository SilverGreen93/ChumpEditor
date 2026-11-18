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
follows it.

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

An int or float tag whose value is longer than 4 bytes holds a run of them
(``camera   -1.058,0.522,0.887`` in a config.txt), which is stored inline
rather than as one of the array types.  A type byte with bit 7 set is an
array, where each element carries its own length.

Unknown types are kept as ``RawValue``: their bytes are preserved so a file
that uses types this code does not know about still round-trips.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator, Sequence

MAGIC = b"ACS$"
#: the version word every chump file carries, 01 00 00 00 on disk
DEFAULT_VERSION = 1
FORMAT_VERSION = DEFAULT_VERSION  # kept as the VB.NET code named it
NAME_ENCODING = "latin-1"  # tag names are single bytes in the format itself
TEXT_ENCODING = "utf-8"  # string values, read and written with surrogateescape
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
    ARRAY_INT32 = 0x07
    ARRAY_FLOAT32 = 0x08
    ARRAY_STRING = 0x09
    ARRAY_BINARY = 0x0A
    ARRAY_INT64 = 0x0B
    KUID = 0x0D
    ARRAY_KUID = 0x0E

    # bit 7 of a type code marks an array of the type in the low 7 bits


#: type code -> the array type holding several of it
_ARRAY_TYPES = {
    TagType.INT32: TagType.ARRAY_INT32,
    TagType.FLOAT32: TagType.ARRAY_FLOAT32,
    TagType.STRING: TagType.ARRAY_STRING,
    TagType.BINARY: TagType.ARRAY_BINARY,
    TagType.INT64: TagType.ARRAY_INT64,
    TagType.KUID: TagType.ARRAY_KUID,
}

#: the column the value is written from, as in the original expander output
VALUE_COLUMN = 40

_NAME_MAX = 0xFF - 1  # the name length byte counts the terminating NUL


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
@dataclass(eq=False)
class Tag:
    """One tag of the tree: a container (no value_type) or a value tag.

    ``value_type`` doubles as the container/array flag: bit 7 marks an
    aggregate, the low 7 bits the type of the values it holds.
    """

    name: str
    tags: list["Tag"] = field(default_factory=list)
    value: object = None
    value_type: int | None = None

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
        return self.value_type is not None and bool(self.value_type & 0x80)

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
            and self.tags == other.tags
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
    if isinstance(value, str):
        return TagType.STRING
    if isinstance(value, (bytes, bytearray)):
        return TagType.BINARY
    if isinstance(value, Kuid):
        return TagType.KUID
    if isinstance(value, (list, tuple)):
        if not value:
            raise ChumpError("cannot guess the element type of an empty list")
        return _ARRAY_TYPES[_type_of(value[0])]
    raise ChumpError(f"unsupported value type: {type(value).__name__}")


def _values_equal(left: object, right: object) -> bool:
    if isinstance(left, Kuid) and isinstance(right, Kuid):
        return left == right
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _values_equal(a, b) for a, b in zip(left, right)
        )
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
    if not 0 <= cid < 2**32:
        raise ChumpError(f"kuid content id out of range: {cid}")
    if not 0 <= version < 128:
        raise ChumpError(f"invalid kuid version: {version}")

    # a negative uid has the sign bit of its 25 bits set, which leaves no room
    # for a version: its top bits are just sign extension
    word = (version << _UID_BITS) | (uid & ((1 << _UID_BITS) - 1)) if version else uid
    return struct.pack("<ii", word, cid)


def hex_to_kuid(data: bytes) -> Kuid:
    """The ``<kuid:uid:cid>`` literal for 8 kuid bytes."""
    if len(data) != 8:
        raise ChumpError(f"a kuid is 8 bytes, got {len(data)}")
    word, cid = struct.unpack("<ii", data)
    version = word >> _UID_BITS
    uid = word & ((1 << _UID_BITS) - 1)
    uid = uid - (1 << _UID_BITS) if uid > _UID_MAX else uid
    if version <= 0 or version > 127:  # top bits are only sign extension
        return Kuid(f"<kuid:{uid}:{cid}>")
    return Kuid(f"<kuid2:{uid}:{cid}:{version}>")


def parse_kuid(text: str) -> tuple[int, int, int]:
    """The uid, content id and version of a ``<kuid...>`` literal.

    A lone number is taken as an uid, like the original code did, and a
    negative uid never carries a version.
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
    if uid < 0:
        return uid, cid, 0
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
    return parse_tag_tree(body[4:4 + size])


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
        if size < 4 or offset + 4 + size > len(data):
            raise ChumpError(f"tag length {size} at {offset} runs past the end")
        yield _parse_tag(data[offset + 4:offset + 4 + size])
        offset += 4 + size


def _parse_tag(body: bytes) -> Tag:
    """One tag, from the bytes that follow its length."""
    (name_len,) = struct.unpack_from("<B", body, 0)
    if name_len < 2 or name_len + 2 > len(body):
        raise ChumpError(f"bad tag header at start of {body[:8]!r}")
    if body[name_len] != 0:
        raise ChumpError("tag name is not NUL terminated")
    name = body[1:name_len].decode(NAME_ENCODING)
    value_type = body[name_len + 1]
    value_bytes = body[name_len + 2:]

    if value_type == TagType.CONTAINER:
        return Tag(name, list(iter_tags(value_bytes)))

    if value_type & 0x80:  # array: the length is repeated for every element
        element_type = value_type & 0x7F
        values: list[object] = []
        offset = 0
        while offset < len(value_bytes):
            if len(value_bytes) - offset < 4:
                raise ChumpError(f"array element truncated in tag {name!r}")
            (element_len,) = struct.unpack_from("<I", value_bytes, offset)
            if offset + 4 + element_len > len(value_bytes):
                raise ChumpError(f"array element length in tag {name!r} is wrong")
            values.append(
                _parse_value(element_type, value_bytes[offset + 4:offset + 4 + element_len])
            )
            offset += 4 + element_len
        return Tag(name, (), values, value_type)

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
        return data.split(b"\x00", 1)[0].decode(TEXT_ENCODING, "surrogateescape")
    if value_type == TagType.BINARY:
        return data
    if value_type == TagType.KUID:
        if len(data) < 8:
            raise ChumpError("kuid tag truncated")
        return hex_to_kuid(data[:8])
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
        value_type = tag.value_type if tag.value_type is not None else _type_of(tag.value)
        if value_type & 0x80:  # array: every element carries its own length
            element_type = value_type & 0x7F
            values = tag.value if isinstance(tag.value, (list, tuple)) else [tag.value]
            body = b"".join(
                struct.pack("<I", len(_pack_value(element_type, value)))
                + _pack_value(element_type, value)
                for value in values
            )
        else:
            body = _pack_value(value_type, tag.value)

    name = tag.name.encode(NAME_ENCODING)
    if len(name) > _NAME_MAX:
        raise ChumpError(f"tag name too long: {tag.name!r}")
    # the length counts the name length byte, the name, its NUL, the type and
    # the value, but not the length itself
    size = len(name) + 3 + len(body)
    if size > 0xFFFFFFFF:
        raise ChumpError(f"tag {tag.name!r} is too big to store ({size} bytes)")
    return struct.pack("<I", size) + bytes([len(name) + 1]) + name + b"\x00" + bytes([value_type]) + body


def _pack_value(value_type: int, value: object) -> bytes:
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
        return str(value).encode(TEXT_ENCODING, "surrogateescape") + b"\x00"
    if value_type == TagType.BINARY:
        return bytes(value)
    if value_type == TagType.KUID:
        return kuid_to_hex(str(value))
    if isinstance(value, RawValue):
        return value.data
    raise ChumpError(f"cannot write value type {value_type:#02x}")


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
    """The indented text form of a container, as the original expander wrote it."""
    lines = [""]
    _render_tags(root.tags, 0, lines, eol)
    return eol.join(lines) + eol


def dump_text(root: Tag, path: str | Path, *, eol: str = "\r\n") -> Path:
    """Write a chump's text form to disk. Returns the path written.

    The original expander wrote UTF-8 with a BOM, so the samples and any file
    it produced start with one.
    """
    target = Path(path)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        stream.write(render_text(root, eol=eol))
    return target


def _render_tags(tags: Sequence[Tag], level: int, lines: list[str], eol: str) -> None:
    for tag in tags:
        if level == 0 and tag.is_container:
            # config.txt files from the Trainz tools leave a line between the
            # entries at the top of the file
            lines.append("")
        if tag.is_container:
            # a container's name stands alone, the brace opens the next line
            lines.append(_render_name(tag.name, level, padded=False))
            lines.append(" " * (2 * level) + "{")
            _render_tags(tag.tags, level + 1, lines, eol)
            lines.append(" " * (2 * level) + "}")
        else:
            lines.append(_render_name(tag.name, level) + _render_value(tag.value, tag.value_type))


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
        element_type = value_type & 0x7F if value_type and value_type & 0x80 else value_type
        return ",".join(_render_one(item, element_type) for item in value)
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
    survives a round trip unchanged.
    """
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        return stream.read()


def parse_text(text: str) -> Tag:
    """A container holding the tags written in the indented text form.

    The text form is the one the expander emits: one tag per line, its value
    after a gap of spaces, containers as a ``{`` / ``}`` pair at the parent's
    indent.  A value that starts with a quote can span lines, which is how the
    multi line license strings of a config.txt survive a round trip.
    """
    lines, eol = _split_lines(text)
    tags, index = _parse_lines(lines, 0, 0, eol)
    if index != len(lines):
        raise ChumpError(f"unbalanced '}}' on line {index + 1}")
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


def _parse_lines(lines: list[str], index: int, level: int, eol: str) -> tuple[list[Tag], int]:
    tags: list[Tag] = []
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if not stripped or stripped == "}":
            index += 1
            continue
        if stripped == "{":  # an empty or malformed container body
            raise ChumpError(f"line {index + 1}: '{{' without a tag name before it")
        if indent < level:
            return tags, index
        if indent > level:
            raise ChumpError(f"line {index + 1}: unexpected indent")

        name, rest = _split_name(stripped)
        index += 1
        if rest:
            value, value_type, index = _parse_value_text(rest, lines, index, eol)
            tags.append(Tag.value_tag(name, value, value_type))
            continue
        if index < len(lines) and lines[index].strip() == "{":
            children, index = _parse_lines(lines, index + 1, level + 2, eol)
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


def _parse_value_text(rest: str, lines: list[str], index: int, eol: str) -> tuple[object, int, int]:
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
            raise ChumpError("a quoted value is never closed")
        return eol.join(chunks), TagType.STRING, index

    if rest.startswith("<"):
        return Kuid(rest), TagType.KUID, index

    parts = [part.strip() for part in rest.split(",")]
    if len(parts) > 1:
        # a run of numbers written comma separated, like a vector: stored as
        # one tag holding several values of the same type, no array header
        values, value_type = [], None
        for part in parts:
            value, value_type, index = _parse_one_text(part, lines, index, eol)
            values.append(value)
        if value_type is None:
            raise ChumpError(f"cannot read the value {rest!r}")
        return values, value_type, index

    return _parse_one_text(rest, lines, index, eol)


def _parse_one_text(token: str, lines: list[str], index: int, eol: str) -> tuple[object, int, int]:
    if token.startswith('"'):
        value, value_type, index = _parse_value_text(token, lines, index, eol)
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
