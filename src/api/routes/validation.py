"""Linguist validation API routes (strategic plan §6.1).

The answer-feedback loop: native speakers review generated answers and rate
them on tone, grounding, and register. That data guides system-prompt
improvement. All endpoints require admin authentication.

    GET  /api/validation/queue   — answers awaiting review (random, unrated)
    POST /api/validation/{id}    — submit a rating for an answer
    GET  /api/validation/stats   — aggregate quality metrics
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func

from src.api.middleware.auth import verify_admin
from src.shared.database import get_session
from src.shared.models import Message, Validation, ValidationRegister

router = APIRouter(prefix="/api/validation", tags=["validation"])


class ValidationCreate(BaseModel):
    # `register_` avoids shadowing a BaseModel attribute; the wire field stays
    # "register" via the alias.
    model_config = ConfigDict(populate_by_name=True)

    tone_score: int          # 1-5
    grounded: bool
    register_: str = Field(alias="register")  # one of ValidationRegister
    notes: str | None = None


def _question_for(session, answer: Message) -> str | None:
    """The user question immediately preceding an assistant answer."""
    user_msg = (
        session.query(Message)
        .filter(
            Message.session_id == answer.session_id,
            Message.role == "user",
            Message.id < answer.id,
        )
        .order_by(Message.id.desc())
        .first()
    )
    return user_msg.text if user_msg else None


# ---------------------------------------------------------------------------
# GET /api/validation/queue
# ---------------------------------------------------------------------------
@router.get("/queue")
def validation_queue(limit: int = 10, token: str = Depends(verify_admin)) -> dict:
    """Return assistant answers that have not been rated yet, in random order.

    Each item carries the original question, the answer, and its citation so a
    linguist has the full context needed to judge tone/grounding/register.
    """
    with get_session() as session:
        rated = session.query(Validation.message_id)
        answers = (
            session.query(Message)
            .filter(Message.role == "assistant", Message.id.notin_(rated))
            .order_by(func.random())
            .limit(limit)
            .all()
        )

        return {
            "queue": [
                {
                    "message_id": a.id,
                    "question": _question_for(session, a),
                    "answer": a.text,
                    "citation": a.citation,
                }
                for a in answers
            ],
            "count": len(answers),
        }


# ---------------------------------------------------------------------------
# POST /api/validation/{message_id}
# ---------------------------------------------------------------------------
@router.post("/{message_id}", status_code=status.HTTP_201_CREATED)
def submit_validation(
    message_id: int,
    body: ValidationCreate,
    token: str = Depends(verify_admin),
) -> dict:
    """Record a linguist's rating of an answer."""
    if not 1 <= body.tone_score <= 5:
        raise HTTPException(status_code=422, detail="tone_score must be between 1 and 5")

    try:
        register = ValidationRegister(body.register_)
    except ValueError:
        allowed = ", ".join(r.value for r in ValidationRegister)
        raise HTTPException(
            status_code=422, detail=f"register must be one of: {allowed}"
        )

    with get_session() as session:
        answer = session.query(Message).filter_by(id=message_id).first()
        if answer is None:
            raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
        if answer.role != "assistant":
            raise HTTPException(
                status_code=422,
                detail="Only assistant answers can be validated, not user questions.",
            )

        record = Validation(
            message_id=message_id,
            tone_score=body.tone_score,
            grounded=body.grounded,
            register=register,
            reviewer="linguist",
            notes=body.notes,
        )
        session.add(record)
        session.flush()

        return {
            "id": record.id,
            "message_id": message_id,
            "tone_score": record.tone_score,
            "grounded": record.grounded,
            "register": register.value,
        }


# ---------------------------------------------------------------------------
# GET /api/validation/stats
# ---------------------------------------------------------------------------
@router.get("/stats")
def validation_stats(token: str = Depends(verify_admin)) -> dict:
    """Aggregate quality metrics across all validations."""
    with get_session() as session:
        total = session.query(func.count(Validation.id)).scalar() or 0

        avg_tone = session.query(func.avg(Validation.tone_score)).scalar()
        grounded_count = (
            session.query(func.count(Validation.id))
            .filter(Validation.grounded.is_(True))
            .scalar()
        ) or 0

        register_rows = (
            session.query(Validation.register, func.count(Validation.id))
            .group_by(Validation.register)
            .all()
        )
        by_register = {r.value: 0 for r in ValidationRegister}
        for reg, cnt in register_rows:
            by_register[reg.value] = cnt

        # How many assistant answers still await a first review.
        rated = session.query(Validation.message_id)
        pending = (
            session.query(func.count(Message.id))
            .filter(Message.role == "assistant", Message.id.notin_(rated))
            .scalar()
        ) or 0

        return {
            "total_validations": total,
            "average_tone": round(float(avg_tone), 2) if avg_tone is not None else None,
            "grounded_count": grounded_count,
            "grounded_pct": round(100 * grounded_count / total, 1) if total else None,
            "by_register": by_register,
            "pending_review": pending,
        }
