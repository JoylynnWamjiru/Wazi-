# Wazi API Reference

> Version 0.1.0 · Base URL (VPS): `http://157.230.232.223` · Local: `http://localhost:8000`

Interactive docs are served live by the app:
- **Swagger UI** — `/docs`
- **ReDoc** — `/redoc`
- **OpenAPI schema** — `/openapi.json`

This file is the at-a-glance reference; `/docs` is the source of truth and lets
you try requests in the browser.

## Authentication

Two kinds of endpoint:

| Kind | Endpoints | Auth |
|------|-----------|------|
| **Public webhook** | `/whatsapp/incoming` | None — Africa's Talking is the caller; the raw wa_id is HMAC-hashed on receipt |
| **Public health** | `/health` | None |
| **Admin API** | everything under `/api/*` | `Authorization: Bearer <ADMIN_PASSWORD>` |

Admin auth failures: **missing** token → `403`, **wrong** token → `401`.

```bash
curl -H "Authorization: Bearer $ADMIN_PASSWORD" http://localhost:8000/api/stats
```

---

## Public endpoints

### `GET /health`
Liveness check. → `200 {"status": "healthy", "service": "wazi-api"}`

### `POST /whatsapp/incoming`
Webhook for incoming WhatsApp messages (form-encoded, from Africa's Talking).
Returns `200` immediately; the answer is delivered asynchronously as a second
WhatsApp message.

| Field | Description |
|-------|-------------|
| `from` | Sender wa_id (hashed on receipt, never stored) |
| `text` | Message body — a question, or the report keyword `SI SAHIHI` |

Behaviour:
- **Question** → RAG pipeline retrieves from pgvector, DeepSeek generates a
  grounded answer, reply carries a `📄 Chanzo:` citation.
- **`SI SAHIHI` / `SIO SAHIHI` / `SI KWELI` / `RIPOTI` / `REPORT`** → files a
  dispute against the citizen's last answer, guarded by the anti-bot checks
  (dedup, 30 s velocity, 3-distinct-reporter diversity).

```bash
curl -X POST http://localhost:8000/whatsapp/incoming \
  -d "from=+254700000001" \
  -d "text=Serikali ya Kaunti ya Nakuru inatarajia kupokea kiasi gani kutoka kwa Serikali ya Kitaifa?"
```

---

## Admin API — Sources (`/api/sources`)

Registry of official documents in the corpus.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/sources` | List sources. Filters: `county`, `government_arm`, `report_type`, `ingestion_status`, `fiscal_year`. → `{sources: [...], total}` |
| `GET` | `/api/sources/{id}` | One source (incl. `chunk_count`). `404` if missing |
| `POST` | `/api/sources` | Register a source → `201` |
| `PATCH` | `/api/sources/{id}` | Update fields. Changing `url`/`report_type`/`government_arm` clears chunks + resets ingestion to `pending` |
| `DELETE` | `/api/sources/{id}` | Delete source + its chunks. `409` if ingestion in progress |
| `POST` | `/api/sources/{id}/ingest` | Trigger manual ingestion → `202` |

**Create body:**
```json
{
  "url": "https://www.oagkenya.go.ke/2023-2024-county-government-audit-reports/",
  "title": "Auditor-General — Nakuru County Executive, FY 2023/24",
  "publisher": "OAG",
  "government_arm": "executive",
  "county": "nakuru",
  "report_type": "audit_report",
  "fiscal_year": "2023/24"
}
```

Enums — `government_arm`: `executive` · `assembly` · `consolidated` · `revenue`.
`report_type`: `audit_report` · `birr` · `exchequer` · `cbrop` · `programme_budget`.
`ingestion_status`: `pending` · `in_progress` · `completed` · `failed`.

---

## Admin API — Disputes (`/api/disputes`)

Moderation queue for citizen reports.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/disputes` | List, newest first. Filters: `dispute_status`, `limit`, `offset`. Each item has a `report_count` (distinct reporters) |
| `GET` | `/api/disputes/{id}` | Full context: disputed answer, the user's question (text only), report count |
| `PATCH` | `/api/disputes/{id}` | Advance status; attach a correction or escalation |

**Status lifecycle:** `pending_review → under_review → {resolved_valid | resolved_invalid | escalated}`; `escalated → resolved_*`. An invalid transition returns `422`.

**Update body:**
```json
{
  "status": "resolved_valid",
  "resolution_note": "Answer cited the wrong page; corrected.",
  "correction_message": "Samahani, jibu sahihi ni ...",
  "escalation_recipient": "EACC"
}
```
`correction_message` is only valid with a `resolved_*` status.

---

## Admin API — Stats & Sessions

### `GET /api/stats`
Aggregate counts for the dashboard: `total_sources`, `sources_by_status`,
`total_chunks`, `total_messages`, `total_disputes`, `disputes_by_status`,
`unique_citizens`, `queries_today`, `queries_this_week`, and source date range.
Every enum bucket is always present (zero-filled).

### `GET /api/sessions`
Conversation sessions, most-recently-active first. Params: `limit`, `offset`,
`is_active`. Each row carries `message_count`, `first_message_at`,
`last_message_at`.

### `GET /api/messages`
Messages, oldest first. Params: `limit`, `offset`, `session_id` (filter; `404`
if the session doesn't exist). Fields: `role`, `text`, `citation`, `created_at`.

---

## Notes

- All list endpoints paginate with `limit` / `offset` and return a `total`.
- Timestamps are ISO-8601 UTC.
- No endpoint returns a phone number or any PII — identities exist only as
  irreversible hashes. See [DATA_RETENTION.md](DATA_RETENTION.md) for how long
  each kind of record is kept.
