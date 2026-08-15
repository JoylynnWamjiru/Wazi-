"""Extract text from county budget PDFs using PyMuPDF (fitz).

Provides a text-layer check to detect scanned/image-only PDFs that would
need OCR, and a per-page text extractor that skips blank/cover pages.
"""

import os
import re

import fitz  # PyMuPDF

# A page with fewer than this many non-whitespace characters is treated as
# effectively empty (blank, cover, or image-only page).
MIN_PAGE_CHARS = 20

# Matches a consolidated-report section heading on its OWN line.  Three
# heading families exist in the corpus:
#   - OAG:    "COUNTY EXECUTIVE OF NAKURU" / "COUNTY ASSEMBLY OF NAKURU"
#   - CoB BIRR: "County Government of Nakuru" (title case)
# Anchored to the full line so the county name is exactly the rest of the
# heading line (never bleeds into following body text).  Case-insensitive so
# both the all-caps and title-case conventions match.
_COUNTY_HEADING_RE = re.compile(
    r"^\s*COUNTY\s+(?:EXECUTIVE|ASSEMBLY|GOVERNMENT)\s+OF\s+([A-Za-z]+(?:\s+[A-Za-z]+)*)\s*$",
    re.IGNORECASE,
)


def _heading_county(text: str) -> str | None:
    """Return the county name from a standalone heading line, or None."""
    for line in text.splitlines():
        m = _COUNTY_HEADING_RE.match(line.strip())
        if m is not None:
            return " ".join(m.group(1).split())
    return None


def extract_county_section(
    pdf_path: str,
    county: str = "nakuru",
    source: str | None = None,
) -> list[dict]:
    """Extract only the pages belonging to one county's section.

    Consolidated OAG/CoB PDFs cover all 47 counties in sequence, each opened
    by a heading like ``COUNTY EXECUTIVE OF NAKURU``.  This walks the pages,
    tracks the current county from the most recent heading, and returns only
    the pages for *county* — so chunking and citations stay scoped to Nakuru
    instead of embedding the whole 47-county document.

    If no heading is found at all (a county-specific, non-consolidated PDF),
    it falls back to returning every non-empty page via ``extract_pages``.
    """
    source = source or os.path.basename(pdf_path)
    current_county: str | None = None
    section_pages: list[dict] = []
    saw_heading = False

    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc):
            text = page.get_text().strip()
            if len(text) < MIN_PAGE_CHARS:
                continue

            heading = _heading_county(text)
            if heading is not None:
                saw_heading = True
                current_county = heading

            if current_county is not None and current_county.lower() == county.lower():
                section_pages.append({
                    "source": source,
                    "page": index + 1,  # 1-indexed
                    "text": text,
                })

    # No county heading anywhere → a single-county (non-consolidated) PDF:
    # return every non-empty page.
    if not saw_heading:
        return extract_pages(pdf_path)

    # Consolidated PDF — return the collected target-county pages (possibly
    # empty if the county simply wasn't present, which callers can detect).
    return section_pages


def check_text_layer(pdf_path: str, pages_to_check: int = 5) -> bool:
    """Return True if the PDF has an extractable text layer.

    Opens the PDF and inspects the first ``pages_to_check`` pages. If every
    checked page is empty or near-empty, the PDF is almost certainly a scanned
    (image-only) document that would need OCR, and this returns False.
    """
    with fitz.open(pdf_path) as doc:
        n = min(pages_to_check, doc.page_count)
        for i in range(n):
            text = doc[i].get_text().strip()
            if len(text) >= MIN_PAGE_CHARS:
                return True
    return False


def extract_pages(pdf_path: str) -> list[dict]:
    """Extract text per page from a PDF.

    Returns a list of dicts, one per non-empty page::

        {"source": <filename>, "page": <1-indexed page number>, "text": <raw text>}

    Pages whose extracted text is empty or under ``MIN_PAGE_CHARS`` characters
    (likely blank or cover pages) are skipped.
    """
    source = os.path.basename(pdf_path)
    pages: list[dict] = []
    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc):
            text = page.get_text().strip()
            if len(text) < MIN_PAGE_CHARS:
                continue
            pages.append({
                "source": source,
                "page": index + 1,  # 1-indexed
                "text": text,
            })
    return pages
