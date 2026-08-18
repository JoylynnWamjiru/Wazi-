"""Tests for table-aware extraction — ruled tables rendered as Markdown."""

from pathlib import Path

import fitz
import pytest

from src.ingestion.extract import extract_pages, page_to_markdown

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _make_table_pdf(path) -> None:
    """Write a one-page PDF whose table is drawn with ruling lines.

    PyMuPDF's ``find_tables(strategy="lines")`` only recognises tables
    actually drawn with vector lines, so we draw the grid explicitly.
    """
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    cells = [
        ["Item", "Amount (Kshs)"],
        ["Basic Salaries", "3,122,265,279"],
        ["Allowances", "2,363,511,258"],
    ]
    x0, y0 = 50, 50
    col_widths = [150, 150]
    row_height = 30
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            page.insert_text(
                (x0 + sum(col_widths[:c]) + 5, y0 + r * row_height + 20),
                cell,
                fontsize=10,
            )
    for r in range(len(cells) + 1):
        y = y0 + r * row_height
        page.draw_line(fitz.Point(x0, y), fitz.Point(x0 + sum(col_widths), y))
    for c in range(len(col_widths) + 1):
        x = x0 + sum(col_widths[:c])
        page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + len(cells) * row_height))
    doc.save(str(path))
    doc.close()


def test_prose_page_has_no_table_markup():
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text(
        (50, 50),
        "This is a normal paragraph of prose with no table.",
        fontsize=10,
    )
    text = page_to_markdown(page)
    doc.close()
    assert "|" not in text
    assert "normal paragraph of prose" in text


def test_ruled_table_renders_as_markdown(tmp_path):
    path = tmp_path / "table.pdf"
    _make_table_pdf(path)
    doc = fitz.open(str(path))
    text = page_to_markdown(doc[0])
    doc.close()

    assert "|" in text
    # The whole point: a label and its figure stay on the same line, so a
    # chunk embedding captures "Basic Salaries <-> 3,122,265,279".
    row = next(line for line in text.splitlines() if "Basic Salaries" in line)
    assert "3,122,265,279" in row


def test_extract_pages_keeps_table_markdown(tmp_path):
    path = tmp_path / "table.pdf"
    _make_table_pdf(path)
    pages = extract_pages(str(path))
    assert pages, "expected at least one page"
    joined = "\n".join(p["text"] for p in pages)
    assert "|" in joined
    assert "Basic Salaries" in joined


def test_extract_pages_can_disable_tables(tmp_path):
    path = tmp_path / "table.pdf"
    _make_table_pdf(path)
    pages = extract_pages(str(path), tables=False)
    joined = "\n".join(p["text"] for p in pages)
    # Raw linear extraction has no Markdown pipes — the cell text is smeared.
    assert "|" not in joined
    assert "Basic Salaries" in joined  # text is still there, just unstructured


# ---------------------------------------------------------------------------
# Real corpus (skipped when data/ is absent) — integration check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["nakuru_audit_report.pdf", "nakuru_birr_q1.pdf"])
def test_corpus_contains_markdown_tables(name):
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"corpus PDF not present: {name}")
    pages = extract_pages(str(path))
    assert pages, "expected at least one non-empty page"
    assert any("|" in p["text"] for p in pages), (
        f"expected at least one ruled table rendered as Markdown in {name}"
    )
