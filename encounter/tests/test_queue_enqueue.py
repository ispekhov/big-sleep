from encounter.models import BrandQueue
from encounter.queueing import enqueue_brands, normalize_url, parse_lines


def test_normalize_url_adds_scheme_and_canonicalises():
    assert normalize_url("rollandhill.com") == "https://rollandhill.com"
    assert normalize_url("https://RollAndHill.com/") == "https://rollandhill.com"
    assert normalize_url("  https://gubi.com/products/  ") == "https://gubi.com/products"
    assert normalize_url("") is None


def test_normalize_url_rejects_empty_and_hostless():
    assert normalize_url("   ") is None
    assert normalize_url("https://") is None


def test_enqueue_dedupes_within_batch_and_against_existing(session):
    items = [
        ("rollandhill.com", "Roll & Hill"),
        ("https://RollAndHill.com/", None),   # same brand, different form
        ("https://gubi.com", "Gubi"),
        ("", None),                            # invalid
    ]
    result = enqueue_brands(session, items)
    assert result.added == 2
    assert result.skipped_existing == 1
    assert result.invalid == [""]
    assert result.pending == 2

    rows = {r.url: r for r in session.scalars(select_all()).all()}
    assert "https://rollandhill.com" in rows
    assert rows["https://rollandhill.com"].name == "Roll & Hill"
    assert rows["https://rollandhill.com"].status == "pending"

    # Re-submitting the same list adds nothing new (both R&H forms + Gubi
    # already exist = 3 skipped; the empty line is invalid, not skipped).
    again = enqueue_brands(session, items)
    assert again.added == 0
    assert again.skipped_existing == 3
    assert again.pending == 2


def test_parse_lines_handles_names_blanks_and_comments():
    text = "rollandhill.com\n# a comment\n\nhttps://gubi.com, Gubi\n"
    assert parse_lines(text) == [
        ("rollandhill.com", None),
        ("https://gubi.com", "Gubi"),
    ]


def select_all():
    from sqlalchemy import select

    return select(BrandQueue)
