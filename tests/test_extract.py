"""Tests for PDF text extraction against the real Nakuru corpus PDFs.

Needs ``pymupdf`` (installed) and the two PDFs in ``data/``. No DB.
"""

from pathlib import Path

import pytest

from src.ingestion.extract import check_text_layer, extract_pages

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PDFS = ["nakuru_audit_report.pdf", "nakuru_birr_q1.pdf"]


def _pdf(name: str) -> str:
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"corpus PDF not present: {name}")
    return str(path)


@pytest.mark.parametrize("name", PDFS)
def test_corpus_pdfs_have_a_text_layer(name):
    assert check_text_layer(_pdf(name)) is True


@pytest.mark.parametrize("name", PDFS)
def test_extract_pages_returns_traceable_pages(name):
    pages = extract_pages(_pdf(name))
    assert pages, "expected at least one non-empty page"
    for p in pages:
        assert p["source"] == name          # filename, for citations
        assert p["page"] >= 1               # 1-indexed
        assert len(p["text"]) >= 20         # short/blank pages skipped


@pytest.mark.parametrize("name", PDFS)
def test_page_numbers_are_strictly_increasing(name):
    pages = extract_pages(_pdf(name))
    numbers = [p["page"] for p in pages]
    assert numbers == sorted(numbers)
    assert len(numbers) == len(set(numbers))  # no duplicates
