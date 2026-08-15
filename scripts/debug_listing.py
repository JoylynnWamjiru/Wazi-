"""Debug helper — fetch a listing page, save its HTML, and dump its links.

Usage:
    python scripts/debug_listing.py <url> [--out <dir>]

Saves the raw HTML to <dir>/page.html and prints every <a href> with its
anchor text, split into PDF vs non-PDF.  Useful for inspecting the real
HTML structure of OAG / CoB / KIPPRA listing pages before tuning the
scraper's selector logic.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a listing page and dump its links.")
    parser.add_argument("url")
    parser.add_argument("--out", default=".", help="Directory for saved HTML/json.")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {args.url} ...", flush=True)
    r = httpx.get(args.url, headers={"User-Agent": UA}, follow_redirects=True, timeout=60)
    r.raise_for_status()
    html = r.text

    slug = re.sub(r"[^a-z0-9]+", "_", args.url.lower()).strip("_")[:60]
    (out / f"{slug}.html").write_text(html, encoding="utf-8")
    print(f"Saved {len(html)} bytes -> {out / (slug + '.html')}", flush=True)

    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        text = (a.get_text(" ", strip=True) or href.rsplit("/", 1)[-1]).strip()
        links.append({
            "title": text,
            "url": urljoin(args.url, href),
            "is_pdf": href.lower().endswith(".pdf"),
        })

    pdfs = [l for l in links if l["is_pdf"]]
    others = [l for l in links if not l["is_pdf"]]

    result = {"url": args.url, "pdf_links": pdfs, "non_pdf_links": others}
    (out / f"{slug}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nPDF links ({len(pdfs)}):", flush=True)
    for l in pdfs[:40]:
        print(f"  [{l['title'][:70]}] -> {l['url'][:120]}", flush=True)

    print(f"\nNon-PDF links ({len(others)}):", flush=True)
    for l in others[:40]:
        print(f"  [{l['title'][:70]}] -> {l['url'][:120]}", flush=True)


if __name__ == "__main__":
    main()
