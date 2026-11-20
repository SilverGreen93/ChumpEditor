"""Tests for chumpeditor.document: the file rules the editor follows.

No Qt here on purpose - these are the rules themselves, so they run whether or
not the GUI is installed.  As everywhere else, the samples of ``test_files``
are only read; anything written goes into a scratch folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chumpeditor.chump import ChumpError, load_chump, parse_text, read_text_file
from chumpeditor.document import (
    ALL_SUFFIXES,
    filter_string,
    is_readable,
    read_document,
    save_chump,
    save_text,
    suggested_path,
)

SAMPLES = Path(__file__).parent / "test_files"


def copy(sample: str, folder: Path) -> Path:
    target = folder / sample
    target.write_bytes((SAMPLES / sample).read_bytes())
    return target


# ---------------------------------------------------------------------------
# what can be opened
# ---------------------------------------------------------------------------
def test_every_form_the_editor_takes_is_listed_once():
    assert ALL_SUFFIXES == (".chump", ".cdp", ".txt")


def test_files_of_both_forms_are_readable(tmp_path):
    for sample in ("config1.chump", "config2.txt"):
        assert is_readable(copy(sample, tmp_path))


def test_a_folder_or_a_stranger_is_not_readable(tmp_path):
    other = tmp_path / "notes.bin"
    other.write_text("not a chump")
    assert not is_readable(other)
    assert not is_readable(tmp_path)
    assert not is_readable(tmp_path / "gone.chump")


def test_the_open_dialog_offers_all_three_extensions_then_each_form():
    assert filter_string() == (
        "All supported files (*.chump *.cdp *.txt)"
        ";;Chump files (*.chump *.cdp)"
        ";;Text files (*.txt)"
    )


def test_a_narrower_group_can_be_asked_for():
    assert filter_string(("Chump files", (".chump", ".cdp"))) == "Chump files (*.chump *.cdp)"


# ---------------------------------------------------------------------------
# what opening puts in the editor
# ---------------------------------------------------------------------------
def test_opening_a_chump_shows_exactly_the_sample_text(tmp_path):
    # config2 is the pair the samples come in unchanged; config1.txt was
    # hand-edited after the expander wrote it, so it is not byte for byte
    source = copy("config2.chump", tmp_path)
    assert read_document(source) == read_text_file(SAMPLES / "config2.txt")


def test_the_text_a_chump_opens_with_reads_back_as_the_same_tags(tmp_path):
    source = copy("config1.chump", tmp_path)
    assert parse_text(read_document(source)) == load_chump(source)


def test_opening_a_txt_shows_the_file_as_it_stands(tmp_path):
    source = copy("config2.txt", tmp_path)
    assert read_document(source) == source.read_text(encoding="utf-8-sig", newline="")


def test_the_bom_of_a_text_file_is_not_part_of_the_text(tmp_path):
    source = copy("config3.txt", tmp_path)
    assert not read_document(source).startswith("\ufeff")
    assert source.read_bytes().startswith(b"\xef\xbb\xbf")


def test_a_file_that_is_not_one_of_the_forms_says_which_ones_are(tmp_path):
    other = tmp_path / "notes.bin"
    other.write_text("nope")
    with pytest.raises(ChumpError) as exc:
        read_document(other)
    assert ".chump" in str(exc.value) and ".txt" in str(exc.value)


def test_a_chump_that_is_not_a_chump_is_the_codecs_complaint(tmp_path):
    broken = tmp_path / "broken.chump"
    broken.write_bytes(b"plain text, not a chump")
    with pytest.raises(ChumpError) as exc:
        read_document(broken)
    assert "not a chump file" in str(exc.value)


# ---------------------------------------------------------------------------
# what saving and exporting write
# ---------------------------------------------------------------------------
def test_saving_the_text_of_a_sample_returns_its_original_bytes(tmp_path):
    text = read_document(copy("config2.txt", tmp_path))
    target = save_chump(text, tmp_path / "rebuilt.chump")
    assert target.read_bytes() == (SAMPLES / "config2.chump").read_bytes()


def test_saving_text_that_does_not_parse_is_refused(tmp_path):
    with pytest.raises(ChumpError) as exc:
        save_chump("kuid-table\n{\n", tmp_path / "half.chump")
    assert "never closed" in str(exc.value)
    assert not (tmp_path / "half.chump").exists()


def test_a_value_spanning_lines_comes_back_with_the_formats_own_endings(tmp_path):
    """The editor holds LF; the format writes CRLF, and so does a save.

    Only the line endings of the document itself are rewritten.  A license
    string that runs over three lines goes back in with CRLF inside it, which
    is what makes a chump opened in the window pack to the same bytes again.
    """
    editor_text = read_document(copy("config3.chump", tmp_path)).replace("\r\n", "\n")
    target = save_chump(editor_text, tmp_path / "back.chump")
    assert target.read_bytes() == (SAMPLES / "config3.chump").read_bytes()


def test_exporting_writes_the_bom_and_crlf_the_format_uses(tmp_path):
    text = read_document(copy("config1.chump", tmp_path)).replace("\r\n", "\n")
    written = save_text(text, tmp_path / "out.txt").read_bytes()
    assert written.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in written
    assert written.count(b"\n") == written.count(b"\r\n")  # no lone LF anywhere
    assert written.decode("utf-8-sig").replace("\r\n", "\n") == text


def test_exporting_leaves_the_spacing_of_the_editor_alone(tmp_path):
    target = save_text("kuid   <kuid:1:2>\nname\ttabbed\n", tmp_path / "spaced.txt")
    assert target.read_text(encoding="utf-8-sig", newline="") == (
        "kuid   <kuid:1:2>\r\nname\ttabbed\r\n"
    )


def test_exporting_makes_the_folder_it_needs(tmp_path):
    target = save_text("a 1\n", tmp_path / "deeper" / "down" / "out.txt")
    assert target.is_file()


# ---------------------------------------------------------------------------
# the names the save dialogs start with
# ---------------------------------------------------------------------------
def test_saving_a_chump_keeps_the_name_it_has(tmp_path):
    assert suggested_path(tmp_path / "config.chump", ".chump") == tmp_path / "config.chump"


def test_a_text_file_becomes_a_chump_of_the_same_name(tmp_path):
    assert suggested_path(tmp_path / "config.txt", ".chump") == tmp_path / "config.chump"


def test_an_extension_without_its_dot_still_works(tmp_path):
    assert suggested_path(tmp_path / "config.txt", "txt") == tmp_path / "config.txt"


def test_without_a_file_there_is_nothing_to_suggest():
    assert suggested_path(None, ".chump") is None
