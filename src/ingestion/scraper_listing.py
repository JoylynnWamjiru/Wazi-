"""Listing-page scraper — find and select the right PDF from a government page.

The ``sources.url`` field stores LISTING PAGES (e.g. an OAG page that hosts
consolidated PDFs for all 47 counties, or a CoB page that hosts every BIRR
edition).  This module turns that page into the one concrete PDF download URL
the source actually represents:

    listing page ──fetch──→ HTML ──parse──→ [(title, pdf_url), ...] ──select──→ pdf_url

Selection is keyword-driven: the source's ``title`` / ``government_arm`` /
``report_type`` are matched against the anchor text of each PDF link.  The
matcher returns a ranked list of candidates, so a mismatch is a loud failure
(no silent wrong-document ingestion) rather than a guess.
"""

import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

# Reuse the browser User-Agent and SSRF guard from the main scraper.
from src.ingestion.scraper import BROWSER_UA, _validate_url

# ---------------------------------------------------------------------------
# Fetch + parse
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: float = 60.0) -> str:
    """GET *url* and return its HTML text (must be a safe public HTTP(S) URL)."""
    _validate_url(url)
    resp = httpx.get(
        url,
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": BROWSER_UA},
    )
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").lower()
    if "html" not in content_type and not url.lower().endswith((".html", ".htm", "/")):
        raise ValueError(
            f"URL does not serve HTML (Content-Type: {content_type}); "
            f"expected a listing page."
        )
    return resp.text


def extract_pdf_links(html: str, base_url: str) -> list[dict]:
    """Parse every ``<a href="*.pdf">`` from *html* into (title, absolute URL).

    Returns a list of dicts ``{"title": str, "url": str}``, deduplicated by
    URL, preserving page order.  Anchor text is used as the document title
    (falling back to the filename when empty).
    """
    return [
        {"title": l["title"], "url": l["url"]}
        for l in extract_links(html, base_url)
        if l["is_pdf"]
    ]


def extract_links(html: str, base_url: str) -> list[dict]:
    """Parse every ``<a href>`` from *html* into (title, absolute URL, is_pdf).

    Returns ``{"title": str, "url": str, "is_pdf": bool}``, deduplicated by
    URL, preserving page order.  Skips fragment / javascript / mailto links.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    links: list[dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        title = (a.get_text(" ", strip=True) or href.rsplit("/", 1)[-1]).strip()
        links.append({
            "title": title,
            "url": absolute,
            "is_pdf": href.lower().endswith(".pdf"),
        })
    return links


def resolve_pdf_url(listing_url: str, source: dict) -> str:
    """Resolve a listing page to the one concrete PDF URL for *source*.

    Handles two page structures:

    1. **Direct PDF listing** (OAG / CoB): the listing page links straight to
       ``.pdf`` files — select the best match by keyword.

    2. **Two-level repository** (KIPPRA): the listing page links to *abstract
       pages* (HTML), each of which holds the actual ``.pdf`` download link.
       The best-matching abstract page is visited, and its first PDF link is
       used.

    Returns the absolute PDF URL.  Raises ``ValueError`` on no match.
    """
    html = fetch_html(listing_url)
    links = extract_links(html, listing_url)

    pdf_links = [l for l in links if l["is_pdf"]]
    if pdf_links:
        return select_pdf(pdf_links, source)

    # No direct PDFs → two-level repository (KIPPRA-style).
    item_links = [l for l in links if not l["is_pdf"]]
    if not item_links:
        raise ValueError(
            f"Listing page '{listing_url}' contains neither PDF links nor item links."
        )

    # Visit abstract pages in descending match order; the first that yields a
    # PDF wins.  A source title like "Nakuru City County Budget Review…"
    # scores highest against the matching item's anchor text.
    ranked = sorted(
        item_links,
        key=lambda l: _score_link(l["title"], source),
        reverse=True,
    )
    for item in ranked[:5]:
        try:
            abstract_html = fetch_html(item["url"])
            abstract_pdfs = [
                l["url"] for l in extract_links(abstract_html, item["url"]) if l["is_pdf"]
            ]
            if abstract_pdfs:
                print(f"[scraper] resolved via abstract page: {item['title']} → {abstract_pdfs[0]}")
                return abstract_pdfs[0]
        except Exception as exc:  # noqa: BLE001 - try the next candidate
            print(f"[scraper] abstract page {item['url']} failed: {type(exc).__name__}")

    raise ValueError(
        f"No abstract page for source '{source['title']}' yielded a PDF. "
        f"Checked: {[l['title'] for l in ranked[:5]]}"
    )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

# Keywords that steer selection, derived from the source's metadata.
_ARM_KEYWORDS = {
    "executive": ["executive"],
    "assembly": ["assembly"],
}
_REPORT_KEYWORDS = {
    "audit_report": ["audit"],
    "birr": ["budget implementation", "birr", "implementation review"],
    "exchequer": ["exchequer"],
    "cbrop": ["budget review", "outlook", "cbrop"],
    "programme_budget": ["programme", "budget estimates", "approved budget"],
}
# Edition terms for the BIRR quarterly family (Q1 / Half / Nine / Annual).
_EDITION_KEYWORDS = [
    "first quarter", "q1",
    "half year", "half-year", "first half",
    "nine months", "nine-months",
    "annual",
]


def _score_link(link_title: str, source: dict) -> int:
    """Score a link title against the source's metadata. Higher = better."""
    text = link_title.lower()
    score = 0

    title_tokens = set(re.findall(r"[a-z0-9]+", source["title"].lower()))
    if title_tokens and title_tokens.intersection(re.findall(r"[a-z0-9]+", text)):
        score += 10  # strong: words overlap with the source title

    for kw in _ARM_KEYWORDS.get(source["government_arm"], []):
        if kw in text:
            score += 5

    for kw in _REPORT_KEYWORDS.get(source["report_type"], []):
        if kw in text:
            score += 4

    for kw in _EDITION_KEYWORDS:
        if kw in text:
            score += 3

    return score


def select_pdf(links: list[dict], source: dict) -> str:
    """Pick the single best PDF URL for *source* from *links*.

    Raises ``ValueError`` if no link scores above zero — a loud failure is
    safer than silently ingesting the wrong consolidated document.
    """
    if not links:
        raise ValueError("Listing page contains no PDF links.")

    scored = sorted(
        ((_score_link(l["title"], source), l) for l in links),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best_link = scored[0]

    if best_score <= 0:
        titles = ", ".join(repr(l["title"]) for l in links[:5])
        raise ValueError(
            f"No PDF on the listing page matched source '{source['title']}' "
            f"(arm={source['government_arm']}, type={source['report_type']}). "
            f"Available links: {titles}"
        )
    return best_link["url"]
