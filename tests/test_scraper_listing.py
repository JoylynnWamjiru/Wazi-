"""Tests for listing-page parsing and county-section extraction.

Pure functions (no network) for the HTML parser and PDF selector, plus a
synthetic-PDF test for the Nakuru heading search.  The embedder is not
exercised here — these cover resolve → parse → select → section-extract.
"""

import pytest

from src.ingestion.scraper_listing import extract_pdf_links, select_pdf


# ---------------------------------------------------------------------------
# extract_pdf_links — HTML parsing
# ---------------------------------------------------------------------------

def test_extract_pdf_links_parses_and_dedups():
    html = """
    <html><body>
      <a href="/reports/executive.pdf">County Executive Reports</a>
      <a href="/reports/assembly.pdf">County Assembly Reports</a>
      <a href="/reports/budget.pdf">Budget Review</a>
      <a href="https://example.com/reports/executive.pdf">Duplicate URL</a>
      <a href="/reports/notes.txt">not a pdf</a>
    </body></html>
    """
    links = extract_pdf_links(html, "https://example.com/listing/")

    # 3 unique PDFs: the 4th anchor resolves to the SAME URL as the 1st.
    assert len(links) == 3
    urls = [l["url"] for l in links]
    assert urls == [
        "https://example.com/reports/executive.pdf",
        "https://example.com/reports/assembly.pdf",
        "https://example.com/reports/budget.pdf",
    ]


def test_extract_pdf_links_uses_filename_when_anchor_text_empty():
    html = '<a href="/docs/report.pdf"></a>'
    links = extract_pdf_links(html, "https://example.com/")
    assert links[0]["title"] == "report.pdf"


def test_extract_pdf_links_returns_empty_for_no_pdfs():
    assert extract_pdf_links("<a href='/x.txt'>text</a>", "https://example.com/") == []


# ---------------------------------------------------------------------------
# select_pdf — keyword matching
# ---------------------------------------------------------------------------

def test_select_pdf_picks_matching_government_arm():
    links = [
        {"title": "County Executive Audit Reports", "url": "https://x/exec.pdf"},
        {"title": "County Assembly Audit Reports", "url": "https://x/assembly.pdf"},
    ]
    src = {
        "title": "Nakuru County Assembly, FY 2023/24",
        "government_arm": "assembly",
        "report_type": "audit_report",
    }
    assert select_pdf(links, src) == "https://x/assembly.pdf"


def test_select_pdf_picks_birr_edition():
    links = [
        {"title": "BIRR First Quarter", "url": "https://x/q1.pdf"},
        {"title": "BIRR First Half Year", "url": "https://x/half.pdf"},
        {"title": "BIRR Nine Months", "url": "https://x/nine.pdf"},
    ]
    src = {
        "title": "County Governments BIRR — First Half FY 2025/26",
        "government_arm": "consolidated",
        "report_type": "birr",
    }
    # "First Half" appears in both the title and the link → highest score.
    assert select_pdf(links, src) == "https://x/half.pdf"


def test_select_pdf_raises_when_nothing_matches():
    links = [{"title": "County Executive Audit Reports", "url": "https://x/exec.pdf"}]
    src = {
        "title": "Nakuru BIRR Report",
        "government_arm": "consolidated",
        "report_type": "birr",
    }
    with pytest.raises(ValueError, match="No PDF"):
        select_pdf(links, src)


def test_select_pdf_raises_for_empty_links():
    with pytest.raises(ValueError, match="no PDF links"):
        select_pdf([], {"title": "x", "government_arm": "executive", "report_type": "audit_report"})


# ---------------------------------------------------------------------------
# extract_county_section — heading search (synthetic PDF)
# ---------------------------------------------------------------------------

def _make_consolidated_pdf(path):
    """Build a tiny 5-page consolidated PDF with per-county headings."""
    import fitz

    doc = fitz.open()
    cover = doc.new_page()
    cover.insert_text((72, 72), "Cover page — consolidated county reports")

    # Nakuru executive section (pages 2-3).
    p = doc.new_page()
    p.insert_text((72, 72), "COUNTY EXECUTIVE OF NAKURU")
    p.insert_text((72, 100), "Budget allocation details for Nakuru executive.")
    p = doc.new_page()
    p.insert_text((72, 72), "Continuation of Nakuru executive figures.")

    # Nandi section (page 4) — a DIFFERENT county must not leak in.
    p = doc.new_page()
    p.insert_text((72, 72), "COUNTY EXECUTIVE OF NANDI")
    p.insert_text((72, 100), "Budget allocation details for Nandi executive.")

    doc.save(str(path))
    doc.close()


def test_extract_county_section_returns_only_target_county(tmp_path):
    from src.ingestion.extract import extract_county_section

    path = tmp_path / "consolidated.pdf"
    _make_consolidated_pdf(path)

    pages = extract_county_section(str(path), county="nakuru")

    page_numbers = [p["page"] for p in pages]
    assert page_numbers == [2, 3]  # cover (1) skipped, Nandi (4) excluded
    assert all("nakuru" in p["text"].lower() or p["page"] == 3 for p in pages)


def test_extract_county_section_falls_back_when_no_headings(tmp_path):
    """A single-county PDF (no 'COUNTY ... OF ...' headings) returns all pages."""
    import fitz

    from src.ingestion.extract import extract_county_section

    path = tmp_path / "single.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "Nakuru county budget figures for the year.")
    p.insert_text((72, 100), "Revenue and expenditure summary line.")
    doc.save(str(path))
    doc.close()

    pages = extract_county_section(str(path), county="nakuru")
    assert len(pages) == 1


def test_extract_county_section_returns_empty_for_missing_county(tmp_path):
    """A consolidated PDF that never mentions the target county → empty."""
    import fitz

    from src.ingestion.extract import extract_county_section

    path = tmp_path / "other.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "COUNTY EXECUTIVE OF NANDI")
    p.insert_text((72, 100), "Nandi budget allocation details here.")
    doc.save(str(path))
    doc.close()

    pages = extract_county_section(str(path), county="nakuru")
    assert pages == []  # saw headings, but none for Nakuru


def test_extract_county_section_matches_birr_title_case_heading(tmp_path):
    """CoB BIRRs use 'County Government of Nakuru' (title case) — must match."""
    import fitz

    from src.ingestion.extract import extract_county_section

    path = tmp_path / "birr.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "County Government of Nakuru")
    p.insert_text((72, 100), "BIRR quarter one revenue and expenditure detail.")
    p = doc.new_page()
    p.insert_text((72, 72), "County Government of Nandi")
    p.insert_text((72, 100), "Nandi BIRR detail line.")
    doc.save(str(path))
    doc.close()

    pages = extract_county_section(str(path), county="nakuru")
    assert [p["page"] for p in pages] == [1]


# ---------------------------------------------------------------------------
# resolve_pdf_url — two-level KIPPRA navigation
# ---------------------------------------------------------------------------

def test_resolve_pdf_url_single_level(monkeypatch):
    """Direct-PDF listing (OAG/CoB) selects the right PDF without visiting
    an abstract page."""
    from src.ingestion import scraper_listing

    monkeypatch.setattr(scraper_listing, "fetch_html", lambda url, timeout=60: """
        <a href="/docs/exec.pdf">County Executive Audit</a>
        <a href="/docs/assembly.pdf">County Assembly Audit</a>
    """)

    src = {"title": "Nakuru County Assembly FY 2024",
           "government_arm": "assembly", "report_type": "audit_report"}
    url = scraper_listing.resolve_pdf_url("https://oag.example/list/", src)
    assert url == "https://oag.example/docs/assembly.pdf"


def test_resolve_pdf_url_two_level_kippra(monkeypatch):
    """KIPPRA listing → abstract page → PDF.  The listing page has no .pdf
    links, only abstract-page links."""
    from src.ingestion import scraper_listing

    pages = {
        "https://repo.example/handle/1": """
            <a href="/items/nakuru-cbrop">Nakuru City County Budget Review and Outlook Paper 2024</a>
            <a href="/items/nairobi-cbrop">Nairobi City County Budget Review and Outlook Paper 2024</a>
        """,
        "https://repo.example/items/nakuru-cbrop": """
            <a href="/bitstream/nakuru-cbrop.pdf">Download</a>
        """,
        "https://repo.example/items/nairobi-cbrop": """
            <a href="/bitstream/nairobi-cbrop.pdf">Download</a>
        """,
    }
    monkeypatch.setattr(scraper_listing, "fetch_html", lambda url, timeout=60: pages[url])

    src = {"title": "Nakuru City County Budget Review and Outlook Paper 2024",
           "government_arm": "executive", "report_type": "cbrop"}
    url = scraper_listing.resolve_pdf_url("https://repo.example/handle/1", src)
    assert url == "https://repo.example/bitstream/nakuru-cbrop.pdf"


def test_resolve_pdf_url_two_level_raises_when_no_pdf(monkeypatch):
    """An abstract page with no PDF link yields a loud failure."""
    from src.ingestion import scraper_listing

    pages = {
        "https://repo.example/handle/1": (
            '<a href="/items/doc">A Document</a>'
        ),
        "https://repo.example/items/doc": "<p>no download link here</p>",
    }
    monkeypatch.setattr(scraper_listing, "fetch_html", lambda url, timeout=60: pages[url])

    src = {"title": "A Document", "government_arm": "executive", "report_type": "cbrop"}
    with pytest.raises(ValueError, match="No abstract page"):
        scraper_listing.resolve_pdf_url("https://repo.example/handle/1", src)
