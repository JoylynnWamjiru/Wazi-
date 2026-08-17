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

# Matches a consolidated-report section heading.  Heading families:
#   - OAG:    "COUNTY EXECUTIVE OF NAKURU – NO.32" (all caps + county number)
#   - CoB BIRR: "3.31. County Government of Nakuru" (numbered, title case)
# Body text uses the same words in running sentences ("...the County Executive
# of Nakuru reported...") and must NOT be treated as a heading.  We therefore
# (a) strip a leading section number, (b) require a short line, and (c) resolve
# the county against a canonical list so the capture can never swallow trailing
# body text.
_COUNTY_HEADING_RE = re.compile(
    r"COUNTY\s+(?:EXECUTIVE|ASSEMBLY|GOVERNMENT)\s+OF\s+(.+)",
    re.IGNORECASE,
)

# Leading section numbers ("3.31.", "3.31.1", "32.") on CoB/DSpace headings.
_LEADING_NUM_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\s*[.)]?\s+)")

# A heading line longer than this many words is almost certainly body text
# (e.g. "County Executive of Nakuru and War Memorial Hospital Management...").
MAX_HEADING_WORDS = 7

# The 47 counties of Kenya (plus the "Nairobi City" variant).  Names containing
# apostrophes/hyphens/slashes are normalised to letters-only before matching so
# "MURANG'A", "THARAKA-NITHI", "TAITA/TAVETA" and "ELGEYO/MARAKWET" all resolve
# to their canonical form.
_KENYAN_COUNTIES = [
    "Baringo", "Bomet", "Bungoma", "Busia", "Elgeyo Marakwet", "Embu",
    "Garissa", "Homa Bay", "Isiolo", "Kajiado", "Kakamega", "Kericho",
    "Kiambu", "Kilifi", "Kirinyaga", "Kisii", "Kisumu", "Kitui", "Kwale",
    "Laikipia", "Lamu", "Machakos", "Makueni", "Mandera", "Marsabit",
    "Meru", "Migori", "Mombasa", "Murang'a", "Nairobi City", "Nairobi",
    "Nakuru", "Nandi", "Narok", "Nyamira", "Nyandarua", "Nyeri", "Samburu",
    "Siaya", "Taita Taveta", "Tana River", "Tharaka Nithi", "Trans Nzoia",
    "Turkana", "Uasin Gishu", "Vihiga", "Wajir", "West Pokot",
]


def _norm(name: str) -> str:
    """Normalise a name to letters-only lowercase for fuzzy matching."""
    return re.sub(r"[^a-z]", "", name.lower())


# Longest-first so "Nairobi City" wins over "Nairobi" as a prefix.
_COUNTIES_NORM = sorted(
    ((_norm(c), c) for c in _KENYAN_COUNTIES),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def _county_from_text(after_of: str) -> str | None:
    """Resolve the text after "COUNTY ... OF" to a known county name.

    The longest known county whose normalised form prefixes the normalised
    text wins, so trailing junk ("Nakuru and War Memorial Hospital ...") is
    ignored and punctuation variants ("TAITA/TAVETA") still match.
    """
    norm = _norm(after_of)
    for norm_name, canonical in _COUNTIES_NORM:
        if norm.startswith(norm_name):
            return canonical
    return None


def _heading_county(text: str) -> str | None:
    """Return the county name from a standalone heading line, or None."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # A heading can split across two text blocks: "COUNTY EXECUTIVE OF" /
        # "NAKURU – NO.32".  Consider the line alone and joined with the next.
        candidates = [line]
        if i + 1 < len(lines):
            candidates.append(f"{line} {lines[i + 1]}")
        for candidate in candidates:
            candidate = candidate.strip()
            candidate = _LEADING_NUM_RE.sub("", candidate)
            m = _COUNTY_HEADING_RE.match(candidate)
            if m is None:
                continue
            if len(candidate.split()) > MAX_HEADING_WORDS:
                continue
            county = _county_from_text(m.group(1).strip())
            if county is not None:
                return county
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
