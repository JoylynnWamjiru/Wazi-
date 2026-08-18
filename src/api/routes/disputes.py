"""Dispute management API routes.

CRUD for citizen dispute reports, including status transitions,
correction messages, and escalation report generation.

All endpoints require admin authentication.
"""

import json
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
    status: str
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


def _dispute_to_dict(dispute: Dispute) -> dict:
    """Serialize a Dispute to the API contract shape.

    ``report_count`` and ``flagged_for_review`` are denormalized onto the row
    by ``create_dispute``, so no extra queries are needed here.
    """
    return {
        "id": dispute.id,
        "message_id": dispute.message_id,
        "status": dispute.status.value,
        "reason": dispute.reason,
        "reported_by_user_id": dispute.reported_by_user_id,
        "report_count": dispute.report_count,
        "flagged_for_review": dispute.flagged_for_review,
        "reviewed_by": dispute.reviewed_by,
        "reviewed_at": dispute.reviewed_at.isoformat() if dispute.reviewed_at else None,
        "resolution_note": dispute.resolution_note,
        "correction_message": getattr(dispute, "correction_message", None),
        "escalation_report": (
            json.loads(dispute.escalation_report) if dispute.escalation_report else None
        ),
        "created_at": dispute.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /api/disputes
# ---------------------------------------------------------------------------
@router.get("")
def list_disputes(
    dispute_status: str | None = None,
    flagged: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    token: str = Depends(verify_admin),
) -> dict:
    """List disputed answers, newest first.

    The queue is grouped by ``message_id`` — one entry per disputed answer,
    represented by its earliest report.  ``flagged`` filters to answers that
    have / have not crossed the diversity threshold.
    """
    with get_session() as session:
        # One representative row per disputed answer: its earliest report.
        # report_count / flagged_for_review are denormalized onto every row by
        # create_dispute, so the representative already carries the aggregate.
        reps = (
            session.query(
                Dispute.message_id,
                func.min(Dispute.id).label("primary_id"),
                func.max(Dispute.created_at).label("last_reported_at"),
            )
            .group_by(Dispute.message_id)
            .subquery()
        )
        query = (
            session.query(Dispute, reps.c.last_reported_at)
            .join(reps, Dispute.id == reps.c.primary_id)
        )

        if dispute_status:
            query = query.filter(Dispute.status == DisputeStatus(dispute_status))
        if flagged is not None:
            query = query.filter(Dispute.flagged_for_review.is_(flagged))

        total = query.count()
        rows = (
            query
            .order_by(reps.c.last_reported_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "disputes": [_dispute_to_dict(d) for d, _last in rows],
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

        result = _dispute_to_dict(dispute)

        # Attach the disputed answer text.
        message = dispute.message
        result["message_preview"] = {
            "role": message.role,
            "text": message.text,
            "citation": message.citation,
        }

        # Attach the user's original question (text only, no identity).
        # The question is the message immediately before the assistant's answer.
        # Read the text INSIDE the session: get_session() commits + closes on
        # exit, which expires attributes — touching user_msg.text afterwards
        # raises sqlalchemy.orm.exc.DetachedInstanceError.
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
            question_text = user_msg.text if user_msg else None
        result["user_question"] = {"text": question_text} if question_text else None

        # Attach the retrieved source passages the model was shown.
        result["retrieved_chunks"] = (
            json.loads(message.retrieved_chunks)
            if getattr(message, "retrieved_chunks", None)
            else []
        )

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
    new_status = DisputeStatus(body.status)

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

        now = datetime.now(timezone.utc)
        dispute.status = new_status
        dispute.reviewed_by = "moderator"
        dispute.reviewed_at = now

        if body.resolution_note:
            dispute.resolution_note = body.resolution_note

        # The queue groups reports by answer — keep every report row for this
        # answer on the same status so the grouped view and per-status stats
        # stay coherent.
        sibling_updates = {
            "status": new_status,
            "reviewed_by": "moderator",
            "reviewed_at": now,
        }
        if body.resolution_note:
            sibling_updates["resolution_note"] = body.resolution_note
        session.query(Dispute).filter(
            Dispute.message_id == dispute.message_id
        ).update(sibling_updates, synchronize_session=False)

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

        # Handle escalation — generate the anonymized report AND persist it so
        # the moderation view can show the template + packaged proof after the
        # fact (the email send itself is still manual).
        if new_status == DisputeStatus.ESCALATED:
            report = _generate_escalation_report(dispute, body.escalation_recipient)
            dispute.escalation_report = json.dumps(report)
            response["escalation_report"] = report

        session.flush()
        return response


def _generate_escalation_report(dispute: Dispute, recipient: str | None) -> dict:
    """Generate an anonymized escalation report.

    Packages the disputed answer, its citation, and the exact source passages
    the model was shown — the proof the recipient needs to verify the source is
    wrong — without any citizen identity.
    """
    message = dispute.message
    passages = (
        json.loads(message.retrieved_chunks)
        if getattr(message, "retrieved_chunks", None)
        else []
    )
    return {
        "dispute_id": dispute.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient or "(not specified)",
        "content": {
            "disputed_answer": message.text[:500],
            "citation": message.citation,
            "retrieved_passages": passages,
            "citizen_report": dispute.reason,
            "moderator_note": dispute.resolution_note,
        },
    }
