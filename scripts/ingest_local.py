"""Ingest the local Nakuru PDFs into pgvector.

This is the missing link between ``build_corpus()`` (which only writes
``chunks.json`` for the Streamlit citizen app) and the pgvector-backed
FastAPI pipeline. Until the automated scraper exists, this script is how
the ``chunks`` table gets populated so the WhatsApp webhook can return
real, grounded answers instead of the fallback.

What it does, per PDF in ``data/``:
    1. Ensure a matching row exists in the ``sources`` table (idempotent
       by title) and grab its ``source_id``.
    2. Delete any existing chunks for that source (so re-runs are clean).
    3. extract_pages -> chunk_pages -> embed + store in pgvector.
    4. Mark the source ``COMPLETED`` with a ``last_scraped_at`` timestamp.

Run on the VPS (where PostgreSQL + pgvector live):
    python scripts/ingest_local.py

Requires: a reachable ``DATABASE_URL`` and the ONNX embedding model
(~470MB) — which is why it runs on the VPS, not the disk-constrained
dev laptop.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.chunk import chunk_pages
from src.ingestion.embed import delete_chunks, store_chunks
from src.ingestion.extract import check_text_layer, extract_pages
from src.shared.database import get_session, init_db
from src.shared.models import (
    GovernmentArm,
    IngestionStatus,
    ReportType,
    Source,
)

DATA_DIR = REPO_ROOT / "data"

# The two Nakuru PDFs already living in ``data/``. These are the
# already-extracted Nakuru sections (not the raw multi-county consolidated
# PDFs the scraper would download), so each maps to a dedicated source row.
LOCAL_PDFS = [
    {
        "filename": "nakuru_audit_report.pdf",
        "title": "Auditor-General's Report — Nakuru County Executive (local corpus)",
        "publisher": "OAG",
        "government_arm": GovernmentArm.EXECUTIVE,
        "report_type": ReportType.AUDIT_REPORT,
        "fiscal_year": "2023/24",
        "url": "local://data/nakuru_audit_report.pdf",
    },
    {
        "filename": "nakuru_birr_q1.pdf",
        "title": "County Governments BIRR — First Quarter (Nakuru, local corpus)",
        "publisher": "CoB",
        "government_arm": GovernmentArm.CONSOLIDATED,
        "report_type": ReportType.BIRR,
        "fiscal_year": "2024/25",
        "url": "local://data/nakuru_birr_q1.pdf",
    },
]

COUNTY = "nakuru"


def _ensure_source(meta: dict) -> int:
    """Find or create the Source row for a local PDF. Returns its id."""
    with get_session() as session:
        source = session.query(Source).filter_by(title=meta["title"]).first()
        if source is None:
            source = Source(
                url=meta["url"],
                title=meta["title"],
                publisher=meta["publisher"],
                government_arm=meta["government_arm"],
                county=COUNTY,
                report_type=meta["report_type"],
                fiscal_year=meta["fiscal_year"],
                ingestion_status=IngestionStatus.PENDING,
            )
            session.add(source)
            session.flush()
            print(f"  + created source row (id={source.id}): {source.title}")
        else:
            print(f"  = reusing source row (id={source.id}): {source.title}")
        return source.id


def _mark_status(source_id: int, status: IngestionStatus, error: str | None = None) -> None:
    with get_session() as session:
        source = session.query(Source).filter_by(id=source_id).first()
        if source is None:
            return
        source.ingestion_status = status
        source.ingestion_error = error
        source.last_scraped_at = datetime.now(timezone.utc)


def ingest_pdf(meta: dict) -> int:
    """Ingest one local PDF into pgvector. Returns the chunk count stored."""
    path = DATA_DIR / meta["filename"]
    print(f"\n>>> {meta['filename']}")

    if not path.exists():
        raise FileNotFoundError(f"Expected PDF not found: {path}")
    if not check_text_layer(str(path)):
        raise ValueError(
            f"Text-layer check failed for '{path.name}': appears scanned/"
            f"image-only and would need OCR."
        )

    source_id = _ensure_source(meta)
    _mark_status(source_id, IngestionStatus.IN_PROGRESS)

    try:
        # Idempotent: clear any chunks from a previous run before re-storing.
        removed = delete_chunks(source_id)
        if removed:
            print(f"  cleared {removed} existing chunks")

        pages = extract_pages(str(path))
        chunks = chunk_pages(pages)
        stored = store_chunks(
            chunks,
            source_id=source_id,
            government_arm=meta["government_arm"],
            county=COUNTY,
        )
        _mark_status(source_id, IngestionStatus.COMPLETED)
        print(f"  stored {stored} chunks in pgvector ({len(pages)} pages)")
        return stored

    except Exception as exc:  # noqa: BLE001
        _mark_status(source_id, IngestionStatus.FAILED, error=str(exc)[:500])
        raise


def main() -> None:
    print("Ingesting local Nakuru PDFs into pgvector...")
    init_db()

    total = 0
    for meta in LOCAL_PDFS:
        total += ingest_pdf(meta)

    print(f"\n✓ Ingestion complete: {total} chunks across {len(LOCAL_PDFS)} sources.")
    print("  Verify: SELECT count(*) FROM chunks;")


if __name__ == "__main__":
    main()
