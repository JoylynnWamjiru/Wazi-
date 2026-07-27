"""Quick smoke test for admin API endpoints."""
import httpx
import os
from dotenv import load_dotenv

load_dotenv()
ADMIN_PW = os.getenv("ADMIN_PASSWORD", "admin")
BASE = "http://localhost:8000"
HEADERS = {"Authorization": f"Bearer {ADMIN_PW}"}

# Test 1: Unauthenticated
r = httpx.get(f"{BASE}/api/sources")
assert r.status_code == 401, f"Expected 401, got {r.status_code}"
print("PASS 1: No auth -> 401")

# Test 2: Sources list
r = httpx.get(f"{BASE}/api/sources", headers=HEADERS)
assert r.status_code == 200
print(f"PASS 2: Sources list -> {r.json()['total']} sources")

# Test 3: Stats
r = httpx.get(f"{BASE}/api/stats", headers=HEADERS)
assert r.status_code == 200
d = r.json()
print(f"PASS 3: Stats -> {d['total_sources']} sources, {d['total_messages']} msgs, {d['total_chunks']} chunks")

# Test 4: Sessions
r = httpx.get(f"{BASE}/api/sessions", headers=HEADERS)
assert r.status_code == 200
print(f"PASS 4: Sessions -> {r.json()['total']} sessions")

# Test 5: Messages
r = httpx.get(f"{BASE}/api/messages", headers=HEADERS)
assert r.status_code == 200
print(f"PASS 5: Messages -> {r.json()['total']} messages")

# Test 6: Disputes
r = httpx.get(f"{BASE}/api/disputes", headers=HEADERS)
assert r.status_code == 200
print(f"PASS 6: Disputes -> {r.json()['total']} disputes")

# Test 7: Create source
r = httpx.post(f"{BASE}/api/sources", json={
    "url": "https://example.com/test.pdf",
    "title": "Test Source - Delete Me",
    "publisher": "OAG",
    "government_arm": "executive",
    "county": "nakuru",
    "report_type": "audit_report",
    "fiscal_year": "2024/25",
}, headers=HEADERS)
assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
src_id = r.json()["id"]
print(f"PASS 7: Create source -> id={src_id}")

# Test 8: Update source
r = httpx.patch(f"{BASE}/api/sources/{src_id}", json={
    "title": "Updated Title",
}, headers=HEADERS)
assert r.status_code == 200
assert r.json()["title"] == "Updated Title"
print(f"PASS 8: Update source -> title changed")

# Test 9: Delete source
r = httpx.delete(f"{BASE}/api/sources/{src_id}", headers=HEADERS)
assert r.status_code == 200
print(f"PASS 9: Delete source -> {r.json()}")

# Test 10: Health (no auth)
r = httpx.get(f"{BASE}/health")
assert r.status_code == 200
print(f"PASS 10: Health -> {r.json()['status']}")

print(f"\nALL 10 TESTS PASSED")
