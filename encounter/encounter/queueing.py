"""Bulk brand enqueue for the batch import queue.

The batch engine (``/brands/queue/run``) drains ``BrandQueue`` rows, but until
now nothing *added* them. This is the missing front door: take a list of brand
websites (e.g. discovered from a directory, or a list you maintain), normalise
and de-duplicate them, and insert ``pending`` queue rows for the importer to
work through one brand at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import BrandQueue


@dataclass
class EnqueueResult:
    added: int = 0
    skipped_existing: int = 0
    invalid: list[str] = field(default_factory=list)
    pending: int = 0


def normalize_url(raw: str) -> str | None:
    """Canonicalise a brand URL for de-duplication, or None if unusable.

    Adds a scheme when missing, lower-cases the host, and trims a trailing
    slash so ``rollandhill.com`` and ``https://RollAndHill.com/`` collapse to
    one queue entry.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except Exception:
        return None
    if not parsed.netloc:
        return None
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{netloc}{path}"


def enqueue_brands(
    session: Session, items: list[tuple[str, str | None]]
) -> EnqueueResult:
    """Insert ``pending`` queue rows for ``items`` (``(url, name)`` pairs).

    De-dupes within the batch and against existing queue rows (any status), so
    re-submitting a list only adds the genuinely new brands.
    """
    existing = set(session.scalars(select(BrandQueue.url)).all())
    seen: set[str] = set()
    result = EnqueueResult()
    for raw_url, name in items:
        norm = normalize_url(raw_url)
        if norm is None:
            result.invalid.append(raw_url)
            continue
        if norm in existing or norm in seen:
            result.skipped_existing += 1
            continue
        seen.add(norm)
        clean_name = (name or "").strip() or None
        session.add(BrandQueue(url=norm, name=clean_name, status="pending"))
        result.added += 1
    session.commit()
    result.pending = int(
        session.scalar(
            select(func.count())
            .select_from(BrandQueue)
            .where(BrandQueue.status == "pending")
        )
        or 0
    )
    return result


def parse_lines(text: str) -> list[tuple[str, str | None]]:
    """Parse pasted/file input: one brand per line, ``url`` or ``url, name``."""
    items: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            url, name = line.split(",", 1)
            items.append((url.strip(), name.strip() or None))
        else:
            items.append((line, None))
    return items
