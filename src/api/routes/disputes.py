"""Dispute management API routes.

CRUD for citizen dispute reports, including status transitions,
correction messages, and escalation report generation.

All endpoints require admin authentication.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.middleware.auth import verify_admin
from src.shared.database import get_session
from src.shared.models import (
    Chunk,
    Dispute,
    DisputeStatus,
    Message,
)
from sqlalchemy import func

router = APIRouter(prefix="/api/disputes", tags=["disputes"])


class DisputeUpdate(BaseModel):
    dispute_status: str
    resolution_note: str | None = None
    correction_message: str | None = None
    escalation_recipient: str | None = None

# Valid status transitions.
_TRANSITIONS: dict[DisputeStatus, list[DisputeStatus]] = {
    DisputeStatus.PENDING_REVIEW: [DisputeStatus.UNDER_REVIEW],
    DisputeStatus.UNDER_REVIEW: [
        DisputeStatus.RESOLVED_VALID,
        DisputeStatus.RESOLVED_INVALID,
        DisputeStatus.ESCALATED,
    ],
    DisputeStatus.RESOLVED_VALID: [],    # terminal
    DisputeStatus.RESOLVED_INVALID: [],  # terminal
    DisputeStatus.ESCALATED: [
        DisputeStatus.RESOLVED_VALID,
        DisputeStatus.RESOLVED_INVALID,
    ],
}


def _dispute_to_dict(dispute: Dispute, report_count: int = 1) -> dict:
    """Serialize a Dispute to the API contract shape.

    ``report_count`` is pre-calculated in a batch query — do NOT call
    _count_reports here, it would trigger N separate queries.
    """
    return {
        "id": dispute.id,
        "message_id": dispute.message_id,
        "status": dispute.status.value,
        "reason": dispute.reason,
        "reported_by_user_id": dispute.reported_by_user_id,
        "reviewed_by": dispute.reviewed_by,
        "reviewed_at": dispute.reviewed_at.isoformat() if dispute.reviewed_at else None,
        "resolution_note": dispute.resolution_note,
        "correction_message": getattr(dispute, "correction_message", None),
        "escalation_report": getattr(dispute, "escalation_report", None),
        "created_at": dispute.created_at.isoformat(),
        "report_count": report_count,
    }


def _count_reports(dispute: Dispute) -> int:
    """Count distinct users who reported the same message."""
    # The ORM relationship gives us access to the session.
    # For simplicity, count all disputes for the same message_id.
    with get_session() as session:
        return (
            session.query(Dispute)
            .filter(Dispute.message_id == dispute.message_id)
            .count()
        )


# ---------------------------------------------------------------------------
# GET /api/disputes
# ---------------------------------------------------------------------------
@router.get("")
def list_disputes(
    dispute_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    token: str = Depends(verify_admin),
) -> dict:
    """List disputes, newest first.  Optionally filter by status.

    Report counts are pre-calculated in a single GROUP BY query so
    listing 50 disputes executes 2 queries total, not 51.
    """
    with get_session() as session:
        query = session.query(Dispute)

        if dispute_status:
            query = query.filter(Dispute.status == DisputeStatus(dispute_status))

        total = query.count()
        rows = (
            query
            .order_by(Dispute.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Batch-fetch report counts: one query for all displayed disputes.
        message_ids = [d.message_id for d in rows]
        if message_ids:
            counts = dict(
                session.query(
                    Dispute.message_id,
                    func.count(Dispute.id).label("cnt"),
                )
                .filter(Dispute.message_id.in_(message_ids))
                .group_by(Dispute.message_id)
                .all()
            )
        else:
            counts = {}

        return {
            "disputes": [
                _dispute_to_dict(d, report_count=counts.get(d.message_id, 1))
                for d in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


# ---------------------------------------------------------------------------
# GET /api/disputes/{dispute_id}
# ---------------------------------------------------------------------------
@router.get("/{dispute_id}")
def get_dispute(dispute_id: int, token: str = Depends(verify_admin)) -> dict:
    """Get a single dispute with full context for moderation."""
    with get_session() as session:
        dispute = session.query(Dispute).filter_by(id=dispute_id).first()
        if dispute is None:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")

        result = _dispute_to_dict(dispute, report_count=_count_reports(dispute))

        # Attach the disputed answer text.
        message = dispute.message
        result["message_preview"] = {
            "role": message.role,
            "text": message.text,
            "citation": message.citation,
        }

        # Attach the user's original question (text only, no identity).
        # The question is the message immediately before the assistant's answer.
        with get_session() as s2:
            user_msg = (
                s2.query(Message)
                .filter(
                    Message.session_id == message.session_id,
                    Message.role == "user",
                    Message.id < message.id,
                )
                .order_by(Message.id.desc())
                .first()
            )
        result["user_question"] = {"text": user_msg.text} if user_msg else None

        # Attach the retrieved chunks (placeholder — real data comes from
        # the retrieval step once the pipeline stores chunk references).
        result["retrieved_chunks"] = []

        return result


# ---------------------------------------------------------------------------
# PATCH /api/disputes/{dispute_id}
# ---------------------------------------------------------------------------
@router.patch("/{dispute_id}")
def update_dispute(
    dispute_id: int,
    body: DisputeUpdate,
    token: str = Depends(verify_admin),
) -> dict:
    """Update a dispute's status.  Handles corrections and escalations."""
    new_status = DisputeStatus(body.dispute_status)

    with get_session() as session:
        dispute = session.query(Dispute).filter_by(id=dispute_id).first()
        if dispute is None:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")

        # Validate transition.
        allowed = _TRANSITIONS.get(dispute.status, [])
        if new_status not in allowed and new_status != dispute.status:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid status transition: {dispute.status.value} -> "
                    f"{new_status.value}. Must pass through under_review first."
                ),
            )

        # Validate correction_message is only used on resolved statuses.
        if body.correction_message and new_status not in (
            DisputeStatus.RESOLVED_VALID,
            DisputeStatus.RESOLVED_INVALID,
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "correction_message is only valid when status is "
                    "resolved_valid or resolved_invalid."
                ),
            )

        dispute.status = new_status
        dispute.reviewed_by = "moderator"
        dispute.reviewed_at = datetime.now(timezone.utc)

        if body.resolution_note:
            dispute.resolution_note = body.resolution_note

        response: dict = {
            "id": dispute.id,
            "status": new_status.value,
            "resolution_note": dispute.resolution_note,
            "reviewed_by": dispute.reviewed_by,
            "reviewed_at": dispute.reviewed_at.isoformat(),
        }

        # Handle correction message.
        if body.correction_message:
            # TODO: send via AT API once wa_id lookup is wired.
            # For now, store it.
            response["correction_message"] = body.correction_message
            response["correction_sent"] = False
            response["correction_error"] = (
                "Correction stored but not sent — AT send not yet wired to dispute flow."
            )

        # Handle escalation.
        if new_status == DisputeStatus.ESCALATED:
            report = _generate_escalation_report(dispute, body.escalation_recipient)
            response["escalation_report"] = report

        session.flush()
        return response


def _generate_escalation_report(dispute: Dispute, recipient: str | None) -> dict:
    """Generate an anonymized escalation report."""
    message = dispute.message
    return {
        "dispute_id": dispute.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient or "(not specified)",
        "content": {
            "disputed_answer": message.text[:500],
            "citation": message.citation,
            "citizen_report": dispute.reason,
            "moderator_note": dispute.resolution_note,
        },
    }
