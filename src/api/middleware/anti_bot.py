"""Anti-bot guards for citizen dispute reports.

A dispute ("this answer is wrong") is a trust signal. Without guards, a
single actor could inflate a message's report count — either to bury a
correct answer or to manufacture the appearance of consensus. These
checks make that expensive:

1. DEDUP     — one hashed identity can report a given answer at most once.
2. VELOCITY  — an identity must wait ``VELOCITY_WINDOW_SECONDS`` between
               reports, so a script can't machine-gun many messages.
3. DIVERSITY — an answer is only "flagged for review" once
               ``DIVERSITY_THRESHOLD`` *distinct* identities report it.
               A lone report is recorded but never surfaced as consensus.

The dispute record is always inserted once dedup + velocity pass — we
need the row to count distinct reporters for the diversity check. The
diversity threshold governs *surfacing*, not creation.

SECURITY: this module works only with the integer ``user_id`` (the FK to
``users.id``, which is itself derived from a hashed wa_id). No raw phone
number ever reaches here.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from src.shared.database import get_session
from src.shared.models import Dispute, DisputeStatus, Message

# --- Tunable thresholds -----------------------------------------------------

# Minimum seconds between two reports from the same identity. Blocks a
# script from filing many reports in a burst.
VELOCITY_WINDOW_SECONDS = 30

# Number of DISTINCT identities that must report the same answer before it
# is treated as a review-worthy signal (not just one person's complaint).
DIVERSITY_THRESHOLD = 3


# --- Individual checks (session-scoped, composable, unit-testable) ----------

def already_reported(session, message_id: int, user_id: int) -> bool:
    """True if this identity has already reported this exact answer."""
    return session.query(
        session.query(Dispute)
        .filter(
            Dispute.message_id == message_id,
            Dispute.reported_by_user_id == user_id,
        )
        .exists()
    ).scalar()


def seconds_since_last_report(session, user_id: int) -> float | None:
    """Seconds since this identity's most recent report, or None if never."""
    last = (
        session.query(Dispute.created_at)
        .filter(Dispute.reported_by_user_id == user_id)
        .order_by(Dispute.created_at.desc())
        .first()
    )
    if last is None:
        return None
    created_at = last[0]
    # Stored timestamps are tz-aware (UTC); guard against naive rows.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created_at).total_seconds()


def distinct_reporter_count(session, message_id: int) -> int:
    """Number of DISTINCT identities that have reported this answer."""
    return (
        session.query(func.count(func.distinct(Dispute.reported_by_user_id)))
        .filter(Dispute.message_id == message_id)
        .scalar()
    ) or 0


# --- Guarded creation service -----------------------------------------------

def create_dispute(message_id: int, user_id: int, reason: str | None = None) -> dict:
    """Attempt to file a dispute, enforcing the anti-bot guards.

    Returns a verdict dict — never raises for the expected rejections, so
    the webhook can turn each outcome into a citizen-facing reply:

        {
          "created": bool,
          "reason": "created" | "message_not_found" | "not_an_answer"
                    | "duplicate" | "rate_limited",
          "report_count": int,          # distinct reporters after this call
          "flagged_for_review": bool,   # crossed DIVERSITY_THRESHOLD
          "retry_after": float | None,  # seconds, only when rate_limited
        }
    """
    with get_session() as session:
        # The report must target a real assistant answer, not a question or
        # a nonexistent id.
        message = session.query(Message).filter_by(id=message_id).first()
        if message is None:
            return _verdict(False, "message_not_found")
        if message.role != "assistant":
            return _verdict(False, "not_an_answer")

        # 1. DEDUP.
        if already_reported(session, message_id, user_id):
            count = distinct_reporter_count(session, message_id)
            return _verdict(
                False, "duplicate",
                report_count=count,
                flagged=count >= DIVERSITY_THRESHOLD,
            )

        # 2. VELOCITY.
        elapsed = seconds_since_last_report(session, user_id)
        if elapsed is not None and elapsed < VELOCITY_WINDOW_SECONDS:
            return _verdict(
                False, "rate_limited",
                retry_after=round(VELOCITY_WINDOW_SECONDS - elapsed, 1),
            )

        # Guards passed — record the dispute.
        try:
            session.add(
                Dispute(
                    message_id=message_id,
                    reported_by_user_id=user_id,
                    reason=reason,
                    status=DisputeStatus.PENDING_REVIEW,
                )
            )
            session.flush()
        except IntegrityError:
            # Race: another request inserted the same (message, reporter)
            # between our dedup check and this insert.  The UNIQUE
            # constraint caught it — treat as a duplicate, not a crash.
            session.rollback()
            count = distinct_reporter_count(session, message_id)
            return _verdict(
                False, "duplicate",
                report_count=count,
                flagged=count >= DIVERSITY_THRESHOLD,
            )

        # 3. DIVERSITY (computed after insert, includes this report).
        count = distinct_reporter_count(session, message_id)
        flagged = count >= DIVERSITY_THRESHOLD
        # Denormalize the aggregate onto EVERY row for this answer so the
        # grouped moderation queue reads a single, current signal per answer
        # without recomputing it.
        session.query(Dispute).filter(Dispute.message_id == message_id).update(
            {"report_count": count, "flagged_for_review": flagged},
            synchronize_session=False,
        )
        return _verdict(
            True, "created",
            report_count=count,
            flagged=flagged,
        )


def _verdict(
    created: bool,
    reason: str,
    *,
    report_count: int = 0,
    flagged: bool = False,
    retry_after: float | None = None,
) -> dict:
    return {
        "created": created,
        "reason": reason,
        "report_count": report_count,
        "flagged_for_review": flagged,
        "retry_after": retry_after,
    }
