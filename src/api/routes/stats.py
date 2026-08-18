"""Corpus health and statistics API route.

GET /api/stats returns aggregate counts for the admin dashboard.
All endpoints require admin authentication.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func

from src.api.middleware.auth import verify_admin
from src.shared.database import get_session
from src.shared.models import (
    Chunk,
    Dispute,
    DisputeStatus,
    IngestionStatus,
    Message,
    Source,
    User,
)

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats(token: str = Depends(verify_admin)) -> dict:
    """Return aggregate corpus and usage statistics."""
    with get_session() as session:
        # --- Single-query aggregates with GROUP BY (not 14 separate COUNTs) ---
        source_status_rows = (
            session.query(
                Source.ingestion_status,
                func.count(Source.id).label("cnt"),
            )
            .group_by(Source.ingestion_status)
            .all()
        )
        sources_by_status = {row[0].value: row[1] for row in source_status_rows}
        # Ensure every enum value appears (even if count is 0).
        for s in IngestionStatus:
            sources_by_status.setdefault(s.value, 0)

        # The moderation queue is grouped by answer; count distinct disputed
        # answers (not per-reporter rows), using each answer's earliest report
        # as its representative status.
        dispute_reps = (
            session.query(func.min(Dispute.id).label("rid"))
            .group_by(Dispute.message_id)
            .subquery()
        )
        dispute_status_rows = (
            session.query(Dispute.status, func.count(Dispute.id).label("cnt"))
            .join(dispute_reps, Dispute.id == dispute_reps.c.rid)
            .group_by(Dispute.status)
            .all()
        )
        disputes_by_status = {row[0].value: row[1] for row in dispute_status_rows}
        for d in DisputeStatus:
            disputes_by_status.setdefault(d.value, 0)
        total_disputes = sum(disputes_by_status.values())

        # --- Date range of sources ---
        oldest = (
            session.query(Source.published_at)
            .filter(Source.published_at.isnot(None))
            .order_by(Source.published_at.asc())
            .first()
        )
        newest = (
            session.query(Source.published_at)
            .filter(Source.published_at.isnot(None))
            .order_by(Source.published_at.desc())
            .first()
        )

        # --- Last ingestion ---
        last_completed = (
            session.query(Source.last_scraped_at)
            .filter(Source.ingestion_status == IngestionStatus.COMPLETED,
                    Source.last_scraped_at.isnot(None))
            .order_by(Source.last_scraped_at.desc())
            .first()
        )

        # --- Query volume (today / this week) ---
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - __time_since_monday(today_start)

        queries_today = (
            session.query(func.count(Message.id))
            .filter(Message.role == "user", Message.created_at >= today_start)
            .scalar()
        )
        queries_this_week = (
            session.query(func.count(Message.id))
            .filter(Message.role == "user", Message.created_at >= week_start)
            .scalar()
        )

        return {
            "total_sources": session.query(func.count(Source.id)).scalar(),
            "sources_by_status": sources_by_status,
            "total_chunks": session.query(func.count(Chunk.id)).scalar(),
            "total_messages": session.query(func.count(Message.id)).scalar(),
            "total_disputes": total_disputes,
            "disputes_by_status": disputes_by_status,
            "last_ingestion_at": (
                last_completed[0].isoformat() if last_completed else None
            ),
            "oldest_source_date": oldest[0].isoformat() if oldest else None,
            "newest_source_date": newest[0].isoformat() if newest else None,
            "unique_citizens": session.query(func.count(User.id)).scalar(),
            "queries_today": queries_today or 0,
            "queries_this_week": queries_this_week or 0,
        }


def __time_since_monday(today: datetime) -> "timedelta":
    """Return a timedelta to subtract to reach the most recent Monday."""
    from datetime import timedelta
    return timedelta(days=today.weekday())
