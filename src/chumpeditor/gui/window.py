"""The window: one file at a time, shown in one rich text area.

There is no queue here and nothing is converted beside it any more.  A file
arrives - named on the command line, dropped on the window, picked in the Open
dialog or out of the list of files opened lately - its text form goes into the
editor, and the window's title says which file that is and whether it has been
changed since it was written.  An assets.tdx opens with both of its settings
blocks decoded into the text area at once.

Writing the file back is the window's decision, not the editor's: *Save chump*
packs the text into a binary file and *Export txt* writes the text form, and
whichever was last written becomes the file the window is talking about.

Searching the text belongs to a panel of its own, stood at the bottom of the
window and brought up from the Edit menu; the window only connects its news to
the status line.  So does the tree of the file's containers, stood to the left of
the text and brought up from the View menu: which containers there are and which
line each is written on is answered by ``outline.py``, and all the window adds is
where the panel stands and what a chosen row does to the caret.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
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
from ..outline import containers
from ..recent import RecentFiles
from ..settings import Settings
from .about import ABOUT_TITLE, about_html
from .drops import accept_file_drop, dropped_paths
from .editor import RichTextEditor
from .find import FindReplacePanel
from .menus import build_menus
from .resources import APP_TITLE, DISPLAY_NAME, DROP_HINT, UNTITLED, window_icon
from .treeview import ContainerTree

__all__ = [
    "CHUMP_WRITE",
    "ChumpWindow",
    "REPORT_LIMIT",
    "SYNTAX_TITLE",
    "TEXT_WRITE",
    "WINDOW_SIZE",
]

#: the starting size: wide enough for a value on column 40 plus its text
WINDOW_SIZE = (940, 660)

#: what the report of a syntax check is called, in the menu and on the box
SYNTAX_TITLE = "Syntax check"

#: how many problems one box will name before it says how many more there are
REPORT_LIMIT = 25

#: what the settings file calls the tree of containers, true while it stands open
TREEVIEW_SETTING = "treeview"

#: what the settings file calls the wrapping of long lines, true while they bend
WRAP_SETTING = "wrap"

#: what the settings file calls the size of the text, in points
FONT_SIZE_SETTING = "font_size"

#: what the settings file calls the size of the window, its width and its height
WINDOW_SIZE_SETTING = "window_size"
#: what the settings file calls the window standing filled across the screen
MAXIMIZED_SETTING = "maximized"


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
        #: what the program remembers about itself between runs
        self.settings = Settings()

        self.editor = RichTextEditor(self)
        self.setCentralWidget(self.editor)

        # the search panel shares the window rather than the text area: it is
        # docked underneath the editor, so the editor and its line numbers are
        # left exactly as they are, and it is out of sight until asked for
        self.find_panel = FindReplacePanel(self.editor)
        self.find_panel.reported.connect(self.say)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.find_panel)

        # the tree of containers stands to the left of the text, out of sight
        # until the View menu asks for it; like the search panel it is docked
        # beside the editor rather than in it, so the text and its line numbers
        # are left exactly as they are
        self.treeview = ContainerTree(self)
        self.treeview.picked.connect(self.reveal_line)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.treeview)

        # when the size of the text changes - turned by Ctrl and the wheel, or
        # read back from the window before this one - two things follow from that
        # one moment: the rows beside the text are written at the new size, since
        # they wear the same letters, and the size is written down, since it is a
        # habit rather than a choice made again for each file
        self.editor.font_size_changed.connect(self.treeview.set_font_size)
        self.editor.font_size_changed.connect(self._remember_font_size)

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
        if self.settings.broken:
            self.say(self.settings.broken)

        # the rows are written out whenever the text changes, rather than when
        # the panel is brought up: a tree of text that is not there any more is
        # worse than no tree, and the check runs whether anybody is looking or not
        self.editor.document().contentsChanged.connect(self._refresh_treeview)
        self._refresh_treeview()
        self._restore_treeview()
        self._restore_line_wrap()
        self._restore_font_size()
        self._restore_window()

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
                self.say("Nothing to open: no .chump, .cdp, .tdx or .txt among them")
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

    # -- the tree of containers -------------------------------------------------
    def toggle_treeview(self, on: bool | None = None) -> None:
        """View > Treeview: put the tree beside the text, or take it away.

        ``on`` comes from the ticked menu item when the menu asks.  A person who
        brought the tree up wants to click a row, so the keyboard goes to the text
        and not to the tree; that also means typing works straight away after the
        panel appears.

        Which way it stands is written down, because a panel somebody keeps
        bringing up on every file is a panel they would rather have already there.
        """
        if on is None:
            on = self.treeview.isHidden()
        if on:
            self.treeview.show()
        else:
            self.treeview.hide()
            # the menu item and the panel are one thing, so a program that hides
            # the panel without asking still leaves the menu telling the truth
            self._view_item("Treeview").setChecked(False)
        self.settings.set(TREEVIEW_SETTING, on)
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def _restore_treeview(self) -> None:
        """Bring the tree back if the last session left it up.

        The panel starts hidden and the menu item starts unticked, so both have to
        be put right here; ticking the item is not enough, because an item brought
        to the checked state by a program does not fire its own shortcut's slot.
        A value that is not a tick or a cross - a settings file edited by hand -
        counts for nothing, and the panel stays out of sight as it would have with
        no file at all.
        """
        if not self.settings.get(TREEVIEW_SETTING, False, as_=bool):
            return
        self.treeview.show()
        self._view_item("Treeview").setChecked(True)

    def reveal_line(self, line: int) -> None:
        """Put the caret on a container's name and select it.

        The name is what gets selected rather than the whole line, so pressing
        Ctrl+C after clicking a row copies the tag and nothing else, and a later
        search finds the word that just been looked at - which is how *Find next*
        behaves when it lands on something.  Scrolling follows the caret by
        itself, and ``ensure_line_in_sight`` pulls the line into the middle of the
        view as well, so a container chosen near the top or bottom of a long file
        can still be seen with what is written under it.

        The name is looked for from the start of its own line, which is where the
        outline says it is written; an indented tag is found through its
        indentation that way, and a line that no longer says what the row said -
        text edited between the row being made and being clicked - leaves the text
        alone rather than selecting the wrong thing.

        The caret is moved *after* the view has been scrolled.  A text area asked
        to show a caret scrolls to it its own way, which puts the line at the top
        of the view; asking for the caret second lets that scroll undo the centring
        and leave the line pressed against the bottom instead.
        """
        document = self.editor.document()
        block = document.findBlockByLineNumber(line - 1)
        if not block.isValid():
            return
        name = self._name_on_row(line)
        at = block.text().find(name) if name else -1
        if at < 0:
            return
        caret = QTextCursor(block)
        caret.setPosition(block.position() + at)
        caret.setPosition(caret.position() + len(name), QTextCursor.MoveMode.KeepAnchor)
        self.ensure_line_in_sight(line)
        self.editor.setTextCursor(caret)
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def ensure_line_in_sight(self, line: int) -> None:
        """Bring a line into the middle of the text area.

        ``QTextEdit.centerCursor`` would do this, and is not used because it takes
        the caret to where the scroll ended up - which on a short document, or one
        whose lines are taller than the view, is somewhere else in the file
        altogether, and has been seen to take the process down with it.  The
        scrollbar is moved instead: the caret stays exactly where it was put, and a
        line that cannot be centred because there is nothing below it to scroll is
        left at the bottom of the view, which is as near as the file allows.
        """
        document = self.editor.document()
        block = document.findBlockByLineNumber(line - 1)
        if not block.isValid():
            return
        edge = document.documentLayout().blockBoundingRect(block)
        bar = self.editor.verticalScrollBar()
        middle_of_text = self.editor.viewport().height() / 2
        bar.setValue(round(edge.top() + edge.height() / 2 - middle_of_text))

    def _name_on_row(self, line: int) -> str:
        """What the tree calls the container written on ``line``, if it has one.

        The rows carry their line numbers and not their names - a name is only
        wanted here - so the list is asked again, which for a file of this size is
        nothing, and the answer comes from the same reading as the rows themselves.
        """
        for one in containers(self.editor.toPlainText()):
            if one.line == line:
                return one.name
        return ""

    def _refresh_treeview(self) -> None:
        """Write the rows out again from whatever is on screen now."""
        self.treeview.set_text(self.editor.toPlainText())

    def _view_item(self, label: str):
        """The View menu's checkable item called ``label``, without its ampersand.

        Found rather than kept, because ``menus.py`` makes the items and this file
        only names what they do; there are two items in that menu, and looking one
        up by name beats remembering another object on the window.
        """
        for action in self.menuBar().actions():
            if action.menu() is not None:
                for item in action.menu().actions():
                    if item.isCheckable() and item.text().replace("&", "") == label:
                        return item
        raise LookupError(f"the View menu has no {label} item")

    # -- how the text is shown -------------------------------------------------
    def toggle_line_wrap(self, on: bool | None = None) -> None:
        """View > Wrap lines: bend the lines too long for the text area, or let
        them run on past its edge.

        ``on`` comes from the ticked item when the menu or the key asks, and is
        left out to mean the opposite of the way it stands now.  The item is put
        in the same state either way, because a menu that says one thing while the
        text does another is a menu that cannot be trusted.

        What changes is only the shape the text is shown in: nothing is written to
        the document, so the undo history is untouched, a line that wraps over three
        rows is still one line of the file and still has one number beside it, and
        the sideways bar the long lines needed comes and goes with them.

        Which way it stands is written down, because whether the lines run straight
        is a habit rather than a decision made file by file.
        """
        if on is None:
            on = not self.editor.is_line_wrapped()
        self.editor.set_line_wrap(on)
        self._view_item("Wrap lines").setChecked(on)
        self.settings.set(WRAP_SETTING, on)

    def _restore_line_wrap(self) -> None:
        """Bend the lines again if the last session left them bent.

        The text area starts with its lines straight and the menu item unticked, so
        both are put right here; ticking the item is not enough, because an item
        brought to the checked state by a program does not fire its own shortcut's
        slot.  A value that is neither true nor false - a settings file edited by
        hand - counts for nothing, and the lines run straight as they would have
        with no file at all.
        """
        if not self.settings.get(WRAP_SETTING, False, as_=bool):
            return
        self.editor.set_line_wrap(True)
        self._view_item("Wrap lines").setChecked(True)

    def _remember_font_size(self, points: float) -> None:
        """Write down the size the text was just changed to.

        Asked for by the text area as it changes, so every way of changing it -
        the wheel over the text, and a size read back from the window before this
        one - is remembered the same way, and there is no second door to forget.
        """
        self.settings.set(FONT_SIZE_SETTING, points)

    def _restore_font_size(self) -> None:
        """Write the text at the size the last session left it.

        The size the text area asks for itself is what it is written at when
        nothing was remembered, so in that case nothing is applied here and
        nothing is written back either - a program that rewrote its settings on
        every start would leave a file nobody had changed.  A size outside the
        bounds the text area allows is brought inside them by the text area
        rather than argued with here, and a value that is not a number at all - a
        settings file edited by hand - counts as nothing remembered.
        """
        points = self.settings.get(FONT_SIZE_SETTING, None, as_=float)
        if points is None:
            return
        self.editor.set_font_size(points)

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
        name = self._the_file_name()
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
        if not self._ok_to_replace():
            event.ignore()
            return
        # the window's own shape is remembered on the way out, once, rather than
        # at every pixel of somebody dragging an edge
        self._remember_window()
        event.accept()

    # -- the window itself ----------------------------------------------------
    def _remember_window(self) -> None:
        """Write down how big the window was, and whether it stood maximized.

        Both are habits rather than decisions made again for each file: a window
        is sized once and then read in for as long as the work lasts.  They are
        written as the window closes rather than as it is resized, because a
        resize by hand is a hundred changes a second and a settings file written
        for every one of them is not worth the disk.

        A window standing filled across the screen is asked for the size it had
        before it was filled, since that is the size it goes back to when somebody
        takes the maximize off it again.
        """
        was = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.settings.set(WINDOW_SIZE_SETTING, [was.width(), was.height()])
        self.settings.set(MAXIMIZED_SETTING, self.isMaximized())

    def _restore_window(self) -> None:
        """Stand the window at the size the last one was left at.

        Only the size comes back, and not the place on the screen it stood: a
        window remembered at a place no monitor has any more is a window nobody
        can see, and the desktop is not the program's to arrange.

        A size that is not two numbers with something in them - a settings file
        edited by hand - counts as nothing remembered.  A size that is a number
        but too small for a window is handed to Qt, which brings it up to the
        least a window can be, so the next window closed writes a size that was
        actually seen.
        """
        remembered = self.settings.get(WINDOW_SIZE_SETTING, None, as_=list)
        if remembered is not None and len(remembered) == 2 and all(
            isinstance(way, (int, float)) and not isinstance(way, bool) and way > 0
            for way in remembered
        ):
            self.resize(int(remembered[0]), int(remembered[1]))
        if self.settings.get(MAXIMIZED_SETTING, False, as_=bool):
            # asked for before the window is ever shown, because a plain show()
            # of a window that is already maximized is how Qt takes the maximize
            # back off, and the window is shown by whoever made it
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

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

    def _the_file_name(self) -> str:
        """What the text on screen is called: the file it came from, or the word
        for a file that has never been written out."""
        return self.path.name if self.path else UNTITLED

    def _refresh_title(self) -> None:
        """The file's name, a star while it is unsaved, and the version.

        The same name is put at the top of the tree of containers, because it is
        one answer - which file is on screen - shown in two places, and asking
        both from here is what keeps the title and the tree from disagreeing.
        """
        name = self._the_file_name()
        star = " *" if self.editor.document().isModified() else ""
        self.setWindowTitle(f"{name}{star} - {APP_TITLE}")
        self.treeview.set_file_name(name)
