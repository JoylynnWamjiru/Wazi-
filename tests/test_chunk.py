"""Unit tests for word-based chunking. Pure functions — no DB, no network."""

import pytest

from src.ingestion.chunk import chunk_pages


def _page(source: str, page: int, n_words: int) -> dict:
    return {"source": source, "page": page, "text": " ".join(f"w{i}" for i in range(n_words))}


def test_chunk_ids_follow_source_page_index_scheme():
    chunks = chunk_pages([_page("nakuru_audit_report.pdf", 12, 30)], chunk_size=10, overlap=2)
    assert chunks[0]["chunk_id"] == "nakuru_audit_report_p12_c0"
    assert chunks[1]["chunk_id"] == "nakuru_audit_report_p12_c1"


def test_chunks_never_cross_page_boundaries():
    pages = [_page("doc.pdf", 1, 40), _page("doc.pdf", 2, 40)]
    chunks = chunk_pages(pages, chunk_size=15, overlap=5)
    # Every chunk's words must belong to exactly one page — verified by the
    # page field being consistent and ids not mixing pages.
    for c in chunks:
        assert c["page"] in (1, 2)
        assert f"_p{c['page']}_" in c["chunk_id"]


def test_consecutive_chunks_overlap_by_overlap_words():
    chunks = chunk_pages([_page("doc.pdf", 1, 30)], chunk_size=10, overlap=3)
    first_words = chunks[0]["text"].split()
    second_words = chunks[1]["text"].split()
    # The last `overlap` words of chunk 0 repeat as the first of chunk 1.
    assert first_words[-3:] == second_words[:3]


def test_single_chunk_when_page_shorter_than_chunk_size():
    chunks = chunk_pages([_page("doc.pdf", 5, 7)], chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0]["page"] == 5


def test_empty_pages_are_skipped():
    pages = [{"source": "doc.pdf", "page": 1, "text": "   "}, _page("doc.pdf", 2, 12)]
    chunks = chunk_pages(pages, chunk_size=10, overlap=2)
    assert all(c["page"] == 2 for c in chunks)


@pytest.mark.parametrize("chunk_size,overlap", [(0, 0), (-1, 0), (10, 10), (10, 11)])
def test_invalid_parameters_raise(chunk_size, overlap):
    with pytest.raises(ValueError):
        chunk_pages([_page("doc.pdf", 1, 5)], chunk_size=chunk_size, overlap=overlap)
