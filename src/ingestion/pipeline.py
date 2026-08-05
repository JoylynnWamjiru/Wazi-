"""Backward-compatible entry point — build corpus from local PDFs.

- ``build_corpus()`` : extract -> chunk -> store in pgvector
- ``get_response()`` : re-exported from ``orchestrate.py``

New code should import directly from the refactored modules:
  from src.ingestion.orchestrate import get_response
  from src.ingestion.retrieve import retrieve
  from src.ingestion.generate import generate, SYSTEM_PROMPT
  from src.ingestion.embed import embed_texts, store_chunks
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.extract import check_text_layer, extract_pages
from src.ingestion.chunk import chunk_pages

DATA_DIR = REPO_ROOT / "data"

PDF_FILES = [
    "nakuru_audit_report.pdf",
    "nakuru_birr_q1.pdf",  # Q1 FY2024/25 (cover: October 2024)
]

# Re-export get_response from the refactored orchestrate module.
from src.ingestion.orchestrate import get_response  # noqa: F401, E402


def build_corpus() -> list[dict]:
    """Build the combined chunk corpus from the Nakuru county PDFs.

    Extracts -> chunks -> writes chunks.json for backward compat with the
    Streamlit citizen chat app (which reads from the JSON file, not pgvector).

    pgvector storage is handled by the scraper (``src/ingestion/scraper.py``)
    which maps each PDF to a real source_id from the ``sources`` table.
    ``build_corpus()`` is a local-only convenience that does NOT require
    PostgreSQL.
    """
    pdf_paths = [DATA_DIR / name for name in PDF_FILES]

    for path in pdf_paths:
        if not path.exists():
            raise FileNotFoundError(f"Expected PDF not found: {path}")
        if not check_text_layer(str(path)):
            raise ValueError(
                f"Text-layer check failed for '{path.name}': the PDF appears "
                f"to be scanned/image-only and would need OCR before extraction."
            )

    all_chunks: list[dict] = []
    for path in pdf_paths:
        pages = extract_pages(str(path))
        chunks = chunk_pages(pages)
        all_chunks.extend(chunks)

    # Write chunks.json for Streamlit citizen chat app.
    out_path = DATA_DIR / "chunks.json"
    out_path.write_text(
        json.dumps(all_chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"build_corpus: {len(all_chunks)} chunks written to chunks.json")
    print("pgvector storage: deferred to scraper (needs source_id from sources table)")

    return all_chunks


if __name__ == "__main__":
    corpus = build_corpus()
    print(f"\nCorpus built: {len(corpus)} chunks total.")
