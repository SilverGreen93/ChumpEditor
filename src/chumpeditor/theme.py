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
"""

from __future__ import annotations

import json
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
    """A list of words that share a style."""

    style: str
    words: tuple[str, ...] = ()


@dataclass(frozen=True)
class Theme:
    """The whole recipe: styles, the pairs they cover, the words they follow."""

    name: str = "Trainz config"
    styles: dict[str, Style] = field(default_factory=dict)
    pairs: tuple[Pair, ...] = ()
    keywords: tuple[Keywords, ...] = ()
    numbers: str | None = None
    case_sensitive: bool = True
    #: each keyword against the style it belongs to; built once, not stored twice
    words: dict[str, str] = field(default_factory=dict, compare=False)

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

    def style(self, id: str) -> Style:
        """The style named by a rule; the default covers anything unaccounted for."""
        return self.styles.get(id) or self.styles.get("default", Style("default"))

    @property
    def default(self) -> Style:
        return self.style("default")

    def to_json(self) -> dict:
        """The theme as it is written to disk."""
        return {
            "name": self.name,
            "caseSensitive": self.case_sensitive,
            "styles": {
                name: _style_as_written(style) for name, style in self.styles.items()
            },
            "pairs": [{"style": p.style, "open": p.open, "close": p.close} for p in self.pairs],
            "keywords": [{"style": k.style, "words": list(k.words)} for k in self.keywords],
            "numbers": self.numbers,
        }


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
        groups.append(Keywords(style=style, words=tuple(str(word) for word in words)))
    return tuple(groups)


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
