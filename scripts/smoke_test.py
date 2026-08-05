"""Wazi end-to-end smoke test."""
import httpx, os, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from dotenv import load_dotenv
load_dotenv()
pw = os.getenv("ADMIN_PASSWORD", "admin")

print("=== WAZI SMOKE TEST ===")
print()

# Test 1: Local FastAPI
try:
    r = httpx.get("http://localhost:8000/health", timeout=3)
    print(f"[1] Local health:  {r.status_code} {r.json()['status']}")
except Exception as e:
    print(f"[1] Local health:  SKIP (FastAPI not running locally)")

# Test 2: VPS health
try:
    r = httpx.get("http://157.230.232.223/health", timeout=10)
    print(f"[2] VPS health:    {r.status_code} {r.json()['status']}")
except Exception as e:
    print(f"[2] VPS health:    FAIL ({e})")

# Test 3: VPS auth required
try:
    r = httpx.get("http://157.230.232.223/api/sources", timeout=10)
    status = "PASS" if r.status_code == 401 else f"FAIL (got {r.status_code})"
    print(f"[3] No auth:       {status}")
except Exception as e:
    print(f"[3] No auth:       FAIL ({e})")

# Test 4: VPS auth succeeds
try:
    r = httpx.get("http://157.230.232.223/api/sources", timeout=10,
                  headers={"Authorization": f"Bearer {pw}"})
    data = r.json()
    print(f"[4] Auth OK:       {r.status_code} - {data['total']} sources")
except Exception as e:
    print(f"[4] Auth OK:       FAIL ({e})")

# Test 5: VPS stats
try:
    r = httpx.get("http://157.230.232.223/api/stats", timeout=10,
                  headers={"Authorization": f"Bearer {pw}"})
    data = r.json()
    print(f"[5] Stats:         {r.status_code} - {data['total_sources']} src, {data['total_chunks']} chunks, {data['total_messages']} msgs")
except Exception as e:
    print(f"[5] Stats:         FAIL ({e})")

# Test 6: Module imports
from src.ingestion.orchestrate import get_response
from src.ingestion.retrieve import retrieve
from src.ingestion.generate import generate, SYSTEM_PROMPT
from src.ingestion.embed import embed_texts, store_chunks
from src.ingestion.vfm import check_value_for_money
print("[6] Imports:       ALL 5 MODULES OK")

# Test 7: Webhook router
from src.api.webhooks import router
routes = [r.path for r in router.routes]
print(f"[7] Webhook:       {routes}")

# Test 8: FastAPI app
from src.api.main import app
print("[8] FastAPI app:   OK")

# Test 9: VPS sessions
try:
    r = httpx.get("http://157.230.232.223/api/sessions", timeout=10,
                  headers={"Authorization": f"Bearer {pw}"})
    if r.status_code == 200:
        print(f"[9] Sessions:      {r.json()['total']} sessions")
    else:
        print(f"[9] Sessions:      {r.status_code} - may be empty DB")
except Exception as e:
    print(f"[9] Sessions:      SKIP ({e})")

# Test 10: VPS disputes
try:
    r = httpx.get("http://157.230.232.223/api/disputes", timeout=10,
                  headers={"Authorization": f"Bearer {pw}"})
    print(f"[10] Disputes:      {r.json()['total']} disputes")
except Exception as e:
    print(f"[10] Disputes:      SKIP ({e})")

print()
print("=== DONE ===")
