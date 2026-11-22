"""Looking for a piece of text, and putting something else in its place.

Free of Qt like ``tweaks.py``, because the whole question - where does this
string stand in that text - has an answer that has nothing to do with a window.
The panel in ``gui/find.py`` asks these questions about the text on screen and
moves the caret to the answers.

Every position here is a character counted through the text the same way the
document counts its own, which is how a match found here can be cut out by
``RichTextEditor.apply_rewrites`` and land where it was worked out to land.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .tweaks import Rewrite

__all__ = ["Match", "find_all", "line_of", "matches", "next_match", "replacements"]


@dataclass(frozen=True)
class Match:
    """One place the text being sought was found.

    The stretch runs from ``start`` up to, but not including, ``end``.
    """

    start: int
    end: int


def find_all(text: str, sought: str, *, match_case: bool = True) -> list[Match]:
    """Every place ``sought`` stands in ``text``, in the order they come.

    Nothing overlaps another and nothing is found twice, because the search
    starts again after the match it just took.  That is what makes a replacement
    containing the very text it replaces safe: each place is still named once.
    An empty ``sought`` asks for nothing, so nothing is found rather than an
    empty match between every two characters.
    """
    if not sought:
        return []
    return [
        Match(one.start(), one.end())
        for one in re.finditer(re.escape(sought), text, 0 if match_case else re.IGNORECASE)
    ]


def matches(piece: str, sought: str, *, match_case: bool = True) -> bool:
    """Whether one stretch of text is the text being sought.

    Asked of a selection, to know whether it is a match the caret is sitting on.
    """
    if not sought:
        return False
    return re.fullmatch(re.escape(sought), piece, 0 if match_case else re.IGNORECASE) is not None


def next_match(text: str, sought: str, after: int, *, match_case: bool = True) -> Match | None:
    """The first place at or after ``after``, or nowhere at all.

    A search that finds nothing past that point starts again at the beginning of
    the file, which is what pressing the same key over and over comes to mean:
    the places are gone round in a ring, and the far end of the file is not a
    wall.
    """
    places = find_all(text, sought, match_case=match_case)
    for one in places:
        if one.start >= after:
            return one
    return places[0] if places else None


def replacements(
    text: str, sought: str, wanted: str, *, match_case: bool = True
) -> list[Rewrite]:
    """Every place as a stretch to cut out, with ``wanted`` going in its place.

    The list is what ``RichTextEditor.apply_rewrites`` takes, so replacing the
    lot of them is one edit block: one press of Undo puts the whole file back.
    """
    return [
        Rewrite(one.start, one.end, wanted)
        for one in find_all(text, sought, match_case=match_case)
    ]


def line_of(text: str, at: int) -> int:
    """Which line the character at ``at`` is on, counting from one.

    Counted the way the numbers down the left of the editor count, so a message
    about line 40 and the 40 beside the text agree.
    """
    return text.count("\n", 0, at) + 1
