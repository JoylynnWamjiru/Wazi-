"""Diagnostic: dump the CoB listing page's WPDM links and per-source scores."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.scraper_listing import (
    _score_link,
    extract_links,
    extract_wpdm_downloads,
    fetch_html,
    select_pdf,
)

URL = "https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/"

html = fetch_html(URL)
print("=== plain .pdf links ===")
for l in extract_links(html, URL):
    if l["is_pdf"]:
        print(f"  {l['title']!r} -> {l['url']}")

print("\n=== WPDM links ===")
wpdm = extract_wpdm_downloads(html, URL)
for i, l in enumerate(wpdm):
    print(f"  [{i}] {l['title']!r}\n      -> {l['url']}")
print(f"=== WPDM count: {len(wpdm)} ===")

sources = [
    {"title": "County Governments BIRR — First Quarter FY 2025/26",
     "government_arm": "consolidated", "report_type": "birr"},
    {"title": "County Governments BIRR — First Half FY 2025/26",
     "government_arm": "consolidated", "report_type": "birr"},
    {"title": "County Governments BIRR — First Nine Months FY 2025/26",
     "government_arm": "consolidated", "report_type": "birr"},
]

for s in sources:
    print(f"\n=== source: {s['title']} ===")
    for l in wpdm:
        print(f"  score={_score_link(l, s):>3}  {l['title']!r}")
    try:
        print("  SELECTED:", select_pdf(wpdm, s))
    except Exception as exc:  # noqa: BLE001
        print("  SELECT ERROR:", exc)
