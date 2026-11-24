"""Make the src layout importable without installing the package first."""

import struct
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chumpeditor.chump import MAGIC, TDX_EDITION_VERSION, TDX_MAGIC, TDX_PLAIN_VERSION  # noqa: E402


@pytest.fixture
def tdx_of():
    """Build an ``assets.tdx`` from the contents of its two CHUMP blocks.

    The caller passes the raw contents of each block, not a whole chump file:
    the builder wraps them in standard headers and adds the TDX header.  A
    version at or above 67 gets a length-prefixed edition string first, and a
    few bytes stand in for the asset database after the second block.
    """

    def build(first: bytes, second: bytes, *, version: int = TDX_PLAIN_VERSION,
              edition: bytes = b"") -> bytes:
        prefix = bytes([len(edition)]) + edition if version >= TDX_EDITION_VERSION else b""
        blocks = (
            MAGIC + struct.pack("<III", 1, 0, len(first)) + first
            + MAGIC + struct.pack("<III", 1, 0, len(second)) + second
        )
        body = prefix + blocks + b"\x00\x00\x00\x00"
        return TDX_MAGIC + struct.pack("<II", version, 12 + len(body)) + body

    return build
