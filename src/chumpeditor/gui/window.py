"""The window: one file at a time, shown in one rich text area.

There is no queue here and nothing is converted beside it any more.  A file
arrives - named on the command line, dropped on the window, picked in the Open
dialog or out of the list of files opened lately - its text form goes into the
editor, and the window's title says which file that is and whether it has been
changed since it was written.

Writing the file back is the window's decision, not the editor's: *Save chump*
packs the text into a binary file and *Export txt* writes the text form, and
whichever was last written becomes the file the window is talking about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PyQt6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from .. import tweaks
from ..chump import ChumpError, Problem
from ..document import (
    CHUMP_GROUP,
    TEXT_GROUP,
    as_file_text,
    check_text,
    filter_string,
    find_problems,
    is_readable,
    read_document,
    save_chump,
    save_text,
    suggested_path,
)
from ..recent import RecentFiles
from .about import ABOUT_TITLE, about_html
from .drops import accept_file_drop, dropped_paths
from .editor import RichTextEditor
from .menus import build_menus
from .resources import APP_TITLE, DISPLAY_NAME, DROP_HINT, window_icon

__all__ = [
    "CHUMP_WRITE",
    "ChumpWindow",
    "REPORT_LIMIT",
    "SYNTAX_TITLE",
    "TEXT_WRITE",
    "UNTITLED",
    "WINDOW_SIZE",
]

#: the starting size: wide enough for a value on column 40 plus its text
WINDOW_SIZE = (940, 660)

#: what the title shows before any file is in the editor
UNTITLED = "Untitled"

#: what the report of a syntax check is called, in the menu and on the box
SYNTAX_TITLE = "Syntax check"

#: how many problems one box will name before it says how many more there are
REPORT_LIMIT = 25


@dataclass(frozen=True)
class WriteForm:
    """One of the two ways the text on screen can be written out."""

    #: what the menu item is called, and what the save dialog is titled
    verb: str
    #: what the status bar says once it has been done
    done: str
    #: the extension a file of this form has
    suffix: str
    #: the extension the save dialog offers, and nothing else
    group: tuple[str, tuple[str, ...]]
    #: the function that does the writing
    write: Callable[[str, Path], Path]


CHUMP_WRITE = WriteForm("Save chump", "Saved", ".chump", CHUMP_GROUP, save_chump)
TEXT_WRITE = WriteForm("Export txt", "Exported", ".txt", TEXT_GROUP, save_text)


def _counted(problems: list[Problem]) -> str:
    """How much a report found, in as few words as the status bar has room for."""
    if not problems:
        return "No problems found"
    return f"{len(problems)} problem{'' if len(problems) == 1 else 's'} found"


class ChumpWindow(QMainWindow):
    """The editor, the title, and the messages the window can give."""

    def __init__(self, paths: list[str] | None = None) -> None:
        super().__init__()
        self.path: Path | None = None
        #: the folder the last file came from or went to, to start a dialog in
        self._folder: Path | None = None
        self._message = ""
        #: which files were opened lately, newest first; the file menu shows them
        self.recent = RecentFiles()
        #: the menu those names are written into, filled in by ``build_menus``
        self.recent_menu = None

        self.editor = RichTextEditor(self)
        self.setCentralWidget(self.editor)

        self.setWindowTitle(APP_TITLE)
        icon = window_icon()
        if icon:
            self.setWindowIcon(icon)
        self.resize(*WINDOW_SIZE)
        build_menus(self)

        # the star in the title follows the document's own idea of being changed
        self.editor.document().modificationChanged.connect(lambda _changed: self._refresh_title())

        # a file can be let go anywhere in the window, the text included
        self.setAcceptDrops(True)
        self.editor.files_dropped.connect(self.open_paths)
        self.editor.files_dragging.connect(self._drop_hint)

        self.say(DROP_HINT)
        if self.recent.broken:
            # the list is a convenience, so a list that cannot be read is
            # mentioned in the status bar and the program carries on without it
            self.say(self.recent.broken)

        if paths:
            self.open_paths(paths)
        self._refresh_title()

    # -- opening ------------------------------------------------------------
    def open_path(self, path: str | Path) -> Path:
        """Show one file in the editor; it stays where it is until saved.

        Raises what the codec raises - a file that is not a chump, or a chump
        that is damaged - so the caller decides how loudly to complain.
        """
        text = read_document(path)
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.path = Path(path)
        self._folder = self.path.parent
        self._refresh_title()
        self.say(f"Opened {self.path.name}")
        self.remember(self.path)
        return self.path

    def open_file(self, path: str | Path) -> bool:
        """The same, with the failure made visible instead of raised.

        Every way a file reaches the editor - command line, drop, Open dialog -
        ends up here, because a file that will not open deserves a dialog
        either way.
        """
        try:
            self.open_path(path)
        except (OSError, ChumpError) as exc:
            self.error(f"{path}\n{exc}")
            return False
        return True

    def open_paths(self, paths: list[str]) -> Path | None:
        """Open the first usable path; one document at a time is the rule here.

        Whatever else was dropped or named is reported rather than quietly
        dropped, because "where is the file I just dropped?" is a bad question
        to have to ask.  Asking before replacing is what keeps a drop from
        wiping work that was never written out.
        """
        usable = [path for path in paths if is_readable(path)]
        if not usable:
            if paths:
                self.say("Nothing to open: no .chump, .cdp or .txt among them")
            return None
        if not self._ok_to_replace():
            return None

        if not self.open_file(usable[0]):
            return None
        opened = self.path
        extra = len(usable) - 1
        if extra:
            skipped = ", ".join(Path(path).name for path in usable[1:])
            self.say(f"Opened {opened.name}; one file at a time, so not {skipped}")
        return opened

    def remember(self, path: Path) -> None:
        """Note that ``path`` was opened, so the file menu can offer it again.

        Only a file that came through is listed, which is why this is called at
        the end of an opening.  Should the list itself refuse to be written, that
        goes in the status bar; it is no reason to lose the file on screen.
        """
        self.recent.remember(path)
        self.fill_recent_menu()
        if self.recent.broken:
            self.say(self.recent.broken)

    # -- the menus ------------------------------------------------------------
    def prompt_open(self) -> None:
        """File > Open: ask for a file, then open it if that is allowed.

        Asking first is what makes the menu safe to press with work in the
        editor: opening replaces the text without saving it.
        """
        if not self._ok_to_replace():
            return
        name, _chosen = QFileDialog.getOpenFileName(
            self, "Open file", self._folder_name(), filter_string()
        )
        if name:
            self.open_file(name)

    def open_recent(self, path: Path) -> None:
        """File > Recent files: open one of the files opened lately.

        Asked about before replacing, exactly as the Open item is: the text on
        screen may be work that was never written out, and a name in a menu is no
        reason to lose it.
        """
        if not self._ok_to_replace():
            return
        self.open_file(path)

    def fill_recent_menu(self) -> None:
        """Rewrite the Recent files menu: the names, then the way to forget them.

        Written out whenever a file is opened and again whenever the menu is about
        to be shown; with ten names at most there is nothing to gain by being
        cleverer.  A file that has gone missing since it was opened stays listed -
        it may be on a drive that is away - but is greyed out rather than promise
        something that will fail.

        The old items are set aside for the event loop to delete rather than
        deleted here.  Choosing a name out of this menu comes back through this
        method, so clearing the menu outright would take the very item away from
        under Qt while it is still working out which item was chosen.
        """
        menu = self.recent_menu
        if menu is None:
            return
        for action in menu.actions():
            menu.removeAction(action)
            action.deleteLater()
        listed = self.recent.paths()
        for path in listed:
            action = menu.addAction(str(path))
            action.setEnabled(path.is_file())
            action.setToolTip(str(path))
            action.triggered.connect(lambda _checked=False, one=path: self.open_recent(one))
        if listed:
            menu.addSeparator()
        clear = menu.addAction("&Clear list")
        clear.setEnabled(bool(listed))
        clear.triggered.connect(self.clear_recent)

    def clear_recent(self) -> None:
        """File > Recent files > Clear list: forget which files were opened."""
        self.recent.clear()
        self.fill_recent_menu()
        self.say("Cleared the list of recent files")
        if self.recent.broken:
            self.say(self.recent.broken)

    def save(self, *, ask: bool = False) -> Path | None:
        """File > Save chump: the text back into a binary config file."""
        return self._write(CHUMP_WRITE, ask)

    def export(self, *, ask: bool = False) -> Path | None:
        """File > Export txt: the text as a .txt file, spacing and all."""
        return self._write(TEXT_WRITE, ask)

    def syntax_check(self) -> None:
        """File > Syntax check: every rule a write is guarded by, said at once.

        A write stops at the first fault it finds, which is the right thing to do
        to a file and a poor way to answer a question.  Here the same rules are
        read out one line each, in the order the lines come, so a person can fix
        a file in one pass instead of pressing Save twenty times.  Nothing on
        screen is touched: a check only reads.  An empty report is said as well,
        because an answer that stays silent when all is well is indistinguishable
        from a shortcut that did nothing.
        """
        problems = find_problems(as_file_text(self.editor.toPlainText()))
        self.say(_counted(problems))
        if not problems:
            QMessageBox.information(self, SYNTAX_TITLE, "No problems found.")
            return
        report = [f"Line {one.line}: {one.message}" for one in problems[:REPORT_LIMIT]]
        if len(problems) > REPORT_LIMIT:
            report.append(f"... and {len(problems) - REPORT_LIMIT} more")
        QMessageBox.warning(self, SYNTAX_TITLE, "\n".join(report))

    def about(self) -> None:
        """Help > About: what this is, and where it comes from."""
        QMessageBox.about(self, ABOUT_TITLE, about_html())

    def convert_obsolete_lists(self) -> None:
        """Tweaks > Convert obsolete lists: numbered tags into one list tag."""
        self._tweak("Convert obsolete lists", tweaks.convert_obsolete_lists)

    def remove_language_tags(self) -> None:
        """Tweaks > Remove language tags: description-de and the rest, gone."""
        self._tweak("Remove language tags", tweaks.remove_language_tags)

    def convert_asset_filename_to_mesh_table(self) -> None:
        """Tweaks > Convert asset-filename to mesh-table: the newer way to name a mesh."""
        self._tweak(
            "Convert asset-filename to mesh-table",
            tweaks.convert_asset_filename_to_mesh_table,
        )

    def reorder_tags(self) -> None:
        """Tweaks > Reorder tags: kuid and username first, the containers last,
        the values of a container before what is written inside it, and every
        container set off from the tags around it with a blank line."""
        self._tweak("Reorder tags", tweaks.reorder_tags)

    def _tweak(
        self,
        title: str,
        tidy: Callable[
            [str], tweaks.Tweaks | tweaks.Sweep | tweaks.MeshTables | tweaks.Order
        ],
    ) -> None:
        """One tidy-up over the text on screen, and then an account of it.

        The change is made as edits in the text rather than by dropping a new
        document in, so the caret keeps its place and one Undo takes the whole
        of it back.  What was done, and what was deliberately left alone, is
        read out afterwards: a tidy-up nobody can see is a tidy-up nobody trusts.
        A tidy-up that had to stop before it started is said as a warning.
        """
        result = tidy(self.editor.toPlainText())
        if result.rewrites:
            self.editor.apply_rewrites(result.rewrites)
        self.say(result.status)
        box = QMessageBox.warning if result.warning else QMessageBox.information
        box(self, title, result.summary())

    def _write(self, form: WriteForm, ask: bool) -> Path | None:
        """Write out in one form, and make that the file being edited.

        The file changes identity because that is what the window has been
        asked for: exporting a chump to text leaves the text on screen, and so
        the text file is the one it now belongs to.

        The text is looked at before any file is chosen.  A file that cannot be
        written should not cost anybody a save dialog, and the same check runs
        again inside the write itself, so the rule is the rule wherever a write
        comes from.
        """
        text = self.editor.toPlainText()
        try:
            check_text(as_file_text(text))
        except ChumpError as exc:
            self.error(str(exc))
            return None

        target = self._target(form, ask)
        if target is None:
            return None
        try:
            form.write(text, target)
        except (OSError, ChumpError) as exc:
            self.error(f"{target}\n{exc}")
            return None
        self.path = target
        self._folder = target.parent
        self.editor.document().setModified(False)
        self._refresh_title()
        self.say(f"{form.done} {target.name}")
        return target

    def _target(self, form: WriteForm, ask: bool) -> Path | None:
        """The file to write: the one being edited, or one just now chosen."""
        if not ask and self.path and self.path.suffix.lower() == form.suffix:
            return self.path

        start = suggested_path(self.path, form.suffix)
        name, _chosen = QFileDialog.getSaveFileName(
            self,
            form.verb,
            str(start) if start else self._folder_name(),
            filter_string(form.group),
        )
        if not name:
            return None
        target = Path(name)
        return target if target.suffix else target.with_suffix(form.suffix)

    def _folder_name(self) -> str:
        """Where a dialog starts: the folder of the last file, or nowhere."""
        return str(self._folder) if self._folder else ""

    def _ok_to_replace(self) -> bool:
        """Whether the editor may be cleared, asking first if anything is at risk.

        The work is asked about the way every other program asks about it: Save
        writes it out and carries on, Discard throws it away, Cancel stops where
        it was.  A box that only offers to discard leaves nobody any way to keep
        the very work it has just warned them about.
        """
        if not self.editor.document().isModified():
            return True
        name = self.path.name if self.path else UNTITLED
        answer = QMessageBox.question(
            self,
            DISPLAY_NAME,
            f"Save changes to {name}?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            # a save that was argued with, cancelled or refused keeps the work
            # on screen, and the thing that was asked for does not happen
            return self.save() is not None
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Closing over work that was never written out is asked about first."""
        if self._ok_to_replace():
            event.accept()
        else:
            event.ignore()

    # -- drag and drop ------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if accept_file_drop(event):
            self._drop_hint(True)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        accept_file_drop(event)  # without this the drop is never offered

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._drop_hint(False)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if accept_file_drop(event):
            self.open_paths(dropped_paths(event.mimeData()))

    def _drop_hint(self, active: bool) -> None:
        """Offer the hint while a file hovers, and give the line back after."""
        self.statusBar().showMessage(DROP_HINT if active else self._message)

    # -- messages -----------------------------------------------------------
    def say(self, text: str) -> None:
        """A line in the status bar: what just happened, or what to do next."""
        self._message = text
        self.statusBar().showMessage(text)

    def error(self, message: str) -> None:
        """Something went wrong and the editor is not going to show it itself."""
        QMessageBox.critical(self, "Error", message)

    def _refresh_title(self) -> None:
        """The file's name, a star while it is unsaved, and the version."""
        name = self.path.name if self.path else UNTITLED
        star = " *" if self.editor.document().isModified() else ""
        self.setWindowTitle(f"{name}{star} - {APP_TITLE}")
