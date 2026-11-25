"""The panel the text is searched from: two boxes and five buttons at the bottom.

It is a dock stood at the bottom of the window rather than anything written into
the text, so the editor keeps every one of its own behaviours and the numbers
down the left stay where they were.  The panel holds the questions and the
answers as words; which characters the answers are made of is the business of
``search.py``, and moving the caret and editing the text is the editor's.

Two questions are asked by ticking a box rather than by typing an answer:
whether the letters have to match, and whether the text counts only where it
stands as a word of its own.

The two keys that repeat a search belong to the panel rather than to a menu, so
they answer from wherever the keyboard is - including the Find box itself - and
stop answering as soon as the panel is put away.

Nothing here asks the window anything: what happened is sent out as a sentence
for the status line, which is where the program says anything at all.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..search import Match, line_of, matches, next_match, previous_match, replacements
from .editor import RichTextEditor

__all__ = ["FindReplacePanel", "PANEL_TITLE"]

#: the panel's own name: it has no title bar to show it in, so the name is there
#: for anything that asks a widget what it is
PANEL_TITLE = "Find and replace"

#: Qt writes this where a selection crosses a line, and a search box holding half
#: a file is a mistake rather than a search
CROSSING_A_LINE = "\u2029"


class FindReplacePanel(QDockWidget):
    """The boxes, the two tick boxes, the buttons, and the four things they ask for."""

    #: what just happened - found it, replaced it, or did not - for the window's
    #: status line, which hears it from the window and nothing else
    reported = pyqtSignal(str)

    def __init__(self, editor: RichTextEditor, parent=None) -> None:
        super().__init__(PANEL_TITLE, parent)
        self.editor = editor
        # part of the window, not a little window of its own: no title bar to
        # drag it by and nothing to float it away or close it from, since the
        # panel has a Close button that says what it is for
        self.setTitleBarWidget(QWidget())
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setWidget(self._boxes_and_buttons())

        # Escape puts the panel away, but only while one of its own boxes has the
        # keyboard: everywhere else the key belongs to whatever is being edited
        self.escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape.activated.connect(self.close_panel)

        # Repeating a search is asked for by a key rather than by a menu, so the
        # key answers from wherever the keyboard stands, the Find box included.
        # A window shortcut answers only while its own widget is on screen, which
        # is what puts the keys away with the panel.
        self.next_key = QShortcut(QKeySequence("F3"), self)
        self.next_key.setContext(Qt.ShortcutContext.WindowShortcut)
        self.next_key.activated.connect(self.find_next)

        self.previous_key = QShortcut(QKeySequence("Shift+F3"), self)
        self.previous_key.setContext(Qt.ShortcutContext.WindowShortcut)
        self.previous_key.activated.connect(self.find_previous)
        self.hide()

    # -- what the panel is made of --------------------------------------------
    def _boxes_and_buttons(self) -> QWidget:
        """The two boxes over each other, and the things beside them.

        The two tick boxes are one over the other, and so are the searches and
        the two changes, because each pair does one thing at a different size:
        the same search again forwards and back, this one match and every match.
        """
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 4, 8, 4)

        boxes = QGridLayout()
        boxes.addWidget(QLabel("Find:"), 0, 0)
        self.find_field = QLineEdit(row)
        self.find_field.setPlaceholderText("the text to look for")
        self.find_field.returnPressed.connect(self.find_next)
        boxes.addWidget(self.find_field, 0, 1)

        boxes.addWidget(QLabel("Replace:"), 1, 0)
        self.replace_field = QLineEdit(row)
        self.replace_field.setPlaceholderText("what to put in its place")
        self.replace_field.returnPressed.connect(self.replace_once)
        boxes.addWidget(self.replace_field, 1, 1)
        boxes.setColumnStretch(1, 1)
        layout.addLayout(boxes, 1)

        ticks = QWidget(row)
        column = QVBoxLayout(ticks)
        column.setContentsMargins(0, 0, 0, 0)
        self.match_case = QCheckBox("Match case", ticks)
        column.addWidget(self.match_case)

        self.whole_word = QCheckBox("Whole word", ticks)
        self.whole_word.setToolTip("Only find the text where it stands on its own")
        column.addWidget(self.whole_word)
        layout.addWidget(ticks)

        searches = QVBoxLayout()
        self.find_next_button = QPushButton("Find next (F3)", row)
        self.find_next_button.clicked.connect(self.find_next)
        searches.addWidget(self.find_next_button)

        self.find_prev_button = QPushButton("Find prev (Shift+F3)", row)
        self.find_prev_button.clicked.connect(self.find_previous)
        searches.addWidget(self.find_prev_button)

        changes = QVBoxLayout()
        self.replace_button = QPushButton("Replace", row)
        self.replace_button.clicked.connect(self.replace_once)
        changes.addWidget(self.replace_button)

        self.replace_all_button = QPushButton("Replace all", row)
        self.replace_all_button.clicked.connect(self.replace_all)
        changes.addWidget(self.replace_all_button)

        layout.addLayout(searches)
        layout.addLayout(changes)

        self.close_button = QPushButton("Close", row)
        self.close_button.clicked.connect(self.close_panel)
        layout.addWidget(self.close_button)
        return row

    # -- bringing it up and putting it away -----------------------------------
    def open(self) -> None:
        """Bring the panel up with the keyboard in the Find box.

        Whatever is selected is offered as the thing to look for, because
        selecting a word and then asking for the rest of them is how a search
        usually starts.  A selection crossing a line is not offered: that is
        nearly always someone who has taken too much, and the box would end up
        holding half a file.
        """
        chosen = self.editor.textCursor().selectedText()
        if chosen and CROSSING_A_LINE not in chosen and "\n" not in chosen:
            self.find_field.setText(chosen)
        self.show()
        self.find_field.setFocus(Qt.FocusReason.OtherFocusReason)
        self.find_field.selectAll()

    def close_panel(self) -> None:
        """Put the panel away and give the keyboard back to the text.

        The panel going out of sight is also what puts away its two search keys,
        which answer only while the panel is on screen.
        """
        self.hide()
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    # -- the four things the panel can be asked to do -------------------------
    def find_next(self) -> None:
        """Put the selection on the next place the text is written.

        From wherever the caret stands, and from the top of the file once the
        bottom of it has been reached: going over the whole file once is what
        tells a person there is nowhere else.
        """
        sought = self.find_field.text()
        if not sought:
            self.reported.emit("Nothing to look for")
            return
        text = self.editor.toPlainText()
        here = self._past_the_caret()
        found = next_match(
            text, sought, here, match_case=self._letters_matter(),
            whole_word=self._only_whole_words(),
        )
        if found is None:
            self.reported.emit(f"Nothing in the file says {sought}")
            return
        self._select(found)
        around = ", from the top of the file again" if found.start < here else ""
        self.reported.emit(f"Found on line {line_of(text, found.start)}{around}")

    def find_previous(self) -> None:
        """Put the selection on the last place before the caret.

        The same ring as *Find next* gone round the other way, so the key can be
        held down and the places come back again in order, the top of the file
        joined to the bottom of it.
        """
        sought = self.find_field.text()
        if not sought:
            self.reported.emit("Nothing to look for")
            return
        text = self.editor.toPlainText()
        here = self._before_the_caret()
        found = previous_match(
            text, sought, here, match_case=self._letters_matter(),
            whole_word=self._only_whole_words(),
        )
        if found is None:
            self.reported.emit(f"Nothing in the file says {sought}")
            return
        self._select(found)
        around = ", from the end of the file again" if found.start > here else ""
        self.reported.emit(f"Found on line {line_of(text, found.start)}{around}")

    def replace_once(self) -> None:
        """Write over the match the selection is on, then find the next one.

        A selection that is not the text being sought is left alone and the next
        match is found instead, so the button can be pressed straight after
        *Find next* without writing over text nobody asked about.  A selection
        made by hand is written over as it was made, whole word or not, since it
        is something the person chose themselves.  Each press is one edit, and
        one press of Undo takes it back.
        """
        sought = self.find_field.text()
        if not sought:
            self.reported.emit("Nothing to look for")
            return
        text = self.editor.toPlainText()
        caret = self.editor.textCursor()
        start, end = caret.selectionStart(), caret.selectionEnd()
        on_a_match = start != end and matches(
            text[start:end], sought, match_case=self._letters_matter()
        )
        if not on_a_match:
            self.find_next()
            return

        caret.insertText(self.replace_field.text())
        wrote = f"Replaced on line {line_of(text, start)}"
        now = self.editor.toPlainText()
        after = next_match(
            # the text asked for again rather than the old one, because putting
            # the sought text in its own place has changed what comes after it
            now, sought, caret.position(), match_case=self._letters_matter(),
            whole_word=self._only_whole_words(),
        )
        if after is None:
            self.reported.emit(f"{wrote}; nothing else says {sought}")
            return
        self._select(after)
        self.reported.emit(f"{wrote}, next on line {line_of(now, after.start)}")

    def replace_all(self) -> None:
        """Every place at once, in one edit block.

        One press of Undo puts the whole change back, which is the least a change
        spread over a file deserves.
        """
        sought = self.find_field.text()
        if not sought:
            self.reported.emit("Nothing to look for")
            return
        every = replacements(
            self.editor.toPlainText(), sought, self.replace_field.text(),
            match_case=self._letters_matter(), whole_word=self._only_whole_words(),
        )
        if not every:
            self.reported.emit(f"Nothing in the file says {sought}")
            return
        self.editor.apply_rewrites(every)
        places = "place" if len(every) == 1 else "places"
        self.reported.emit(f"Replaced {len(every)} {places}")

    # -- the parts that are not decisions -------------------------------------
    def _letters_matter(self) -> bool:
        """Whether the letters have to match, which is the first tick box's answer."""
        return self.match_case.isChecked()

    def _only_whole_words(self) -> bool:
        """Whether the text counts only where it stands on its own, which is what
        the second tick box says; ``search.py`` puts the rings about the search
        when it is ticked.
        """
        return self.whole_word.isChecked()

    def _past_the_caret(self) -> int:
        """Where the next search starts: past the selection, however it was made.

        A selection dragged backwards leaves the caret at its beginning, and a
        search starting there would find again the match it is sitting on.
        """
        caret = self.editor.textCursor()
        return max(caret.position(), caret.anchor())

    def _before_the_caret(self) -> int:
        """Where a search backwards starts: before the selection, however it was
        made.

        A selection dragged forwards leaves the caret at its end, and a search
        starting there would find again the match it is sitting on.
        """
        caret = self.editor.textCursor()
        return min(caret.position(), caret.anchor())

    def _select(self, found: Match) -> None:
        """Put the selection on a match, and bring its line into sight.

        Moving the caret is what does the second part by itself: the text area
        scrolls to wherever its caret is put, so pressing the key again over a
        long file keeps the match it found on the screen.
        """
        caret = self.editor.textCursor()
        caret.setPosition(found.start)
        caret.setPosition(found.end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(caret)
