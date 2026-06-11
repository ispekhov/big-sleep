"""Database engine/session wiring (SQLAlchemy 2.0)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

_engine_kwargs: dict = {"future": True}
if _settings.database_url.startswith("sqlite"):
    # SQLite needs check_same_thread off when used across FastAPI threads.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif _settings.serverless_db:
    # Behind a transaction pooler (Supabase/pgbouncer) each lambda invocation
    # is short-lived: don't keep a client-side pool and disable psycopg's
    # prepared statements (incompatible with transaction pooling).
    _engine_kwargs["poolclass"] = NullPool
    _engine_kwargs["connect_args"] = {"prepare_threshold": None}

engine = create_engine(_settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create all tables. Use Alembic/SQL migrations in production."""
    from . import models  # noqa: F401  (register mappers)

    if not _settings.auto_create_tables:
        return
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
