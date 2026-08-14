"""Automated document scraper — download + ingest government PDFs.

This is the production ingestion path that replaces the hackathon-era
``build_corpus()`` and the stopgap ``ingest_local.py``.  It downloads a
PDF from a URL, validates it, and runs the full extract → chunk → embed →
store pipeline into pgvector.

Architecture:
    URL ──httpx──→ temp file ──extract──→ pages ──chunk──→ chunks ──embed──→ pgvector
                                                                              │
                                                    ┌─────────────────────────┘
                                                    ▼
                                            sources.ingestion_status = COMPLETED

Usage:
    # CLI — ingest an already-registered source
    python -m src.ingestion.scraper --source-id 1

    # CLI — register + ingest in one shot
    python -m src.ingestion.scraper \\
        --url https://oagkenya.go.ke/reports/nakuru-fy2024.pdf \\
        --title "OAG Nakuru Executive Audit FY2023/24" \\
        --publisher OAG \\
        --government-arm executive \\
        --report-type audit_report \\
        --fiscal-year "2023/24"

    # Programmatic — called by the admin API background task
    from src.ingestion.scraper import ingest_source
    ingest_source(source_id=1)
"""

import argparse
import hashlib
import ipaddress
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import update

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum PDF file size (bytes).  The largest known Kenyan government PDF
# (47-county consolidated BIRR) is ~47 MB.  100 MB leaves headroom while
# preventing disk-exhaustion DoS from misconfigured or malicious servers.
MAX_PDF_BYTES = 100 * 1024 * 1024  # 100 MB

# Kenyan government portals (oagkenya.go.ke, treasury.go.ke, etc.) frequently
# block the default httpx User-Agent.  A browser UA avoids 403s from
# Cloudflare / Incapsula WAFs.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Private / loopback / link-local networks.  We reject these to prevent
# SSRF from a compromised admin account probing internal infrastructure.
_SSRF_BLOCKED_NETWORKS = (
    ipaddress.IPv4Network("127.0.0.0/8"),       # loopback
    ipaddress.IPv4Network("10.0.0.0/8"),        # private
    ipaddress.IPv4Network("172.16.0.0/12"),     # private
    ipaddress.IPv4Network("192.168.0.0/16"),    # private
    ipaddress.IPv4Network("169.254.0.0/16"),    # link-local (cloud metadata)
    ipaddress.IPv4Network("0.0.0.0/8"),         # "this" network
)

# ---------------------------------------------------------------------------
# URL validation (SSRF guard)
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> str:
    """Validate *url* is a safe, public HTTP(S) URL.  Returns the scheme.

    Raises ValueError for internal/private hosts or non-HTTP schemes.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme not in ("http", "https"):
        raise ValueError(
            f"Unsupported URL scheme '{scheme}'. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if hostname is None:
        raise ValueError(f"URL has no resolvable hostname: {url!r}")

    # Resolve the hostname and check every IP against blocked networks.
    try:
        addrs = {ipaddress.IPv4Address(hostname)}
    except ValueError:
        # Not an IP literal — do a DNS lookup.
        import socket
        try:
            addrs_list = socket.getaddrinfo(hostname, None, socket.AF_INET)
            addrs = {ipaddress.IPv4Address(a[4][0]) for a in addrs_list}
        except socket.gaierror:
            raise ValueError(f"Cannot resolve hostname: {hostname!r}")

    for addr in addrs:
        for net in _SSRF_BLOCKED_NETWORKS:
            if addr in net:
                raise ValueError(
                    f"URL resolves to a private/internal IP ({addr}), "
                    f"which is not allowed for security reasons."
                )

    return scheme


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------

def _safe_suffix(content_disposition: str) -> str:
    """Extract a safe ``.pdf`` suffix from a Content-Disposition header.

    Guards against path-traversal (``filename="bad/path/report.pdf"``) and
    non-PDF filenames.
    """
    if "filename=" not in content_disposition:
        return ".pdf"

    # Crude extraction — fine for MVP.
    raw = content_disposition.split("filename=")[-1].strip('"; \t\n\r')
    # Take only the last path component (basename) and strip any leading dots.
    filename = Path(raw).name.lstrip(".")

    if not filename:
        return ".pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    # Prefix with underscore so we don't accidentally match a real file.
    return "_" + filename


# ---------------------------------------------------------------------------
# Download (with size limit, SSRF guard, User-Agent, and SHA-256 checksum)
# ---------------------------------------------------------------------------

def download_pdf(url: str, timeout: float = 120.0) -> tuple[Path, str]:
    """Download a PDF from *url* to a temporary file.

    Returns ``(file_path, sha256_hex)``.  The caller owns the temp file —
    delete it with ``Path.unlink()`` after ingestion.

    Enforces a ``MAX_PDF_BYTES`` size cap and validates the URL against
    internal/private hosts before connecting.
    """
    _validate_url(url)

    # Stream so we don't buffer a 100 MB PDF into RAM.
    with httpx.stream(
        "GET", url,
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": BROWSER_UA},
    ) as resp:
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").lower()
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            raise ValueError(
                f"URL does not appear to serve a PDF "
                f"(Content-Type: {content_type}). "
                f"If this IS a PDF, add .pdf to the URL."
            )

        suffix = _safe_suffix(resp.headers.get("content-disposition", ""))

        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        sha = hashlib.sha256()
        total = 0

        try:
            for chunk in resp.iter_bytes(chunk_size=8192):
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    raise ValueError(
                        f"PDF exceeds maximum size of {MAX_PDF_BYTES // 1024 // 1024} MB "
                        f"(received {total // 1024 // 1024} MB so far)."
                    )
                sha.update(chunk)
                tmp.write(chunk)
        except Exception:
            tmp.close()
            Path(tmp.name).unlink(missing_ok=True)
            raise
        finally:
            tmp.close()

    return Path(tmp.name), sha.hexdigest()


# ---------------------------------------------------------------------------
# Core ingestion (reuses extract → chunk → embed from the existing pipeline)
# ---------------------------------------------------------------------------

def _run_pipeline(
    pdf_path: Path,
    source_id: int,
    government_arm: GovernmentArm,
    county: str,
) -> int:
    """Extract, chunk, embed, and store ONE PDF.  Returns chunk count."""
    path_str = str(pdf_path)

    if not check_text_layer(path_str):
        raise ValueError(
            f"Text-layer check failed for '{pdf_path.name}': "
            f"appears scanned/image-only and would need OCR."
        )

    # Idempotent: clear old chunks so re-runs don't duplicate.
    removed = delete_chunks(source_id)
    if removed:
        print(f"  cleared {removed} existing chunks for source {source_id}")

    pages = extract_pages(path_str)
    chunks = chunk_pages(pages)
    stored = store_chunks(
        chunks,
        source_id=source_id,
        government_arm=government_arm,
        county=county,
    )
    print(f"  stored {stored} chunks from {len(pages)} pages ({pdf_path.name})")
    return stored


def _mark_status(
    source_id: int,
    status: IngestionStatus,
    error: str | None = None,
    content_hash: str | None = None,
) -> None:
    """Update a source's ingestion status (commits immediately).

    ``content_hash``, when provided, is the SHA-256 of the downloaded PDF.
    """
    with get_session() as session:
        source = session.query(Source).filter_by(id=source_id).first()
        if source is None:
            return
        source.ingestion_status = status
        source.ingestion_error = error
        source.last_scraped_at = datetime.now(timezone.utc)
        if content_hash is not None:
            source.content_hash = content_hash


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_source(source_id: int) -> dict:
    """Download + ingest an already-registered source.  Returns a summary dict.

    Called by the admin API (``POST /api/sources/{id}/ingest``) as a
    background task, and by the CLI.

    The PDF is downloaded to a temp file which is cleaned up after ingestion
    (success or failure).  The source's ``ingestion_status`` is always
    updated to COMPLETED or FAILED.

    Guards:
    - Atomically claims the source (IN_PROGRESS) so two concurrent
      ingestions of the same source can't both run — the loser gets
      "skipped" without ever downloading the PDF.
    - Enforces SSRF, max file size, and filename sanitization in download_pdf.
    """
    with get_session() as session:
        source = session.query(Source).filter_by(id=source_id).first()
        if source is None:
            return {"source_id": source_id, "status": "error", "error": "not_found"}

        url = source.url
        government_arm = source.government_arm
        county = source.county

        # Atomic claim: set IN_PROGRESS only if it isn't already.  The
        # rowcount tells us whether WE won the claim (1) or another
        # ingestion already holds it (0).  This closes the TOCTOU race
        # that a read-then-write guard would leave open.
        result = session.execute(
            update(Source)
            .where(
                Source.id == source_id,
                Source.ingestion_status != IngestionStatus.IN_PROGRESS,
            )
            .values(ingestion_status=IngestionStatus.IN_PROGRESS)
        )
        if result.rowcount == 0:
            return {
                "source_id": source_id,
                "status": "skipped",
                "error": f"Source {source_id} is already being ingested (status: in_progress).",
            }

    pdf_path: Path | None = None
    try:
        pdf_path, content_hash = download_pdf(url)
        print(
            f"[scraper] downloaded {url} → {pdf_path} "
            f"({pdf_path.stat().st_size} bytes, sha256={content_hash[:12]}…)"
        )

        stored = _run_pipeline(pdf_path, source_id, government_arm, county)

        _mark_status(source_id, IngestionStatus.COMPLETED, content_hash=content_hash)
        return {
            "source_id": source_id,
            "status": "completed",
            "chunks_stored": stored,
            "content_hash": content_hash,
        }

    except Exception as exc:  # noqa: BLE001
        _mark_status(source_id, IngestionStatus.FAILED, error=str(exc)[:500])
        return {
            "source_id": source_id,
            "status": "failed",
            "error": str(exc)[:500],
        }

    finally:
        if pdf_path is not None:
            pdf_path.unlink(missing_ok=True)


def ingest_url(
    url: str,
    *,
    title: str,
    publisher: str,
    government_arm: GovernmentArm,
    report_type: ReportType,
    fiscal_year: str = "",
    county: str = "nakuru",
) -> dict:
    """Register a new source AND ingest it in one call.  Returns a summary dict.

    This is the CLI convenience path — no separate admin-dashboard
    registration step needed.
    """
    # Validate the URL BEFORE touching the database (SSRF guard).
    _validate_url(url)

    # 1. Register the source (idempotent by (url, title) — a listing page can
    #    legitimately host MANY documents, so ``url`` alone is not a unique
    #    identity; the (url, title) pair identifies a specific document edition.
    with get_session() as session:
        existing = session.query(Source).filter_by(url=url, title=title).first()
        if existing:
            source_id = existing.id
            # Update metadata in case it changed.
            existing.title = title
            existing.publisher = publisher
            existing.government_arm = government_arm
            existing.report_type = report_type
            existing.fiscal_year = fiscal_year
            existing.county = county
            print(f"[scraper] reusing existing source {source_id}: {title}")
        else:
            source = Source(
                url=url,
                title=title,
                publisher=publisher,
                government_arm=government_arm,
                report_type=report_type,
                fiscal_year=fiscal_year,
                county=county,
                ingestion_status=IngestionStatus.PENDING,
            )
            session.add(source)
            session.flush()
            source_id = source.id
            print(f"[scraper] registered new source {source_id}: {title}")

    # 2. Ingest.
    return ingest_source(source_id)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download + ingest a government PDF into Wazi's pgvector corpus.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--source-id",
        type=int,
        help="Ingest an already-registered source by its database ID.",
    )
    group.add_argument(
        "--url",
        help="Register AND ingest a new source in one step.",
    )

    # --url mode metadata (required when --url is used).
    parser.add_argument("--title", help="Human-readable title for the document.")
    parser.add_argument("--publisher", help='Publisher (e.g. "OAG", "CoB", "KIPPRA").')
    parser.add_argument(
        "--government-arm",
        choices=[a.value for a in GovernmentArm],
        help="Government arm this document covers.",
    )
    parser.add_argument(
        "--report-type",
        choices=[r.value for r in ReportType],
        help="Type of financial document.",
    )
    parser.add_argument("--fiscal-year", default="", help='Fiscal year (e.g. "2023/24").')
    parser.add_argument("--county", default="nakuru", help="County name (default: nakuru).")

    args = parser.parse_args()

    init_db()

    if args.source_id:
        result = ingest_source(args.source_id)
    else:
        # Validate --url mode has all required metadata.
        missing = []
        for field in ("title", "publisher", "government_arm", "report_type"):
            if not getattr(args, field.replace("-", "_"), None):
                missing.append(f"--{field}")
        if missing:
            parser.error(f"--url mode also requires: {', '.join(missing)}")

        result = ingest_url(
            url=args.url,
            title=args.title,
            publisher=args.publisher,
            government_arm=GovernmentArm(args.government_arm),
            report_type=ReportType(args.report_type),
            fiscal_year=args.fiscal_year,
            county=args.county,
        )

    print(f"\n[scraper] {result}")


if __name__ == "__main__":
    main()
