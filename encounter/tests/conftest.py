"""Test configuration.

Sets env vars to an isolated temp dir BEFORE any ``encounter`` module is
imported, so the cached Settings point at a throwaway SQLite DB and local
storage. Also provides image/session helpers.
"""

from __future__ import annotations

import io
import os
import tempfile

# Must run before importing encounter.* so get_settings() caches these.
_TMP = tempfile.mkdtemp(prefix="encounter-test-")
os.environ.setdefault("ENCOUNTER_DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("ENCOUNTER_STORAGE_LOCAL_DIR", f"{_TMP}/storage")

import pytest  # noqa: E402
from PIL import Image as PILImage, ImageDraw  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from encounter.db import Base  # noqa: E402


def make_jpeg(color=(200, 60, 40), seed: int = 0, size: int = 128) -> bytes:
    """Deterministic non-trivial JPEG for a given colour/seed."""
    import random

    rng = random.Random(sum(color) + seed)
    img = PILImage.new("RGB", (size, size), (18, 18, 22))
    draw = ImageDraw.Draw(img)
    for _ in range(5):
        x0, y0 = rng.randint(0, size - 40), rng.randint(0, size - 40)
        draw.ellipse([x0, y0, x0 + 40, y0 + 40], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


@pytest.fixture
def session():
    """Fresh in-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sess = Local()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()
