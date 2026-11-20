"""What the About box says.

Kept apart from the menu so the wording can be checked without opening a
window, and so the version, the name and the address come from
:mod:`.resources` like everywhere else.
"""

from __future__ import annotations

from .resources import APP_NAME, APP_TITLE, CREDIT, DESCRIPTION, HOME_URL, ISSUES_URL, SUMMARY

__all__ = ["ABOUT_TITLE", "about_html"]

ABOUT_TITLE = f"About {APP_NAME}"


def about_html() -> str:
    """The box's text: what it is, where it comes from, who wrote it.

    Rich text, because the address is a link and Qt opens a link in the
    browser rather than expecting the text of it to be copied by hand.  The
    heading carries the version string, which is the one thing a bug report
    always needs.
    """
    return f"""
<h3>{APP_TITLE}</h3>
<p>{SUMMARY}</p>
<p>{DESCRIPTION}</p>
<p><a href="{HOME_URL}">{HOME_URL}</a><br>
<a href="{ISSUES_URL}">{ISSUES_URL}</a></p>
<p>{CREDIT}</p>
"""
