# Wazi — Full System Startup Guide

> Last updated: 2026-08-05

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│ Your Local Machine (Windows)                                  │
│                                                                │
│  Docker Desktop → PostgreSQL 16 + pgvector (port 5432)        │
│  Terminal 1 → FastAPI (port 8000)                              │
│  Terminal 2 → Admin Dashboard (port 8502)                      │
│  Terminal 3 → Citizen Chat (port 8501) [dev/demo only]        │
└──────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────┐
│ VPS (157.230.232.223) — Ubuntu 24.04, 1GB RAM                │
│                                                                │
│  PostgreSQL 16 + pgvector (port 5432, localhost only)         │
│  FastAPI via systemd (port 8000 → Nginx port 80)              │
│  systemctl {start,stop,status,restart} wazi                    │
└──────────────────────────────────────────────────────────────┘
```

---

## Local Development Startup

### Step 1: Start PostgreSQL

```powershell
docker compose up -d
docker compose ps   # verify: wazi-postgres is healthy
```

### Step 2: Verify database has tables + seed data

```powershell
.\venv\Scripts\python.exe -c "from src.shared.database import init_db,get_session; init_db(); from src.shared.models import Source; s=get_session().__enter__(); print(s.query(Source).count()); s.close()"
# Expected: 9 (or more if you've added sources via admin dashboard)
```

### Step 3: Start FastAPI backend

```powershell
.\venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --port 8000
```

Verify:
```powershell
curl http://localhost:8000/health
# Expected: {"status":"healthy","service":"wazi-api"}
```

### Step 4: Start Admin Dashboard (separate terminal)

```powershell
.\venv\Scripts\python.exe -m streamlit run src/admin/dashboard.py --server.port 8502
```

Open `http://localhost:8502` → login with `ADMIN_PASSWORD` from `.env`.

### Step 5: Start Citizen Chat (separate terminal, dev/demo only)

```powershell
.\venv\Scripts\python.exe -m streamlit run src/app/streamlit_app.py --server.port 8501
```

Open `http://localhost:8501` → ask a Swahili question.

---

## VPS Deployment

### Check status

```powershell
ssh root@157.230.232.223 "systemctl status wazi --no-pager"
```

### Restart after code update

```powershell
# On your machine:
git push origin main  # after PR merge

# On VPS:
ssh root@157.230.232.223
cd /opt/wazi && git pull origin main
systemctl restart wazi
curl http://localhost:8000/health
```

### View logs

```powershell
ssh root@157.230.232.223 "journalctl -u wazi -n 50 --no-pager"
```

### Database access on VPS

```bash
ssh root@157.230.232.223
sudo -u postgres psql -d wazi_db
# Then: SELECT count(*) FROM sources; SELECT count(*) FROM chunks; etc.
```

---

## Smoke Tests

### Test 1: Health check (local)
```powershell
curl http://localhost:8000/health
```

### Test 2: Health check (VPS)
```powershell
curl http://157.230.232.223/health
```

### Test 3: Admin auth required
```powershell
curl http://localhost:8000/api/sources
# Expected: 401 Unauthorized
```

### Test 4: Admin auth succeeds
```powershell
curl -H "Authorization: Bearer admin" http://localhost:8000/api/sources
# Expected: {"sources": [...], "total": 9}
```

### Test 5: WhatsApp webhook (dev mode)
```powershell
c:/Users/USER/Desktop/Wazi-/venv/Scripts/python.exe -c "
import httpx
r = httpx.post('http://localhost:8000/whatsapp/incoming', data={
    'from': '+254700000001',
    'text': 'Kaunti ya Nakuru inapokea pesa ngapi kutoka kwa Serikali ya Kitaifa?'
})
print(f'Webhook: {r.status_code}')
"
# Expected: 200 — check Sessions tab in admin dashboard for the new message
```

### Test 6: Stats endpoint
```powershell
curl -H "Authorization: Bearer admin" http://localhost:8000/api/stats
# Expected: {"total_sources": 9, "total_chunks": 0, "total_messages": ..., ...}
```

### Test 7: Full CRUD on sources
```powershell
c:/Users/USER/Desktop/Wazi-/venv/Scripts/python.exe scripts/test_admin_api.py
# Expected: ALL 10 TESTS PASSED
```

### Test 8: Citizen chat app answers (local only)
Open `http://localhost:8501`, ask:
- "Kaunti ya Nakuru inapokea pesa ngapi kutoka kwa Serikali ya Kitaifa?"
- Expected: Kshs 14.13 bilioni from `nakuru_birr_q1.pdf, page 2`

- "What did the Auditor-General find about pending bills?"
- Expected: Kshs 1.44 billion figure from the corpus

- "Mradi wa Keringet uligharimu pesa ngapi?"
- Expected: Kshs 16,999,852 from `nakuru_audit_report.pdf, page 15`

- "Je, unaweza kuniambia kuhusu mazingira ya Mars?"
- Expected: "sina taarifa za kutosha" (out-of-corpus question)

---

## Current Known Issues

| Issue | Impact | Resolution |
|-------|--------|------------|
| pgvector has 0 chunks after refactor | Pipeline returns fallback | Need to run `build_corpus()` or manual ingest via scraper |
| Streamlit citizen chat uses old JSON pipeline | Still works — reads from chunks.json | Will migrate to API-based retrieval post-MVP |
| FAISS not loaded in FastAPI context | Webhook always returns fallback | After pgvector has chunks, wire `orchestrate.get_response` into webhook |
| Admin dashboard pointed at localhost:8000 | Only works when FastAPI is running locally | Set `WAZI_API_URL=http://157.230.232.223` for VPS |

---

## Full Startup Checklist (Demo Day)

- [ ] Docker Desktop running → `docker compose up -d`
- [ ] PostgreSQL healthy → `docker compose ps`
- [ ] Database seeded → 9 sources in admin dashboard Sources tab
- [ ] FastAPI running on :8000 → `curl localhost:8000/health` returns 200
- [ ] Admin dashboard on :8502 → login successful, all tabs render
- [ ] Citizen chat on :8501 → asks a question, gets grounded answer
- [ ] Webhook test → `curl POST /whatsapp/incoming` returns 200
- [ ] VPS responding → `curl 157.230.232.223/health` returns 200
- [ ] Rotation: DeepSeek API key rotated, old key deleted
