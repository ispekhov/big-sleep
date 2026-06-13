"""Derive a precise, human product name from a product URL handle.

Brand storefronts routinely give every variant the same generic title — Roll &
Hill lists eight different "Cloud" fixtures all titled "Cloud" — while the real
distinction lives in the Shopify handle (``cloud-pendant-14``,
``cloud-floor-lamp-01``). For products with a ``/products/<handle>`` URL we
build the name from that handle; otherwise we keep the page title.

Rules:
- ``14-inch`` / ``14-in`` → ``14"`` (the redundant unit word is dropped), and a
  bare trailing number that looks like a fixture size (no leading zero, 4–120)
  also becomes inches; a version index like ``01`` stays as-is.
- availability noise the brand bakes into URLs (``in-stock``, ``sold-out`` …) is
  stripped — it is not part of a product's name.
"""

from __future__ import annotations

import re

_HANDLE_RE = re.compile(r"/products/([^/?#]+)")
_NOISE_RE = re.compile(
    r"\b(in stock|out of stock|sold out|coming soon|pre[ -]?order|back ?order)\b",
    re.I,
)


def _token(tok: str) -> str:
    if tok.isdigit():
        if len(tok) >= 2 and tok[0] != "0" and 4 <= int(tok) <= 120:
            return f'{tok}"'  # plausible fixture size → inches
        return tok            # version index / small number → as-is
    return tok.capitalize()


def humanize_handle(handle: str) -> str:
    parts = [p for p in re.split(r"[-_]+", handle) if p]
    out: list[str] = []
    i = 0
    while i < len(parts):
        tok = parts[i]
        nxt = parts[i + 1].lower() if i + 1 < len(parts) else ""
        # explicit "<n> inch/inches/in" → "<n>"" and drop the unit word
        if tok.isdigit() and nxt in ("inch", "inches", "in"):
            out.append(f'{int(tok)}"')
            i += 2
            continue
        out.append(_token(tok))
        i += 1
    name = " ".join(out)
    name = _NOISE_RE.sub(" ", name)          # strip availability noise
    name = re.sub(r'\s+(")', r"\1", name)    # tidy stray space before "
    return re.sub(r"\s+", " ", name).strip()


def derive_product_name(title: str | None, product_url: str | None) -> str | None:
    """Precise name from the Shopify handle; fall back to the page title."""
    m = _HANDLE_RE.search(product_url or "")
    if m:
        human = humanize_handle(m.group(1))
        if human:
            return human
    return (title or "").strip() or None
