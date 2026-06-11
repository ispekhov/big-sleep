"""Database engine/session wiring (SQLAlchemy 2.0)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

# SQLite needs check_same_thread off when used across FastAPI threads.
_connect_args = (
    {"check_same_thread": False}
    if _settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    _settings.database_url, future=True, connect_args=_connect_args
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create all tables. Use Alembic for real migrations in production."""
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and background work."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
