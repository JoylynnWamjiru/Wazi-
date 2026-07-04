"""Extract text from county budget PDFs using PyMuPDF (fitz).

Provides a text-layer check to detect scanned/image-only PDFs that would
need OCR, and a per-page text extractor that skips blank/cover pages.
"""

import os

import fitz  # PyMuPDF

# A page with fewer than this many non-whitespace characters is treated as
# effectively empty (blank, cover, or image-only page).
MIN_PAGE_CHARS = 20


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
