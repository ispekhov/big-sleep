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
else:
    _connect_args: dict = {}
    if _settings.serverless_db:
        # Behind a transaction pooler (Supabase/pgbouncer) each lambda
        # invocation is short-lived: don't keep a client-side pool and disable
        # psycopg's prepared statements (incompatible with transaction pooling).
        _engine_kwargs["poolclass"] = NullPool
        _connect_args["prepare_threshold"] = None
    if _settings.db_schema:
        # Pin search_path so the app only touches its own schema, even when
        # connecting through a shared/superuser role.
        _connect_args["options"] = f"-c search_path={_settings.db_schema}"
    if _connect_args:
        _engine_kwargs["connect_args"] = _connect_args

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
