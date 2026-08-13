"""Database connection and session management for Wazi.

Uses SQLAlchemy with a synchronous engine. For an MVP with low traffic,
synchronous calls are simpler and sufficient. Upgrade to async if
concurrency becomes a bottleneck.

Usage:
    from src.shared.database import get_session, init_db

    # Once, at app startup:
    init_db()

    # Per-request:
    with get_session() as session:
        user = session.query(User).filter_by(hashed_wa_id=...).first()
"""

import os
from collections.abc import Generator
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as DBSession, sessionmaker

from src.shared.models import Base

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://wazi:wazi_password@localhost:5432/wazi_db",
)

# The engine is a module-level singleton — created once, reused across requests.
_engine = create_engine(
    DATABASE_URL,
    echo=False,             # Set to True to see SQL in logs (dev only)
    pool_size=5,            # Max 5 concurrent connections (enough for MVP)
    pool_pre_ping=True,     # Verify connection is alive before using it
)

# Session factory — call get_session() for each unit of work.
_SessionFactory = sessionmaker(bind=_engine)


def init_db() -> None:
    """Create all tables if they don't exist.

    Call once at application startup. Safe to call repeatedly.
    Enables the pgvector extension before creating tables so the
    ``VECTOR(384)`` column type is recognised.

    The ``CREATE EXTENSION`` step is Postgres-only; it is skipped on other
    dialects (e.g. the SQLite used in tests / local boots) so the app can
    still start there without the vector-backed retrieval path.
    """
    if _engine.dialect.name == "postgresql":
        with _engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    Base.metadata.create_all(_engine)


@contextmanager
def get_session() -> Generator[DBSession, None, None]:
    """Yield a database session for a single unit of work.

    Use as a context manager:
        with get_session() as session:
            ...

    The session is automatically closed when the context exits.
    """
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def drop_all() -> None:
    """Drop all tables. DEVELOPMENT USE ONLY — never in production."""
    Base.metadata.drop_all(_engine)
