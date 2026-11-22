"""Tests for the CHUMP codec: the binary form, the text form, and the round trips.

The byte expectations come from ``chump-format.md`` and are the same bytes the
original Visual Basic expander wrote; the tests keep the format stable.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from chumpeditor.chump import (
    MAGIC,
    NAME_ENCODING,
    VALUE_COLUMN,
    ChumpError,
    Kuid,
    RawValue,
    Tag,
    TagType,
    check_text,
    convert_file,
    dump_chump,
    dump_text,
    hex_to_kuid,
    iter_tags,
    kuid_to_hex,
    load_chump,
    load_text,
    pack_chump,
    pack_tag_tree,
    parse_chump,
    parse_kuid,
    parse_tag_tree,
    parse_text,
    read_text_file,
    render_text,
)

SAMPLES = Path(__file__).parent / "test_files"

CONTAINER = TagType.CONTAINER
INT32 = TagType.INT32
FLOAT32 = TagType.FLOAT32
STRING = TagType.STRING
BINARY = TagType.BINARY
NULL = TagType.NULL
INT64 = TagType.INT64
KUID = TagType.KUID


def tag_bytes(name: str, value_type: int, value: bytes = b"", *, encoding: str = "utf-8") -> bytes:
    """One tag as the format frames it: length, name, NUL, type byte, value.

    The length counts everything after itself, so a tag named ``k`` holding one
    int32 is eight bytes of body and twelve bytes all told.
    """
    raw_name = name.encode(encoding)
    body = bytes([len(raw_name) + 1]) + raw_name + b"\x00" + bytes([value_type]) + value
    return struct.pack("<I", len(body)) + body


def file_of(content: bytes) -> bytes:
    """A CHUMP file header around some tags."""
    return MAGIC + struct.pack("<III", 1, 0, len(content)) + content


def chump_of(*tags: Tag) -> bytes:
    return file_of(b"".join(pack_tag_tree((tag,)) for tag in tags))


def read_first_tag(data: bytes) -> Tag:
    return next(iter_tags(data))


def names(root: Tag) -> list[str]:
    return [tag.name for tag in root.tags]


# --------------------------------------------------------------------------
# reading the binary form: the file header
# --------------------------------------------------------------------------
def test_the_sample_files_all_read():
    for stem in ("config1", "config2", "config3"):
        root = load_chump(SAMPLES / f"{stem}.chump")
        assert root.is_container
        assert root.tags


def test_config1_reads_the_tags_the_expander_shows():
    root = load_chump(SAMPLES / "config1.chump")
    assert names(root) == [
        "trackside", "category-class", "username", "author", "contact-email",
        "contact-website", "license", "kind", "category-region", "trainz-build",
        "category-era", "mesh-table", "kuid", "kuid-table",
    ]
    assert root.tags[0].value == 2.5
    assert root.tags[0].value_type == FLOAT32


def test_a_container_holds_containers_and_values():
    mesh_table = load_chump(SAMPLES / "config1.chump").tags[11]
    assert mesh_table.name == "mesh-table"
    assert mesh_table.is_container
    assert all(entry.is_container for entry in mesh_table.tags)
    assert mesh_table.tags[0].tags[0].name == "auto-create"
    assert mesh_table.tags[0].tags[0].value == 1
    assert mesh_table.tags[0].tags[1].name == "mesh"
    assert mesh_table.tags[0].tags[1].value_type == STRING


def test_the_header_is_the_magic_and_three_numbers():
    data = chump_of(Tag("k", (), 42, INT32))
    assert data[:4] == b"ACS$"
    assert struct.unpack_from("<III", data, 4) == (1, 0, 12)
    assert len(data) == 28


def test_the_content_length_counts_the_tags_not_the_header():
    one = pack_tag_tree((Tag("k", (), 42, INT32),))
    assert file_of(one)[12:16] == struct.pack("<I", len(one))


def test_the_reserved_field_is_written_as_zero_and_ignored():
    data = MAGIC + struct.pack("<III", 1, 0x7F, 12) + pack_tag_tree((Tag("k", (), 42, INT32),))
    assert parse_chump(data).tags[0].value == 42


def test_the_file_starts_with_the_tags_at_the_offset_the_header_promises():
    data = chump_of(Tag("k", (), 42, INT32))
    assert struct.unpack_from("<I", data, 16)[0] == 8


def test_an_empty_file_is_a_header_and_nothing_else():
    root = parse_chump(file_of(b""))
    assert root.tags == []
    assert pack_chump(root) == file_of(b"")
    assert len(file_of(b"")) == 16


def test_a_short_file_is_rejected():
    with pytest.raises(ChumpError, match="file too short to be a chump file"):
        parse_chump(b"ACS$")


def test_a_file_that_is_not_a_chump_is_rejected():
    with pytest.raises(ChumpError, match=r"not a chump file \(starts with b'TXT!'\)"):
        parse_chump(b"TXT!" + b"\x00" * 20)


def test_a_content_length_that_runs_long_is_reported():
    data = MAGIC + struct.pack("<III", 1, 0, 99) + pack_tag_tree((Tag("k", (), 42, INT32),))
    with pytest.raises(ChumpError, match="content length 99 does not match the 12 bytes"):
        parse_chump(data)


def test_a_content_length_that_runs_short_is_reported():
    data = MAGIC + struct.pack("<III", 1, 0, 4) + pack_tag_tree((Tag("k", (), 42, INT32),))
    with pytest.raises(ChumpError, match="content length 4 does not match the 12 bytes"):
        parse_chump(data)


# --------------------------------------------------------------------------
# reading the binary form: tag framing
# --------------------------------------------------------------------------
def test_a_truncated_tag_header_is_reported():
    # the stream ends with fewer bytes than a tag needs to say what it is
    with pytest.raises(ChumpError, match="tag header truncated at 0"):
        list(iter_tags(b"\x04\x00"))


def test_a_tag_length_that_cannot_hold_a_tag_is_reported():
    with pytest.raises(ChumpError, match="tag length 1 at 0 is too small for a tag"):
        list(iter_tags(struct.pack("<I", 1) + b"\x01"))


def test_a_tag_running_past_the_end_of_the_stream_is_reported():
    with pytest.raises(ChumpError, match="tag length 9999 at 0 runs past the end"):
        list(iter_tags(struct.pack("<I", 9999) + b"\x02k\x00\x00"))


def test_a_tag_name_has_to_be_at_least_one_character():
    with pytest.raises(ChumpError, match="tag name length 1 does not fit in 4 bytes"):
        list(iter_tags(struct.pack("<I", 4) + b"\x01k\x00\x00"))


def test_a_name_length_that_does_not_fit_the_tag_is_reported():
    with pytest.raises(ChumpError, match="tag name length 20 does not fit in 4 bytes"):
        list(iter_tags(struct.pack("<I", 4) + b"\x14k\x00\x00"))


def test_a_name_without_its_nul_is_reported():
    with pytest.raises(ChumpError, match="tag name is not NUL terminated"):
        list(iter_tags(struct.pack("<I", 4) + b"\x02k\x01\x00"))


def test_a_broken_tag_after_a_good_one_is_reported():
    body = tag_bytes("kind", STRING, b"scenery\x00") + b"\xff\xff\xff"
    with pytest.raises(ChumpError, match="tag header truncated at 19"):
        list(iter_tags(body))


def test_a_name_of_the_longest_length_the_format_allows_round_trips():
    # the length byte counts the NUL, and 0xFF is the largest value: 254 bytes
    longest = "x" * 254
    assert parse_chump(chump_of(Tag(longest, (), 1, INT32))).tags[0].name == longest


# --------------------------------------------------------------------------
# reading the binary form: values
# --------------------------------------------------------------------------
def test_int32_value():
    assert read_first_tag(tag_bytes("k", INT32, b"\x2a\x00\x00\x00")) == Tag("k", (), 42, INT32)


def test_int32_negative():
    assert read_first_tag(tag_bytes("k", INT32, struct.pack("<i", -7))).value == -7


def test_float32_value():
    tag = read_first_tag(tag_bytes("k", FLOAT32, struct.pack("<f", 1.5)))
    assert (tag.value, tag.value_type) == (1.5, FLOAT32)


def test_string_value():
    assert read_first_tag(tag_bytes("kind", STRING, b"scenery\x00")).value == "scenery"


def test_binary_value_is_the_bytes_it_holds():
    assert read_first_tag(tag_bytes("mesh", BINARY, b"\x01\x02\x00\xff")).value == b"\x01\x02\x00\xff"


def test_null_value():
    tag = read_first_tag(tag_bytes("era", NULL))
    assert (tag.value, tag.value_type) == (None, NULL)
    assert not tag.is_container


def test_int64_value():
    tag = read_first_tag(tag_bytes("k", INT64, struct.pack("<q", 2**40)))
    assert (tag.value, tag.value_type) == (2**40, INT64)


def test_an_empty_string_round_trips_to_its_terminator():
    assert read_first_tag(tag_bytes("s", STRING, b"\x00")).value == ""


def test_a_nul_inside_a_string_is_kept():
    assert read_first_tag(tag_bytes("s", STRING, b"a\x00b\x00")).value == "a\x00b"


def test_a_run_of_int32_values_is_a_list():
    tag = read_first_tag(tag_bytes("k", INT32, b"".join(
        struct.pack("<i", n) for n in (1, 2, 3))))
    assert tag.value == [1, 2, 3]
    assert tag.is_array


def test_a_run_of_float32_values_is_a_list():
    tag = read_first_tag(tag_bytes("k", FLOAT32, b"".join(
        struct.pack("<f", n) for n in (1.5, 2.5))))
    assert tag.value == [1.5, 2.5]


def test_a_run_of_int64_values_is_a_list():
    tag = read_first_tag(tag_bytes("k", INT64, b"".join(
        struct.pack("<q", n) for n in (1, 2))))
    assert tag.value == [1, 2]


def test_a_truncated_int32_is_reported():
    with pytest.raises(ChumpError, match="int32 tag truncated"):
        read_first_tag(tag_bytes("k", INT32, b"\x01\x02\x03"))


def test_a_truncated_float32_is_reported():
    with pytest.raises(ChumpError, match="float32 tag truncated"):
        read_first_tag(tag_bytes("k", FLOAT32, b"\x01\x02\x03"))


def test_a_truncated_int64_is_reported():
    with pytest.raises(ChumpError, match="int64 tag truncated"):
        read_first_tag(tag_bytes("k", INT64, b"\x01\x02\x03\x04"))


def test_a_value_type_the_format_does_not_define_keeps_its_bytes():
    tag = read_first_tag(tag_bytes("k", 0x08, b"ab"))
    assert tag.value == RawValue(0x08, b"ab")
    assert tag.value_type == 0x08


# --------------------------------------------------------------------------
# reading the binary form: containers
# --------------------------------------------------------------------------
def test_nested_containers():
    body = tag_bytes("mesh-table", CONTAINER, tag_bytes(
        "default", CONTAINER,
        tag_bytes("auto-create", INT32, struct.pack("<i", 1)),
    ))
    root = parse_tag_tree(body)
    assert root.tags[0].name == "mesh-table"
    assert root.tags[0].tags[0].name == "default"
    assert root.tags[0].tags[0].tags[0].value == 1


def test_an_empty_container():
    tag = read_first_tag(tag_bytes("era", CONTAINER))
    assert tag.tags == []
    assert tag.is_container


def test_a_tag_name_may_hold_a_colon():
    assert read_first_tag(tag_bytes("a:b", INT32, struct.pack("<i", 1))).name == "a:b"


def test_a_tag_name_may_hold_spaces():
    assert read_first_tag(tag_bytes("contact email", STRING, b"a\x00")).name == "contact email"


def test_names_are_read_as_utf8():
    raw = tag_bytes("café", STRING, b"x\x00", encoding="utf-8")
    assert parse_tag_tree(raw).tags[0].name == "café"


def test_a_name_that_is_not_utf8_survives_a_round_trip():
    raw = tag_bytes("bad", STRING, b"x\x00", encoding="latin-1")
    name = parse_tag_tree(raw).tags[0].name
    assert name.encode(NAME_ENCODING, "surrogateescape") == b"bad"
    assert pack_tag_tree([parse_tag_tree(raw).tags[0]]) == raw


# --------------------------------------------------------------------------
# writing the binary form
# --------------------------------------------------------------------------
def test_a_tag_is_a_length_a_name_length_a_name_a_nul_a_type_and_a_value():
    assert tag_bytes("k", INT32, struct.pack("<i", 42)) == (
        b"\x08\x00\x00\x00\x02k\x00\x01\x2a\x00\x00\x00"
    )


def test_writing_a_single_top_level_value_tag():
    assert chump_of(Tag("k", (), 42, INT32)) == (
        b"ACS$\x01\x00\x00\x00\x00\x00\x00\x00\x0c\x00\x00\x00"
        b"\x08\x00\x00\x00\x02k\x00\x01\x2a\x00\x00\x00"
    )


def test_tag_length_counts_the_nul_of_the_name():
    # one byte name, its NUL, the length byte and the type byte make four
    assert pack_tag_tree((Tag("k", (), None, NULL),)) == b"\x04\x00\x00\x00\x02k\x00\x05"
    assert pack_tag_tree((Tag("k", (), None, NULL),))[0:4] == struct.pack("<I", 4)


def test_a_tag_with_an_empty_name_is_refused():
    with pytest.raises(ChumpError, match="a tag needs a name"):
        chump_of(Tag("", (), 1, INT32))


def test_a_tag_name_holding_a_nul_is_refused():
    with pytest.raises(ChumpError, match="contains a NUL"):
        chump_of(Tag("a\x00b", (), 1, INT32))


def test_a_tag_name_longer_than_one_byte_can_hold_is_refused():
    with pytest.raises(ChumpError, match="tag name too long"):
        chump_of(Tag("x" * 255, (), 1, INT32))


def test_a_value_that_does_not_fit_the_type_is_refused():
    with pytest.raises(ChumpError, match="cannot store 2147483648 as type 0x1"):
        chump_of(Tag("big", (), 2**31, INT32))


def test_a_number_beyond_int32_needs_int64():
    assert Tag("big", (), 2**40).value_type == INT64
    assert parse_tag_tree(pack_tag_tree((Tag("big", (), 2**40),))).tags[0].value == 2**40


def test_a_string_is_written_with_a_trailing_nul():
    assert pack_tag_tree((Tag("kind", (), "scenery", STRING),)) == tag_bytes(
        "kind", STRING, b"scenery\x00"
    )


def test_a_string_tag_holds_one_value():
    with pytest.raises(ChumpError, match="holds one value, not 2"):
        pack_tag_tree((Tag("s", (), ["a", "b"], STRING),))


def test_a_binary_tag_holds_one_value():
    with pytest.raises(ChumpError, match="holds one value, not 2"):
        pack_tag_tree((Tag("b", (), [b"a", b"b"], BINARY),))


def test_a_value_tag_forgets_nothing_on_the_way_out():
    root = Tag.container("<root>", [
        Tag("kind", (), "scenery", STRING),
        Tag.container("mesh-table", [
            Tag.container("default", [
                Tag("auto-create", (), 1, INT32),
                Tag("mesh", (), b"tables\\mesh.bin\x00", BINARY),
            ]),
        ]),
    ])
    again = parse_chump(pack_chump(root))
    assert again == root
    assert again.tags[1].tags[0].tags[1].value == b"tables\\mesh.bin\x00"


def test_the_binary_form_survives_being_written_and_read_again():
    for stem in ("config1", "config2", "config3"):
        data = (SAMPLES / f"{stem}.chump").read_bytes()
        assert pack_chump(parse_chump(data)) == data


# --------------------------------------------------------------------------
# equality and value types
# --------------------------------------------------------------------------
def test_tag_eq_ignores_float32_noise():
    # only single precision is stored, so the shortest text that reads back to
    # the same four bytes is the same value
    assert Tag("k", (), 1.3, FLOAT32) == Tag("k", (), 1.2999999523162842, FLOAT32)


def test_two_different_numbers_are_not_equal():
    assert Tag("k", (), 1.3, FLOAT32) != Tag("k", (), 1.4, FLOAT32)
    assert Tag("k", (), 1, INT32) != Tag("k", (), 2, INT32)


def test_a_float_and_an_int_are_different_types():
    assert Tag("k", (), 2, INT32) != Tag("k", (), 2.0, FLOAT32)


def test_null_is_not_the_empty_string():
    assert Tag("era", (), None, NULL) != Tag("era", (), "", STRING)


def test_a_kuid_is_not_a_string():
    assert Tag("s", (), "<kuid:1:2>", STRING) != Tag("k", (), Kuid("<kuid:1:2>"), KUID)


def test_tag_eq_ignores_the_container_being_a_tuple_or_a_list():
    assert Tag("a", ()) == Tag("a", [])
    assert Tag("a", (Tag("b", (), 1, INT32),)) == Tag("a", [Tag("b", (), 1, INT32)])


def test_an_empty_container_is_not_a_null_tag():
    assert Tag("era", ()).is_container
    assert not Tag("era", (), None, NULL).is_container
    assert Tag("era", ()) != Tag("era", (), None, NULL)


def test_repr_shows_the_type_as_a_number():
    assert repr(Tag("kind", (), "scenery")) == (
        "Tag(name='kind', tags=(), value='scenery', value_type=3)"
    )


def test_the_value_type_is_guessed_from_a_python_value():
    assert Tag("k", (), 1).value_type == INT32
    assert Tag("k", (), 1.5).value_type == FLOAT32
    assert Tag("k", (), "x").value_type == STRING
    assert Tag("k", (), b"x").value_type == BINARY
    assert Tag("k", (), Kuid("<kuid:1:2>")).value_type == KUID
    assert Tag("k", (), [1, 2]).value_type == INT32
    assert Tag("k", (), None).value_type is None  # an empty container


def test_a_string_value_is_not_reparsed():
    assert Tag("k", (), "1").value_type == STRING


def test_a_list_of_values_gets_the_type_of_its_first_element():
    assert Tag("k", (), [1, 2, 3]).value_type == INT32
    assert Tag("k", (), [1.5, 2.5]).value_type == FLOAT32


def test_an_empty_list_has_no_type_to_guess():
    with pytest.raises(ChumpError, match="cannot guess the element type of an empty list"):
        Tag("k", (), [])


def test_a_value_of_an_unknown_python_type_is_refused():
    with pytest.raises(ChumpError, match="unsupported value type: object"):
        Tag("k", (), object())


# --------------------------------------------------------------------------
# kuid values
# --------------------------------------------------------------------------
def test_kuid_is_a_string_that_knows_its_numbers():
    kuid = Kuid("<kuid2:474195:10010:1>")
    assert kuid == "<kuid2:474195:10010:1>"
    assert (kuid.uid, kuid.cid, kuid.version) == (474195, 10010, 1)
    assert kuid.kind == "kuid2"


def test_kuid_parsing_reads_the_three_numbers():
    assert parse_kuid("<kuid:1:2>") == (1, 2, 0)
    assert parse_kuid("<kuid2:1:2:8>") == (1, 2, 8)
    assert parse_kuid("<kuid:-1:2>") == (-1, 2, 0)
    assert parse_kuid("<kuid:1>") == (1, -1, 0)
    assert parse_kuid("5") == (5, -1, 0)


def test_kuid_parsing_of_an_empty_literal_has_nothing_to_give():
    assert parse_kuid("") == (-1, -1, 0)
    assert parse_kuid("<kuid>") == (-1, -1, 0)


def test_kuid_parsing_refuses_a_number_that_is_not_a_number():
    for text in ("<kuid:a:1>", "<kuid2:1:2:x>", "<kuid2:1:2:3:4>"):
        with pytest.raises(ChumpError, match="invalid kuid"):
            parse_kuid(text)


def test_the_numbers_are_checked_when_the_bytes_are_written():
    with pytest.raises(ChumpError, match="invalid kuid version: -1"):
        kuid_to_hex("<kuid2:1:2:-1>")
    with pytest.raises(ChumpError, match="invalid kuid version: 128"):
        kuid_to_hex("<kuid2:1:2:128>")
    with pytest.raises(ChumpError, match="kuid uid out of range"):
        kuid_to_hex("<kuid:16777216:1>")
    with pytest.raises(ChumpError, match="kuid content id out of range"):
        kuid_to_hex("<kuid:1:2147483648>")


def test_a_kuid_becomes_eight_bytes():
    # the examples of kuid-format.md, spelled with the type byte 0x0d of chump
    assert kuid_to_hex("<kuid:474195:100073>").hex() == "533c0700e9860100"
    assert kuid_to_hex("<kuid2:474195:100073:8>").hex() == "533c0710e9860100"
    assert kuid_to_hex("<kuid:-1:-1>").hex() == "ff" * 8


def test_eight_bytes_become_a_kuid_back():
    assert hex_to_kuid(bytes.fromhex("533c0700e9860100")) == "<kuid:474195:100073>"
    assert hex_to_kuid(bytes.fromhex("533c0710e9860100")) == "<kuid2:474195:100073:8>"
    assert hex_to_kuid(bytes.fromhex("533c0700e9860100")).cid == 100073
    assert hex_to_kuid(bytes.fromhex("533c0710e9860100")).version == 8


def test_a_kuid_written_without_a_version_reads_back_without_one():
    assert hex_to_kuid(kuid_to_hex("<kuid:474195:10010>")) == "<kuid:474195:10010>"


def test_a_kuid_with_a_version_reads_back_with_one():
    for version in (1, 8, 64, 127):
        text = f"<kuid2:474195:10010:{version}>"
        assert hex_to_kuid(kuid_to_hex(text)) == text


def test_the_kuid_the_tools_use_for_no_asset_is_all_zeroes_or_all_ones():
    assert hex_to_kuid(b"\x00" * 8) == "<kuid:0:0>"
    # -1:-1 with the version bits set as well, which is how the docs spell "unset"
    assert hex_to_kuid(b"\xff" * 8) == "<kuid:-1:-1>"


def test_the_uid_and_content_id_ranges_round_trip():
    ends = [
        "<kuid:16777215:2147483647>",
        "<kuid:-16777216:-2147483648>",
        "<kuid2:16777215:2147483647:127>",
        "<kuid:0:0>",
    ]
    assert [hex_to_kuid(kuid_to_hex(text)) for text in ends] == ends


def test_hex_to_kuid_needs_eight_bytes():
    with pytest.raises(ChumpError, match="a kuid is 8 bytes, got 4"):
        hex_to_kuid(b"\x01\x02\x03\x04")


def test_a_kuid_tag_holds_eight_bytes():
    assert pack_tag_tree((Tag("k", (), "<kuid:1:2>", KUID),)) == tag_bytes(
        "k", KUID, kuid_to_hex("<kuid:1:2>")
    )


def test_a_kuid_tag_holds_a_kuid_even_when_a_string_is_handed_over():
    assert isinstance(Tag("k", (), "<kuid:1:2>", KUID).value, Kuid)


def test_a_run_of_kuids_is_a_list_of_kuids():
    tag = Tag("k", (), ["<kuid:1:2>", "<kuid:3:4>"], KUID)
    assert all(isinstance(item, Kuid) for item in tag.value)
    again = parse_tag_tree(pack_tag_tree((tag,))).tags[0]
    assert again == tag
    assert again.value == ["<kuid:1:2>", "<kuid:3:4>"]


def test_a_kuid_body_that_is_not_a_whole_number_of_kuids_is_reported():
    with pytest.raises(ChumpError, match="kuid tag truncated"):
        read_first_tag(tag_bytes("k", KUID, b"\x01"))
    with pytest.raises(ChumpError, match="kuid tag truncated"):
        read_first_tag(tag_bytes("k", KUID, b""))


# --------------------------------------------------------------------------
# rendering the text form
# --------------------------------------------------------------------------
def test_values_start_on_the_value_column():
    assert VALUE_COLUMN == 40
    assert render_text(Tag("<root>", [Tag("k", (), 42, INT32)])) == (
        "\r\nk" + " " * 39 + "42\r\n"
    )


def test_render_a_container():
    text = render_text(Tag("<root>", [Tag.container("t", [Tag("k", (), 1, INT32)])]))
    assert text == "\r\nt\r\n{\r\n  k" + " " * 37 + "1\r\n}\r\n"


def test_a_container_is_indented_two_spaces_per_level():
    text = render_text(Tag("<root>", [
        Tag.container("a", [Tag.container("b", [Tag("k", (), 1, INT32)])]),
    ]))
    assert "    k" + " " * 35 + "1" in text


def test_a_container_is_set_off_from_the_tags_beside_it():
    text = render_text(Tag("<root>", [
        Tag("kind", (), "scenery", STRING),
        Tag.container("t", []),
        Tag("k", (), 1, INT32),
    ]))
    assert text.split("\r\n") == [
        "",
        "kind" + " " * 36 + '"scenery"',
        "",
        "t",
        "{",
        "}",
        "",
        "k" + " " * 39 + "1",
        "",
    ]


def test_one_blank_line_serves_two_containers_written_one_after_the_other():
    text = render_text(Tag("<root>", [
        Tag("kind", (), "scenery", STRING),
        Tag.container("a", [Tag("k", (), 1, INT32)]),
        Tag.container("b", []),
        Tag("era", (), 3, INT32),
    ]))
    assert text.split("\r\n") == [
        "",
        "kind" + " " * 36 + '"scenery"',
        "",
        "a",
        "{",
        "  k" + " " * 37 + "1",
        "}",
        "",
        "b",
        "{",
        "}",
        "",
        "era" + " " * 37 + "3",
        "",
    ]


def test_the_containers_inside_a_container_are_set_off_as_well():
    text = render_text(Tag("<root>", [Tag.container("outer", [
        Tag("kind", (), "x", STRING),
        Tag.container("inner", [Tag("k", (), 1, INT32)]),
        Tag("era", (), 3, INT32),
    ])]))
    assert text.split("\r\n") == [
        "",
        "outer",
        "{",
        "  kind" + " " * 34 + '"x"',
        "",
        "  inner",
        "  {",
        "    k" + " " * 35 + "1",
        "  }",
        "",
        "  era" + " " * 35 + "3",
        "}",
        "",
    ]


def test_no_blank_line_goes_next_to_a_brace_or_at_the_ends_of_the_file():
    text = render_text(Tag("<root>", [Tag.container("a", [Tag.container("b", [])])]))
    assert text.split("\r\n") == ["", "a", "{", "  b", "  {", "  }", "}", ""]


def test_render_an_empty_string():
    assert render_text(Tag("<root>", [Tag("s", (), "", STRING)])) == (
        "\r\ns" + " " * 39 + '""\r\n'
    )


def test_render_a_null_tag():
    assert render_text(Tag("<root>", [Tag("era", (), None, NULL)])) == (
        "\r\nera" + " " * 37 + "\r\n"
    )


def test_render_an_empty_container():
    assert render_text(Tag("<root>", [Tag("era", [])])) == "\r\nera\r\n{\r\n}\r\n"


def test_render_a_binary_value_as_the_bytes_it_holds():
    assert render_text(Tag("<root>", [Tag("b", (), b"ab", BINARY)])) == (
        "\r\nb" + " " * 39 + "ab\r\n"
    )


def test_render_a_run_of_values_comma_separated():
    assert render_text(Tag("<root>", [Tag("k", (), [1, 2, 3], INT32)])) == (
        "\r\nk" + " " * 39 + "1,2,3\r\n"
    )


def test_a_value_column_is_two_spaces_from_a_long_name():
    # a name that reaches the column gets its value two spaces later
    assert render_text(Tag("<root>", [Tag("x" * 39, (), 1, INT32)])) == (
        "\r\n" + "x" * 39 + "  1\r\n"
    )


def test_render_uses_crlf_by_default():
    assert render_text(Tag("<root>", [])) == "\r\n"
    assert render_text(Tag("<root>", []), eol="\n") == "\n"


def test_render_a_string_value_keeps_it_quoted():
    assert render_text(Tag("<root>", [Tag("kind", (), "scenery", STRING)])) == (
        "\r\nkind" + " " * 36 + '"scenery"\r\n'
    )


def test_a_kuid_is_written_bare():
    assert render_text(Tag("<root>", [Tag("k", (), Kuid("<kuid:1:2>"), KUID)])) == (
        "\r\nk" + " " * 39 + "<kuid:1:2>\r\n"
    )


def test_a_float_is_written_as_shortly_as_a_float32_allows():
    # 1.3 is not exact in a float32; the text form says what the bytes mean
    assert render_text(Tag("<root>", [Tag("k", (), 1.3, FLOAT32)])) == (
        "\r\nk" + " " * 39 + "1.3\r\n"
    )


def test_a_value_of_a_type_the_reader_does_not_know_is_written_back_as_it_came():
    # the text form cannot say what the bytes meant, so they go out verbatim,
    # the way the original expander wrote them; the tag keeps its type byte
    text = render_text(Tag("<root>", [Tag("k", (), RawValue(0x08, b"ab"), 0x08)]))
    assert text.endswith("k" + " " * 39 + "ab\r\n")
    again = parse_chump(pack_chump(Tag("<root>", [Tag("k", (), RawValue(0x08, b"ab"), 0x08)])))
    assert again.tags[0].value_type == 0x08
    assert again.tags[0].value.data == b"ab"


# --------------------------------------------------------------------------
# reading the text form
# --------------------------------------------------------------------------
def test_the_text_form_of_a_value_tag():
    assert parse_text("k" + " " * 39 + "42") == Tag("<root>", [Tag("k", (), 42, INT32)])
    assert parse_text("k -7").tags[0].value == -7
    assert parse_text("k 4294967295").tags[0].value_type == INT32
    assert (parse_text("k 1.5").tags[0].value, parse_text("k 1.5").tags[0].value_type) == (
        1.5, FLOAT32,
    )


def test_a_quoted_value_is_a_string_even_when_it_looks_like_a_number():
    assert parse_text('k "1"').tags[0] == Tag("k", (), "1", STRING)


def test_a_lone_name_is_a_null_tag():
    assert parse_text("era") == Tag("<root>", [Tag("era", (), None, NULL)])


def test_a_run_of_values_reads_as_one_tag():
    assert parse_text("k 1,2,3").tags[0].value == [1, 2, 3]
    assert parse_text("k 1,2,3").tags[0].value_type == INT32
    assert parse_text("k -1.058,0.522").tags[0].value == [-1.058, 0.522]
    assert parse_text("k -1.058,0.522").tags[0].value_type == FLOAT32


def test_a_run_of_values_that_mixes_types_is_refused():
    with pytest.raises(ChumpError, match="mixes a type 0x01 with a type 0x02"):
        parse_text("k 1,2.5")


def test_a_run_of_values_with_a_missing_element_is_refused():
    with pytest.raises(ChumpError, match="has an empty element"):
        parse_text("k 1,2,")


def test_a_bare_kuid_literal_is_a_kuid_and_a_quoted_one_stays_a_string():
    tag = parse_text("k <kuid:1:2>").tags[0]
    assert (tag.value_type, tag.value) == (KUID, "<kuid:1:2>")
    assert isinstance(tag.value, Kuid)
    assert parse_text('k "<kuid:1:2>"').tags[0].value_type == STRING


def test_the_braces_of_a_container_are_the_only_structure():
    four = parse_text("t\n{\n    k 1\n}\n")
    two = parse_text("t\n{\n  k 1\n}\n")
    same_line = parse_text("t {\n  k 1\n}\n")
    assert four == two == same_line
    assert four.tags[0].tags[0].value == 1


def test_blank_lines_are_ignored():
    assert parse_text("\n\nt\n{\n\n}\n\n").tags[0] == Tag("t", [])


def test_a_container_that_is_never_closed_is_reported():
    with pytest.raises(ChumpError, match=r"line 1: container 'a' is never closed"):
        parse_text("a\n{\nb\n{\n}\n")


def test_a_brace_with_nothing_before_it_is_reported():
    with pytest.raises(ChumpError, match=r"line 2: '\{' without a tag name before it"):
        parse_text("t 1\n{\n}\n")


def test_a_closing_brace_at_the_top_level_is_reported():
    with pytest.raises(ChumpError, match=r"line 1: '\}' with no container open"):
        parse_text("}")


def test_a_quoted_value_that_is_never_closed_is_reported():
    with pytest.raises(ChumpError, match=r"line 1: quoted value for tag 'k' is never closed"):
        parse_text('k "abc')


def test_a_quoted_value_may_span_lines_and_keeps_its_line_endings():
    assert parse_text('k "{\r\n}"').tags[0].value == "{\r\n}"
    assert parse_text('k "{\n}"').tags[0].value == "{\n}"


def test_a_brace_inside_quotes_is_part_of_the_value():
    assert parse_text('k "}"').tags[0] == Tag("k", (), "}", STRING)
    assert parse_text('k "a b # c"').tags[0].value == "a b # c"


def test_a_number_larger_than_int32_is_refused_when_it_is_written():
    tag = parse_text("k 4294967295").tags[0]
    assert tag.value_type == INT32
    with pytest.raises(ChumpError, match="cannot store 4294967295 as type 0x1"):
        pack_chump(Tag("<root>", [tag]))


def test_a_value_tag_and_a_brace_do_not_mix():
    assert parse_text('k "{"').tags[0].value == "{"


# --------------------------------------------------------------------------
# the check a write is guarded by: quotes, angle brackets and repeated names
# --------------------------------------------------------------------------
def test_check_text_hands_back_the_tags_the_parser_makes():
    assert check_text('k 1\ns "two"\n') == parse_text('k 1\ns "two"\n')


def test_a_quote_mark_in_a_value_that_does_not_start_with_one_is_reported():
    with pytest.raises(ChumpError, match=r"line 2: value for tag 'username' has a quote mark"):
        check_text("k 1\nusername bob\"\n")


def test_a_quoted_value_that_never_gets_its_closing_quote_is_reported_by_line():
    with pytest.raises(ChumpError, match=r"line 4: quoted value for tag 'k' is never closed"):
        check_text("k 1\nt\n{\nk \"abc\n}\n")


def test_a_quoted_value_with_text_after_its_closing_quote_is_reported():
    with pytest.raises(ChumpError, match="quoted value for tag 'k' is never closed"):
        check_text('k "say "hi" and no more\n')


def test_quotes_that_pair_up_inside_a_quoted_value_are_kept():
    assert check_text('k "say ""hi"" ok"').tags[0].value == 'say ""hi"" ok'


def test_a_kuid_without_its_closing_bracket_is_reported():
    with pytest.raises(ChumpError, match=r"line 1: value for tag 'kuid': '<' with no '>' after it"):
        check_text("kuid <kuid:1:2\n")


def test_a_kuid_without_its_opening_bracket_is_reported():
    with pytest.raises(ChumpError, match=r"line 1: value for tag 'kuid': '>' with no '<' before"):
        check_text("kuid kuid:1:2>\n")


def test_a_kuid_inside_a_container_is_blamed_on_its_own_line():
    with pytest.raises(ChumpError, match=r"line 3: value for tag 'k': '<' with no '>' after it"):
        check_text("kuid-table\n{\nk <kuid:1:2\n}\n")


def test_a_quoted_value_may_hold_angle_brackets():
    assert check_text('d "less than < and a > sign"').tags[0].value == "less than < and a > sign"


def test_an_unquoted_value_may_hold_a_pair_of_angle_brackets():
    assert check_text("d prose <not a kuid> here").tags[0].value == "prose <not a kuid> here"


def test_a_value_spanning_lines_says_what_it_likes():
    """A license string holds brackets and quotes; the run's marks pair up."""
    text = (
        'license "a < b and a > sign\n'
        'and a "quoted" word here\n'
        'and an unclosed bracket <"\n'
        'name "ok"\n'
    )
    tags = check_text(text).tags
    assert tags[0].value == (
        'a < b and a > sign\nand a "quoted" word here\nand an unclosed bracket <'
    )
    assert [tag.name for tag in tags] == ["license", "name"]


def test_a_quote_mark_with_no_partner_on_one_line_is_reported():
    with pytest.raises(ChumpError, match=r"line 1: quoted value for tag 'k' has a quote mark "
                                         "with no partner"):
        check_text('k "a" b"\n')


def test_a_missing_closing_quote_that_eats_the_next_tag_is_reported():
    """The usual slip: the run goes on until a later value's quote closes it."""
    with pytest.raises(ChumpError, match=r"line 1: quoted value for tag 'kind' has a quote mark "
                                         "with no partner"):
        check_text('kind "interior\nkuid <kuid:1:2>\nname "bob"\n')


def test_a_quote_mark_in_a_tag_name_is_reported():
    with pytest.raises(ChumpError, match=r"line 2: tag name 'kind\"' has a quote mark in it"):
        check_text('k 1\nkind" 2\n')


def test_a_tag_written_twice_at_the_top_of_the_file_is_reported():
    with pytest.raises(ChumpError, match=r"line 2: tag 'username' is written twice at the "
                                         "same level, the first one on line 1"):
        check_text('username "abc"\nusername "bcdf"\n')


def test_a_tag_written_twice_inside_a_container_is_reported():
    with pytest.raises(ChumpError, match=r"line 4: tag 'distance' is written twice at the "
                                         "same level, the first one on line 3"):
        check_text("c\n{\ndistance 2\ndistance 3\n}\n")


def test_two_containers_of_one_name_at_the_same_level_are_reported():
    with pytest.raises(ChumpError, match=r"line 8: tag 'kuid-table' is written twice at the "
                                         "same level, the first one on line 3"):
        check_text(
            'username "test"\n'
            "\n"
            "kuid-table\n{\n0 <kuid:12:12>\n}\n"
            "\n"
            "kuid-table\n{\n1 <kuid:23:23>\n}\n"
        )


def test_a_container_and_a_tag_of_the_same_name_written_beside_each_other_are_reported():
    with pytest.raises(ChumpError, match=r"line 4: tag 'mesh-table' is written twice"):
        check_text("mesh-table\n{\n}\nmesh-table 3\n")


def test_a_tag_written_again_inside_a_container_is_a_different_tag():
    # the container the second one is written in is a different container, so
    # the two of them say nothing contradictory about one name
    check_text('username "abc"\n\nc\n{\nusername "bcdf"\n}\n')


def test_a_name_repeated_down_through_the_levels_is_fine():
    check_text("kuid-table\n{\nkuid-table\n{\n}\n}\n")


def test_the_same_name_in_two_different_containers_is_fine():
    check_text("a\n{\nd 1\n}\n\nb\n{\nd 2\n}\n")


def test_a_broken_brace_is_blamed_before_a_name_written_twice():
    # the stray '}' is the real problem, and a repeat that only the broken
    # layout would seem to create has to wait behind it
    with pytest.raises(ChumpError, match=r"line 5: '\}' with no container open"):
        check_text("a\n{\nx 1\n}\n}\nx 2\n")


def test_a_brace_with_no_name_before_it_is_blamed_before_a_name_written_twice():
    with pytest.raises(ChumpError, match=r"line 1: '\{' without a tag name before it"):
        check_text("{\nx 1\nx 2\n}\n")


def test_the_sample_text_files_pass_the_check():
    for stem in ("config1", "config2", "config3", "obsolete_config"):
        check_text(read_text_file(SAMPLES / f"{stem}.txt"))


# --------------------------------------------------------------------------
# the sample files, text form and binary form
# --------------------------------------------------------------------------
def test_the_sample_text_files_read_back_to_the_tags_of_their_binaries():
    for stem in ("config2", "config3"):
        assert load_text(SAMPLES / f"{stem}.txt") == load_chump(SAMPLES / f"{stem}.chump")


def test_the_sample_text_files_pack_back_to_their_binaries():
    for stem in ("config2", "config3"):
        data = (SAMPLES / f"{stem}.chump").read_bytes()
        assert pack_chump(load_text(SAMPLES / f"{stem}.txt")) == data


def test_config2_is_rendered_exactly_as_its_text_file():
    on_disk = (SAMPLES / "config2.txt").read_text(encoding="utf-8-sig", newline="")
    assert render_text(load_chump(SAMPLES / "config2.chump")) == on_disk


def test_config1_is_rendered_like_its_text_file_apart_from_the_edited_lines():
    # config1.txt went through a text editor after the expander wrote it: the
    # username, one mesh name and one kuid were changed by hand
    rendered = render_text(load_chump(SAMPLES / "config1.chump")).split("\r\n")
    on_disk = (SAMPLES / "config1.txt").read_text(encoding="utf-8-sig", newline="").split("\r\n")
    assert len(rendered) == len(on_disk)
    differing = [disk for line, disk in zip(rendered, on_disk) if line != disk]
    assert [line.split()[0] for line in differing] == ["username", "mesh", "kuid"]


def test_config1_agrees_with_its_text_file_about_the_tag_tree():
    text = parse_text((SAMPLES / "config1.txt").read_text(encoding="utf-8-sig", newline=""))
    chump = load_chump(SAMPLES / "config1.chump")
    assert names(text) == names(chump)
    assert [tag.value_type for tag in text.tags] == [tag.value_type for tag in chump.tags]
    assert text.tags[10].value_type == NULL == chump.tags[10].value_type
    assert text.tags[11].tags[0].tags[0].value_type == INT32
    assert chump.tags[11].tags[0].tags[0].value_type == INT32
    assert text.tags[12].value_type == KUID == chump.tags[12].value_type


def test_a_signal_asset_decodes_into_text_that_reads_back_as_the_same_text():
    # semnal.chump is a real signal asset: 24 tags at the top, containers inside
    # containers (a signals container holding one container per signal, each of
    # those holding a value), and a license running over a dozen lines
    root = parse_chump((SAMPLES / "semnal.chump").read_bytes())
    text = render_text(root)
    signals = root.get("signals")

    check_text(text)
    assert [tag.name for tag in signals.tags] == ["0", "4", "8"]
    assert all(tag.is_container for tag in signals.tags)
    assert render_text(parse_text(text)) == text


def test_a_signal_asset_sets_its_containers_off_however_deep_they_are():
    # the signals of a signal asset are containers two levels down, written one
    # under another, and they are set off just like the containers at the top
    text = render_text(load_chump(SAMPLES / "semnal.chump"))

    assert (
        "}\r\n\r\nsignals\r\n{\r\n"
        "  0\r\n  {\r\n    light" + " " * 31 + "3\r\n  }\r\n"
        "\r\n"
        "  4\r\n  {\r\n    light" + " " * 31 + "3\r\n  }\r\n"
        "\r\n"
        "  8\r\n  {\r\n    light" + " " * 31 + "3\r\n  }\r\n"
        "}\r\n\r\nlights\r\n{\r\n}\r\n\r\nmesh-table\r\n"
    ) in text


# --------------------------------------------------------------------------
# reading and writing files
# --------------------------------------------------------------------------
def test_read_text_file_gives_the_text_as_it_is_on_disk():
    text = read_text_file(SAMPLES / "config1.txt")
    assert not text.startswith("\ufeff")
    assert text.split("\r\n")[0] == ""
    assert text.endswith("\r\n")


def test_a_text_file_without_a_byte_order_mark_reads_the_same():
    for stem in ("config1", "config2", "config3"):
        raw = (SAMPLES / f"{stem}.txt").read_bytes()
        assert parse_text(raw.decode("utf-8-sig", "surrogateescape")) == load_text(
            SAMPLES / f"{stem}.txt"
        )


def test_dump_text_writes_the_text_form_of_a_tree(tmp_path):
    target = tmp_path / "out" / "config.txt"
    dump_text(load_chump(SAMPLES / "config2.chump"), target)
    assert parse_text(target.read_text(encoding="utf-8-sig", newline="")) == load_chump(
        SAMPLES / "config2.chump"
    )


def test_dump_text_honours_the_line_ending(tmp_path):
    target = tmp_path / "config.txt"
    root = Tag("<root>", [Tag("k", (), 42, INT32)])
    dump_text(root, target, eol="\n")
    assert target.read_bytes() == b"\xef\xbb\xbf\nk" + b" " * 39 + b"42\n"
    dump_text(root, target, eol="\r\n")
    assert target.read_bytes() == b"\xef\xbb\xbf\r\nk" + b" " * 39 + b"42\r\n"


def test_dump_chump_writes_bytes_that_read_back(tmp_path):
    target = tmp_path / "nested" / "config.chump"
    dump_chump(load_chump(SAMPLES / "config3.chump"), target)
    assert target.read_bytes() == (SAMPLES / "config3.chump").read_bytes()


def test_a_text_file_written_by_hand_packs_into_a_chump_file(tmp_path):
    source = tmp_path / "hand.txt"
    source.write_text("k 1\nera\n", newline="")
    dump_chump(parse_text(source.read_text()), tmp_path / "hand.chump")
    assert parse_chump((tmp_path / "hand.chump").read_bytes()) == parse_text(
        source.read_text()
    )


# --------------------------------------------------------------------------
# converting a file: the extension decides the direction
# --------------------------------------------------------------------------
def test_a_chump_file_becomes_a_text_file_beside_it(tmp_path):
    source = tmp_path / "config.chump"
    source.write_bytes((SAMPLES / "config2.chump").read_bytes())
    target = convert_file(source)
    assert target == tmp_path / "config.txt"
    assert target.read_bytes() == (SAMPLES / "config2.txt").read_bytes()


def test_a_text_file_becomes_a_chump_file_beside_it(tmp_path):
    source = tmp_path / "config.txt"
    source.write_bytes((SAMPLES / "config3.txt").read_bytes())
    target = convert_file(source)
    assert target == tmp_path / "config.chump"
    assert target.read_bytes() == (SAMPLES / "config3.chump").read_bytes()


def test_a_cdp_file_is_a_chump_file_under_another_name(tmp_path):
    source = tmp_path / "config.cdp"
    source.write_bytes((SAMPLES / "config1.chump").read_bytes())
    target = convert_file(source)
    assert target == tmp_path / "config.txt"
    assert parse_text(target.read_text(encoding="utf-8-sig", newline="")) == load_chump(
        SAMPLES / "config1.chump"
    )


def test_an_explicit_target_is_used_as_it_is(tmp_path):
    source = SAMPLES / "config2.chump"
    target = tmp_path / "nested" / "other.txt"
    assert convert_file(source, target) == target
    assert target.read_bytes() == (SAMPLES / "config2.txt").read_bytes()


def test_a_file_that_is_neither_form_is_refused(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("hello")
    with pytest.raises(ChumpError, match=r"not a chump file \('.chump/.cdp'\) and not a text file"):
        convert_file(source)
