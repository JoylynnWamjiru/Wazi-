"""Tests for the anti-bot dispute guards.

Marked ``db`` — uses the in-memory SQLite fixture, no PostgreSQL needed
(disputes/messages/users tables have no pgvector column).
"""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def answer(seed):
    """A user + session + one assistant answer to report against."""
    uid = seed.user("hash_reporter")
    sid = seed.session(uid)
    aid = seed.message(sid, "assistant", "Kshs 14.13 bilioni. Chanzo: nakuru_birr_q1.pdf")
    return {"user_id": uid, "session_id": sid, "answer_id": aid}


def test_first_report_is_created_but_not_yet_flagged(answer):
    from src.api.middleware.anti_bot import create_dispute

    v = create_dispute(answer["answer_id"], answer["user_id"])
    assert v["created"] is True
    assert v["reason"] == "created"
    assert v["report_count"] == 1
    assert v["flagged_for_review"] is False


def test_same_identity_cannot_report_the_same_answer_twice(answer):
    from src.api.middleware.anti_bot import create_dispute

    create_dispute(answer["answer_id"], answer["user_id"])
    dup = create_dispute(answer["answer_id"], answer["user_id"])
    assert dup["created"] is False
    assert dup["reason"] == "duplicate"
    assert dup["report_count"] == 1  # still just the one distinct reporter


def test_velocity_blocks_a_second_report_within_the_window(seed):
    from src.api.middleware.anti_bot import create_dispute

    uid = seed.user("hash_fast")
    sid = seed.session(uid)
    a1 = seed.message(sid, "assistant", "answer one")
    a2 = seed.message(sid, "assistant", "answer two")

    first = create_dispute(a1, uid)
    assert first["created"] is True

    # Different answer, same identity, immediately after → rate limited.
    second = create_dispute(a2, uid)
    assert second["created"] is False
    assert second["reason"] == "rate_limited"
    assert second["retry_after"] is not None and second["retry_after"] > 0


def test_diversity_flags_only_after_three_distinct_reporters(seed):
    from src.api.middleware.anti_bot import create_dispute

    owner = seed.user("hash_owner")
    sid = seed.session(owner)
    aid = seed.message(sid, "assistant", "disputed answer")

    reporters = [seed.user(f"hash_r{i}") for i in range(3)]
    verdicts = [create_dispute(aid, uid) for uid in reporters]

    assert [v["report_count"] for v in verdicts] == [1, 2, 3]
    assert [v["flagged_for_review"] for v in verdicts] == [False, False, True]


def test_cannot_report_a_user_message(seed):
    from src.api.middleware.anti_bot import create_dispute

    uid = seed.user("hash_u")
    sid = seed.session(uid)
    question_id = seed.message(sid, "user", "swali langu")

    v = create_dispute(question_id, uid)
    assert v["created"] is False
    assert v["reason"] == "not_an_answer"


def test_reporting_a_nonexistent_message(seed):
    from src.api.middleware.anti_bot import create_dispute

    uid = seed.user("hash_u")
    v = create_dispute(999_999, uid)
    assert v["created"] is False
    assert v["reason"] == "message_not_found"
