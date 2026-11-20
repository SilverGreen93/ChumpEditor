"""Two tidy-ups a person asks for, done to the text and nothing else.

The first is the numbered tags Trainz has moved on from.  Trainz used to write
a list as a run of tags with a number on the end - ``category-era-0``,
``category-era-1``, ``category-era-2`` - and reads the same list now as one tag
with the elements between semicolons: ``category-era "1920s;1930s;1940s"``.

The second is the language tags.  An asset used to repeat a tag once per
language it had text for - ``description``, ``description-de``,
``description-fr`` - and the translations are usually of no interest.  Every tag
whose name ends in a dash and two letters comes out with its value, whatever
that value is: one on the line, one running over several lines, or a whole
container.  The plain ``description`` stays.

Neither tidy-up ever decides on its own that a file needs fixing, and each
leaves a tag alone the moment it is not sure about it.

A numbered tag is changed only when

* it stands on its own line with a dash and a number on the end and holds a
  quoted value, so a kuid, a number or a value running over several lines is not
  touched - ``load0`` and ``camera0`` carry no dash, and mean something else
  entirely;
* the neighbours written under the same name can be read with it.  A run of them
  becomes one tag whose values sit between semicolons; one standing on its own
  keeps the value it has and only loses the number, because a list of one is
  still written as a single tag;
* none of the values holds a semicolon itself, which would read as two
  elements once they are joined up;
* the plain name is not already used by a tag with a value, and no group of the
  same tags has already taken that name, either of which would leave the file
  holding the same tag twice.

Anything that is looked at and turned down is said out loud in the summary
rather than passed over in silence.

The elements come out in the order the numbers say, not the order of the lines,
so ``era-10`` follows ``era-9`` rather than ``era-1``; the merged line keeps the
column the tags were written at; and everything else in the text - the order of
the other tags, the blank lines, the spacing - is left exactly as it was.

A language tag is one whose whole name ends in a dash and two letters, which is
how the assets write it even where they ignore the proper code: ``username-cn``
and ``username-jp`` go the same way as ``description-de``.  A tag that is only
spelled as if it were a language one is left alone, so ``contact-email`` stays -
an email is not written in the Ewe language.  Out goes the tag and its value and
nothing in between, which for a container means its ``{`` and ``}`` and
everything inside them, since that is the value.

Everything here is free of Qt and answers in character positions within the
text, so the rules can be read and tested without a window and the editor can
apply the changes as edits a person can undo in one go.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "Conversion",
    "Removal",
    "Rewrite",
    "Sweep",
    "Tweaks",
    "convert_obsolete_lists",
    "remove_language_tags",
]

#: a tag with a number on the end and a quoted value of its own after the
#: spaces.  The name is taken up to the last dash before the digits, so
#: category-era-0 is era 0 of category-era and not "category" of "era-0".  The
#: value has to be closed on the same line and hold something, which is what
#: keeps a kuid, a number and the first line of a multi line string out.
_MEMBER = re.compile(r"([ \t]*)([A-Za-z0-9_-]+)-([0-9]+)[ \t]+\"([^\"]+)\"[ \t]*")

#: a tag line with something after the name, which is how a name already in use
#: is recognised
_TAG_WITH_A_VALUE = re.compile(r"[ \t]*([A-Za-z0-9_-]+)[ \t]+\S.*")

#: a tag whose name ends in a dash and two letters, which is how an asset marks
#: out one language of a tag it has once of each.  Any two letters, not only the
#: proper codes, because the assets write -cn and -jp as often as they write -zh
#: and -ja.  The two letters have to end the name, with either the end of the
#: line or a space after them, which is what keeps contact-email in: an email is
#: not written in the Ewe language.
_LANGUAGE_TAG = re.compile(
    r"([ \t]*)([A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*)-([A-Za-z]{2})(?:[ \t]+.*)?$"
)

#: the first word of a line that is a tag line, used only to say which names the
#: file holds
_A_NAME = re.compile(r"[ \t]*([A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*)")


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
    """One tag, or run of numbered tags, that was changed."""

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
    #: numbered tags that were looked at and turned down, and why
    skipped: tuple[str, ...]

    def summary(self) -> str:
        """What happened, in the words the window shows afterwards."""
        parts: list[str] = []
        if self.conversions:
            listed = "\n".join(f"  {item}" for item in self.conversions)
            parts.append(f"{self.status}:\n\n{listed}")
        else:
            parts.append(
                "Nothing was converted.  A tag with a number on the end is only "
                "changed when it stands on a line of its own holding a quoted "
                "value, and the shorter name is not already used."
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
        return f"Converted {count} obsolete {'tag' if count == 1 else 'tags'}"


def convert_obsolete_lists(text: str) -> Tweaks:
    """Fold ``tag-0``, ``tag-1`` and the rest into one ``tag "a;b;c"``.

    A run of them makes one list; one standing on its own keeps the value it has
    and only loses the number on the end, because a list of one is still written
    as a single tag.
    """
    lines, eol = _split(text)
    runs = _runs_of_numbered_tags(lines)
    taken = _names_already_in_use(lines, runs)

    changes: list[tuple[Rewrite, Conversion]] = []
    notes: list[tuple[int, str]] = []
    # which group of tags has already had each shorter name given to it
    owners: dict[str, _Run] = {}

    # a run of two or more is a list beyond doubt, so it is served first and a
    # lone tag gives way to it; past that the order of the file decides, which
    # keeps the whole thing reproducible instead of a matter of chance
    for run in sorted(runs, key=lambda group: len(group.members), reverse=True):
        reason = _turned_down_because(run, taken, owners)
        if reason:
            notes.append((run.members[0].line, f"{_names(run)} {reason}"))
            continue
        owners[run.tag] = run
        members = sorted(run.members, key=lambda member: (member.number, member.line))
        # the stretch is the lines as they were written, even when the numbers
        # on them were not
        changes.append((
            Rewrite(
                start=_start_of(lines, eol, run.members[0].line),
                end=_end_of(lines, eol, run.members[-1].line),
                text=_merged(run, members),
            ),
            Conversion(
                tag=run.tag,
                sources=tuple(member.tag for member in members),
                values=tuple(member.value for member in members),
            ),
        ))

    changes.sort(key=lambda change: change[0].start)
    return Tweaks(
        text=_apply(text, [change[0] for change in changes]),
        rewrites=tuple(change[0] for change in changes),
        conversions=tuple(change[1] for change in changes),
        skipped=tuple(note for _line, note in sorted(notes)),
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


def _opens_a_running_value(line: str) -> bool:
    """Whether this line starts a quoted value that carries on below it.

    The codec's own rule: a value that starts with a quote and is not closed by
    the end of the line runs over into the next one.
    """
    parts = line.strip().split(None, 1)
    rest = parts[1].strip() if len(parts) > 1 else ""
    return rest.startswith('"') and not (len(rest) > 1 and rest.endswith('"'))


def _turned_down_because(run: _Run, taken: set[str], owners: dict[str, _Run]) -> str:
    """Why these tags are left as they are, in a clause, or nothing at all.

    Saying the reason is the point of the sentence: tags that were passed over
    for a good reason look exactly like tags that were missed, and the person
    reading the file afterwards cannot tell the two apart.
    """
    if run.tag in taken:
        return f"would repeat {run.tag}, which the file already has"
    if run.tag in owners:
        # the name has gone to a bigger run of the same tags, or to the ones
        # written above these; either way a second tag of that name would be a
        # file nobody can read
        return f"would repeat {run.tag}, which {_names(owners[run.tag])} became"
    if len(run.members) > 1 and any(";" in member.value for member in run.members):
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


# --------------------------------------------------------------------------
# language tags


@dataclass(frozen=True)
class Removal:
    """One language tag that came out, and the stretch of text it held."""

    #: the tag's own name: description-de
    tag: str
    #: the character the stretch starts at, and the one it stops before, with
    #: the line ending included so the file does not gain a blank line
    start: int
    end: int
    #: what the tag held, quotes and all, over as many lines as it ran over
    value: str
    #: whether a tag of the same name without the language on the end is left
    #: in the file behind this one
    stays: bool

    @property
    def base(self) -> str:
        """The name with the language taken off the end: description."""
        return self.tag[: self.tag.rindex("-")]

    def __str__(self) -> str:
        held = _brief(self.value)
        went = f"{self.tag} {held}" if held else self.tag
        left = f"{self.base} stays" if self.stays else f"no {self.base} in the file"
        return f"{went} went; {left}"


@dataclass(frozen=True)
class Sweep:
    """The text after the language tags, and how to get from the old one to it.

    Shaped the way ``Tweaks`` is - ``text``, ``rewrites``, ``status`` and
    ``summary`` - so whoever applies one can apply the other without asking.
    """

    #: the whole text, with every language tag out of it
    text: str
    #: the edits that turn the old text into the new one, in the order they
    #: appear in the text, and never overlapping
    rewrites: tuple[Rewrite, ...]
    #: the tags that came out, in the order they stood in the file
    removals: tuple[Removal, ...]
    #: language tags that were seen and left where they are, and why
    notes: tuple[str, ...]

    def summary(self) -> str:
        """What happened, in the words the window shows afterwards."""
        parts: list[str] = []
        if self.removals:
            listed = "\n".join(f"  {item}" for item in self.removals)
            parts.append(f"{self.status}:\n\n{listed}")
        else:
            parts.append(
                "Nothing was removed.  A language tag is a tag whose name ends "
                "in a dash and two letters, like description-de."
            )
        for note in self.notes:
            parts.append(f"Left alone: {note}.")
        return "\n\n".join(parts)

    @property
    def status(self) -> str:
        """The same news in one line, for a status bar too narrow for the rest."""
        count = len(self.removals)
        if not count:
            return "No language tags"
        return f"Removed {count} language {'tag' if count == 1 else 'tags'}"


@dataclass(frozen=True)
class _Cut:
    """A language tag found in the text, before it is known what stays."""

    tag: str
    start: int
    end: int
    value: str


def remove_language_tags(text: str) -> Sweep:
    """Take out every tag whose name ends in a dash and two letters.

    Of ``description``, ``description-de`` and ``description-pl`` the plain
    ``description`` is what is left standing.  A language tag with no plain tag
    beside it comes out as well, because the ask is about the language tags, and
    the summary says that nothing of that name is left behind.
    """
    lines, eol = _split(text)
    names = _names_in_the_text(lines)
    cuts: list[_Cut] = []
    notes: list[str] = []
    line, running = 0, False
    while line < len(lines):
        if running:
            # still inside somebody's multi line value, where a line that looks
            # like a tag is only a sentence
            running = not lines[line].endswith('"')
            line += 1
            continue
        found = _LANGUAGE_TAG.fullmatch(lines[line])
        if found is None:
            running = _opens_a_running_value(lines[line])
            line += 1
            continue

        tag = f"{found.group(2)}-{found.group(3)}"
        rest = lines[line][len(found.group(1)) + len(tag) :].strip()
        last, because = _the_tag_takes_up_to(lines, line, rest)
        if because:
            notes.append(f"{tag} {because}")
            running = _opens_a_running_value(lines[line])
            line += 1
            continue

        block = eol.join(lines[line : last + 1])
        cuts.append(
            _Cut(
                tag=tag,
                start=_start_of(lines, eol, line),
                # the line ending goes with the tag so it leaves no gap behind;
                # the last line of a file with no ending has none to take
                end=(
                    _start_of(lines, eol, last + 1)
                    if last + 1 < len(lines)
                    else _end_of(lines, eol, last)
                ),
                value=block[len(found.group(1)) + len(tag) :],
            )
        )
        # the whole tag goes, taking whatever it held with it, so the scan
        # carries on after the block rather than reading through it
        line, running = last + 1, False

    gone = {cut.tag for cut in cuts}
    removals: list[Removal] = []
    for cut in cuts:
        base = cut.tag[: cut.tag.rindex("-")]
        removals.append(
            Removal(
                tag=cut.tag,
                start=cut.start,
                end=cut.end,
                value=cut.value,
                # a plain tag of this name is only really left behind when no
                # other language tag of that name had already taken it
                stays=base in names and base not in gone,
            )
        )
    rewrites = tuple(Rewrite(start=r.start, end=r.end, text="") for r in removals)
    return Sweep(
        text=_apply(text, list(rewrites)),
        rewrites=rewrites,
        removals=tuple(removals),
        notes=tuple(notes),
    )


def _brief(value: str) -> str:
    """What a tag held, squeezed onto one line however many it ran over."""
    flat = " ".join(value.split())
    return flat if len(flat) <= 60 else f"{flat[:57]}..."


def _names_in_the_text(lines: list[str]) -> set[str]:
    """Every tag name in the text, so a tag left behind can be named.

    Only the lines the codec reads as tag lines count: a line inside a value
    running over several lines is somebody's prose about licensing, not a tag.
    """
    names: set[str] = set()
    running = False
    for line in lines:
        if running:
            running = not line.endswith('"')
            continue
        found = _A_NAME.match(line)
        if found:
            names.add(found.group(1))
        running = _opens_a_running_value(line)
    return names


def _the_tag_takes_up_to(lines: list[str], where: int, rest: str) -> tuple[int, str]:
    """The last line a tag and its value take up, or why it cannot be cut out.

    A value ends on its own line, or on the line the quote closing it ends, or -
    for a container - on the ``}`` that closes the one the tag opened, which the
    codec also reads as opening on the line below the name.  A value or a
    container left open has no such line, and a tag of that kind is left alone
    rather than cutting a hole in the rest of the file.
    """
    if rest.startswith('"') and not (len(rest) > 1 and rest.endswith('"')):
        closing = _the_value_closing_line(lines, where + 1)
        if closing is None:
            return where, "holds a quoted value that is never closed"
        return closing, ""

    brace = -1
    if rest.startswith("{") and not rest.endswith("}"):
        brace = where  # the brace sits on the name's own line
    elif not rest and _a_brace_is_next(lines, where + 1):
        brace = where + 1  # and the name's line holds nothing else
    if brace >= 0:
        closing = _the_container_ends_at(lines, brace + 1, 1)
        if closing is None:
            return where, "opens a container that is never closed"
        return closing, ""

    # a value closed where it opened, a number, a kuid, a word, or nothing at
    # all: the name's line and no more
    return where, ""


def _the_container_ends_at(lines: list[str], where: int, depth: int) -> int | None:
    """The line closing a container whose body starts at ``where``.

    ``depth`` counts the containers already open here, the one being cut out
    among them.  A nested container opens another and its ``}`` is not the one
    wanted, so the same braces the codec counts are counted here: the block that
    comes out is the block the editor would have read.
    """
    line, running = where, False
    while line < len(lines):
        if running:
            running = not lines[line].endswith('"')
            line += 1
            continue
        stripped = lines[line].strip()
        if stripped == "}":
            depth -= 1
            if not depth:
                return line
            line += 1
            continue
        rest = _the_rest_of(stripped)
        if rest == "{":
            depth += 1
            line += 1
        elif rest and _opens_a_running_value(lines[line]):
            running = True
            line += 1
        elif _a_brace_is_next(lines, line + 1):
            depth += 1
            line += 2  # a name and the brace below it are one container
        else:
            line += 1
    return None


def _the_value_closing_line(lines: list[str], where: int) -> int | None:
    """The line holding the quote that closes a value running over lines.

    The codec's own rule: the first line ending in a quote closes the value.
    """
    for line in range(where, len(lines)):
        if lines[line].endswith('"'):
            return line
    return None


def _a_brace_is_next(lines: list[str], where: int) -> bool:
    """Whether a container's opening brace is saved for this line."""
    return where < len(lines) and lines[where].strip() == "{"


def _the_rest_of(stripped: str) -> str:
    """The text after a tag name, the way the codec separates the two."""
    parts = stripped.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""
