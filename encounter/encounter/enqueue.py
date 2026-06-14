"""Bulk-enqueue brands into the import queue from a file or stdin.

    python -m encounter.enqueue brands.txt
    cat brands.txt | python -m encounter.enqueue

Input is one brand per line: ``url`` or ``url, Brand Name``. Blank lines and
``#`` comments are ignored. URLs are normalised and de-duplicated. Drain the
queue afterwards with ``/brands/queue/run`` (or the encounter-import workflow).
"""

from __future__ import annotations

import sys

from .db import init_db, session_scope
from .queueing import enqueue_brands, parse_lines


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = open(argv[0], encoding="utf-8").read() if argv else sys.stdin.read()
    items = parse_lines(text)
    if not items:
        print("No brands found in input.", file=sys.stderr)
        return 1

    init_db()
    with session_scope() as session:
        result = enqueue_brands(session, items)

    print(
        f"Enqueued {result.added} new brand(s); "
        f"skipped {result.skipped_existing} already queued; "
        f"{len(result.invalid)} invalid; {result.pending} pending total."
    )
    if result.invalid:
        print("Invalid lines:", file=sys.stderr)
        for bad in result.invalid:
            print(f"  {bad!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
