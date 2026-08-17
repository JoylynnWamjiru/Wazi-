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


# ---------------------------------------------------------------------------
# _heading_county — robust section-heading detection (unit, no PDF needed)
# ---------------------------------------------------------------------------

def test_heading_county_oag_allcaps_with_number():
    from src.ingestion.extract import _heading_county
    assert _heading_county("COUNTY EXECUTIVE OF NAKURU \u2013 NO.32") == "Nakuru"


def test_heading_county_cob_numbered_title_case():
    from src.ingestion.extract import _heading_county
    assert _heading_county("3.31. County Government of Nakuru") == "Nakuru"


def test_heading_county_rejects_long_body_sentence():
    from src.ingestion.extract import _heading_county
    # Body text starts with the same words as a heading but is a full sentence.
    text = ("County Executive of Nakuru and War Memorial Hospital Management "
            "which is the subject of this audit finding")
    assert _heading_county(text) is None


def test_heading_county_resolves_punctuated_county_names():
    from src.ingestion.extract import _heading_county
    assert _heading_county("COUNTY EXECUTIVE OF THARAKA-NITHI \u2013 NO.13") == "Tharaka Nithi"
    assert _heading_county("COUNTY EXECUTIVE OF MURANG'A \u2013 NO.21") == "Murang'a"
    assert _heading_county("COUNTY EXECUTIVE OF TAITA/TAVETA \u2013 NO.6") == "Taita Taveta"
    assert _heading_county("COUNTY EXECUTIVE OF NAIROBI CITY \u2013 NO.47") == "Nairobi City"


def test_heading_county_split_across_lines():
    from src.ingestion.extract import _heading_county
    assert _heading_county("COUNTY EXECUTIVE OF\nNAKURU \u2013 NO.32") == "Nakuru"


def test_heading_county_ignores_unknown_county():
    from src.ingestion.extract import _heading_county
    assert _heading_county("COUNTY EXECUTIVE OF ATLANTIS \u2013 NO.99") is None
