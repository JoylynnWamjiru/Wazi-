"""Seed the database with initial source documents.

Run once after setting up Docker and installing dependencies:
    python scripts/seed_db.py

URL strategy:
    The ``url`` field stores the LISTING PAGE where PDFs are found, NOT direct
    PDF download links. The scraper visits this page, finds the relevant PDF
    link(s), downloads them, and runs extraction + chunking + embedding.

    OAG pattern: https://www.oagkenya.go.ke/{FY}-county-government-audit-reports/
        FY format: "2023-2024", "2024-2025", etc.
        Each page lists two consolidated PDFs covering all 47 counties:
          - "County Executives" PDF  (all county executive audits)
          - "County Assemblies" PDF   (all county assembly audits)
        Within each, Nakuru's section is headed "COUNTY EXECUTIVE OF NAKURU"
        or "COUNTY ASSEMBLY OF NAKURU".  The scraper downloads the full
        consolidated PDF, locates the Nakuru section by heading search,
        extracts only those pages, then chunks + embeds.

    CoB pattern: https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/
        Lists all BIRRs (Q1, Half-Year, Nine-Months, Annual) as individual
        PDFs, each covering all 47 counties.  The scraper extracts only the
        Nakuru section (same heading-search approach).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.shared.database import get_session, init_db
from src.shared.models import GovernmentArm, IngestionStatus, ReportType, Source

# ---------------------------------------------------------------------------
# OAG FY-specific listing pages.
# URL template: https://www.oagkenya.go.ke/{FY}-county-government-audit-reports/
# Two consolidated PDFs per FY — one for all 47 County Executives, one for
# all 47 County Assemblies.  Nakuru's section in each is headed:
#   "COUNTY EXECUTIVE OF NAKURU"
#   "COUNTY ASSEMBLY OF NAKURU"
# The scraper downloads the full consolidated PDF, searches for the heading,
# and extracts only the Nakuru pages before chunking.
# ---------------------------------------------------------------------------
OAG_BASE = "https://www.oagkenya.go.ke"

# ---------------------------------------------------------------------------
# CoB consolidated BIRR listing page.
# All four BIRR editions (Q1, Half-Year, Nine-Months, Annual) are published
# as individual PDFs on this single page.  Each PDF covers all 47 counties;
# the scraper extracts only the Nakuru section.
# ---------------------------------------------------------------------------
COB_BIRR_URL = "https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/"

SEED_SOURCES = [
    # --- OAG: County Executive audit reports ---
    {
        "url": f"{OAG_BASE}/2023-2024-county-government-audit-reports/",
        "title": "Auditor-General's Report — Nakuru County Executive, FY 2023/24",
        "publisher": "OAG",
        "government_arm": GovernmentArm.EXECUTIVE,
        "county": "nakuru",
        "report_type": ReportType.AUDIT_REPORT,
        "fiscal_year": "2023/24",
    },
    # --- OAG: County Assembly audit reports ---
    {
        "url": f"{OAG_BASE}/2023-2024-county-government-audit-reports/",
        "title": "Auditor-General's Report — Nakuru County Assembly, FY 2023/24",
        "publisher": "OAG",
        "government_arm": GovernmentArm.ASSEMBLY,
        "county": "nakuru",
        "report_type": ReportType.AUDIT_REPORT,
        "fiscal_year": "2023/24",
    },
    # --- OAG: FY 2024/25 (most current — already published) ---
    {
        "url": f"{OAG_BASE}/2024-2025-county-government-audit-reports/",
        "title": "Auditor-General's Report — Nakuru County Executive, FY 2024/25",
        "publisher": "OAG",
        "government_arm": GovernmentArm.EXECUTIVE,
        "county": "nakuru",
        "report_type": ReportType.AUDIT_REPORT,
        "fiscal_year": "2024/25",
    },
    {
        "url": f"{OAG_BASE}/2024-2025-county-government-audit-reports/",
        "title": "Auditor-General's Report — Nakuru County Assembly, FY 2024/25",
        "publisher": "OAG",
        "government_arm": GovernmentArm.ASSEMBLY,
        "county": "nakuru",
        "report_type": ReportType.AUDIT_REPORT,
        "fiscal_year": "2024/25",
    },
    # --- CoB: Budget Implementation Review Reports (FY 2025/26) ---
    {
        "url": COB_BIRR_URL,
        "title": "County Governments BIRR — First Quarter FY 2025/26",
        "publisher": "CoB",
        "government_arm": GovernmentArm.CONSOLIDATED,
        "county": "nakuru",
        "report_type": ReportType.BIRR,
        "fiscal_year": "2025/26",
    },
    {
        "url": COB_BIRR_URL,
        "title": "County Governments BIRR — First Half FY 2025/26",
        "publisher": "CoB",
        "government_arm": GovernmentArm.CONSOLIDATED,
        "county": "nakuru",
        "report_type": ReportType.BIRR,
        "fiscal_year": "2025/26",
    },
    {
        "url": COB_BIRR_URL,
        "title": "County Governments BIRR — First Nine Months FY 2025/26",
        "publisher": "CoB",
        "government_arm": GovernmentArm.CONSOLIDATED,
        "county": "nakuru",
        "report_type": ReportType.BIRR,
        "fiscal_year": "2025/26",
    },
]


def main() -> None:
    print("Seeding Wazi database with initial sources...")
    init_db()

    with get_session() as session:
        existing = session.query(Source).count()
        if existing > 0:
            print(f"  Database already has {existing} sources. Skipping seed.")
            return

        for src in SEED_SOURCES:
            source = Source(
                **src,
                ingestion_status=IngestionStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            session.add(source)
            print(f"  + {source.title} [{source.government_arm.value}]")

    print(f"\n✓ Seeded {len(SEED_SOURCES)} sources.")


if __name__ == "__main__":
    main()
