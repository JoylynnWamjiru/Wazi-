"""Wazi end-to-end smoke test — run against a live instance.

Usage:
    # Local (FastAPI on 8502):
    python scripts/smoke_test.py

    # VPS:
    python scripts/smoke_test.py --base-url http://157.230.232.223

    # Custom port:
    python scripts/smoke_test.py --base-url http://localhost:8502
"""

import argparse
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from dotenv import load_dotenv

load_dotenv()

PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        print(f"  ✅ {label} {detail}")
        PASSED += 1
    else:
        print(f"  ❌ {label} {detail}")
        FAILED += 1


def test_health(base: str) -> None:
    print("\n--- Health ---")
    try:
        r = httpx.get(f"{base}/health", timeout=5)
        check("GET /health", r.status_code == 200 and r.json()["status"] == "healthy",
              f"→ {r.json()}")
    except Exception as e:
        check("GET /health", False, f"→ {e}")


def test_auth(base: str) -> None:
    print("\n--- Auth ---")
    r = httpx.get(f"{base}/api/sources", timeout=5)
    check("No token → 401/403", r.status_code in (401, 403), f"→ {r.status_code}")

    r = httpx.get(f"{base}/api/sources", timeout=5,
                  headers={"Authorization": f"Bearer wrong"})
    check("Wrong token → 401", r.status_code == 401, f"→ {r.status_code}")

    r = httpx.get(f"{base}/api/sources", timeout=5,
                  headers={"Authorization": f"Bearer {PASSWORD}"})
    check("Correct token → 200", r.status_code == 200,
          f"→ {r.json().get('total', '?')} sources")


def test_sources_crud(base: str) -> None:
    print("\n--- Sources CRUD ---")
    h = {"Authorization": f"Bearer {PASSWORD}"}
    body = {
        "url": "https://example.com/smoke-test.pdf",
        "title": "Smoke Test Source",
        "publisher": "OAG",
        "government_arm": "executive",
        "county": "nakuru",
        "report_type": "audit_report",
        "fiscal_year": "2024/25",
    }

    r = httpx.post(f"{base}/api/sources", json=body, headers=h, timeout=5)
    check("POST /api/sources → 201", r.status_code == 201, f"→ id={r.json().get('id', '?')}")
    src_id = r.json().get("id")

    if src_id:
        r = httpx.get(f"{base}/api/sources/{src_id}", headers=h, timeout=5)
        check("GET /api/sources/{id} → 200", r.status_code == 200)

        r = httpx.patch(f"{base}/api/sources/{src_id}", json={"title": "Updated Smoke Test"},
                        headers=h, timeout=5)
        check("PATCH /api/sources/{id} → 200", r.status_code == 200,
              f"→ title={r.json().get('title', '?')}")

        r = httpx.delete(f"{base}/api/sources/{src_id}", headers=h, timeout=5)
        check("DELETE /api/sources/{id} → 200", r.status_code == 200)

        r = httpx.get(f"{base}/api/sources/{src_id}", headers=h, timeout=5)
        check("GET deleted → 404", r.status_code == 404)
    else:
        check("Sources CRUD", False, "→ no ID returned, skipping remaining CRUD tests")


def test_stats(base: str) -> None:
    print("\n--- Stats ---")
    h = {"Authorization": f"Bearer {PASSWORD}"}
    r = httpx.get(f"{base}/api/stats", headers=h, timeout=5)
    if r.status_code == 200:
        d = r.json()
        required = ("total_sources", "total_chunks", "total_messages",
                    "total_disputes", "sources_by_status", "disputes_by_status",
                    "unique_citizens", "queries_today", "queries_this_week")
        check("GET /api/stats → 200 + all keys",
              all(k in d for k in required),
              f"→ {d['total_sources']} src, {d['total_chunks']} chunks")
    else:
        check("GET /api/stats → 200", False, f"→ {r.status_code}")


def test_sessions(base: str) -> None:
    print("\n--- Sessions ---")
    h = {"Authorization": f"Bearer {PASSWORD}"}
    r = httpx.get(f"{base}/api/sessions", headers=h, timeout=5)
    check("GET /api/sessions → 200", r.status_code == 200,
          f"→ {r.json().get('total', '?')} sessions")


def test_disputes(base: str) -> None:
    print("\n--- Disputes ---")
    h = {"Authorization": f"Bearer {PASSWORD}"}
    r = httpx.get(f"{base}/api/disputes", headers=h, timeout=5)
    check("GET /api/disputes → 200", r.status_code == 200,
          f"→ {r.json().get('total', '?')} disputes")


def test_validation(base: str) -> None:
    print("\n--- Validation ---")
    h = {"Authorization": f"Bearer {PASSWORD}"}
    r = httpx.get(f"{base}/api/validation/queue", headers=h, timeout=5)
    check("GET /api/validation/queue → 200", r.status_code == 200,
          f"→ {r.json().get('count', '?')} unrated")
    r = httpx.get(f"{base}/api/validation/stats", headers=h, timeout=5)
    check("GET /api/validation/stats → 200", r.status_code == 200,
          f"→ {r.json().get('total_validations', '?')} ratings")


def test_whatsapp_webhook(base: str) -> None:
    print("\n--- WhatsApp Webhook ---")
    r = httpx.post(f"{base}/whatsapp/incoming",
                   data={"from": "+254700000099", "text": "smoke test question"},
                   timeout=10)
    check("POST /whatsapp/incoming → 200", r.status_code == 200,
          f"→ ACK within {r.elapsed.total_seconds():.1f}s")


def test_dispute_keyword(base: str) -> None:
    print("\n--- Dispute Keyword ---")
    r = httpx.post(f"{base}/whatsapp/incoming",
                   data={"from": "+254700000099", "text": "si sahihi"},
                   timeout=5)
    # Expect 200 — even if no prior answer (returns "Hakuna jibu..." reply).
    check("POST dispute keyword → 200", r.status_code == 200)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wazi end-to-end smoke test.")
    parser.add_argument("--base-url", default="http://localhost:8502",
                        help="Base URL of the running Wazi API (default: http://localhost:8502)")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    print(f"=== WAZI SMOKE TEST ===\nTarget: {base}")

    test_health(base)
    test_auth(base)
    test_sources_crud(base)
    test_stats(base)
    test_sessions(base)
    test_disputes(base)
    test_validation(base)
    test_whatsapp_webhook(base)
    test_dispute_keyword(base)

    print(f"\n{'='*40}")
    print(f"Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    if FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()

# Test 10: VPS disputes
try:
    r = httpx.get("http://157.230.232.223/api/disputes", timeout=10,
                  headers={"Authorization": f"Bearer {pw}"})
    print(f"[10] Disputes:      {r.json()['total']} disputes")
except Exception as e:
    print(f"[10] Disputes:      SKIP ({e})")

print()
print("=== DONE ===")
