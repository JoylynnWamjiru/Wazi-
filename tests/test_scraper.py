"""Tests for the automated scraper (src/ingestion/scraper.py).

Unit tests for download, status transitions, source registration, URL
validation, and filename sanitization.  The full pipeline (extract →
chunk → embed → store) exercises pgvector and is tested separately via
``test_extract.py`` + ``test_chunk.py`` + VPS integration.

Marked ``db`` — uses the in-memory SQLite fixture for source/user tables.
"""

import pytest

pytestmark = pytest.mark.db

# ---------------------------------------------------------------------------
# _safe_suffix — Content-Disposition filename sanitization
# ---------------------------------------------------------------------------

def test_safe_suffix_handles_path_traversal():
    from src.ingestion.scraper import _safe_suffix

    assert _safe_suffix('attachment; filename="bad/path/report.pdf"') == "_report.pdf"


def test_safe_suffix_adds_pdf_extension_when_missing():
    from src.ingestion.scraper import _safe_suffix

    assert _safe_suffix('attachment; filename="report"') == "_report.pdf"


def test_safe_suffix_falls_back_for_empty_header():
    from src.ingestion.scraper import _safe_suffix

    assert _safe_suffix("") == ".pdf"
    assert _safe_suffix("attachment") == ".pdf"


# ---------------------------------------------------------------------------
# _validate_url — SSRF guard
# ---------------------------------------------------------------------------

def test_validate_url_rejects_loopback():
    from src.ingestion.scraper import _validate_url

    with pytest.raises(ValueError, match="private/internal IP"):
        _validate_url("http://127.0.0.1/report.pdf")

    with pytest.raises(ValueError, match="private/internal IP"):
        _validate_url("http://localhost/report.pdf")


def test_validate_url_rejects_cloud_metadata():
    from src.ingestion.scraper import _validate_url

    with pytest.raises(ValueError, match="private/internal IP"):
        _validate_url("http://169.254.169.254/latest/meta-data/")


def test_validate_url_rejects_private_ranges():
    from src.ingestion.scraper import _validate_url

    for host in ("192.168.1.1", "10.0.0.1", "172.16.0.1"):
        with pytest.raises(ValueError, match="private/internal IP"):
            _validate_url(f"http://{host}/report.pdf")


def test_validate_url_rejects_non_http_scheme():
    from src.ingestion.scraper import _validate_url

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        _validate_url("ftp://example.com/report.pdf")


def test_validate_url_accepts_public_url():
    from src.ingestion.scraper import _validate_url

    # Should not raise.
    scheme = _validate_url("https://www.oagkenya.go.ke/reports/nakuru.pdf")
    assert scheme == "https"


# ---------------------------------------------------------------------------
# _mark_status
# ---------------------------------------------------------------------------

def test_mark_status_updates_ingestion_status(db):
    from src.ingestion.scraper import _mark_status
    from src.shared.models import IngestionStatus, Source

    with db.get_session() as s:
        src = Source(
            url="https://example.com/report.pdf",
            title="Test Report",
            publisher="OAG",
            government_arm="executive",
            county="nakuru",
            report_type="audit_report",
            fiscal_year="2023/24",
            ingestion_status=IngestionStatus.PENDING,
        )
        s.add(src)
        s.flush()
        sid = src.id

    _mark_status(sid, IngestionStatus.COMPLETED, content_hash="abc123")

    with db.get_session() as s:
        src = s.query(Source).filter_by(id=sid).first()
        assert src.ingestion_status == IngestionStatus.COMPLETED
        assert src.last_scraped_at is not None
        assert src.ingestion_error is None
        assert src.content_hash == "abc123"


def test_mark_status_records_error(db):
    from src.ingestion.scraper import _mark_status
    from src.shared.models import IngestionStatus, Source

    with db.get_session() as s:
        src = Source(
            url="https://example.com/report.pdf",
            title="Test Report",
            publisher="OAG",
            government_arm="executive",
            county="nakuru",
            report_type="audit_report",
            fiscal_year="2023/24",
            ingestion_status=IngestionStatus.PENDING,
        )
        s.add(src)
        s.flush()
        sid = src.id

    _mark_status(sid, IngestionStatus.FAILED, error="PDF is scanned, needs OCR")

    with db.get_session() as s:
        src = s.query(Source).filter_by(id=sid).first()
        assert src.ingestion_status == IngestionStatus.FAILED
        assert "OCR" in (src.ingestion_error or "")


def test_mark_status_silently_skips_nonexistent_source(db):
    from src.ingestion.scraper import _mark_status
    from src.shared.models import IngestionStatus

    _mark_status(999_999, IngestionStatus.COMPLETED)


# ---------------------------------------------------------------------------
# ingest_source — IN_PROGRESS guard
# ---------------------------------------------------------------------------

def test_ingest_source_rejects_concurrent_ingestion(db):
    from src.ingestion.scraper import ingest_source
    from src.shared.models import IngestionStatus, Source

    with db.get_session() as s:
        src = Source(
            url="https://example.com/report.pdf",
            title="Already Running",
            publisher="OAG",
            government_arm="executive",
            county="nakuru",
            report_type="audit_report",
            fiscal_year="2023/24",
            ingestion_status=IngestionStatus.IN_PROGRESS,
        )
        s.add(src)
        s.flush()
        sid = src.id

    result = ingest_source(sid)
    assert result["status"] == "skipped"
    assert "already being ingested" in result["error"]


def test_ingest_source_returns_error_for_nonexistent(db):
    from src.ingestion.scraper import ingest_source

    result = ingest_source(999_999)
    assert result["status"] == "error"
    assert result["error"] == "not_found"


# ---------------------------------------------------------------------------
# ingest_url — registration + reuse
# ---------------------------------------------------------------------------

def test_ingest_url_registers_a_new_source(db, monkeypatch):
    from src.ingestion.scraper import ingest_url
    from src.shared.models import GovernmentArm, IngestionStatus, ReportType, Source

    # Patch download_pdf to avoid the actual HTTP call.
    monkeypatch.setattr(
        "src.ingestion.scraper.download_pdf",
        lambda url, timeout=120: (_ for _ in ()).throw(
            RuntimeError("mock: no real PDF in unit test")
        ),
    )

    result = ingest_url(
        url="https://example.com/nakuru-fy2024.pdf",
        title="Nakuru Audit FY2024",
        publisher="OAG",
        government_arm=GovernmentArm.EXECUTIVE,
        report_type=ReportType.AUDIT_REPORT,
        fiscal_year="2023/24",
        county="nakuru",
    )

    assert result["source_id"] > 0
    assert result["status"] == "failed"

    with db.get_session() as s:
        src = s.query(Source).filter_by(url="https://example.com/nakuru-fy2024.pdf").first()
        assert src is not None
        assert src.title == "Nakuru Audit FY2024"
        assert src.ingestion_status == IngestionStatus.FAILED


def test_ingest_url_reuses_source_with_same_url_and_title(db, monkeypatch):
    """Idempotent by (url, title): re-registering the SAME document edition
    updates the existing row rather than duplicating it."""
    from src.ingestion.scraper import ingest_url
    from src.shared.models import GovernmentArm, ReportType, Source

    with db.get_session() as s:
        s.add(Source(
            url="https://example.com/report.pdf",
            title="Nakuru Audit FY2024",
            publisher="OAG",
            government_arm="executive",
            county="nakuru",
            report_type="audit_report",
            fiscal_year="2022/23",
        ))
        s.flush()

    monkeypatch.setattr(
        "src.ingestion.scraper.download_pdf",
        lambda url, timeout=120: (_ for _ in ()).throw(
            RuntimeError("mock: no real PDF in unit test")
        ),
    )

    result = ingest_url(
        url="https://example.com/report.pdf",
        title="Nakuru Audit FY2024",          # SAME title → reuse
        publisher="CoB",
        government_arm=GovernmentArm.CONSOLIDATED,
        report_type=ReportType.BIRR,
        fiscal_year="2023/24",
        county="nakuru",
    )

    assert result["status"] == "failed"  # mock download fails

    with db.get_session() as s:
        sources = s.query(Source).filter_by(url="https://example.com/report.pdf").all()
        assert len(sources) == 1             # idempotent — no duplicate
        src = sources[0]
        assert src.publisher == "CoB"        # metadata updated in place


def test_ingest_url_allows_same_url_with_different_title(db, monkeypatch):
    """A listing page hosts many documents — the same URL with a DIFFERENT
    title (edition) must create a separate source, not reuse."""
    from src.ingestion.scraper import ingest_url
    from src.shared.models import GovernmentArm, ReportType, Source

    with db.get_session() as s:
        s.add(Source(
            url="https://example.com/oag-fy2024/",
            title="Nakuru County Executive FY 2024",
            publisher="OAG",
            government_arm="executive",
            county="nakuru",
            report_type="audit_report",
            fiscal_year="2024",
        ))
        s.flush()

    monkeypatch.setattr(
        "src.ingestion.scraper.download_pdf",
        lambda url, timeout=120: (_ for _ in ()).throw(
            RuntimeError("mock: no real PDF in unit test")
        ),
    )

    ingest_url(
        url="https://example.com/oag-fy2024/",
        title="Nakuru County Assembly FY 2024",   # DIFFERENT title → new source
        publisher="OAG",
        government_arm=GovernmentArm.ASSEMBLY,
        report_type=ReportType.AUDIT_REPORT,
        fiscal_year="2024",
        county="nakuru",
    )

    with db.get_session() as s:
        sources = s.query(Source).filter_by(url="https://example.com/oag-fy2024/").all()
        assert len(sources) == 2             # both documents coexist


def test_ingest_url_rejects_private_ip_before_registration(db):
    """SSRF guard runs before touching the database."""
    from src.ingestion.scraper import ingest_url
    from src.shared.models import GovernmentArm, ReportType

    with pytest.raises(ValueError, match="private/internal IP"):
        ingest_url(
            url="http://127.0.0.1/admin",
            title="Should Not Register",
            publisher="OAG",
            government_arm=GovernmentArm.EXECUTIVE,
            report_type=ReportType.AUDIT_REPORT,
            fiscal_year="2023/24",
        )


# ---------------------------------------------------------------------------
# download_pdf — error handling (no network)
# ---------------------------------------------------------------------------

def test_download_pdf_rejects_non_pdf_content_type(monkeypatch):
    import httpx
    from src.ingestion.scraper import download_pdf

    class MockResponse:
        def raise_for_status(self):
            pass
        headers = {"content-type": "text/html"}

    class _CM:
        def __init__(self, resp): self._r = resp
        def __enter__(self): return self._r
        def __exit__(self, *a): pass

    monkeypatch.setattr(httpx, "stream", lambda *a, **kw: _CM(MockResponse()))

    with pytest.raises(ValueError, match="does not appear to serve a PDF"):
        download_pdf("https://example.com/not-a-pdf")


def test_download_pdf_rejects_non_http_url():
    from src.ingestion.scraper import download_pdf

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        download_pdf("ftp://example.com/report.pdf")
