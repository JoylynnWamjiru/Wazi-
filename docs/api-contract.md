# Wazi — API Contract

> Version: 0.2.0
> Base URL: `http://localhost:8000/api`
> Auth: Bearer token (set via `ADMIN_PASSWORD` env var)
>
> Changelog:
> - 0.2.0: Added DELETE/PATCH sources, user question + chunks in dispute
>   detail, correction_message on resolve, session listing, EACC escalation
>   report generation.
> - 0.1.0: Initial contract.
>
> This contract defines every endpoint the Streamlit admin dashboard consumes
> from the FastAPI backend.  Both team members build against this spec.

---

## 1. Authentication

All `/api/*` endpoints (except `/health`) require a Bearer token.

```
Authorization: Bearer <ADMIN_PASSWORD>
```

The token is the value of the `ADMIN_PASSWORD` environment variable.  If the
header is missing or the token does not match, the server returns `401`.

**Error response (401):**
```json
{"detail": "Invalid or missing authentication token"}
```

---

## 2. Disputes

### 2.1 List Disputes

```
GET /api/disputes?status=pending_review&limit=50&offset=0
```

**Query parameters:**

| Param    | Type   | Default            | Description                                      |
|----------|--------|--------------------|--------------------------------------------------|
| `status` | string | (all)              | Filter by `DisputeStatus` enum value             |
| `limit`  | int    | 50                 | Max results per page                             |
| `offset` | int    | 0                  | Pagination offset                                |

**Response (200):**
```json
{
  "disputes": [
    {
      "id": 1,
      "message_id": 42,
      "status": "pending_review",
      "reason": "The figure quoted for Keringet project is different from what I saw on the ground",
      "reported_by_user_id": 7,
      "created_at": "2026-07-20T14:30:00Z",
      "report_count": 3
    }
  ],
  "total": 12,
  "limit": 50,
  "offset": 0
}
```

**Notes:**
- `report_count` is the number of distinct users who have reported the same
  `message_id`.  The admin UI uses this to surface highly-disputed answers.
- `reported_by_user_id` is the hashed ID — it is never a phone number.
- Disputes are ordered by `created_at` descending (newest first).

### 2.2 Get Single Dispute

```
GET /api/disputes/{dispute_id}
```

**Response (200):**
```json
{
  "id": 1,
  "message_id": 42,
  "status": "pending_review",
  "reason": "The figure quoted for Keringet project is different...",
  "reported_by_user_id": 7,
  "reviewed_by": null,
  "reviewed_at": null,
  "resolution_note": null,
  "correction_message": null,
  "escalation_report": null,
  "created_at": "2026-07-20T14:30:00Z",
  "report_count": 3,
  "message_preview": {
    "role": "assistant",
    "text": "Mradi wa Keringet uligharimu Kshs 16,999,852...",
    "citation": "nakuru_audit_report.pdf, page 15"
  },
  "user_question": {
    "text": "Je, mradi wa Keringet ulikuwa na thamani ya pesa iliyotumika?"
  },
  "retrieved_chunks": [
    {
      "chunk_id": 28,
      "source_title": "Auditor-General's Report — Nakuru County Executive, FY 2023/24",
      "government_arm": "executive",
      "page_number": 15,
      "chunk_text": "...two dormitories, kitchen, dining area and a shed at Keringet Sports Center at a contract sum of Kshs 16,999,852..."
    }
  ]
}
```

**Notes:**
- `user_question` contains the citizen's original query text.  This is
  necessary for the moderator to determine whether the AI answered the
  right question.  The citizen's identity is NOT exposed — only the text.
- `retrieved_chunks` is the exact set of chunks the RAG pipeline retrieved
  and passed to the LLM as context.  This allows the moderator to
  determine whether the AI hallucinated (chunk says X, answer says Y) or
  whether the source document itself was the problem (chunk says X, AI
  faithfully repeated X, but X is factually wrong on the ground).
- `correction_message` is populated after a moderator resolves a dispute
  with a correction (see §2.3).
- `escalation_report` is populated when the dispute is escalated (see §2.3).

### 2.3 Update Dispute Status

```
PATCH /api/disputes/{dispute_id}
```

**Request body (resolve with correction):**
```json
{
  "status": "resolved_valid",
  "resolution_note": "Confirmed: the contract sum in the source is Kshs 16,999,852, but the AI rounded it to Kshs 17M. The answer was misleading.",
  "correction_message": "Marekebisho: Hapo awali tulikwambia mradi wa Keringet uligharimu Kshs milioni 17. Takwimu sahihi kutoka kwa ripoti ya Mkaguzi Mkuu ni Kshs 16,999,852. Tunasikitika kwa hitilafu hiyo."
}
```

**Request body (escalate to EACC):**
```json
{
  "status": "escalated",
  "resolution_note": "Multiple citizens report this project does not exist on the ground despite the audit report confirming payment. Referred to EACC for investigation.",
  "escalation_recipient": "corruption-reporting@cob.go.ke"
}
```

**Request body (simple resolve, no correction):**
```json
{
  "status": "resolved_invalid",
  "resolution_note": "The answer matches the source document. No issue found."
}
```

| Field                  | Type   | Required | Description |
|------------------------|--------|----------|-------------|
| `status`               | string | Yes      | New `DisputeStatus` value |
| `resolution_note`      | string | No       | Moderator's explanation |
| `correction_message`   | string | No       | If provided, the backend sends this as a WhatsApp message to the citizen who asked the original question. Only valid when `status` is `resolved_valid` or `resolved_invalid`. |
| `escalation_recipient` | string | No       | Email address to include in the escalation report. Only valid when `status` is `escalated`. |

**Valid status transitions:**

```
pending_review  →  under_review
under_review    →  resolved_valid | resolved_invalid | escalated
resolved_*      →  (terminal — no further transitions)
escalated       →  resolved_valid | resolved_invalid
```

**Correction message behavior:**

When `correction_message` is provided, the backend:
1. Looks up the session that produced the disputed message.
2. Retrieves the citizen's raw `wa_id` from that session (transient — never
   stored or logged).
3. Calls the Africa's Talking send-message API with the correction text.
4. Stores `correction_message` on the dispute record.
5. The citizen receives: *"Marekebisho: ..."* (prefixed by the backend).

If the AT API call fails, the status update still succeeds but the response
includes `"correction_sent": false` and `"correction_error": "..."`.

**Escalation behavior:**

When `status` is `escalated`, the backend:
1. Generates an anonymized escalation report (JSON) containing:
   - The disputed answer text and citation.
   - The user's question (text only, no identity).
   - The retrieved chunks the AI was given.
   - The citizen's dispute reason.
   - The moderator's `resolution_note`.
   - The `escalation_recipient` email address.
2. Stores the report as `escalation_report` on the dispute record.
3. Returns the report in the response.  The moderator is responsible for
   manually sending it to the recipient (EACC / CoB / OAG).

Full automated email sending is deferred to post-MVP pending legal review
of the template and verified recipient addresses.

**Response (200) — resolved with correction:**
```json
{
  "id": 1,
  "status": "resolved_valid",
  "resolution_note": "Confirmed: the contract sum in the source is...",
  "correction_message": "Marekebisho: Hapo awali tulikwambia...",
  "correction_sent": true,
  "reviewed_by": "moderator",
  "reviewed_at": "2026-07-22T10:15:00Z"
}
```

**Response (200) — escalated:**
```json
{
  "id": 1,
  "status": "escalated",
  "resolution_note": "Multiple citizens report this project does not exist...",
  "escalation_report": {
    "dispute_id": 1,
    "generated_at": "2026-07-22T10:15:00Z",
    "recipient": "corruption-reporting@cob.go.ke",
    "content": {
      "disputed_answer": "Mradi wa Keringet uligharimu Kshs 16,999,852...",
      "citation": "nakuru_audit_report.pdf, page 15",
      "user_question": "Je, mradi wa Keringet ulikuwa na thamani...",
      "retrieved_chunks": ["...two dormitories, kitchen... contract sum of Kshs 16,999,852..."],
      "citizen_report": "The figure quoted for Keringet project is different...",
      "moderator_note": "Multiple citizens report this project does not exist..."
    }
  },
  "reviewed_by": "moderator",
  "reviewed_at": "2026-07-22T10:15:00Z"
}
```

**Error (422):**
```json
{"detail": "Invalid status transition: pending_review -> resolved_valid. Must pass through under_review first."}
```

**Error (422) — correction on wrong status:**
```json
{"detail": "correction_message is only valid when status is resolved_valid or resolved_invalid, not escalated."}
```

---

## 3. Sources

### 3.1 List Sources

```
GET /api/sources?county=nakuru&government_arm=executive&ingestion_status=completed
```

**Query parameters (all optional):**

| Param              | Type   | Description                              |
|--------------------|--------|------------------------------------------|
| `county`           | string | Filter by county slug                    |
| `government_arm`   | string | Filter by `GovernmentArm` enum value     |
| `report_type`      | string | Filter by `ReportType` enum value        |
| `ingestion_status` | string | Filter by `IngestionStatus` enum value   |
| `fiscal_year`      | string | Filter by fiscal year (e.g. "2025/26")   |

**Response (200):**
```json
{
  "sources": [
    {
      "id": 1,
      "url": "https://www.oagkenya.go.ke/2024-2025-county-government-audit-reports/",
      "title": "Auditor-General's Report — Nakuru County Executive, FY 2024/25",
      "publisher": "OAG",
      "government_arm": "executive",
      "county": "nakuru",
      "report_type": "audit_report",
      "fiscal_year": "2024/25",
      "published_at": null,
      "last_scraped_at": null,
      "ingestion_status": "pending",
      "ingestion_error": null,
      "chunk_count": 0,
      "created_at": "2026-07-22T09:00:00Z"
    }
  ],
  "total": 7
}
```

### 3.2 Register a New Source

```
POST /api/sources
```

**Request body:**
```json
{
  "url": "https://www.oagkenya.go.ke/2024-2025-county-government-audit-reports/",
  "title": "Auditor-General's Report — Nakuru County Executive, FY 2024/25",
  "publisher": "OAG",
  "government_arm": "executive",
  "county": "nakuru",
  "report_type": "audit_report",
  "fiscal_year": "2024/25"
}
```

All fields are required except `fiscal_year`.

**Response (201):**
```json
{
  "id": 8,
  "url": "https://www.oagkenya.go.ke/2024-2025-county-government-audit-reports/",
  "title": "Auditor-General's Report — Nakuru County Executive, FY 2024/25",
  "publisher": "OAG",
  "government_arm": "executive",
  "county": "nakuru",
  "report_type": "audit_report",
  "fiscal_year": "2024/25",
  "ingestion_status": "pending",
  "created_at": "2026-07-22T11:00:00Z"
}
```

### 3.3 Trigger Manual Ingestion

```
POST /api/sources/{source_id}/ingest
```

Triggers the scraper to download, extract, chunk, and embed this source
immediately (bypassing the scheduler).  Returns immediately with the
updated status; ingestion runs in the background.

**Response (202):**
```json
{
  "source_id": 1,
  "ingestion_status": "in_progress",
  "message": "Ingestion started. Check status via GET /api/sources/{source_id}."
}
```

**Error (409) — ingestion already in progress:**
```json
{"detail": "Source 1 is already being ingested (status: in_progress)"}
```

### 3.4 Get Single Source

```
GET /api/sources/{source_id}
```

Same shape as a single item from the list endpoint (see §3.1), but with
`chunk_count` and `ingestion_error` populated with the latest data.

### 3.5 Update Source Metadata

```
PATCH /api/sources/{source_id}
```

Update metadata fields without re-triggering ingestion.  All fields are
optional — only the fields present in the request body are updated.

**Request body (example — fix a typo in the title):**
```json
{
  "title": "Auditor-General's Report — Nakuru County Executive, FY 2024/25",
  "fiscal_year": "2024/25"
}
```

| Field            | Type   | Required | Description |
|------------------|--------|----------|-------------|
| `url`            | string | No       | Updated listing-page URL |
| `title`          | string | No       | Corrected title |
| `publisher`      | string | No       | Updated publisher |
| `government_arm` | string | No       | `GovernmentArm` enum value |
| `county`         | string | No       | County slug |
| `report_type`    | string | No       | `ReportType` enum value |
| `fiscal_year`    | string | No       | Fiscal year (e.g. "2025/26") |

**Response (200):** Same shape as §3.1 list item with updated fields.

**Note:** Changing `government_arm` or `county` does NOT retroactively
update existing chunks.  If the metadata change means chunks are
mislabeled, delete the source (§3.6) and re-register it.

### 3.6 Delete a Source

```
DELETE /api/sources/{source_id}
```

Permanently removes the source record **and cascade-deletes all its
vector chunks** from pgvector.  This is the cleanup path for a wrongly
uploaded PDF or a duplicate entry.

**Response (200):**
```json
{
  "deleted": true,
  "source_id": 1,
  "chunks_deleted": 48
}
```

**Error (409) — ingestion in progress:**
```json
{"detail": "Cannot delete source 1 while ingestion is in progress. Wait for it to complete or fail."}
```

---

## 4. Corpus Health

### 4.1 Get Corpus Statistics

```
GET /api/stats
```

**Response (200):**
```json
{
  "total_sources": 7,
  "sources_by_status": {
    "pending": 5,
    "in_progress": 0,
    "completed": 2,
    "failed": 0
  },
  "total_chunks": 342,
  "total_messages": 156,
  "total_disputes": 8,
  "disputes_by_status": {
    "pending_review": 5,
    "under_review": 1,
    "resolved_valid": 1,
    "resolved_invalid": 1,
    "escalated": 0
  },
  "last_ingestion_at": "2026-07-20T08:00:00Z",
  "oldest_source_date": "2024-10-15",
  "newest_source_date": "2026-05-20",
  "unique_citizens": 23,
  "queries_today": 12,
  "queries_this_week": 89
}
```

**Notes:**
- `unique_citizens` is the count of distinct `hashed_wa_id` values — not a
  count of identifiable people.
- `oldest_source_date` / `newest_source_date` come from `published_at` on the
  Source table.  If `published_at` is null for all sources, these return
  `null`.

---

## 5. Linguist Validation

### 5.1 Fetch Answers for Review

```
GET /api/validation/answers?limit=10&reviewed=false
```

Returns a random sample of answers that need linguist review.

**Query parameters:**

| Param      | Type | Default | Description                              |
|------------|------|---------|------------------------------------------|
| `limit`    | int  | 10      | Number of answers to return              |
| `reviewed` | bool | false   | `false` = unreviewed only; `true` = all  |

**Response (200):**
```json
{
  "answers": [
    {
      "message_id": 42,
      "query_text": "Kaunti ya Nakuru inapokea pesa ngapi kutoka kwa Serikali ya Kitaifa?",
      "answer_text": "Kaunti ya Nakuru inatarajiwa kupokea Kshs 4.2 bilioni...",
      "citation": "nakuru_birr_q2.pdf, page 3",
      "chunks_used": [
        {
          "chunk_id": 15,
          "source_title": "County Governments BIRR — First Half FY 2025/26",
          "government_arm": "consolidated",
          "chunk_text": "Nakuru County expects to receive Kshs 4.2 billion..."
        }
      ],
      "created_at": "2026-07-20T14:30:00Z"
    }
  ],
  "total_unreviewed": 47
}
```

### 5.2 Submit Linguist Rating

```
POST /api/validation/answers/{message_id}/rate
```

**Request body:**
```json
{
  "tone_score": 4,
  "factually_grounded": true,
  "register_correct": true,
  "expected_register": "formal_swahili",
  "actual_register": "formal_swahili",
  "notes": "Good translation, but 'bilioni' should be written out for low-literacy readers."
}
```

| Field               | Type    | Required | Description                                      |
|---------------------|---------|----------|--------------------------------------------------|
| `tone_score`        | int     | Yes      | 1–5 rating of tone appropriateness               |
| `factually_grounded`| bool    | Yes      | Whether the answer matches the cited source       |
| `register_correct`  | bool    | Yes      | Whether the register matches the query            |
| `expected_register` | string  | Yes      | Detected register: `formal_swahili`, `sheng`, `english` |
| `actual_register`   | string  | Yes      | Register the answer was delivered in              |
| `notes`             | string  | No       | Free-text feedback from the linguist              |

**Response (200):**
```json
{
  "message_id": 42,
  "rated": true
}
```

---

## 6. Sessions

### 6.1 List Sessions

```
GET /api/sessions?limit=20&offset=0&is_active=true
```

**Query parameters:**

| Param       | Type | Default | Description |
|-------------|------|---------|-------------|
| `limit`     | int  | 20      | Max results |
| `offset`    | int  | 0       | Pagination offset |
| `is_active` | bool | (none)  | Filter: `true` = active only, `false` = closed only, omit = all |

**Response (200):**
```json
{
  "sessions": [
    {
      "id": 5,
      "user_id": 12,
      "is_active": true,
      "message_count": 8,
      "first_message_at": "2026-07-21T09:00:00Z",
      "last_message_at": "2026-07-21T09:20:00Z",
      "created_at": "2026-07-21T09:00:00Z"
    }
  ],
  "total": 34,
  "limit": 20,
  "offset": 0
}
```

**Notes:**
- `user_id` is the hashed wa_id — never a phone number.
- Sessions are ordered by `last_message_at` descending (most active first).
- The admin dashboard uses this to build a conversation browser: click a
  session → calls `GET /api/messages?session_id=5` to view the transcript.

---

## 7. Messages (Chat History)

### 7.1 List Recent Messages

```
GET /api/messages?limit=20&offset=0&session_id=5
```

Used by the admin dashboard to show recent conversations for context.

**Query parameters:**

| Param        | Type | Default | Description                    |
|--------------|------|---------|--------------------------------|
| `limit`      | int  | 20      | Max results                    |
| `offset`     | int  | 0       | Pagination offset              |
| `session_id` | int  | (none)  | Filter to a specific session   |

**Response (200):**
```json
{
  "messages": [
    {
      "id": 84,
      "session_id": 5,
      "role": "user",
      "text": "What did the Auditor-General find about pending bills?",
      "citation": null,
      "created_at": "2026-07-21T09:15:00Z"
    },
    {
      "id": 85,
      "session_id": 5,
      "role": "assistant",
      "text": "Mkaguzi Mkuu alibaini kuwa bili...",
      "citation": "nakuru_audit_report.pdf, page 22",
      "created_at": "2026-07-21T09:15:05Z"
    }
  ],
  "total": 156,
  "limit": 20,
  "offset": 0
}
```

**Security note:** Messages are linked to sessions, not directly to users.
The `user_id` is not exposed via this endpoint.  To find "who asked this
question" requires a separate query joining through the sessions table,
which is intentionally not exposed via the API.

---

## 8. Health

### 8.1 Health Check

```
GET /health
```

**No authentication required.**

**Response (200):**
```json
{
  "status": "healthy",
  "service": "wazi-api",
  "database": "connected",
  "version": "0.1.0"
}
```

---

## 9. Error Responses

All errors follow this shape:

```json
{
  "detail": "Human-readable description of what went wrong"
}
```

| Status | Meaning                                  |
|--------|------------------------------------------|
| 400    | Bad request (invalid query parameters)   |
| 401    | Missing or invalid auth token            |
| 404    | Resource not found                       |
| 409    | Conflict (e.g., ingestion already running)|
| 422    | Validation error (invalid status transition, missing required field) |
| 500    | Internal server error                    |

---

## 10. Data Types Reference

### Enums

| Enum               | Values                                                                    |
|--------------------|---------------------------------------------------------------------------|
| `GovernmentArm`    | `executive`, `assembly`, `consolidated`, `revenue`                        |
| `ReportType`       | `audit_report`, `birr`, `exchequer`                                       |
| `IngestionStatus`  | `pending`, `in_progress`, `completed`, `failed`                           |
| `DisputeStatus`    | `pending_review`, `under_review`, `resolved_valid`, `resolved_invalid`, `escalated` |
| `Register`         | `formal_swahili`, `sheng`, `english`                                      |

### Timestamps

All timestamps are ISO 8601 in UTC (`2026-07-22T10:15:00Z`).

### Pagination

All list endpoints use `limit` (default 50, max 100) and `offset` (default 0)
and return `total` for the unfiltered count.

---

> **This contract is a living document.**  If an endpoint needs a new field
> or a response shape changes, update this file BEFORE writing code.  Both
> team members should review changes before implementation.
