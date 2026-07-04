"""Orchestrate the ingestion pipeline: check -> extract -> chunk -> save.

Builds a single corpus of page-traceable text chunks from the Nakuru county
PDFs in ``data/`` and writes it to ``data/chunks.json`` for inspection.
"""

import json
from pathlib import Path

# Support both `python src/ingestion/pipeline.py` (script dir on sys.path) and
# `from ingestion.pipeline import build_corpus` (package import).
try:
    from extract import check_text_layer, extract_pages
    from chunk import chunk_pages
except ImportError:  # pragma: no cover - import shim for package-style use
    from ingestion.extract import check_text_layer, extract_pages
    from ingestion.chunk import chunk_pages

# Repo root is three levels up from this file: src/ingestion/pipeline.py
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

PDF_FILES = [
    "nakuru_audit_report.pdf",
    "nakuru_birr_q2.pdf",
]


def build_corpus() -> list[dict]:
    """Build the combined chunk corpus from the Nakuru county PDFs.

    Runs the text-layer check on each PDF (raising if any fails), extracts and
    chunks their pages, combines the chunks, writes them to ``data/chunks.json``
    (pretty-printed), and returns the combined list.
    """
    pdf_paths = [DATA_DIR / name for name in PDF_FILES]

    # 1. Guard: every PDF must have an extractable text layer.
    for path in pdf_paths:
        if not path.exists():
            raise FileNotFoundError(f"Expected PDF not found: {path}")
        if not check_text_layer(str(path)):
            raise ValueError(
                f"Text-layer check failed for '{path.name}': the PDF appears "
                f"to be scanned/image-only and would need OCR before extraction."
            )

    # 2 + 3. Extract pages and chunk them, per document, then combine.
    corpus: list[dict] = []
    for path in pdf_paths:
        pages = extract_pages(str(path))
        corpus.extend(chunk_pages(pages))

    # 4. Persist for human inspection.
    out_path = DATA_DIR / "chunks.json"
    out_path.write_text(
        json.dumps(corpus, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return corpus


if __name__ == "__main__":
    corpus = build_corpus()

    # Breakdown of chunk counts by source document.
    counts: dict[str, int] = {}
    for chunk in corpus:
        counts[chunk["source"]] = counts.get(chunk["source"], 0) + 1

    print("=" * 70)
    print(f"Total chunks produced: {len(corpus)}")
    for source in PDF_FILES:
        print(f"  {source}: {counts.get(source, 0)} chunks")
    print(f"Saved to: {DATA_DIR / 'chunks.json'}")
    print("=" * 70)

    # First chunk from each document, for a visual sanity check.
    for source in PDF_FILES:
        first = next((c for c in corpus if c["source"] == source), None)
        print()
        print(f"--- First chunk from {source} ---")
        if first is None:
            print("  (no chunks produced for this document)")
            continue
        print(f"chunk_id: {first['chunk_id']}  (page {first['page']})")
        print(first["text"])
        print("-" * 70)
