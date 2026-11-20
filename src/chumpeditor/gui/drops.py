"""Letting go of a file on the window, or straight on the text area.

Two widgets take drops - the window and the editor inside it - so the reading
of the drag sits here once: what a drag is offering, and the local files inside
it.  What happens to those files is the window's decision.
"""

from __future__ import annotations

__all__ = ["accept_file_drop", "dropped_paths"]


def dropped_paths(mime_data) -> list[str]:
    """The local files a drag carries, in the order they were dropped."""
    return [url.toLocalFile() for url in mime_data.urls() if url.isLocalFile()]


def accept_file_drop(event) -> bool:
    """Take the drop if it names files, and say whether it was taken.

    A drag of plain text is left alone on purpose: pasting text into the
    editor by dragging it there is still a thing people do.
    """
    if not event.mimeData().hasUrls():
        return False
    event.acceptProposedAction()
    return True
