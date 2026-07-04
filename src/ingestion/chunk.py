"""Split extracted page text into overlapping, word-based chunks.

Chunks never cross page boundaries, so every chunk remains traceable to
exactly one source document and page — important for grounded citations.
"""


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
        words = page["text"].split()
        if not words:
            continue

        index = 0
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
            # Stop once this window reached the end of the page's words.
            if start + chunk_size >= len(words):
                break
            start += step

    return chunks
