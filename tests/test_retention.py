"""Tests for the data-retention policy (scripts/retention.py).

Marked ``db`` — in-memory SQLite fixture, controlled clock. Verifies the
90-day / 365-day interaction: a message under a surviving dispute is kept
even past 90 days, and removed only once its dispute also expires.
"""

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.db

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def _days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


@pytest.fixture
def scenario(db):
    """Build a fixed corpus of aged messages + disputes. Returns their ids."""
    from src.shared.models import Dispute, DisputeStatus, Message, Session, User

    with db.get_session() as s:
        owner = User(hashed_wa_id="owner")
        r1 = User(hashed_wa_id="reporter1")
        r2 = User(hashed_wa_id="reporter2")
        s.add_all([owner, r1, r2])
        s.flush()

        sess = Session(user_id=owner.id)
        s.add(sess)
        s.flush()

        def msg(age_days, text):
            m = Message(session_id=sess.id, role="assistant", text=text,
                        created_at=_days_ago(age_days))
            s.add(m)
            s.flush()
            return m.id

        recent = msg(10, "recent answer")
        old_orphan = msg(100, "old answer, no dispute")
        protected = msg(100, "old answer under a fresh dispute")
        expiring = msg(100, "old answer under a stale dispute")

        # Fresh dispute (30d) protects `protected`; stale dispute (400d) on
        # `expiring` will be purged, freeing that message.
        s.add(Dispute(message_id=protected, reported_by_user_id=r1.id,
                      status=DisputeStatus.PENDING_REVIEW, created_at=_days_ago(30)))
        s.add(Dispute(message_id=expiring, reported_by_user_id=r2.id,
                      status=DisputeStatus.PENDING_REVIEW, created_at=_days_ago(400)))
        s.flush()

    return {"recent": recent, "old_orphan": old_orphan,
            "protected": protected, "expiring": expiring}


def _counts(db):
    from src.shared.models import Dispute, Message
    with db.get_session() as s:
        return s.query(Message).count(), s.query(Dispute).count()


def test_dry_run_deletes_nothing(scenario, db):
    from scripts.retention import purge

    result = purge(now=NOW, dry_run=True)

    assert result["disputes_deleted"] == 1   # the 400-day dispute
    assert result["messages_deleted"] == 2   # old_orphan + expiring
    assert _counts(db) == (4, 2)             # nothing actually removed


def test_purge_respects_the_dispute_interaction(scenario, db):
    from scripts.retention import purge
    from src.shared.models import Message

    purge(now=NOW)

    messages_left, disputes_left = _counts(db)
    assert messages_left == 2   # recent + protected survive
    assert disputes_left == 1   # only the fresh dispute survives

    with db.get_session() as s:
        surviving_ids = {m.id for m in s.query(Message).all()}
    assert scenario["recent"] in surviving_ids
    assert scenario["protected"] in surviving_ids       # kept by fresh dispute
    assert scenario["old_orphan"] not in surviving_ids
    assert scenario["expiring"] not in surviving_ids     # freed once dispute purged


def test_purge_is_idempotent(scenario, db):
    from scripts.retention import purge

    purge(now=NOW)
    second = purge(now=NOW)

    assert second["disputes_deleted"] == 0
    assert second["messages_deleted"] == 0
