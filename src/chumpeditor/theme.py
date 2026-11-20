"""The colours the editor puts on a config file, and the words they follow.

A theme is one small JSON file, written to be edited by hand: a handful of
named styles, the pairs of characters that enclose a stretch of text, and the
lists of keywords that get the colours.  Everything in here is free of Qt so
the format and the rules it describes can be read and tested on their own;
``gui.highlighter`` is what turns the rules into colours on screen.

The theme the editor uses is ``trainz.json``: the copy in the configuration
directory if someone has put one there, and the copy inside the program
otherwise.  Both are plain text, and the styles are named after what they
cover, so changing a colour means changing one line.

A style may name a second colour for a dark background, since the whole point
of a colour is that it can be seen; ``gui.editor`` says which of the two the
text is sitting on.

A list of keywords may give regular expressions instead of, or as well as,
literal words, so a family of tags written ``category-era-0``, ``category-era-1``
and on takes one line rather than one entry each.  A theme can also say that a
tag ending in a two letter language suffix - ``description-ru`` - is coloured as
the tag it is written after.  ``scan.py`` is what applies both.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .paths import config_dir

__all__ = [
    "DEFAULT_THEME",
    "Theme",
    "ThemeError",
    "bundled_theme_path",
    "default_theme",
    "load_theme",
    "save_theme",
    "theme_path",
    "theme_paths",
]

#: the theme used when nothing else is asked for
DEFAULT_THEME = "trainz.json"

#: the tail a tag carries when it is written for one language: a hyphen and two
#: letters, as in description-ru.  Only the shape is checked, because a list of
#: every two letter language code is not something this program could keep up
#: to date, and a wrong guess only means a tag stays its default colour.
_LANGUAGE_SUFFIX = re.compile(r"-[A-Za-z]{2}$")


class ThemeError(ValueError):
    """A theme file that does not make sense, with the reason in its message."""


@dataclass(frozen=True)
class Style:
    """One colour, and whether it is bold or italic.

    ``dark`` is the same style for a dark background - the colours that read
    well in a light editor are usually far too dim in a dark one, and black on
    black reads as nothing at all.  Left out, the one colour is used either way.
    """

    name: str
    colour: str = "#000000"
    bold: bool = False
    italic: bool = False
    dark: str | None = None

    def colour_for(self, dark: bool) -> str:
        """The colour to paint with, once it is known what it sits on."""
        return (self.dark or self.colour) if dark else self.colour


@dataclass(frozen=True)
class Pair:
    """A stretch of text that starts with one string and ends with another."""

    style: str
    open: str
    close: str


@dataclass(frozen=True)
class Keywords:
    """One style, and the words and the patterns that wear it.

    ``patterns`` are regular expressions tried against a whole word, never part
    of one, which is what lets a family of tags - ``category-era-0``,
    ``category-era-1``, and however many more - be written as one line.
    """

    style: str
    words: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Theme:
    """The whole recipe: styles, the pairs they cover, the words they follow."""

    name: str = "Trainz config"
    styles: dict[str, Style] = field(default_factory=dict)
    pairs: tuple[Pair, ...] = ()
    keywords: tuple[Keywords, ...] = ()
    numbers: str | None = None
    case_sensitive: bool = True
    #: a tag ending in a two letter language suffix is coloured as the tag it
    #: is written after: description-ru reads as description
    language_suffixes: bool = False
    #: each keyword against the style it belongs to; built once, not stored twice
    words: dict[str, str] = field(default_factory=dict, compare=False)
    #: each pattern of the keyword lists, compiled, with the style it gives;
    #: tried in the order the theme lists them, and the first one wins
    matchers: tuple[tuple[re.Pattern[str], str], ...] = field(default_factory=tuple, compare=False)

    def __post_init__(self) -> None:
        if not self.words:
            table: dict[str, str] = {}
            # walked backwards, so the first list keeps a word it shares with a
            # later one
            for group in reversed(self.keywords):
                for word in group.words:
                    key = word if self.case_sensitive else word.lower()
                    table[key] = group.style
            object.__setattr__(self, "words", table)
        if not self.matchers:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            object.__setattr__(
                self,
                "matchers",
                tuple(
                    (re.compile(pattern, flags), group.style)
                    for group in self.keywords
                    for pattern in group.patterns
                ),
            )

    def style(self, id: str) -> Style:
        """The style named by a rule; the default covers anything unaccounted for."""
        return self.styles.get(id) or self.styles.get("default", Style("default"))

    def keyword_style(self, word: str) -> str | None:
        """The style a whole word asks for, or nothing when no rule covers it.

        The lists of words are tried before the patterns, so a theme can still
        pick one member of a family out and colour it another way.  A theme that
        counts language suffixes tries once more with a trailing ``-ru`` style
        tail taken off, which is how a tag written for one language is coloured
        as the tag it belongs to.
        """
        style = self._style_of_word(word)
        if style or not self.language_suffixes:
            return style
        base = _LANGUAGE_SUFFIX.sub("", word)
        return self._style_of_word(base) if base != word else None

    def _style_of_word(self, word: str) -> str | None:
        """One word against the lists, and then against the patterns."""
        style = self.words.get(word if self.case_sensitive else word.lower())
        if style:
            return style
        for pattern, style in self.matchers:
            if pattern.fullmatch(word):
                return style
        return None

    @property
    def default(self) -> Style:
        return self.style("default")

    def to_json(self) -> dict:
        """The theme as it is written to disk."""
        written: dict = {
            "name": self.name,
            "caseSensitive": self.case_sensitive,
        }
        if self.language_suffixes:
            written["languageSuffixes"] = True
        written["styles"] = {
            name: _style_as_written(style) for name, style in self.styles.items()
        }
        written["pairs"] = [
            {"style": pair.style, "open": pair.open, "close": pair.close}
            for pair in self.pairs
        ]
        written["keywords"] = [_keywords_as_written(group) for group in self.keywords]
        written["numbers"] = self.numbers
        return written


def theme_path(name: str = DEFAULT_THEME) -> Path:
    """Where a theme written by whoever uses this program lives."""
    return config_dir() / "themes" / _file_name(name)


def bundled_theme_path(name: str = DEFAULT_THEME) -> Path:
    """Where the themes that come with this program live."""
    return Path(__file__).parent / "themes" / _file_name(name)


def _file_name(name: str) -> str:
    """A theme named with an extension, since that is how they are kept."""
    return name if name.endswith(".json") else f"{name}.json"


def theme_paths(name: str = DEFAULT_THEME) -> tuple[Path, ...]:
    """Every place a named theme is looked for, in the order they win.

    A theme in the configuration directory beats the one that ships, so the
    colours can be changed without opening the program's own files.
    """
    return (theme_path(name), bundled_theme_path(name))


def default_theme() -> Theme:
    """The theme the editor colours with when nobody has chosen one."""
    return load_theme()


def load_theme(name: str | Path | None = None) -> Theme:
    """Read a theme, and say plainly what is wrong with it if it will not read.

    Give a path to read one particular file; give a bare name, or nothing, to
    look that theme up in the places it is kept.
    """
    if name is None:
        wanted = theme_paths()
    else:
        given = Path(name)
        wanted = (given,) if given.suffix == ".json" else theme_paths(given.name)
    source = next((found for found in wanted if found.is_file()), wanted[-1])
    try:
        text = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ThemeError(f"{source}: {exc.strerror or exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ThemeError(f"{source}: {exc.msg} at line {exc.lineno}") from exc
    return parse_theme(data, str(source))


def parse_theme(data: object, origin: str = "theme") -> Theme:
    """Build a theme from the dictionary a JSON file holds."""
    if not isinstance(data, dict):
        raise ThemeError(f"{origin}: a theme is one object with styles, pairs and keywords")

    styles = _styles(data.get("styles"), origin)
    pairs = _pairs(data.get("pairs"), styles, origin)
    groups = _keywords(data.get("keywords"), styles, origin)
    numbers = data.get("numbers")
    if numbers is not None and numbers not in styles:
        raise ThemeError(f"{origin}: numbers name a style that is not there: {numbers!r}")

    return Theme(
        name=str(data.get("name") or "theme"),
        styles=styles,
        pairs=pairs,
        keywords=groups,
        numbers=numbers if isinstance(numbers, str) else None,
        case_sensitive=bool(data.get("caseSensitive", True)),
        language_suffixes=bool(data.get("languageSuffixes", False)),
    )


def save_theme(theme: Theme, path: str | Path) -> Path:
    """Write a theme out in the form a person can read and change."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(theme.to_json(), indent=2) + "\n", encoding="utf-8")
    return target


def _styles(data: object, origin: str) -> dict[str, Style]:
    if not isinstance(data, dict) or not data:
        raise ThemeError(f"{origin}: styles is a name for each colour, and there are none")
    styles = {}
    for name, entry in data.items():
        entry = {"colour": entry} if isinstance(entry, str) else entry
        if not isinstance(entry, dict):
            raise ThemeError(f"{origin}: style {name!r} is a colour, or bold, italic and one")
        styles[str(name)] = Style(
            name=str(name),
            colour=_colour(str(name), entry.get("colour", "#000000"), origin),
            bold=bool(entry.get("bold", False)),
            italic=bool(entry.get("italic", False)),
            dark=_colour(str(name), entry["dark"], origin) if entry.get("dark") else None,
        )
    if "default" not in styles:
        raise ThemeError(f"{origin}: no default style, so plain text would have no colour")
    return styles


def _style_as_written(style: Style) -> dict:
    """One style, in the form the file holds it: the dark colour only when the
    style has one, so a theme that does not bother with dark mode stays short."""
    written = {"colour": style.colour, "bold": style.bold, "italic": style.italic}
    if style.dark:
        written["dark"] = style.dark
    return written


def _colour(name: str, value: object, origin: str) -> str:
    """A colour as ``#rrggbb``, whether it was written with the hash or not."""
    text = str(value).strip().lstrip("#").lower()
    if len(text) == 3:
        text = "".join(digit * 2 for digit in text)
    if len(text) != 6 or any(digit not in "0123456789abcdef" for digit in text):
        raise ThemeError(f"{origin}: style {name!r} has something that is not a colour: {value!r}")
    return f"#{text}"


def _pairs(data: object, styles: dict[str, Style], origin: str) -> tuple[Pair, ...]:
    pairs = []
    for entry in _as_list(data, "pairs", origin):
        if not isinstance(entry, dict):
            raise ThemeError(f"{origin}: a pair is an opening and a closing string")
        style = _style_id(entry.get("style"), styles, "pair", origin)
        open, close = str(entry.get("open", "")), str(entry.get("close", ""))
        if not open:
            raise ThemeError(f"{origin}: pair for {style!r} has nothing to open it")
        pairs.append(Pair(style=style, open=open, close=close))
    return tuple(pairs)


def _keywords(data: object, styles: dict[str, Style], origin: str) -> tuple[Keywords, ...]:
    groups = []
    for entry in _as_list(data, "keywords", origin):
        if not isinstance(entry, dict):
            raise ThemeError(f"{origin}: a keyword list is a style and the words in it")
        style = _style_id(entry.get("style"), styles, "keyword list", origin)
        words = entry.get("words", [])
        if not isinstance(words, list):
            raise ThemeError(f"{origin}: the words of {style!r} are a list")
        written = entry.get("patterns", [])
        patterns = _as_list([written] if isinstance(written, str) else written, "patterns", origin)
        sources = tuple(str(pattern) for pattern in patterns)
        for pattern in sources:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ThemeError(
                    f"{origin}: the patterns of {style!r} have one that cannot be read:"
                    f" {pattern!r} ({exc.msg})"
                ) from exc
        groups.append(
            Keywords(
                style=style,
                words=tuple(str(word) for word in words),
                patterns=sources,
            )
        )
    return tuple(groups)


def _keywords_as_written(group: Keywords) -> dict:
    """One keyword list in the form the file holds it: the patterns only when
    the list has any, so a theme of plain words stays as short as it was."""
    written = {"style": group.style, "words": list(group.words)}
    if group.patterns:
        written["patterns"] = list(group.patterns)
    return written


def _style_id(value: object, styles: dict[str, Style], what: str, origin: str) -> str:
    name = str(value or "")
    if name not in styles:
        raise ThemeError(f"{origin}: {what} names a style that is not there: {name!r}")
    return name


def _as_list(data: object, what: str, origin: str) -> list:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ThemeError(f"{origin}: {what} is a list")
    return data
