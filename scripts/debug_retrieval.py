"""Diagnostic: run pgvector retrieval for sample queries and print top-k."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.retrieve import retrieve

QUERIES = [
    "What happened at Njoro Level 4 Hospital?",
    "How much did the construction of the outpatient block at Njoro Level 4 Hospital cost?",
    "Njoro Level 4 Hospital stalled construction contract amount",
    "Kaunti ya Nakuru Njoro Level 4 Hospital",
]

for q in QUERIES:
    print(f"\n=== QUERY: {q!r}")
    results = retrieve(q, k=8)
    if not results:
        print("  (no results)")
    for r in results:
        snippet = " ".join(r["chunk_text"].split())[:90]
        print(f"  sim={r['similarity']:.3f} src={r['source_id']} p={r['page_number']} :: {snippet}")
