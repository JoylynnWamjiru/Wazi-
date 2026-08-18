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


# ---------------------------------------------------------------------------
# Table-aware text (ruled tables -> Markdown)
# ---------------------------------------------------------------------------

# PyMuPDF's default table detection (strategy="text") hallucinates tables out
# of prose: on a 17-page OAG report it turned the "Basis for Qualified
# Opinion" paragraph into a 48-row "table" with words split across columns
# ("h flows|refl|ects Nil balan|ce").  The "lines" strategy only recognises
# tables actually drawn with ruling lines — exactly what the OAG/CoB/county
# budget PDFs use for figures — so we use that and ignore text-only "tables".
_TABLE_STRATEGY = "lines"


def _markdown_table(table) -> str:
    """Render one PyMuPDF table to a Markdown table string.

    PyMuPDF inserts ``<br>`` for wrapped cell text; we collapse those to a
    space so embeddings read a cell as one phrase rather than
    "Amount<br>as<br>per".
    """
    try:
        md = table.to_markdown()
    except Exception:  # pragma: no cover - defensive across PyMuPDF versions
        return ""
    if not md:
        return ""
    return md.replace("<br>", " ").replace("<br/>", " ").strip()


def _block_inside_table(block_rect, table_rects) -> bool:
    """True if more than half of *block_rect* lies inside any table rect."""
    if block_rect.is_empty:
        return False
    for table_rect in table_rects:
        inter = block_rect & table_rect
        if not inter.is_empty:
            if inter.get_area() / block_rect.get_area() > 0.5:
                return True
    return False


def page_to_markdown(page) -> str:
    """Return a page's text with ruled tables rendered as Markdown tables.

    Table cell text is otherwise smeared together by ``page.get_text()`` (a
    budget figure and its label end up far apart), which hurts retrieval.
    Rendering tables as pipe-delimited Markdown keeps each row's label and
    figure on one line, so chunk embeddings capture "what belongs to what".

    Non-table prose is preserved as-is, and content order is reconstructed by
    vertical then horizontal position so top-to-bottom, left-to-right reading
    order survives.
    """
    text = page.get_text().strip()
    # Fast path: a page with no vector drawings cannot contain ruled tables,
    # so skip the expensive find_tables call for the common prose-only page.
    try:
        if not page.get_drawings():
            return text
        finder = page.find_tables(strategy=_TABLE_STRATEGY)
    except Exception:  # pragma: no cover - some pages may fail; fall back
        return text

    tables: list[tuple[fitz.Rect, str]] = []
    for table in finder.tables:
        if not table.bbox:
            continue
        md = _markdown_table(table)
        if md:
            tables.append((fitz.Rect(table.bbox), md))
    if not tables:
        return text

    table_rects = [rect for rect, _ in tables]
    # Each item is keyed by (y0, x0) so the final sort reads top-to-bottom,
    # then left-to-right.  Sorting by y0 alone scrambles side-by-side blocks
    # and tables whose tops differ by a pixel or two; the x0 tie-break keeps
    # a stable left-to-right order within a horizontal band.
    items: list[tuple[tuple[float, float], str]] = []

    for block in page.get_text("blocks", sort=True):
        x0, y0, x1, y1, block_text, _block_no, _block_type = block
        rect = fitz.Rect(x0, y0, x1, y1)
        if _block_inside_table(rect, table_rects):
            continue
        if block_text.strip():
            items.append(((y0, x0), block_text.strip()))

    for rect, md in tables:
        items.append(((rect.y0, rect.x0), md))

    items.sort(key=lambda item: item[0])
    return "\n\n".join(content for _, content in items)


def extract_county_section(
    pdf_path: str,
    county: str = "nakuru",
    source: str | None = None,
    tables: bool = True,
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
            text = page_to_markdown(page) if tables else page.get_text().strip()
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
        return extract_pages(pdf_path, tables=tables)

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


def extract_pages(pdf_path: str, tables: bool = True) -> list[dict]:
    """Extract text per page from a PDF.

    When ``tables`` is True (the default), ruled tables are rendered as
    Markdown tables via :func:`page_to_markdown` so tabular figures stay
    structured for retrieval.

    Returns a list of dicts, one per non-empty page::

        {"source": <filename>, "page": <1-indexed page number>, "text": <raw text>}

    Pages whose extracted text is empty or under ``MIN_PAGE_CHARS`` characters
    (likely blank or cover pages) are skipped.
    """
    source = os.path.basename(pdf_path)
    pages: list[dict] = []
    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc):
            text = page_to_markdown(page) if tables else page.get_text().strip()
            if len(text) < MIN_PAGE_CHARS:
                continue
            pages.append({
                "source": source,
                "page": index + 1,  # 1-indexed
                "text": text,
            })
    return pages
