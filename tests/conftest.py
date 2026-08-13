"""Shared pytest fixtures.

The DB fixture stands up an **in-memory SQLite** database and rebinds the
app's session factory to it, so tests that touch users/sessions/messages/
disputes run with no PostgreSQL, no Docker, and no network.

Why SQLite works here: none of those four tables use pgvector. Only the
``chunks`` table has a ``VECTOR(384)`` column, which SQLite can't create —
so we deliberately create only the non-vector tables. Retrieval tests that
need real vectors are marked ``@pytest.mark.pgvector`` and run on the VPS.

The rebind trick: modules do ``from src.shared.database import get_session``,
but ``get_session()`` reads ``database._SessionFactory`` from the module
global *at call time*. Monkeypatching that global therefore redirects every
caller (webhook, anti_bot, routes) to the test database with no per-module
patching.
"""

import os
import tempfile

import pytest

# Importing ``src.shared.database`` builds the engine at module load. Point it
# at a throwaway SQLite file so that import needs no psycopg2/Postgres — the DB
# tests below never use this engine (they patch in an in-memory factory), but
# the module-level engine must still construct. A file URL (not ":memory:") so
# the default QueuePool accepts the ``pool_size`` kwarg. Set before any import.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    tempfile.gettempdir(), "wazi_test_import.db"
)


@pytest.fixture
def db(monkeypatch):
    """Rebind the app to a fresh in-memory SQLite DB for one test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.shared import database
    from src.shared.models import Base, Dispute, Message, Session, Source, User

    # StaticPool + shared connection so every session sees the same in-memory
    # DB (a plain "sqlite://" gives each connection its own empty database).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create only the tables that don't depend on pgvector.
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Session.__table__,
            Message.__table__,
            Dispute.__table__,
            Source.__table__,
        ],
    )

    monkeypatch.setattr(database, "_SessionFactory", sessionmaker(bind=engine))
    return database


# --- Small seed helpers (return ids, keep tests terse) ----------------------

@pytest.fixture
def seed(db):
    """Return helpers that create rows via the patched session factory."""
    from src.shared.models import Message, Session, User

    class Seed:
        def user(self, hashed: str) -> int:
            with db.get_session() as s:
                u = User(hashed_wa_id=hashed)
                s.add(u)
                s.flush()
                return u.id

        def session(self, user_id: int) -> int:
            with db.get_session() as s:
                sess = Session(user_id=user_id)
                s.add(sess)
                s.flush()
                return sess.id

        def message(self, session_id: int, role: str, text: str) -> int:
            with db.get_session() as s:
                m = Message(session_id=session_id, role=role, text=text)
                s.add(m)
                s.flush()
                return m.id

    return Seed()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Reset the process-wide webhook limiters around every test.

    They are module-level singletons, so without this a test that sends many
    webhook messages could leak rate-limit state into the next test.
    """
    from src.api.middleware.rate_limit import block_notice_limiter, webhook_limiter

    webhook_limiter.reset()
    block_notice_limiter.reset()
    yield
    webhook_limiter.reset()
    block_notice_limiter.reset()
