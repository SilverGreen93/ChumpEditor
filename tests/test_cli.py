"""Tests for chumpeditor.cli: which mode runs, both directions, what goes wrong.

The samples of ``tests/test_files`` drive the conversions.  Wherever the CLI
writes next to the input, a copy of the sample is made first, so the repository
fixtures are only ever read.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

import pytest

from chumpeditor.chump import load_chump, load_text, pack_chump, parse_text, read_text_file
from chumpeditor.cli import main, run_cli, text_of, verb

SAMPLES = Path(__file__).parent / "test_files"


def copy(sample: str, folder: Path) -> Path:
    """A copy of a sample, because the CLI writes its output beside the input."""
    target = folder / sample
    target.write_bytes((SAMPLES / sample).read_bytes())
    return target


def read_text(path: Path) -> str:
    """A text file as it stands on disk, line endings and all.

    ``Path.read_text`` only grew a ``newline`` argument in 3.13 and the package
    still supports 3.9, so the file is opened with ``open`` and read whole.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return stream.read()


# ---------------------------------------------------------------------------
# which mode runs
# ---------------------------------------------------------------------------
def test_no_arguments_launch_the_gui(monkeypatch):
    pytest.importorskip("PyQt6.QtWidgets")
    seen = []
    monkeypatch.setattr("chumpeditor.gui.run_gui", lambda paths=None: seen.append(paths) or 0)
    assert main([]) == 0
    assert seen == [[]]


def test_no_arguments_without_pyqt_says_what_to_install(monkeypatch, capsys):
    # a distro package installs the CLI on its own; the hint is the help
    monkeypatch.setitem(sys.modules, "chumpeditor.gui", None)
    assert main([]) == 1
    err = capsys.readouterr().err
    assert "PyQt6" in err
    assert 'chumpeditor "config.chump"' in err


def test_help_lists_both_ways_of_naming_the_output(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--out" in out
    assert "--stdout" in out


# ---------------------------------------------------------------------------
# chump -> text
# ---------------------------------------------------------------------------
def test_a_chump_expands_into_a_text_file_beside_it(tmp_path, capsys):
    source = copy("config1.chump", tmp_path)
    assert main([str(source)]) == 0
    text = tmp_path / "config1.txt"
    assert text.is_file()
    out = capsys.readouterr().out
    assert out.startswith("expanded ")
    assert out.strip().endswith("config1.txt")
    assert parse_text(read_text(text)) == load_chump(source)


def test_only_the_input_and_its_other_form_are_in_the_folder(tmp_path):
    source = copy("config1.chump", tmp_path)
    assert main([str(source)]) == 0
    assert sorted(path.name for path in tmp_path.iterdir()) == ["config1.chump", "config1.txt"]


def test_the_text_written_for_config2_is_its_sample_text_byte_for_byte(tmp_path):
    # the sample text is what the original expander wrote for that chump, so
    # matching it byte for byte proves our text form matches its text form
    source = copy("config2.chump", tmp_path)
    assert main([str(source)]) == 0
    assert (tmp_path / "config2.txt").read_bytes() == (SAMPLES / "config2.txt").read_bytes()


def test_the_text_written_for_config1_matches_apart_from_its_hand_edits(tmp_path):
    # config1.txt has been edited by hand: the user name and the mesh name have
    # lost a suffix and the kuid names another asset.  Everything else, blank
    # lines and column alignment included, comes out the same.
    source = copy("config1.chump", tmp_path)
    assert main([str(source)]) == 0
    written = read_text(tmp_path / "config1.txt").split("\r\n")
    sample = read_text(SAMPLES / "config1.txt").split("\r\n")
    changed = [
        (sample[i1:i2], written[j1:j2])
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, sample, written).get_opcodes()
        if tag != "equal"
    ]
    assert len(changed) == 3
    for before, after in changed:
        assert len(before) == len(after) == 1
        assert before[0].split()[0] == after[0].split()[0]
        assert before[0].split()[0] in ("username", "mesh", "kuid")


def test_a_cdp_file_expands_like_a_chump(tmp_path):
    source = tmp_path / "config1.cdp"
    source.write_bytes((SAMPLES / "config1.chump").read_bytes())
    assert main([str(source)]) == 0
    assert (tmp_path / "config1.txt").is_file()


# ---------------------------------------------------------------------------
# text -> chump
# ---------------------------------------------------------------------------
def test_a_text_file_packs_into_a_chump_beside_it(tmp_path, capsys):
    source = copy("config2.txt", tmp_path)
    assert main([str(source)]) == 0
    packed = tmp_path / "config2.chump"
    assert packed.is_file()
    out = capsys.readouterr().out
    assert out.startswith("packed ")
    assert out.strip().endswith("config2.chump")
    assert packed.read_bytes() == (SAMPLES / "config2.chump").read_bytes()


@pytest.mark.parametrize("stem", ["config1", "config2", "config3"])
def test_a_chump_packed_from_the_text_it_just_wrote_is_the_file_again(tmp_path, stem):
    # the round trip the tool exists for: expand, pack the text, same bytes
    source = copy(f"{stem}.chump", tmp_path)
    original = source.read_bytes()
    assert main([str(source)]) == 0
    source.unlink()
    assert main([str(tmp_path / f"{stem}.txt")]) == 0
    assert (tmp_path / f"{stem}.chump").read_bytes() == original


# ---------------------------------------------------------------------------
# --out and --stdout
# ---------------------------------------------------------------------------
def test_out_names_the_file_to_write(tmp_path):
    source = copy("config1.chump", tmp_path)
    target = tmp_path / "somewhere deeper" / "out.txt"
    assert main(["--out", str(target), str(source)]) == 0
    assert target.is_file()  # the folder is made if it is not there
    assert not (tmp_path / "config1.txt").exists()


def test_out_can_pack_too(tmp_path):
    source = copy("config2.txt", tmp_path)
    target = tmp_path / "packed.chump"
    assert main(["--out", str(target), str(source)]) == 0
    assert target.read_bytes() == (SAMPLES / "config2.chump").read_bytes()


def test_out_takes_one_input_only(tmp_path, capsys):
    first = copy("config1.chump", tmp_path)
    second = copy("config2.chump", tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["--out", str(tmp_path / "out.txt"), str(first), str(second)])
    assert exc.value.code == 2
    assert "--out takes a single input file" in capsys.readouterr().err


def test_stdout_prints_the_text_form_of_a_chump(tmp_path, capsys):
    source = copy("config1.chump", tmp_path)
    assert main(["--stdout", str(source)]) == 0
    assert "mesh-table" in capsys.readouterr().out
    assert not (tmp_path / "config1.txt").exists()


def test_stdout_prints_a_text_file_as_it_stands(tmp_path, capsys):
    source = copy("config3.txt", tmp_path)
    assert main(["--stdout", str(source)]) == 0
    # stdout is opened in text mode, so only the line endings may differ
    assert capsys.readouterr().out.replace("\r", "") == read_text(source).replace("\r", "")


def test_text_of_answers_the_same_whichever_way_the_file_comes(tmp_path):
    # for config2 the text form in the file is exactly the one we would write,
    # so reading it and expanding the chump have to agree down to the byte
    assert text_of(SAMPLES / "config2.txt") == text_of(SAMPLES / "config2.chump")


# ---------------------------------------------------------------------------
# what goes wrong
# ---------------------------------------------------------------------------
def test_a_file_of_another_kind_is_refused(tmp_path, capsys):
    junk = tmp_path / "notes.bin"
    junk.write_text("not a chump at all")
    assert main([str(junk)]) == 1
    assert "notes.bin: not a chump file" in capsys.readouterr().err


def test_a_file_that_is_not_a_chump_is_reported(tmp_path, capsys):
    junk = tmp_path / "config.chump"
    junk.write_bytes(b"plain text, not a chump")
    assert main([str(junk)]) == 1
    err = capsys.readouterr().err
    assert "Error:" in err
    assert "not a chump file (starts with b'plai')" in err


def test_a_text_file_whose_braces_do_not_balance_is_reported(tmp_path, capsys):
    broken = tmp_path / "config.txt"
    broken.write_text("kuid-table\n{\n")
    assert main([str(broken)]) == 1
    assert "is never closed" in capsys.readouterr().err


def test_a_missing_file_is_reported(tmp_path, capsys):
    assert main([str(tmp_path / "nope.chump")]) == 1
    assert "nope.chump" in capsys.readouterr().err


def test_one_bad_path_does_not_stop_the_others(tmp_path, capsys):
    source = copy("config1.chump", tmp_path)
    assert main([str(tmp_path / "nope.chump"), str(source)]) == 1
    out = capsys.readouterr().out
    assert "config1.chump" in out
    assert (tmp_path / "config1.txt").is_file()


def test_run_cli_says_whether_every_file_worked(tmp_path):
    source = copy("config1.chump", tmp_path)
    assert run_cli([str(source)]) is True
    assert run_cli([str(source), str(tmp_path / "nope.chump")]) is False


# ---------------------------------------------------------------------------
# the words it uses
# ---------------------------------------------------------------------------
def test_the_verb_names_the_direction():
    assert verb(Path("config.chump")) == "expanded"
    assert verb(Path("config.CDP")) == "expanded"
    assert verb(Path("config.txt")) == "packed"
    assert verb(Path("config.bin")) == "converted"


def test_a_whole_folder_can_be_converted_at_once(tmp_path):
    for stem in ("config1", "config2", "config3"):
        copy(f"{stem}.chump", tmp_path)
    chumps = sorted(tmp_path.glob("*.chump"))
    assert run_cli([str(path) for path in chumps]) is True
    assert len(list(tmp_path.glob("*.txt"))) == 3
    for stem in ("config2", "config3"):
        assert parse_text(read_text(tmp_path / f"{stem}.txt")) == load_text(SAMPLES / f"{stem}.txt")
