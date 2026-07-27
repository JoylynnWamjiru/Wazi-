"""Source registry API routes.

CRUD for government documents in the ingestion pipeline.
All endpoints require admin authentication.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func

from src.api.middleware.auth import verify_admin
from src.shared.database import get_session
from src.shared.models import (
    Chunk,
    GovernmentArm,
    IngestionStatus,
    ReportType,
    Source,
)

router = APIRouter(prefix="/api/sources", tags=["sources"])


# --- Pydantic schemas ---

class SourceCreate(BaseModel):
    url: str
    title: str
    publisher: str
    government_arm: str
    county: str
    report_type: str
    fiscal_year: str | None = None


class SourceUpdate(BaseModel):
    url: str | None = None
    title: str | None = None
    publisher: str | None = None
    government_arm: str | None = None
    county: str | None = None
    report_type: str | None = None
    fiscal_year: str | None = None


def _source_to_dict(source: Source, chunk_count: int | None = None) -> dict:
    """Serialize a Source ORM object to the API contract shape.

    ``chunk_count``, if provided, avoids a lazy-load trip to the database.
    """
    return {
        "id": source.id,
        "url": source.url,
        "title": source.title,
        "publisher": source.publisher,
        "government_arm": source.government_arm.value,
        "county": source.county,
        "report_type": source.report_type.value,
        "fiscal_year": source.fiscal_year,
        "published_at": source.published_at.isoformat() if source.published_at else None,
        "last_scraped_at": source.last_scraped_at.isoformat() if source.last_scraped_at else None,
        "ingestion_status": source.ingestion_status.value,
        "ingestion_error": source.ingestion_error,
        "chunk_count": chunk_count if chunk_count is not None else 0,
        "created_at": source.created_at.isoformat() if source.created_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/sources
# ---------------------------------------------------------------------------
@router.get("")
def list_sources(
    county: str | None = None,
    government_arm: str | None = None,
    report_type: str | None = None,
    ingestion_status: str | None = None,
    fiscal_year: str | None = None,
    token: str = Depends(verify_admin),
) -> dict:
    """List registered sources with optional filters."""
    with get_session() as session:
        query = session.query(Source)

        if county:
            query = query.filter(Source.county == county)
        if government_arm:
            query = query.filter(Source.government_arm == GovernmentArm(government_arm))
        if report_type:
            query = query.filter(Source.report_type == ReportType(report_type))
        if ingestion_status:
            query = query.filter(Source.ingestion_status == IngestionStatus(ingestion_status))
        if fiscal_year:
            query = query.filter(Source.fiscal_year == fiscal_year)

        total = query.count()
        sources = query.order_by(Source.created_at.desc()).all()

        # Batch-fetch chunk counts in ONE query instead of len(source.chunks)
        # which would fetch every Chunk object into RAM.
        if sources:
            chunk_counts = dict(
                session.query(
                    Chunk.source_id,
                    func.count(Chunk.id).label("cnt"),
                )
                .filter(Chunk.source_id.in_([s.id for s in sources]))
                .group_by(Chunk.source_id)
                .all()
            )
        else:
            chunk_counts = {}

        return {
            "sources": [
                _source_to_dict(s, chunk_count=chunk_counts.get(s.id, 0))
                for s in sources
            ],
            "total": total,
        }


# ---------------------------------------------------------------------------
# GET /api/sources/{source_id}
# ---------------------------------------------------------------------------
@router.get("/{source_id}")
def get_source(source_id: int, token: str = Depends(verify_admin)) -> dict:
    """Get a single source by ID."""
    with get_session() as session:
        source = session.query(Source).filter_by(id=source_id).first()
        if source is None:
            raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
        chunk_count = (
            session.query(func.count(Chunk.id))
            .filter(Chunk.source_id == source_id)
            .scalar()
        )
        return _source_to_dict(source, chunk_count=chunk_count)


# ---------------------------------------------------------------------------
# POST /api/sources
# ---------------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
def create_source(body: SourceCreate, token: str = Depends(verify_admin)) -> dict:
    """Register a new source document."""
    with get_session() as session:
        source = Source(
            url=body.url,
            title=body.title,
            publisher=body.publisher,
            government_arm=GovernmentArm(body.government_arm),
            county=body.county,
            report_type=ReportType(body.report_type),
            fiscal_year=body.fiscal_year,
            ingestion_status=IngestionStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(source)
        session.flush()
        return _source_to_dict(source)


# ---------------------------------------------------------------------------
# PATCH /api/sources/{source_id}
# ---------------------------------------------------------------------------
@router.patch("/{source_id}")
def update_source(
    source_id: int,
    body: SourceUpdate,
    token: str = Depends(verify_admin),
) -> dict:
    """Update source metadata. Only supplied fields are changed.

    If the URL or report_type changes, all existing chunks are deleted
    and ingestion_status is reset to PENDING — the old chunks now point
    to the wrong PDF.
    """
    with get_session() as session:
        source = session.query(Source).filter_by(id=source_id).first()
        if source is None:
            raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

        url_changed = body.url is not None and body.url != source.url
        arm_changed = body.government_arm is not None and body.government_arm != source.government_arm.value
        rtype_changed = body.report_type is not None and body.report_type != source.report_type.value

        if body.url is not None:
            source.url = body.url
        if body.title is not None:
            source.title = body.title
        if body.publisher is not None:
            source.publisher = body.publisher
        if body.government_arm is not None:
            source.government_arm = GovernmentArm(body.government_arm)
        if body.county is not None:
            source.county = body.county
        if body.report_type is not None:
            source.report_type = ReportType(body.report_type)
        if body.fiscal_year is not None:
            source.fiscal_year = body.fiscal_year

        # If the URL or document identity changed, the existing chunks
        # belong to the OLD document.  Delete them and reset ingestion
        # so the scraper re-ingests from the new URL.
        if url_changed or arm_changed or rtype_changed:
            deleted = (
                session.query(Chunk)
                .filter(Chunk.source_id == source_id)
                .delete()
            )
            source.ingestion_status = IngestionStatus.PENDING
            source.last_scraped_at = None
            source.ingestion_error = None

        session.flush()

        chunk_count = (
            session.query(func.count(Chunk.id))
            .filter(Chunk.source_id == source_id)
            .scalar()
        )
        return _source_to_dict(source, chunk_count=chunk_count)


# ---------------------------------------------------------------------------
# DELETE /api/sources/{source_id}
# ---------------------------------------------------------------------------
@router.delete("/{source_id}")
def delete_source(source_id: int, token: str = Depends(verify_admin)) -> dict:
    """Delete a source and cascade-delete all its chunks."""
    with get_session() as session:
        source = session.query(Source).filter_by(id=source_id).first()
        if source is None:
            raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

        if source.ingestion_status == IngestionStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete source {source_id} while ingestion is in progress.",
            )

        chunk_count = (
            session.query(func.count(Chunk.id))
            .filter(Chunk.source_id == source_id)
            .scalar()
        )
        session.delete(source)  # cascade-deletes chunks via ORM relationship
        session.flush()

        return {"deleted": True, "source_id": source_id, "chunks_deleted": chunk_count}


# ---------------------------------------------------------------------------
# POST /api/sources/{source_id}/ingest
# ---------------------------------------------------------------------------
@router.post("/{source_id}/ingest", status_code=status.HTTP_202_ACCEPTED)
def trigger_ingestion(source_id: int, token: str = Depends(verify_admin)) -> dict:
    """Trigger manual ingestion for a source (runs in background)."""
    with get_session() as session:
        source = session.query(Source).filter_by(id=source_id).first()
        if source is None:
            raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

        if source.ingestion_status == IngestionStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=409,
                detail=f"Source {source_id} is already being ingested (status: in_progress)",
            )

        source.ingestion_status = IngestionStatus.IN_PROGRESS
        session.flush()

        # TODO: trigger actual scraper via background task once scheduler.py exists
        return {
            "source_id": source_id,
            "ingestion_status": "in_progress",
            "message": f"Ingestion started. Check status via GET /api/sources/{source_id}.",
        }
