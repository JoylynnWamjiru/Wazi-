"""Diagnostic: download a consolidated PDF and dump heading detection.

Shows every county-heading transition and the pages the current
``extract_county_section`` would collect for the target county, so the
truncation cause is visible directly.

Usage:
    python scripts/debug_headings.py <pdf-url> [county]
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import fitz  # PyMuPDF

from src.ingestion.extract import MIN_PAGE_CHARS, _COUNTY_HEADING_RE, _heading_county
from src.ingestion.scraper import download_pdf


def first_match_line(text: str):
    for line in text.splitlines():
        m = _COUNTY_HEADING_RE.match(line.strip())
        if m is not None:
            return line.strip(), m.group(1)
    return None, None


def main(url: str, county: str = "nakuru") -> None:
    path, sha = download_pdf(url)
    print(f"[debug] downloaded: {path}")

    current = None
    nakuru_pages = []

    with fitz.open(path) as doc:
        print(f"[debug] total pages: {doc.page_count}")
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if len(text) < MIN_PAGE_CHARS:
                continue
            heading = _heading_county(text)
            if heading is not None and heading != current:
                line, _ = first_match_line(text)
                print(f"[debug] p{i + 1:>4}: {current!r} -> {heading!r}\n"
                      f"           line: {line[:100]!r}")
                current = heading
            if current is not None and current.lower() == county.lower():
                nakuru_pages.append(i + 1)

    print("\n=== SUMMARY ===")
    print(f"[debug] '{county}' pages collected: {len(nakuru_pages)}")
    print(f"[debug] pages: {nakuru_pages}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "nakuru")
