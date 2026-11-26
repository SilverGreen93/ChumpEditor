"""Which containers a text holds, and which line each of them starts on.

Free of Qt like ``search.py`` and ``tweaks.py``: the question "what is this file
made of, and where" has an answer that has nothing to do with a window.  The
tree beside the text in ``gui/treeview.py`` asks these questions about the text
on screen, and the window moves the caret to the answers.  The same file
answers what taking one of those containers out of the text would do to it,
which is a question about lines and braces rather than about a window either.

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
from .tweaks import (
    Rewrite,
    _end_of,
    _opens_a_running_value,
    _split,
    _start_of,
    _the_name_and_the_rest,
    _the_tag_takes_up_to,
)

__all__ = ["Container", "ContainerBlock", "containers", "the_container_block"]


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


@dataclass(frozen=True)
class ContainerBlock:
    """What deleting one container would do to the text.

    The same shape every other answer in this package that changes text hands
    over - ``tweaks.Tweaks``, ``tweaks.Sweep``, ``search.ReplaceAll`` - so the
    window reports it the way it reports everything else: a status line for the
    bar, a paragraph for a box, and the rewrites to lay on the text.

    ``rewrites`` is empty when nothing can be deleted, and ``warning`` says
    whether what happened is worth a box that has to be clicked past or only the
    status line: text whose container never closes is a fault in the file, while a
    row that turns out to name no block at all is a request with nothing in it,
    said quietly and done with.
    """

    text: str
    rewrites: tuple[Rewrite, ...] = ()
    status: str = ""
    warning: bool = False

    def summary(self) -> str:
        """The paragraph for the box: what went, and why nothing did if not."""
        return self.status



def _it_holds_a_container(lines: list[str], at: int) -> bool:
    """Whether the tag on this line opens a container rather than holding a value.

    The two shapes ``containers`` itself walks, read from the name's own line: a
    brace standing behind the name with nothing else after it, or the name alone
    with its brace taking the whole of the line below.  Anything else - a quoted
    value, a number, a ``name {}`` written on one line, a tag with nothing after
    it and no brace below - holds a value or holds nothing, and no row of the tree
    stands for it.

    Read off the lines rather than from what ``_the_name_and_the_rest`` says
    follows the name: that hands back only the first word after it, so a container
    whose name is written with spaces - one of the screenshot containers under a
    ``.tdx`` - looks like a tag holding the value ``{``.  Asking the codec's own
    ``_split_name`` cannot make that mistake, and cannot call one shape a container
    here and another one in ``containers``.
    """
    stripped = lines[at].strip()
    name, rest = _split_name(stripped, _a_brace_below(lines, at))
    if not name or name == "{":
        # the line is blank, or a brace standing on its own closing what was
        # opened higher up
        return False
    if rest:
        return rest == "{"
    # nothing after the name: the brace is either the whole of the line below,
    # which opens a container, or missing, which leaves a tag holding nothing
    return _a_brace_below(lines, at) and lines[at + 1].strip() == "{"




def the_container_block(text: str, line: int) -> ContainerBlock:
    """Take the container written at ``line`` out of ``text``, with everything
    written inside it.

    ``line`` is the 1-based number of the line the container's *name* stands on -
    the answer ``Container.line`` gives and the number down the left of the
    editor, which is what a row of the tree carries - so the caller never has to
    know that every helper here counts from nought.

    Where the block ends is not counted out again here: it is asked of
    ``tweaks._the_tag_takes_up_to``, the same walk that decides which tags
    ``tweaks.remove_language_tags`` takes out and what ``chump`` reads as a
    container, so a delete cannot cut a block somewhere other than where the
    codec says one ends.  It follows a name whose brace stands behind it on the
    same line (``kuid-table {}`` is one line of text, and one block), stops at
    the closing brace of an outer container before any stray one further down,
    and reads a multi-line quoted value as part of whatever stands around it
    rather than as a brace.

    Everything inside goes with it, which is what was asked for: right-clicking
    ``mesh-table`` takes ``default``, the tags written in ``default``, and
    ``mesh-table``'s own closing brace, because they are all between its name and
    that brace.  The line ending goes too, so deleting a container leaves no
    blank line where it stood; at the very end of the file there is no next line
    to stand at, and the last line's own ending is taken instead, which keeps one
    fewer empty line rather than adding one.

    A blank line standing directly over the name goes with the block as well, for
    the same reason: it is there to set this container off from what stands beside
    it, and once the container is gone it sets nothing off.  ``_the_gap_above``
    counts how far up that run of blanks runs; a container opening the file keeps
    its place at the top, since there is nothing over its gap for the gap to part.

    Two refusals, both answered without touching the text:

    * nothing is written at ``line``, or what is written there is blank, a brace
      on its own, or the closing end of some other container - there is no block
      to take;
    * the tag opens something that is never closed.  Where it should have ended
      has no answer, and guessing one would delete the rest of the file, which is
      what an unclosed ``mesh-table`` at the top of a broken config otherwise
      swallows.

    The first is said in the status bar; the second is put in a box as well,
    because text that cannot say where its container ends is worth more than a
    line at the bottom of the window.
    """
    lines, eol = _split(text)
    at = line - 1
    if not 0 <= at < len(lines):
        return ContainerBlock(
            text=text,
            status="there is nothing written on that line",
            warning=False,
        )
    name, rest = _the_name_and_the_rest(lines, at)
    if not name:
        return ContainerBlock(
            text=text,
            status="there is no tag written on that line",
            warning=False,
        )
    if not _it_holds_a_container(lines, at):
        # the tag holds a value rather than opening a container.  No row of the
        # tree stands for one, so this is only reached when the text has moved
        # since the rows were written out; either way there is no block here
        return ContainerBlock(
            text=text,
            status=f"that line does not hold the name of a container",
            warning=False,
        )
    last, because = _the_tag_takes_up_to(lines, at, rest)
    if because:
        # the block has no end to cut at, and guessing one would take the rest of
        # the file with it
        return ContainerBlock(
            text=text,
            status=f"the {name!r} container {because}",
            warning=True,
        )
    # the block runs from the first character of the name's line to the first
    # character of the line after it, which takes the closing brace and the line
    # ending with it; see remove_language_tags for the same step at the end of a
    # file, where there is no next line to stand at
    start = _start_of(lines, eol, _the_gap_above(lines, at))
    end = (
        _start_of(lines, eol, last + 1)
        if last + 1 < len(lines)
        else _end_of(lines, eol, last)
    )
    return ContainerBlock(
        text=text,
        rewrites=(Rewrite(start=start, end=end, text=""),),
        status=f"deleted the {name!r} container and what is written in it",
    )


def _the_gap_above(lines: list[str], at: int) -> int:
    """The first line of the block naming ``at``, taking the blank lines above it.

    A container stands off from the tags beside it by a blank line - which is what
    ``tweaks.reorder_tags`` puts right - and that gap exists to set *this* container
    off.  Once the container is gone the gap sets nothing off, so it goes with the
    block; leaving it would leave a hole where the container stood, and one blank
    line too many between what was above and what was below.

    Only the run of blanks directly above is taken, and only when there is a line
    written over it: a gap with nothing above it is not parting anything from the
    container, it is the start of the text, and taking it would move what stands at
    the top of the file up over it.
    """
    if at == 0:
        return 0
    first = at
    while first > 0 and not lines[first - 1].strip():
        first -= 1
    return first if first else at
