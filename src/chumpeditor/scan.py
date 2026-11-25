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

The name at the start of a line is read whole, the way ``chump.parse_text``
reads it: every symbol but a space and a brace belongs to a name, so a dot in
``junction.forward`` and the brackets of a kuid name are part of it, and so is a
space when what follows it is no value of its own - ``Scenery Objects`` is one
name, and the brace a container opens is the only thing ending
``2018-12-15 162811.jpg``.  That name is also the one place a theme can colour a
whole sort of name at once, every tag or every container, so the scanner says
which sort it is looking at, which needs the line below, hence the ``following``
argument.  A pair of the theme colours a value and never that name, which is how
a name written ``<kuid2:1:2:3>`` is coloured as a name while the same thing
after a space is coloured as a value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chump import _split_name
from .theme import CONTAINERS, TAGS, Theme

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


def scan_line(
    text: str,
    theme: Theme,
    state: int = STATE_NONE,
    following: str = "",
) -> tuple[list[Span], int]:
    """The spans to colour on this line, and which pair is still open after it.

    ``state`` is what the previous line ended with: ``STATE_NONE``, or the
    number of the pair that was left open.  ``following`` is the line below,
    which is the only way to tell ``mesh-table`` from ``mesh-table { ... }`` when
    the brace is written on a line of its own.
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
    else:
        position = _name_at_the_head(text, theme, following, spans)

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


def _name_at_the_head(text: str, theme: Theme, following: str, spans: list[Span]) -> int:
    """Colour the name this line starts with, and say where the rest begins.

    The name is read with ``chump._split_name``, the same cut the reader makes:
    it runs to the first space a whole value follows, so ``junction.forward`` is
    one name and so is ``Scenery Objects``, and it runs to the brace a container
    opens, which is the only thing saying ``2018-12-15 162811.jpg`` is one name.
    None of the theme's pairs is tried against a name, because those colour
    values, and a colon written straight after the name, the old spelling
    ``name: value``, is not part of it.
    """
    head = len(text) - len(text.lstrip())
    stripped = text.strip()
    if not stripped or stripped[0] in "{}":
        return head  # a line of nothing but spaces, or one of nothing but a brace

    brace_below = following.strip() == "{"
    name, rest = _split_name(stripped, brace_below)
    # the brace says a name runs to it, whether it ends this line or waits on
    # the line below, where a name filling the whole line is the only thing a
    # brace can follow
    whole = name == stripped.rstrip(":")
    role = CONTAINERS if rest == "{" or (brace_below and whole) else TAGS

    style = _style_of(name, theme, role)  # _split_name already took off a colon
    if style and name:
        spans.append(Span(head, len(name), style))
    return head + len(name)


def _style_of(word: str, theme: Theme, role: str = "") -> str | None:
    """The style a word asks for, if any: a keyword, then a number, then none.

    Which words count as keywords - the ones listed, the ones a pattern of the
    theme reaches, the ones carrying a language suffix, and the whole sort of
    name a theme covers - is the theme's business, in ``chumpeditor.theme``;
    this only asks it the question, and says what sort of name it is asking
    about.
    """
    style = theme.keyword_style(word, role)
    if style:
        return style
    if theme.numbers and _NUMBER.fullmatch(word):
        return theme.numbers
    return None
