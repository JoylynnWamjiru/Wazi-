"""Session and message listing API routes.

GET /api/sessions — list conversation sessions for the admin browser.
GET /api/messages — list messages, optionally filtered by session_id.
All endpoints require admin authentication.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from src.api.middleware.auth import verify_admin
from src.shared.database import get_session as db_session
from src.shared.models import Message, Session

router = APIRouter(prefix="/api", tags=["sessions"])


@router.get("/sessions")
def list_sessions(
    limit: int = 20,
    offset: int = 0,
    is_active: bool | None = None,
    token: str = Depends(verify_admin),
) -> dict:
    """List conversation sessions, most active first.

    Uses a single query with subquery-loaded aggregates to avoid N+1:
    one query for sessions + one query for message counts/timestamps,
    instead of 1 + N individual queries.
    """
    with db_session() as session:
        # Subquery: per-session message stats.
        msg_stats = (
            session.query(
                Message.session_id,
                func.count(Message.id).label("cnt"),
                func.min(Message.created_at).label("first_at"),
                func.max(Message.created_at).label("last_at"),
            )
            .group_by(Message.session_id)
            .subquery()
        )

        query = (
            session.query(
                Session,
                func.coalesce(msg_stats.c.cnt, 0).label("message_count"),
                msg_stats.c.first_at,
                msg_stats.c.last_at,
            )
            .outerjoin(msg_stats, Session.id == msg_stats.c.session_id)
        )

        if is_active is not None:
            query = query.filter(Session.is_active == is_active)

        total = query.count()
        rows = (
            query
            .order_by(msg_stats.c.last_at.desc().nullslast())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "sessions": [
                {
                    "id": s.id,
                    "user_id": s.user_id,
                    "is_active": s.is_active,
                    "message_count": message_count,
                    "first_message_at": (
                        first_at.isoformat()
                        if first_at
                        else s.created_at.isoformat()
                    ),
                    "last_message_at": (
                        last_at.isoformat()
                        if last_at
                        else s.created_at.isoformat()
                    ),
                    "created_at": s.created_at.isoformat(),
                }
                for s, message_count, first_at, last_at in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/messages")
def list_messages(
    limit: int = 20,
    offset: int = 0,
    session_id: int | None = None,
    token: str = Depends(verify_admin),
) -> dict:
    """List messages, optionally filtered by session."""
    with db_session() as db:
        query = db.query(Message)

        if session_id is not None:
            # Verify session exists.
            if db.query(Session).filter_by(id=session_id).first() is None:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
            query = query.filter(Message.session_id == session_id)

        total = query.count()
        rows = (
            query
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "messages": [
                {
                    "id": m.id,
                    "session_id": m.session_id,
                    "role": m.role,
                    "text": m.text,
                    "citation": m.citation,
                    "created_at": m.created_at.isoformat(),
                }
                for m in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
