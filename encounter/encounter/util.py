"""Small shared utilities."""

from __future__ import annotations

from bs4 import BeautifulSoup


def make_soup(html: str) -> BeautifulSoup:
    """Parse HTML, preferring lxml but falling back to the stdlib parser.

    lxml is faster but needs a compiled wheel that isn't always available
    (e.g. some serverless build images); ``html.parser`` is always present.
    """
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")
