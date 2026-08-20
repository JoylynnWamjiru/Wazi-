"""Split extracted page text into overlapping, word-based chunks.

Chunks never cross page boundaries, so every chunk remains traceable to
exactly one source document and page — important for grounded citations.
"""

import re

# County audit reports number their sections "839.4. Stalled Construction ..."
# or "665. Supply, Installation ...".  A heading boundary forces a hard chunk
# break so one project's story (contract + payments + status) stays in a single
# chunk instead of being split across a fixed word window.  The pattern is
# deliberately specific (2-3 digits, a dot, an optional sub-number, then a
# capitalised word) so it does not fire on figures like "Kshs. 148,902,024" or
# "10.5 million" or on table cells like "Table 3.457".
_HEADING_RE = re.compile(r"(?=\b\d{2,3}\.(?:\d+\.?)?\s+[A-Z][a-z])")


def _chunk_id(source: str, page: int, index: int) -> str:
    """Build a unique chunk id like ``nakuru_audit_report_p12_c0``."""
    stem = source.rsplit(".", 1)[0]  # drop the .pdf extension
    return f"{stem}_p{page}_c{index}"


def chunk_pages(
    pages: list[dict],
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[dict]:
    """Split each page's text into ~``chunk_size``-word overlapping chunks.

    Consecutive chunks from the same page repeat ``overlap`` words so context
    isn't lost at chunk edges. Text is never merged across page boundaries.
    Section headings (e.g. ``839.4``) force a hard boundary so one section is
    never merged with its neighbour.

    Returns a list of dicts shaped like::

        {"chunk_id": <str>, "source": <filename>, "page": <int>, "text": <str>}
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    step = chunk_size - overlap
    chunks: list[dict] = []

    for page in pages:
        text = page["text"]
        # Split on audit-report section headings first, so a heading always
        # starts a new chunk (even if the preceding window was short).  Pages
        # without headings collapse to a single segment, so the word-window
        # behaviour below is unchanged for them.
        segments = _HEADING_RE.split(text) if text else []
        if not segments:
            continue

        index = 0
        for segment in segments:
            words = segment.split()
            if not words:
                continue

            start = 0
            while start < len(words):
                window = words[start:start + chunk_size]
                chunks.append({
                    "chunk_id": _chunk_id(page["source"], page["page"], index),
                    "source": page["source"],
                    "page": page["page"],
                    "text": " ".join(window),
                })
                index += 1
                # Stop once this window reached the end of the segment.
                if start + chunk_size >= len(words):
                    break
                start += step

    return chunks
