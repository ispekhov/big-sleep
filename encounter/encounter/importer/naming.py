"""Derive a precise, human product name from a product URL handle.

Brand storefronts routinely give every variant the same generic title — Roll &
Hill lists eight different "Cloud" fixtures all titled "Cloud" — while the real
distinction lives in the URL handle (``cloud-pendant-14``, ``cloud-floor-lamp-01``).
We humanise the handle and, when it's more descriptive than the title, use it.

Trailing numbers are interpreted as fixture sizes in inches when they look like
a real size (no leading zero, 4–120) and kept as-is otherwise, so ``-14`` →
``14"`` but a version index like ``-01`` stays ``01``.
"""

from __future__ import annotations

import re

_HANDLE_RE = re.compile(r"/products/([^/?#]+)")
_LAST_SEG_RE = re.compile(r"/([^/?#]+)/?(?:[?#].*)?$")


def _token(tok: str) -> str:
    if tok.isdigit():
        if len(tok) >= 2 and tok[0] != "0" and 4 <= int(tok) <= 120:
            return f'{tok}"'  # plausible fixture size → inches
        return tok            # version index / small number → as-is
    return tok.capitalize()


def humanize_handle(handle: str) -> str:
    parts = [p for p in re.split(r"[-_]+", handle) if p]
    return " ".join(_token(p) for p in parts)


def derive_product_name(title: str | None, product_url: str | None) -> str | None:
    """Best human name: the handle when it's more descriptive than the title."""
    title = (title or "").strip()
    handle = ""
    if product_url:
        m = _HANDLE_RE.search(product_url) or _LAST_SEG_RE.search(product_url)
        if m:
            handle = m.group(1)
    if not handle:
        return title or None
    human = humanize_handle(handle)
    if human and len(human.split()) > len(title.split()):
        return human
    return title or human or None
