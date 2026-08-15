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


def extract_wpdm_downloads(html: str, base_url: str) -> list[dict]:
    """Parse WordPress Download Manager links (used by CoB).

    WPDM renders the download as ``<a href="#" onclick="location.href='…?wpdmdl=N'">``
    with the report title in a following ``<h3>``.  The ``onclick`` URL serves
    the PDF directly.  Returns ``{"title": str, "url": str, "is_pdf": True}``.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    results: list[dict] = []
    for a in soup.find_all("a", href=True):
        cls = " ".join(a.get("class", []))
        onclick = a.get("onclick", "")
        m = re.search(r"location\.href\s*=\s*'([^']+)'", onclick)
        if m is None:
            continue
        url = urljoin(base_url, m.group(1))
        if url in seen:
            continue
        seen.add(url)
        # Title lives in the nearest following (or preceding) <h3>.
        title = ""
        h3 = a.find_next("h3")
        if h3 is None:
            h3 = a.find_previous("h3")
        if h3 is not None:
            title = h3.get_text(" ", strip=True)
        if not title:
            title = url.rsplit("/", 1)[-1]
        results.append({"title": title, "url": url, "is_pdf": True})
    return results


def resolve_pdf_url(listing_url: str, source: dict) -> str:
    """Resolve a listing page to the one concrete PDF URL for *source*.

    Handles three page structures:

    1. **Direct PDF listing** (OAG): the listing page links straight to
       ``.pdf`` files — select the best match by keyword (the filename carries
       the signal when the anchor is a bare "Download").

    2. **WordPress Download Manager** (CoB): download URLs are hidden in
       ``onclick="location.href='…?wpdmdl=N'"`` with titles in ``<h3>``.

    3. **Two-level repository** (KIPPRA abstract pages): the listing page links
       to HTML pages, each of which holds the actual ``.pdf`` link.

    Returns the absolute download URL.  Raises ``ValueError`` on no match.
    """
    html = fetch_html(listing_url)
    links = extract_links(html, listing_url)

    pdf_links = [l for l in links if l["is_pdf"]]
    if pdf_links:
        return select_pdf(pdf_links, source)

    # WPDM downloads (CoB) — onclick download URLs, not plain .pdf anchors.
    wpdm = extract_wpdm_downloads(html, listing_url)
    if wpdm:
        return select_pdf(wpdm, source)

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
        key=lambda l: _score_link(l, source),
        reverse=True,
    )
    for item in ranked[:5]:
        try:
            abstract_html = fetch_html(item["url"])
            abstract_pdfs = [
                l["url"] for l in extract_links(abstract_html, item["url"]) if l["is_pdf"]
            ]
            if abstract_pdfs:
                print(f"[scraper] resolved via abstract page: {item['title']} -> {abstract_pdfs[0]}")
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
    "executive": ["executive", "executives"],
    "assembly": ["assembly", "assemblies"],
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


def _score_link(link: dict, source: dict) -> int:
    """Score a link against the source's metadata. Higher = better.

    Scores BOTH the anchor text and the URL/filename — many sites (OAG) use a
    bare "Download" anchor where the filename carries the signal
    ("GREEN-BOOK-EXECUTIVES-…").  Arm keyword matches score ABOVE title-token
    overlap because a generic term like "county" appears in many titles and
    must not beat the arm/type discriminator.
    """
    text = f"{link.get('title', '')} {link.get('url', '')}".lower()
    score = 0

    # Weighted title-token overlap: each shared word adds points, so
    # "First Half" beats "First Quarter" for a "… First Half …" source even
    # though both share "first".
    src_tokens = set(re.findall(r"[a-z0-9]+", source["title"].lower()))
    link_tokens = set(re.findall(r"[a-z0-9]+", text))
    score += 2 * len(src_tokens.intersection(link_tokens))

    for kw in _ARM_KEYWORDS.get(source["government_arm"], []):
        if kw in text:
            score += 15  # strongest discriminator (executive vs assembly)

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
        ((_score_link(l, source), l) for l in links),
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
