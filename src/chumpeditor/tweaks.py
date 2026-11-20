"""One tidy-up a person asks for: the numbered tags Trainz has moved on from.

Trainz used to write a list as a run of tags with a number on the end -
``category-era-0``, ``category-era-1``, ``category-era-2`` - and reads the same
list now as one tag with the elements between semicolons:
``category-era "1920s;1930s;1940s"``.  This makes that change, and nothing else:
it never decides on its own that a file needs fixing, and it leaves a tag alone
the moment it is not sure about it.

A tag is folded up only when

* two or more of them stand on neighbouring lines under the same name, with a
  dash and a number on the end - one tag on its own is not a list, and ``load0``
  or ``camera0`` standing alone means something else entirely;
* every one of them holds a quoted value on its own line, so a kuid, a number or
  a value running over several lines is not touched;
* none of the values holds a semicolon itself, which would read as two
  elements once they are joined up;
* the plain name is not already used by a tag with a value, and no other group
  would make the same name, either of which would leave the file holding the
  same tag twice.

Anything that is looked at and turned down is said out loud in the summary
rather than passed over in silence.

The elements come out in the order the numbers say, not the order of the lines,
so ``era-10`` follows ``era-9`` rather than ``era-1``; the merged line keeps the
column the tags were written at; and everything else in the text - the order of
the other tags, the blank lines, the spacing - is left exactly as it was.

Everything here is free of Qt and answers in character positions within the
text, so the rules can be read and tested without a window and the editor can
apply the changes as edits a person can undo in one go.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Conversion", "Rewrite", "Tweaks", "convert_obsolete_lists"]

#: a tag with a number on the end and a quoted value of its own after the
#: spaces.  The name is taken up to the last dash before the digits, so
#: category-era-0 is era 0 of category-era and not "category" of "era-0".  The
#: value has to be closed on the same line and hold something, which is what
#: keeps a kuid, a number and the first line of a multi line string out.
_MEMBER = re.compile(r"([ \t]*)([A-Za-z0-9_-]+)-([0-9]+)[ \t]+\"([^\"]+)\"[ \t]*")

#: a tag line with something after the name, which is how a name already in use
#: is recognised
_TAG_WITH_A_VALUE = re.compile(r"[ \t]*([A-Za-z0-9_-]+)[ \t]+\S.*")


@dataclass(frozen=True)
class Rewrite:
    """A stretch of the text to cut out, and what goes in its place."""

    #: the character the stretch starts at, and the one it stops before
    start: int
    end: int
    #: what replaces it, which never holds a line ending of its own
    text: str


@dataclass(frozen=True)
class Conversion:
    """One list that was folded up."""

    #: the tag it has become: category-era
    tag: str
    #: the tags that went into it, in the order the values are now in
    sources: tuple[str, ...]
    #: the values, without their quotes, in that same order
    values: tuple[str, ...]

    @property
    def value(self) -> str:
        """The one value the elements make between them."""
        return ";".join(self.values)

    def __str__(self) -> str:
        return f"{', '.join(self.sources)} became {self.tag} {self.value!r}"


@dataclass(frozen=True)
class Tweaks:
    """The text after the change, and how to get from the old one to it."""

    #: the whole text, with every conversion in it
    text: str
    #: the edits that turn the old text into the new one, in the order they
    #: appear in the text, and never overlapping
    rewrites: tuple[Rewrite, ...]
    #: what each of those edits did
    conversions: tuple[Conversion, ...]
    #: groups that looked like a list but were left alone, and why
    skipped: tuple[str, ...]

    def summary(self) -> str:
        """What happened, in the words the window shows afterwards."""
        parts: list[str] = []
        if self.conversions:
            listed = "\n".join(f"  {item}" for item in self.conversions)
            parts.append(f"{self.status}:\n\n{listed}")
        else:
            parts.append(
                "Nothing was converted.  Tags are folded up only when two or more "
                "of them with a number on the end stand on neighbouring lines and "
                "each holds a quoted value."
            )
        for note in self.skipped:
            parts.append(f"Left alone: {note}.")
        return "\n\n".join(parts)

    @property
    def status(self) -> str:
        """The same news in one line, for a status bar too narrow for the rest."""
        count = len(self.conversions)
        if not count:
            return "Nothing was converted"
        return f"Converted {count} obsolete {'list' if count == 1 else 'lists'}"


def convert_obsolete_lists(text: str) -> Tweaks:
    """Fold ``tag-0``, ``tag-1`` and the rest into one ``tag "a;b;c"``."""
    lines, eol = _split(text)
    runs = _runs_of_numbered_tags(lines)
    taken = _names_already_in_use(lines, runs)
    doubled = _names_made_twice(runs)

    conversions: list[Conversion] = []
    rewrites: list[Rewrite] = []
    skipped: list[str] = []
    for run in runs:
        if len(run.members) < 2:
            continue
        reason = _turned_down_because(run, taken, doubled)
        if reason:
            skipped.append(f"{_names(run)} {reason}")
            continue
        members = sorted(run.members, key=lambda member: (member.number, member.line))
        conversions.append(
            Conversion(
                tag=run.tag,
                sources=tuple(member.tag for member in members),
                values=tuple(member.value for member in members),
            )
        )
        # the stretch is the lines as they were written, even when the numbers
        # on them were not
        rewrites.append(
            Rewrite(
                start=_start_of(lines, eol, run.members[0].line),
                end=_end_of(lines, eol, run.members[-1].line),
                text=_merged(run, members),
            )
        )

    # a numbered tag the run broke off from, one element left stranded
    folded = {conversion.tag for conversion in conversions}
    for run in runs:
        if len(run.members) == 1 and run.tag in folded:
            stranded = run.members[0].tag
            skipped.append(f"{stranded} stands apart from the rest and stays as it is")

    rewrites.sort(key=lambda rewrite: rewrite.start)
    return Tweaks(
        text=_apply(text, rewrites),
        rewrites=tuple(rewrites),
        conversions=tuple(conversions),
        skipped=tuple(skipped),
    )


@dataclass(frozen=True)
class _Member:
    """One numbered tag: which line it is on and what it is called and holds."""

    line: int
    tag: str
    number: int
    value: str


@dataclass(frozen=True)
class _Run:
    """Neighbouring numbered tags under one name, and where they stand."""

    tag: str
    indent: str
    column: int
    members: tuple[_Member, ...]


def _split(text: str) -> tuple[list[str], str]:
    """The lines of the text and the line ending it uses.

    The same rule the codec uses when it reads the text form, so a file written
    with CRLF is folded up with CRLF and the editor's document, which holds
    ``\\n``, is folded up with that.
    """
    eol = "\r\n" if "\r\n" in text else ("\r" if "\r" in text else "\n")
    return text.split(eol), eol


def _runs_of_numbered_tags(lines: list[str]) -> list[_Run]:
    """The groups of neighbouring numbered tags, in the order they are written.

    A line that is part of a value running over several lines is not a tag line
    at all, which is what keeps the lines of a multi line license string out of
    the run.
    """
    runs: list[_Run] = []
    inside_a_value = False
    for number, line in enumerate(lines):
        if inside_a_value:
            inside_a_value = not line.endswith('"')
            continue
        found = _MEMBER.fullmatch(line)
        if not found:
            inside_a_value = _opens_a_running_value(line)
            continue
        indent, base, digits, value = found.groups()
        member = _Member(
            line=number,
            tag=f"{base}-{digits}",
            number=int(digits),
            value=value,
        )
        if _continues(runs[-1] if runs else None, base, indent, number):
            members = runs[-1].members + (member,)
            runs[-1] = _Run(runs[-1].tag, indent, runs[-1].column, members)
        else:
            # group 4 is what sits between the quotes, so the column the group
            # starts at is one past the quote the value is lined up on
            runs.append(_Run(base, indent, found.start(4) - 1, (member,)))
    return runs


def _continues(run: _Run | None, base: str, indent: str, line: int) -> bool:
    """Whether this tag belongs to the group before it: same name, same place.

    The line count has to be next door as well.  Two groups of the same name
    with anything between them are two separate lists, and folding the lines of
    one into the other would move text that was never meant to move.
    """
    return bool(
        run
        and run.tag == base
        and run.indent == indent
        and line == run.members[-1].line + 1
    )


def _names_made_twice(runs: list[_Run]) -> set[str]:
    """The names two or more groups would each make.

    One tag called ``category-era`` is what a list is; two of them in the same
    body is a file nobody can read, so neither group is touched.
    """
    names = [run.tag for run in runs if len(run.members) > 1]
    return {name for name in names if names.count(name) > 1}


def _opens_a_running_value(line: str) -> bool:
    """Whether this line starts a quoted value that carries on below it.

    The codec's own rule: a value that starts with a quote and is not closed by
    the end of the line runs over into the next one.
    """
    parts = line.strip().split(None, 1)
    rest = parts[1].strip() if len(parts) > 1 else ""
    return rest.startswith('"') and not (len(rest) > 1 and rest.endswith('"'))


def _turned_down_because(run: _Run, taken: set[str], doubled: set[str]) -> str:
    """Why this group is left as it is, in a clause, or nothing at all.

    Saying the reason is the point of the sentence: a group that was passed over
    for a good reason looks exactly like one that was missed, and the person
    looking at the file cannot tell the two apart.
    """
    if run.tag in taken:
        return f"would repeat {run.tag}, which the file already has"
    if run.tag in doubled:
        return f"would repeat {run.tag}, which another group would make"
    if any(";" in member.value for member in run.members):
        return "holds a ';' in a value, which would read as two"
    return ""


def _names_already_in_use(lines: list[str], runs: list[_Run]) -> set[str]:
    """The tags the folded up names must not collide with.

    A name is in use when some other line carries that name and a value.  What
    a run of numbered tags itself is called does not count, since those lines
    are the ones being replaced.
    """
    numbered = {member.tag for run in runs for member in run.members}
    taken: set[str] = set()
    inside_a_value = False
    for line in lines:
        if inside_a_value:
            inside_a_value = not line.endswith('"')
            continue
        inside_a_value = _opens_a_running_value(line)
        found = _TAG_WITH_A_VALUE.fullmatch(line)
        if found and found.group(1) not in numbered:
            taken.add(found.group(1))
    return taken


def _merged(run: _Run, members: list[_Member]) -> str:
    """The one line the members become, lined up where they were lined up."""
    prefix = run.indent + run.tag
    pad = max(run.column - len(prefix), 2)
    values = ";".join(member.value for member in members)
    return f"{prefix}{' ' * pad}\"{values}\""


def _names(run: _Run) -> str:
    return ", ".join(member.tag for member in run.members)


def _start_of(lines: list[str], eol: str, number: int) -> int:
    """The character a line starts at, counted the way the document counts."""
    return sum(len(line) + len(eol) for line in lines[:number])


def _end_of(lines: list[str], eol: str, number: int) -> int:
    """The character just after a line, before whatever ends it."""
    return _start_of(lines, eol, number) + len(lines[number])


def _apply(text: str, rewrites: list[Rewrite]) -> str:
    """Every rewrite at once, from the end backwards so the places stay put."""
    for rewrite in sorted(rewrites, key=lambda item: item.start, reverse=True):
        text = text[: rewrite.start] + rewrite.text + text[rewrite.end :]
    return text
