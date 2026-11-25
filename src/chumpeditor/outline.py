"""Which containers a text holds, and which line each of them starts on.

Free of Qt like ``search.py`` and ``tweaks.py``: the question "what is this file
made of, and where" has an answer that has nothing to do with a window.  The
tree beside the text in ``gui/treeview.py`` asks these questions about the text
on screen, and the window moves the caret to the answers.

A container here is a tag written with braces - ``kuid-table``, ``mesh-table``
and whatever stands inside them - and nothing else: a tag holding one value on
its own line is a single line tag and gets no row of its own.  An empty
container still counts as one, which is how the ``obsolete-table {}`` at the end
of an asset shows up.  A container's name may hold spaces, since the brace says
where it ends: the ``2018-12-15 162811.jpg`` inside a screenshots container is
one name, and one row of the tree.

The lines are walked by hand rather than read with ``chump.parse_text``, for two
reasons: the parser throws the line numbers away, and it refuses a file that
writes one name twice, which text being edited does all the time.  The walk
follows the codec's own rules all the same - the brace placement of
``tweaks._the_brace_the_tag_opens``, the running value of
``tweaks._opens_a_running_value``, and ``chump._split_name`` and
``chump._a_brace_below``, which together read a line as a name and what follows
it - so a line inside somebody's multi-line license string is never mistaken for
a tag, and the three ways of writing a container all read the way the codec
reads them.  A closing brace closes a level even when the line that opened it
could not be read, which is what keeps one unclosed container from swallowing
the rest of the file.

Every line number counts from 1, the way ``chump.find_problems``,
``search.line_of`` and the numbers down the left of the editor count them, so a
row in the tree and the number beside the text agree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .chump import _a_brace_below, _split_lines, _split_name
from .tweaks import _opens_a_running_value

__all__ = ["Container", "containers"]


@dataclass(frozen=True)
class Container:
    """One container in the text: what it is called and where it stands.

    ``level`` counts from 0 at the top of the file, so a tree can be built out
    of the flat list without looking back at the lines.  ``path`` is the names
    from the top of the file down to this one, which is what tells two rows with
    the same name apart and lets a row say where in the file it is.
    """

    #: the tag's own name, spelled as the text spells it
    name: str
    #: how deep inside the file it stands: 0 at the top
    level: int
    #: the line its name is written on, counted from 1
    line: int
    #: the names of its parents and its own, outermost first
    path: tuple[str, ...] = field(default=())

    def __str__(self) -> str:
        return "/".join(self.path)


def containers(text: str) -> list[Container]:
    """Every container in the text, in the order their names are written.

    Depth first: a container comes before whatever stands inside it, and its
    sub-containers follow it one after another.  A flat list of them is therefore
    already in tree order, which is what lets ``gui/treeview.py`` build its rows
    by walking down the levels.

    Text that is broken mid-edit still gets an answer: a value or a container
    that is never closed leaves whatever follows it read as though nothing had
    gone wrong, and a line that is not a tag at all is passed over.  An empty
    text - and a text of nothing but single line tags - gives an empty list.
    """
    lines, _eol = _split_lines(text)
    found: list[Container] = []
    # the containers standing open above this line, innermost last; their names
    # are what a new row is written under
    parents: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped == "}":
            # the container above closes here, even when the line that opened it
            # could not be read; that is what stops one unclosed brace from
            # swallowing the rest of the file
            if parents:
                parents.pop()
            index += 1
            continue

        name, rest = _split_name(stripped, _a_brace_below(lines, index))
        if rest == "{":
            found.append(_a_container(name, parents, index))
            parents.append(name)
            index += 1
            continue
        if rest and not rest.startswith("{"):
            # a value on the name's own line: either closed there - a string, a
            # number, a kuid, or a one-line ``name { ... }``, which is a value
            # and not a container - or running over the lines under it, where a
            # line that looks like a tag is only prose.  Which of the two it is
            # is settled on the name's own line, as in ``tweaks``: waiting to ask
            # it until the line below has been read would take the first line of
            # a value for a tag line
            line = lines[index]
            index += 1
            if _opens_a_running_value(line):
                closed = _the_quote_closing_it(lines, index)
                # a value whose closing quote never comes owns the rest of the
                # text as far as the codec is concerned - which is what
                # ``chump.find_problems`` says about it too - but a tree that
                # stops working halfway through an edit is worse than one that
                # shows the tags below it as well, so the walk carries on
                index = closed + 1 if closed is not None else index
            continue
        if not rest:
            if _a_brace_below(lines, index):
                # the name alone, its brace kept for the line below
                found.append(_a_container(name, parents, index))
                parents.append(name)
                index += 2
                continue
            # a tag with nothing after it and no brace below holds nothing, and
            # is one of the single line tags this list leaves out
            index += 1
            continue
        # ``name {`` with something else after the brace: read as a value by the
        # codec, so a row is not made for it and the walk carries on below
        index += 1
    return found


def _the_quote_closing_it(lines: list[str], where: int) -> int | None:
    """The line holding the quote that closes a value running over lines.

    The codec's own rule, the one ``tweaks._the_value_closing_line`` uses as
    well: the first line ending in a quote closes the value.  Nothing does when
    the value was never closed.
    """
    for at in range(where, len(lines)):
        if lines[at].endswith('"'):
            return at
    return None


def _a_container(name: str, parents: list[str], at: int) -> Container:
    """One container, found on the line ``at`` counts from nought."""
    path = (*parents, name)
    return Container(name=name, level=len(parents), line=at + 1, path=path)
