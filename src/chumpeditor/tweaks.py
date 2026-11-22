"""Four tidy-ups a person asks for, done to the text and nothing else.

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

None of them ever decides on its own that a file needs fixing, and each leaves a
tag alone the moment it is not sure about it.

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

The third tidy-up moves an asset onto the newer way of naming its mesh.  Where
the older kind has one tag::

    asset-filename                          "MS_Shelter_4"

the newer kind has a container, so the tag goes and this comes in its place, the
name of the file to load carrying the ``.im`` the tag left off::

    mesh-table
    {
      default
      {
        mesh                                "MS_Shelter_4.im"
        auto-create                         1
      }
    }

A file that already has a mesh-table is left exactly as it is and the person is
warned, since a second one would leave Trainz choosing between two meshes.

The fourth tidy-up puts the tags in the order a chump file is usually written
in::

    kuid and username                 first, whatever was written above them
    the tags that hold one value      next, in the order they were found
    the containers                    after them, in the order they were found
    kuid-table, obsolete-table        last of all, when the file has them

The same order is put right inside the containers, by a simpler rule: the tags
holding a value come before the containers written beside them, each keeping the
order they were found in, and that at every depth of the file.  Down there the
few names pinned to the top and the bottom of an asset are not pinned, since
what a tag means at the top of a file says nothing about what it means three
containers down.

Nothing is ever moved out of the container it is written in.  The blank lines
under a tag travel with it so the gaps keep their shape, and the blank lines at
the end of the file stay at the end.  On top of that, every container is set off
from the tags around it with a blank line - one under its closing brace wherever
a tag follows it, and one above the line naming it wherever a tag stands there -
however deep inside the file the container is, since that gap is what shows
where a container ends and a tag begins.  None goes in beside a brace: above
another closing brace would drive a wedge between a tag and the container it is
written inside, and below an opening one would part a container from the brace it
opens; and none at the start or the end of the file, where there is nothing to
separate.  A tag whose value or container is never closed, and a line that is not
a tag at all, mean the tags cannot be told apart from each other, and then
nothing at all is moved and the person is warned.

Everything here is free of Qt and answers in character positions within the
text, so the rules can be read and tested without a window and the editor can
apply the changes as edits a person can undo in one go.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chump import VALUE_COLUMN

__all__ = [
    "Conversion",
    "Gap",
    "MeshTable",
    "MeshTables",
    "Move",
    "Order",
    "Removal",
    "Rewrite",
    "Sweep",
    "Tweaks",
    "convert_asset_filename_to_mesh_table",
    "convert_obsolete_lists",
    "remove_language_tags",
    "reorder_tags",
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
    #: what replaces it, which is one line for a tag that stays a tag and
    #: several for a tag that becomes a block of them
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

    @property
    def warning(self) -> bool:
        """Whether the window shows the answer as a warning rather than as news.

        Anything the tweak looked at and turned down is worth the louder box: a
        tag left the way it was may be one the person wants to fix by hand.
        """
        return bool(self.skipped)


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

    @property
    def warning(self) -> bool:
        """Whether the window shows the answer as a warning rather than as news."""
        return bool(self.notes)


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

    brace = _the_brace_the_tag_opens(rest, lines, where)
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


@dataclass(frozen=True)
class MeshTable:
    """One ``mesh-table`` container the tweak put into the text.

    ``source`` is the name as the asset-filename tag held it and ``mesh`` is the
    file Trainz will load, ``.im`` on the end.  ``start`` and ``end`` are where
    the tag it replaces stood, end before the line break after it.
    """

    #: the container's own level, which is always the default one
    name: str
    #: what the asset-filename tag said
    source: str
    #: the mesh file the container loads
    mesh: str
    start: int
    end: int
    #: the container that went in, exactly as the text now holds it
    text: str

    def __str__(self) -> str:
        return f"asset-filename {self.source!r} became mesh-table {self.mesh!r}"


@dataclass(frozen=True)
class MeshTables:
    """What converting the asset-filename tags did, and the text after it.

    Shaped the way ``Tweaks`` and ``Sweep`` are - ``text``, ``rewrites``,
    ``status`` and ``summary`` - so whoever applies one can apply the other
    without asking.  ``blocked`` is why nothing was touched when the file already
    has a mesh-table, and is empty when the tweak was free to work.
    """

    #: the whole text, with every container in it
    text: str
    #: the edits that turn the old text into the new one, in the order they
    #: appear in the text, and never overlapping
    rewrites: tuple[Rewrite, ...] = ()
    #: the containers that went in, in the order they stand in the file
    mesh_tables: tuple[MeshTable, ...] = ()
    #: asset-filename tags that were seen and left where they are, and why
    notes: tuple[str, ...] = ()
    #: why the file was left alone altogether, or '' when it was not
    blocked: str = ""

    @property
    def status(self) -> str:
        """The same news in one line, for a status bar too narrow for the rest."""
        if self.blocked:
            return "Already has a mesh-table"
        if self.mesh_tables:
            return f"Added {_the_mesh_tables(len(self.mesh_tables))}"
        return "Nothing was converted"

    @property
    def warning(self) -> bool:
        """Whether the window shows the answer as a warning rather than as news.

        A file that already loads its meshes is the loud case: the person asked
        for a change that could not be made safely.
        """
        return bool(self.blocked)

    def summary(self) -> str:
        """What happened, in the words the window shows afterwards."""
        if self.blocked:
            return f"{self.status}: {self.blocked}"
        parts: list[str] = []
        if self.mesh_tables:
            listed = "\n".join(f"  {item}" for item in self.mesh_tables)
            parts.append(f"{self.status}:\n\n{listed}")
        else:
            parts.append(
                "Nothing was converted.  An asset-filename tag is only changed "
                "when it stands on a line of its own holding a mesh name in "
                "quotes, and only where the file holds no mesh-table already."
            )
        for note in self.notes:
            parts.append(f"Left alone: {note}.")
        return "\n\n".join(parts)


def _the_mesh_tables(how_many: int) -> str:
    """The containers the tweak added, said the way the status line says them."""
    return f"{how_many} mesh-table{'' if how_many == 1 else 's'}"


# --------------------------------------------------------------------------- #
# Convert asset-filename into mesh-table
# --------------------------------------------------------------------------- #


def convert_asset_filename_to_mesh_table(text: str) -> MeshTables:
    """Replace every ``asset-filename`` tag with a ``mesh-table`` container.

    The container goes where the tag stood, at the same indent, and holds the
    name from the tag with ``.im`` on the end as the default mesh.  A file that
    already has a mesh-table is not touched at all and the person is told why,
    because a second container would leave Trainz picking between two meshes; a
    tag that does not name a file simply gets a note and stays as it is.
    """
    lines, eol = _split(text)
    tags = _the_lines_holding(lines, "asset-filename")
    # a file with no tag to convert has nothing to be done to it, mesh-table or
    # not, so the one worth complaining about is the file that wanted converting
    already = _a_mesh_table_is_already_there(lines) if tags else ""
    if already:
        # the file already says which mesh to load; a second container would
        # only give Trainz two answers to choose between
        return MeshTables(text=text, blocked=already)

    rewrites: list[Rewrite] = []
    tables: list[MeshTable] = []
    notes: list[str] = []
    for at in tags:
        rest = _the_rest_of(lines[at].strip())
        fault = _the_mesh_name_is_missing(rest, lines, at)
        if fault:
            notes.append(f"the asset-filename on line {at + 1} {fault}")
            continue
        given = rest[1:-1].strip()
        mesh = _with_an_im_on_the_end(given)
        start, end = _start_of(lines, eol, at), _end_of(lines, eol, at)
        block = _the_mesh_table(_the_indent(lines[at]), mesh, eol)
        # the tag's own line is what is replaced, so the break after it stays
        rewrites.append(Rewrite(start=start, end=end, text=block))
        tables.append(
            MeshTable(name="default", source=given, mesh=mesh, start=start, end=end, text=block)
        )

    return MeshTables(
        text=_apply(text, rewrites),
        rewrites=tuple(rewrites),
        mesh_tables=tuple(tables),
        notes=tuple(notes),
    )


def _a_mesh_table_is_already_there(lines: list[str]) -> str:
    """Whether the file already loads its meshes, and how - '' when it does not.

    One mesh-table anywhere is enough to stop, since a second would leave two
    containers answering the same question.  Whether a default mesh was found
    inside decides the wording, because a mesh-table holding one is the case the
    person asked to be told about.
    """
    tables = _the_lines_holding(lines, "mesh-table")
    if not tables:
        return ""
    for at in tables:
        # the container's own body, which is where a default would be found
        last, _ = _the_tag_takes_up_to(lines, at, _the_rest_of(lines[at].strip()))
        if _the_lines_holding(lines[at + 1 : last + 1], "default"):
            return "a mesh-table with a default mesh is in the file"
    return "a mesh-table is in the file"


def _the_mesh_name_is_missing(rest: str, lines: list[str], at: int) -> str:
    """Why a tag line does not name a mesh file, or '' when it names one.

    A name has to be one stretch of text in quotes on the tag's own line.  A
    container, an empty value, a number or a kuid, and a value running over
    several lines are all shapes an asset-filename tag has been seen in, and none
    of them says which mesh to load.
    """
    if rest == "{" or (not rest and _a_brace_is_next(lines, at + 1)):
        return "is a container rather than a name"
    if not rest:
        return "has no value"
    if not rest.startswith('"'):
        return f"holds {rest!r} rather than a name in quotes"
    if not (len(rest) > 1 and rest.endswith('"')):
        return "has a value running over several lines"
    if not rest[1:-1].strip():
        return "has empty quotes where the mesh name should be"
    return ""


def _the_lines_holding(lines: list[str], name: str) -> list[int]:
    """The lines where a tag of this name starts, in the order they appear.

    Only the lines the codec reads as tag lines count: a line inside a value
    running over several lines is somebody's prose, not a tag.
    """
    found: list[int] = []
    running = False
    for at, line in enumerate(lines):
        if running:
            running = not line.endswith('"')
            continue
        tag = _A_NAME.match(line)
        if tag and tag.group(1).lower() == name:
            found.append(at)
        running = _opens_a_running_value(line)
    return found


def _with_an_im_on_the_end(name: str) -> str:
    """The mesh name with its ``.im`` on the end, unless it already has one."""
    return name if name.lower().endswith(".im") else f"{name}.im"


def _the_mesh_table(indent: str, mesh: str, eol: str) -> str:
    """The container the newer kind of asset writes in place of the tag.

    Written the way the codec writes a container: the name alone on its line, the
    ``{`` on the line below, two spaces deeper at each level, and the values
    starting on the same column they do everywhere else in the file.
    """
    inner, outer = indent + "  ", indent + "    "
    return eol.join(
        [
            indent + "mesh-table",
            indent + "{",
            inner + "default",
            inner + "{",
            outer + "mesh" + " " * _the_gap(outer, "mesh") + f'"{mesh}"',
            outer + "auto-create" + " " * _the_gap(outer, "auto-create") + "1",
            inner + "}",
            indent + "}",
        ]
    )


def _the_gap(indent: str, name: str) -> int:
    """The spaces that put a value on VALUE_COLUMN, two at the closest."""
    return max(VALUE_COLUMN - len(indent) - len(name), 2)


def _the_indent(line: str) -> str:
    """Whatever a line starts with before its tag name."""
    return line[: len(line) - len(line.lstrip())]


# --------------------------------------------------------------------------- #
# Reorder the top level tags
# --------------------------------------------------------------------------- #

#: the tags that always come first, in this order: the kuid is how Trainz knows
#: which asset the file is, and the name under it is what the person reads
_FIRST_TAGS = ("kuid", "username")

#: the containers that always come after every other container, in this order,
#: because they are the ones Trainz fills in for itself
_LAST_CONTAINERS = ("kuid-table", "obsolete-table")


@dataclass(frozen=True)
class Move:
    """One top level tag that ended up somewhere other than where it started."""

    #: the tag's own name, spelled as the file spells it
    tag: str
    #: the line the tag stood on, and the line it stands on now, both counted
    #: from 1 the way the codec counts them in what it says about a file
    from_line: int
    to_line: int

    def __str__(self) -> str:
        return f"{self.tag} moved from line {self.from_line} to line {self.to_line}"


@dataclass(frozen=True)
class Gap:
    """One container that had no blank line beside it, and the line it got one.

    ``line`` is the container's own line - its closing brace when the blank line
    went under the container and its name when the blank line went above it -
    counted in the text as it stands afterwards, which is the text the person is
    looking at when the window says this.
    """

    #: the tag whose container it is, spelled as the file spells it
    tag: str
    #: the line the closing brace, or the name, stands on, counted from 1
    line: int
    #: whether the blank line went above the container rather than under it
    above: bool = False

    def __str__(self) -> str:
        side = "above" if self.above else "under"
        return f"a blank line went {side} the {self.tag} on line {self.line}"


@dataclass(frozen=True)
class Order:
    """What reordering did, and the text after it.

    Shaped the way ``Tweaks``, ``Sweep`` and ``MeshTables`` are - ``text``,
    ``rewrites``, ``status`` and ``summary`` - so whoever applies one can apply
    this one without asking.  ``blocked`` is why the tags could not be moved at
    all, and is empty when they could be.
    """

    #: the whole text, with the tags in their new places at every depth and every
    #: container set off from the tags around it
    text: str
    #: the edits that did it: one for each stretch of tags that moved, in a
    #: container as well as at the top, and one for each blank line that came in
    #: where nothing moved; empty when nothing needed doing
    rewrites: tuple[Rewrite, ...] = ()
    #: the tags that changed place, here and inside every container, in the order
    #: they stand in the text now
    moves: tuple[Move, ...] = ()
    #: the containers that got a blank line beside them, in the order the lines
    #: stand in the text now
    gaps: tuple[Gap, ...] = ()
    #: the lines a blank line was taken off, because a blank line parts a
    #: container from what stands beside it and nothing else, counted in the text
    #: as it stands afterwards
    shut: tuple[int, ...] = ()
    #: why the file was left alone altogether, or '' when it was not
    blocked: str = ""

    @property
    def status(self) -> str:
        """The same news in one line, for a status bar too narrow for the rest."""
        if self.blocked:
            return "The tags cannot be reordered"
        said = ""
        if self.moves:
            count = len(self.moves)
            said = f"Reordered {count} {'tag' if count == 1 else 'tags'}"
        if self.gaps:
            count = len(self.gaps)
            lines = f"{count} blank {'line' if count == 1 else 'lines'}"
            said = f"Added {lines}" if not said else f"{said}, added {lines}"
        if self.shut:
            count = len(self.shut)
            lines = f"{count} blank {'line' if count == 1 else 'lines'}"
            said = f"Removed {lines}" if not said else f"{said}, removed {lines}"
        return said or "Nothing was reordered"

    @property
    def warning(self) -> bool:
        """Whether the window shows the answer as a warning rather than as news.

        A file whose tags cannot be told apart is the loud case: the person asked
        for a change that could not be made without moving something that was not
        asked for.
        """
        return bool(self.blocked)

    def summary(self) -> str:
        """What happened, in the words the window shows afterwards."""
        if self.blocked:
            return f"{self.status}: {self.blocked}"
        if not self.moves and not self.gaps and not self.shut:
            return (
                "Nothing was reordered.  kuid and username come first, then the "
                "tags that hold one value, then the containers, and kuid-table "
                "and obsolete-table after all of them; inside every container "
                "the tags that hold a value come before the containers written "
                "in it, and every container is set off from the tags around it."
            )
        told = [str(item) for item in (*self.moves, *self.gaps)]
        told += [
            f"a blank line came out under line {number}" for number in self.shut
        ]
        listed = "\n".join(f"  {item}" for item in told)
        return f"{self.status}:\n\n{listed}"


def reorder_tags(text: str) -> Order:
    """Put the tags in the order a chump file is written in, at every depth.

    At the top of the file ``kuid`` and ``username`` go first, then the tags that
    hold one value in the order they were found, then the containers in the order
    they were found, and ``kuid-table`` and ``obsolete-table`` after the rest of
    the containers.  Inside a container the rule is simpler: the tags holding a
    value come before the containers written beside them, each group keeping the
    order the file has them in, and no name is special that far down.  A tag is
    never moved out of the container it is written in, and a container travels
    whole with whatever stands inside it.

    On top of the order, a blank line parts a container from the line written
    beside it and nothing else, however deep inside the file it is: one under a
    closing brace and one above the line naming a container, each only where a
    line that is not a brace stands there, so a container and its own brace are
    never parted and two tags holding one value are never split.  What that asks
    for comes in where it is missing, which is ``_the_blank_lines_to_open``, and
    what it does not ask for comes out, which is ``_the_blank_lines_to_shut``: a
    blank line between two tags, a second blank line where one gap says the same
    thing once, and a blank line under an opening brace or above a closing one.
    The blank lines above the first tag of the file and the ones making up its
    ending are nobody's gap and are left alone.  Both are looked for in the text
    as it will stand once the tags have moved, since a container that moved has
    something else beside it.

    Only the stretch between the first tag out of place and the last one is
    rewritten, in every container that has tags out of place as well as at the
    top, plus one short edit for each blank line that has to come in or go where
    nothing moved, so the change stays small enough to follow afterwards.  The lot
    of them go in as one edit that one press of Undo takes back.
    """
    lines, eol = _split(text)
    # the blank lines at the end of the text are the file's ending rather than
    # somebody's gap, so they are out of reach of the walk
    keep = len(lines) - _the_blank_lines_at_the_end(lines)
    top, because = _the_region(lines, 0, keep, _AT_THE_TOP)
    if because or top is None:
        return Order(text=text, blocked=because)

    # the lines of the file as they stand once every tag has been put in its
    # place, at every depth, with the ending of the file kept exactly as it was
    settled = _the_lines_as_they_stand(top) + list(range(keep, len(lines)))
    moved = [lines[number] for number in settled]

    # the blank lines standing where no blank line belongs once the tags have
    # moved, and the lines of the text with those blank lines off them
    shut = set(_the_blank_lines_to_shut(moved))
    standing: list[str] = []
    back: list[int] = []  # which line of the moved text each one of them was
    for at, line in enumerate(moved):
        if at not in shut:
            standing.append(line)
            back.append(at)

    # the containers with no blank line beside them, told as the line the blank
    # line goes under in the text the moves have made
    want = _the_blank_lines_to_open(standing)
    opening = {one.after for one in want}

    # every line once the blank lines that came out are gone and the ones that
    # have to come in are in, so the text the rewrites write out can be cut
    # straight out of it
    finished: list[str] = []
    for at, line in enumerate(standing):
        finished.append(line)
        if at in opening:
            finished.append("")

    # which line of the finished text each line that stands still ends up on, and
    # where each line of the moved text holds its place there; a blank line that
    # came out has no line of its own to point at, and is noted as the line it
    # stood on in the text as it stands afterwards
    stand: dict[int, int] = {}
    place: dict[int, int] = {}
    gone: list[int] = []
    where = 0
    at = 0
    for was, number in enumerate(settled):
        if was in shut:
            gone.append(where)  # the line it stood under, counted the way lines are
            continue
        stand[number] = where
        place[was] = where
        where += 1
        if at in opening:
            where += 1  # the blank line that came in under this one pushes it down
        at += 1

    # the lines of the moved text a blank line comes in under, which is where the
    # rewrites look for them
    opened = {back[one.after] for one in want}
    stretches = _the_stretches_written_out(top)
    rewrites = [
        _one_stretch_written_out(lines, eol, finished, place, opened, stretch)
        for stretch in stretches
    ]
    for one in want:
        number = settled[back[one.after]]
        if not _a_stretch_holds(stretches, number):
            # the blank line is put in after the line, leaving the line itself
            # and everything on either side of it exactly as it was
            at = _end_of(lines, eol, number)
            rewrites.append(Rewrite(start=at, end=at, text=eol))
    for was in sorted(shut):
        number = settled[was]
        if not _a_stretch_holds(stretches, number):
            # the blank line goes with the line ending it stands on, which leaves
            # every line with something written on it exactly as it was
            at = _start_of(lines, eol, number)
            rewrites.append(Rewrite(start=at, end=at + len(eol), text=""))

    return Order(
        text=_apply(text, rewrites),
        rewrites=tuple(rewrites),
        moves=_the_tags_that_moved(top, stand),
        gaps=tuple(
            Gap(
                tag=one.tag,
                line=stand[settled[back[one.about]]] + 1,
                above=one.above,
            )
            for one in want
        ),
        shut=tuple(gone),
    )


_AT_THE_TOP = "at the top of the file"
_INSIDE_A_CONTAINER = "inside a container"


@dataclass(frozen=True)
class _Block:
    """One tag written in one region, the lines it takes up, and its braces.

    ``last`` is the last of the blank lines written under a tag, which travel with
    it so the gaps keep their shape; under a container with nothing blank below it
    that is the ``}`` closing the container.  ``brace`` is the line holding the
    ``{`` of a container, or -1 when the tag holds a value, and ``closes`` is the
    line holding the ``}`` that closes that container again.  No two blocks of one
    region share a ``first``, which is what tells apart two tags written exactly
    alike.
    """

    tag: str
    container: bool
    first: int
    last: int
    brace: int = -1
    closes: int = -1


class _Region:
    """The tags written between two lines, and the order they should stand in.

    A region is the top of the file, or the lines between one pair of braces:
    every container holds a region of its own, read the same way, which is how
    the order comes out right at every depth rather than only at the top.  The
    blocks are held twice over, as they are written and as they should stand, and
    the two are no more than a shuffle of each other.  ``edges`` holds the first
    and last places they differ, or nothing when the region already stands in
    order, and ``inside`` holds the region of every container in this one, found
    by the line the container is named on.
    """

    def __init__(
        self,
        start: int,
        stop: int,
        blocks: list[_Block],
        wanted: list[_Block],
        edges: tuple[int, int] | None,
        inside: dict[int, "_Region"],
    ) -> None:
        self.start = start
        self.stop = stop
        self.blocks = blocks
        self.wanted = wanted
        self.edges = edges
        self.inside = inside


def _the_region(
    lines: list[str], start: int, stop: int, rule: str
) -> tuple[_Region | None, str]:
    """The tags written between two lines, read to be put in order, or why not.

    ``start`` is where the tags may stand and ``stop`` is the line closing the
    region they are written in: the ``}`` of a container, or the end of the file
    for the tags at the top of it.  Neither line is one of the tags.  Every
    container found holds a region of its own, read the same way, so a file is
    only left alone when a tag cannot be told apart at any depth.  ``rule`` says
    which order the region follows: ``_AT_THE_TOP``, where a few names are pinned
    to the top and the bottom, or ``_INSIDE_A_CONTAINER``, where the tags holding
    a value come before the containers written beside them.
    """
    blocks, because = _the_blocks_between(lines, start, stop)
    if because:
        return None, because

    inside: dict[int, _Region] = {}
    for block in blocks:
        if not block.container:
            continue
        child, because = _the_region(
            lines, block.brace + 1, block.closes, _INSIDE_A_CONTAINER
        )
        if because:
            return None, f"the {block.tag} on line {block.first + 1} {because}"
        inside[block.first] = child

    order = (
        _the_order_at_the_top_of_the_file
        if rule == _AT_THE_TOP
        else _the_order_inside_a_container
    )
    goal = order(blocks)
    return (
        _Region(start, stop, blocks, goal, _the_part_that_moves(blocks, goal), inside),
        "",
    )


def _the_blocks_between(
    lines: list[str], start: int, stop: int
) -> tuple[list[_Block], str]:
    """The tags written between two lines, in order, or why they can't be told.

    The walk goes from a tag to the line its block ends on and starts again below
    it, which is how the codec reads a file as well, so a tag inside a container
    is never mistaken for one at the top and the lines of a value running over
    several lines are never mistaken for tags.  Blank lines below a tag belong to
    that tag and travel with it, while the blank lines above the first tag of a
    region stay where they are.  A value or a container that is not closed before
    the region closes, and a line that is not a tag at all, mean there is no safe
    line to cut on: the whole file is left alone and told about.
    """
    blocks: list[_Block] = []
    at = start
    while at < stop:
        if not lines[at].strip():
            at += 1  # the gaps above the first tag stay where they are
            continue
        found = _A_NAME.match(lines[at])
        if found is None:
            return [], f"line {at + 1} holds {lines[at].strip()!r}, which is not a tag"
        name = found.group(1)
        rest = _the_rest_of(lines[at].strip())
        last, because = _the_tag_takes_up_to(lines, at, rest)
        if because:
            return [], f"the {name} on line {at + 1} {because}"
        if last >= stop:
            return [], f"the {name} on line {at + 1} is not closed in its container"
        brace = _the_brace_the_tag_opens(rest, lines, at)
        end = min(last + _the_blank_lines_below(lines, last + 1, stop), stop - 1)
        blocks.append(
            _Block(
                tag=name,
                container=brace >= 0,
                first=at,
                last=end,
                brace=brace,
                closes=last if brace >= 0 else -1,
            )
        )
        at = end + 1
    return blocks, ""


def _the_blank_lines_at_the_end(lines: list[str]) -> int:
    """How many lines at the end of the text hold nothing.

    A text ending in a line ending has one more line in it than it has endings,
    and that last empty line is the ending itself, not a gap to be shuffled.
    """
    count = 0
    while count < len(lines) and not lines[len(lines) - 1 - count].strip():
        count += 1
    return count


def _the_blank_lines_below(lines: list[str], where: int, keep: int) -> int:
    """How many blank lines follow this one, short of the end of the text."""
    count = 0
    while where + count < keep and not lines[where + count].strip():
        count += 1
    return count


def _the_brace_the_tag_opens(rest: str, lines: list[str], at: int) -> int:
    """The line holding the ``{`` a tag opens, or nothing when it opens none.

    The brace either sits after the name on the name's own line or waits on the
    line below, which are the two ways the codec reads a container; and they are
    the two ways ``_the_tag_takes_up_to`` knows where the block ends, so which
    tags are containers and how far they reach are decided together.  A brace
    closed on the very line it opened on is a value, not a container, which is
    how a kuid-table written on one line is read.
    """
    if rest.startswith("{") and not rest.endswith("}"):
        return at  # the brace sits on the name's own line
    if not rest and _a_brace_is_next(lines, at + 1):
        return at + 1  # and the name's line holds nothing else
    return -1


def _the_order_at_the_top_of_the_file(blocks: list[_Block]) -> list[_Block]:
    """The top level tags in the order the file should hold them.

    Within each of the four groups the tags keep the order the file has them in,
    which is what makes pressing the tweak a second time do nothing at all.
    """
    left = list(blocks)
    top = _the_first_called(left, _FIRST_TAGS)
    bottom = _the_first_called(left, _LAST_CONTAINERS)
    plain = [block for block in left if not block.container]
    deep = [block for block in left if block.container]
    return top + plain + deep + bottom


def _the_order_inside_a_container(blocks: list[_Block]) -> list[_Block]:
    """The tags of one container in the order they should stand.

    The tags holding a value come first and the containers written inside them
    come after, each keeping the order the file has them in.  No name is special
    down here: a ``kuid`` written inside a sub-container stays where the file put
    it, since which tag means what at the top of an asset says nothing about what
    it means three containers down.
    """
    plain = [block for block in blocks if not block.container]
    deep = [block for block in blocks if block.container]
    return plain + deep


def _the_first_called(left: list[_Block], names: tuple[str, ...]) -> list[_Block]:
    """The first tag with each of these names, in that order, out of the list.

    Taking them out of ``left`` is what keeps a kuid-table from being counted
    twice, once as an ordinary container and once again as the last one.
    """
    chosen: list[_Block] = []
    for name in names:
        for block in left:
            if block.tag.lower() == name:
                chosen.append(block)
                left.remove(block)
                break
    return chosen


def _the_part_that_moves(
    blocks: list[_Block], wanted: list[_Block]
) -> tuple[int, int] | None:
    """The first and last places the tags are not already in, or nothing at all.

    Above the first one and below the last one the file is already in order, so
    those tags and the lines between them are not touched and the person sees a
    change no bigger than it has to be.
    """
    out_of_place = [
        at for at, (was, will_be) in enumerate(zip(blocks, wanted))
        if was is not will_be
    ]
    if not out_of_place:
        return None
    return out_of_place[0], out_of_place[-1]


def _the_lines_as_they_stand(region: _Region) -> list[int]:
    """The lines of a region, as the numbers of the lines they stand on now.

    Every line of the region comes back exactly once, so the caller can cut the
    text that will stand in its place straight out of the lines the file holds.
    The blank lines above the first tag stay where they are and the blank lines
    under a tag are already part of that tag; a container is written out as its
    name and opening brace, then what stands inside it in its own new order, then
    the closing brace and whatever blank lines follow it.
    """
    if not region.blocks:
        return list(range(region.start, region.stop))

    settled = list(range(region.start, region.blocks[0].first))
    for block in region.wanted:
        inside = region.inside.get(block.first)
        if inside is None:
            settled.extend(range(block.first, block.last + 1))
            continue
        settled.extend(range(block.first, block.brace + 1))
        settled.extend(_the_lines_as_they_stand(inside))
        settled.extend(range(block.closes, block.last + 1))
    settled.extend(range(region.blocks[-1].last + 1, region.stop))
    return settled


def _the_stretches_written_out(region: _Region) -> list[tuple[int, int]]:
    """Every stretch of lines a rewrite writes out, at this depth and below.

    One stretch covers the tags of a region that change place, from the first of
    them to the last; the tags above and below it already stand in order and are
    left exactly as they are.  A container that stands still but has its tags
    shuffled inside it holds a stretch of its own, kept within the lines of that
    container, while a container that moves itself carries its inside along in the
    stretch above rather than getting a stretch of its own.

    A stretch stands on the same lines before and after the shuffle, since it
    holds the same lines either way and nothing outside it moves; that is what
    lets the caller look up what a line of it comes to in either text.
    """
    found: list[tuple[int, int]] = []
    first = last = -1  # nothing moves here when the region already stands in order
    if region.edges is not None:
        first, last = region.edges
        found.append((region.blocks[first].first, region.blocks[last].last))
    for at, block in enumerate(region.blocks):
        if first <= at <= last:
            continue  # the stretch above covers whatever is inside this one
        inside = region.inside.get(block.first)
        if inside is not None:
            found.extend(_the_stretches_written_out(inside))
    return found


def _one_stretch_written_out(
    lines: list[str],
    eol: str,
    finished: list[str],
    place: dict[int, int],
    opened: set[int],
    stretch: tuple[int, int],
) -> Rewrite:
    """One rewrite, writing a whole stretch of lines out as they should stand.

    The stretch stands on the same lines in the text as it is and the text as it
    will be, so the lines it holds are read out of ``place``, the line each line of
    the stretch holds in the finished text: the blank lines that came in above it
    have pushed it down there already, and the blank lines that came out are not in
    it at all.  However many lines the stretch ends up with, the line ending below
    the last of them is left in the file, which is what joins the stretch to
    whatever follows it.  A blank line wanted under a line the stretch holds goes
    into the same rewrite: a rewrite of its own cut at the end of the stretch
    would work against it once the rewrites are carried out from the end of the
    file backwards.
    """
    low, high = stretch
    above = place[low]
    last = high
    while last not in place:
        last -= 1  # the blank lines at the end of the stretch came out
    below = place[last] + 1
    if last in opened:
        below += 1
    return Rewrite(
        start=_start_of(lines, eol, low),
        # the line ending after the last line is left outside the stretch, so the
        # file keeps the ending it had
        end=_end_of(lines, eol, high),
        text=eol.join(finished[above:below]),
    )


def _a_stretch_holds(stretches: list[tuple[int, int]], line: int) -> bool:
    """Whether the blank line under this line comes inside a stretch anyway."""
    return any(low <= line <= high for low, high in stretches)


def _the_tags_that_moved(
    region: _Region, stand: dict[int, int]
) -> tuple[Move, ...]:
    """Which tags changed place, here and inside every container, in their new order.

    The line a tag lands on is looked up rather than counted out of the blocks in
    front of it, because the blank lines opened under the containers change what
    those blocks add up to.  A container that moves carries whatever is written
    inside it along, so those subtags are not named one by one; a container that
    stands still but has its subtags shuffled does name them, since the lines
    inside it really are written out again.
    """
    found: list[Move] = []
    first = last = -1  # nothing moves here when the region already stands in order
    if region.edges is not None:
        first, last = region.edges
        for offset, block in enumerate(region.wanted[first : last + 1]):
            if block is not region.blocks[first + offset]:
                found.append(
                    Move(
                        tag=block.tag,
                        from_line=block.first + 1,
                        to_line=stand[block.first] + 1,
                    )
                )
    for at, block in enumerate(region.blocks):
        if first <= at <= last:
            continue  # this container moves, so its inside moves along with it
        inside = region.inside.get(block.first)
        if inside is not None:
            found.extend(_the_tags_that_moved(inside, stand))
    return tuple(sorted(found, key=lambda change: change.to_line))


@dataclass(frozen=True)
class _Tag:
    """One tag read out of a stretch of lines, with the lines it takes up.

    ``brace`` is the line holding the ``{`` of a container, or -1 when the tag
    holds a value: it is what tells the walk where to look for the subtags,
    between the braces rather than through them.
    """

    tag: str
    first: int
    last: int
    brace: int


@dataclass(frozen=True)
class _Opening:
    """One blank line that has to come in, and the container that wants it.

    ``after`` is the line the blank line goes under in the text as it stands
    before any of them come in, which is where the edit is cut.  ``about`` is the
    line the container is named on - its closing brace when the blank line goes
    under it and its name when the blank line goes above it - so what is said
    afterwards quotes a line the person can find in the text they are looking at.
    """

    after: int
    about: int
    tag: str
    above: bool


def _the_blank_lines_to_open(lines: list[str]) -> tuple[_Opening, ...]:
    """Where a blank line has to come in, and which container asked for it.

    A container is set off from the tags around it on both sides: a blank line
    goes under its closing brace, wherever a tag follows that, and above the
    line naming it, wherever a tag stands on that.  Neither goes in next to a
    brace - nothing above another closing brace, which would part a tag from the
    container it is written inside, and nothing below an opening one, which
    would separate a container from the brace it opens - and none at the start
    or the end of the file, where there is no tag to separate.  A blank line
    already there is left alone, since a second one would say the same thing
    twice, which also means one gap between two containers serves them both.
    """
    wanted: dict[int, _Opening] = {}
    for container in _the_containers_in(lines):
        below = container.last
        follower = lines[below + 1].strip() if below + 1 < len(lines) else ""
        if follower and not follower.startswith("}"):
            wanted.setdefault(
                below,
                _Opening(after=below, about=below, tag=container.tag, above=False),
            )
        above = container.first - 1
        over = lines[above].strip() if above >= 0 else ""
        if over and not over.endswith("{"):
            wanted.setdefault(
                above,
                _Opening(after=above, about=above + 1, tag=container.tag, above=True),
            )
    return tuple(wanted[place] for place in sorted(wanted))


def _the_blank_lines_to_shut(lines: list[str]) -> tuple[int, ...]:
    """Which blank lines stand where no blank line is asked for.

    The same rule read from the other side as ``_the_blank_lines_to_open``: a
    blank line parts a container from the line written beside it and nothing else,
    so a blank line is in the way between two tags that each hold one value, under
    an opening brace, above a closing one, and twice over where one gap already
    says the same thing once.  The blank lines above the first tag of the text and
    the ones making up its ending are nobody's gap here either, and a blank line
    standing inside a value written over several lines belongs to that value rather
    than to anybody's gap; a blank line that comes out is told as its place among
    these lines, which is where the edit cutting it is cut.
    """
    containers = _the_containers_in(lines)
    names = {one.first for one in containers}
    braces = {one.brace for one in containers if one.brace != one.first}
    closes = {one.last for one in containers}
    held = _the_lines_held_by_a_value(lines)

    # the ending of the text is one blank line longer than its line endings, and
    # the blank lines below the last tag belong to it rather than to anybody
    keep = len(lines) - _the_blank_lines_at_the_end(lines)
    gone: list[int] = []
    at = 0
    while at < keep:
        if lines[at].strip():
            at += 1
            continue
        run = [at]
        while run[-1] + 1 < keep and not lines[run[-1] + 1].strip():
            run.append(run[-1] + 1)
        if run[0] and not held.intersection(run):
            over, under = run[0] - 1, run[-1] + 1
            if under >= keep or not _a_blank_line_belongs(over, under, names, braces, closes):
                gone.extend(run)  # nothing here asks for a blank line at all
            else:
                gone.extend(run[1:])  # one gap between them says it once already
        at = run[-1] + 1
    return tuple(gone)


def _a_blank_line_belongs(
    over: int, under: int, names: set[int], braces: set[int], closes: set[int]
) -> bool:
    """Whether a blank line may stand between two lines that hold something.

    ``over`` and ``under`` are the lines above and below the gap, and they are not
    blank.  A blank line stands there when it parts a container from what is
    written beside it: a closing brace with a line under it, or the line naming a
    container with a line above it, one gap between two containers serving them
    both.  Nothing stands under an opening brace or above a closing one, since
    that would part a container from its own brace; a name written with its brace
    after it is the name's own line rather than an opening brace, which is why the
    gap above such a container still comes in.
    """
    if over in braces or under in closes:
        return False
    return over in closes or under in names


def _the_lines_held_by_a_value(lines: list[str]) -> set[int]:
    """The lines a value written over more than one line takes up.

    A blank line in the middle of a quoted value is part of that value, not a gap
    somebody left between two tags, and no blank line rule reaches into it.  The
    walk is the codec's own, from a tag to the line its value ends on and on to the
    next, so the lines of a running value are found inside a container as well as
    at the top of the file.
    """
    held: set[int] = set()
    todo: list[tuple[int, int]] = [(0, len(lines))]
    while todo:
        start, end = todo.pop()
        tags, because = _the_tags_between(lines, start, end)
        if because:
            continue
        for tag in tags:
            if tag.brace >= 0:
                todo.append((tag.brace + 1, tag.last))
            elif tag.last > tag.first:
                held.update(range(tag.first + 1, tag.last + 1))
    return held


def _the_containers_in(lines: list[str]) -> tuple[_Tag, ...]:
    """Every container in the text, in the order their names are written.

    The containers inside other containers are read the same way as the ones at
    the top, each stretch between a pair of braces on its own, and what comes back
    is in the order of the lines.  A stretch the codec cannot read is left out
    rather than guessed at, which only ever happens below a container the caller
    has already read without complaint.
    """
    found: list[_Tag] = []
    todo: list[tuple[int, int]] = [(0, len(lines))]
    while todo:
        start, end = todo.pop()
        tags, because = _the_tags_between(lines, start, end)
        if because:
            continue
        for tag in tags:
            if tag.brace >= 0:
                found.append(tag)
                todo.append((tag.brace + 1, tag.last))
    found.sort(key=lambda container: container.first)
    return tuple(found)


def _the_tags_between(
    lines: list[str], start: int, end: int
) -> tuple[list[_Tag], str]:
    """The tags written between two lines, or why they cannot be told apart.

    The walk is the codec's own: from a tag to the line its block ends on, and
    from there to the next tag, so the lines of a value running over several
    lines are never mistaken for tags.  ``start`` is where the tags may stand and
    ``end`` is the ``}`` closing the container they are written inside, which is
    not one of them; a tag reaching past it belongs to the container above rather
    than to this one, and is said about rather than cut in half.  Blank lines are
    passed over, and a brace that has no tag name above it is not a tag.
    """
    tags: list[_Tag] = []
    at = start
    while at < end:
        if not lines[at].strip():
            at += 1
            continue
        found = _A_NAME.match(lines[at])
        if found is None:
            return [], f"line {at + 1} holds {lines[at].strip()!r}, which is not a tag"
        name = found.group(1)
        rest = _the_rest_of(lines[at].strip())
        last, because = _the_tag_takes_up_to(lines, at, rest)
        if because:
            return [], f"the {name} on line {at + 1} {because}"
        if last >= end:
            return [], f"the {name} on line {at + 1} is not closed in its container"
        tags.append(
            _Tag(
                tag=name,
                first=at,
                last=last,
                brace=_the_brace_the_tag_opens(rest, lines, at),
            )
        )
        at = last + 1
    return tags, ""
