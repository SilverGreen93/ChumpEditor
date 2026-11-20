"""Which part of a line gets which colour.

Free of Qt, and deliberately so: the rules of a theme are worth testing
without a window, and the highlighter in :mod:`chumpeditor.gui.highlighter` is
only a thin coat of paint over what this returns.

A line is read left to right. An opening pair wins over anything inside it, so
a keyword in a quoted value stays the colour of the value, A pair with no closing
string on the line is carried into the next one, because a Trainz license
string runs over several lines; a pair whose closing string is left out of the
theme altogether covers the rest of the line and no more, which is how a
comment to the end of a line would be written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .theme import Theme

__all__ = ["Span", "scan_line", "STATE_NONE"]

#: no pair is open at the start of the line
STATE_NONE = -1

_WORD = re.compile(r"[A-Za-z0-9_-]+")
_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Span:
    """A stretch of the line, and the style it asks for."""

    start: int
    length: int
    style: str

    def __len__(self) -> int:
        return self.length


def scan_line(text: str, theme: Theme, state: int = STATE_NONE) -> tuple[list[Span], int]:
    """The spans to colour on this line, and which pair is still open after it.

    ``state`` is what the previous line ended with: ``STATE_NONE``, or the
    number of the pair that was left open.
    """
    spans: list[Span] = []
    position = 0

    if 0 <= state < len(theme.pairs):
        pair = theme.pairs[state]
        end = _closing(text, pair, 0)
        if end is None:
            return [Span(0, len(text), pair.style)], state
        spans.append(Span(0, end, pair.style))
        position = end

    while position < len(text):
        opened = _opening_at(text, position, theme)
        if opened is not None:
            index, pair = opened
            end = _closing(text, pair, position + len(pair.open))
            if end is None:
                spans.append(Span(position, len(text) - position, pair.style))
                # a pair with no closing string of its own ends with the line;
                # one that simply has not closed yet waits for the next one
                return spans, STATE_NONE if not pair.close else index
            spans.append(Span(position, end - position, pair.style))
            position = end
            continue

        # a number is tried before a word so that the point of 12.5 belongs to
        # it; a keyword beginning with a digit would be read as a number
        number = _NUMBER.match(text, position) if theme.numbers else None
        word = number or _WORD.match(text, position)
        if word:
            style = _style_of(word.group(), theme)
            if style:
                spans.append(Span(word.start(), word.end() - word.start(), style))
            position = word.end()
            continue

        position += 1

    return spans, STATE_NONE


def _opening_at(text: str, position: int, theme: Theme) -> tuple[int, object] | None:
    """The first pair that opens here, in the order the theme lists them."""
    for index, pair in enumerate(theme.pairs):
        if pair.open and text.startswith(pair.open, position):
            return index, pair
    return None


def _closing(text: str, pair, start: int) -> int | None:
    """Where the pair ends: one past its closing string, or nowhere on this line."""
    if not pair.close:
        return None
    found = text.find(pair.close, start)
    return None if found < 0 else found + len(pair.close)


def _style_of(word: str, theme: Theme) -> str | None:
    """The style a word asks for, if any: a keyword, then a number, then none."""
    style = theme.words.get(word)
    if style:
        return style
    if theme.numbers and _NUMBER.fullmatch(word):
        return theme.numbers
    return None
